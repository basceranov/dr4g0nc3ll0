# models.py
# OSINT Intelligence Report - Intermediate Data Model (Pydantic 1.x)
# Python 3.11+

from __future__ import annotations
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field, HttpUrl, validator, root_validator, conlist, constr
from datetime import datetime, date
import hashlib
import re
import uuid

# =========================
# Enums & literals
# =========================

SourceType = Literal["UN", "ONG", "Media-Intl", "Media-IT", "Gov", "ThinkTank", "Other"]
ReliabilityGrade = Literal["A", "B", "C", "D", "E"]
SupportLevel = Literal["Supported", "Partial", "Contested", "Unknown"]
ActorKind = Literal["PERSON", "ORG", "STATE", "OTHER"]
RelationshipType = Literal[
    "supports", "opposes", "affiliates", "negotiates", "sanctions",
    "investigates", "trades_with", "other"
]
SentimentEnum = Literal["positive", "neutral", "negative"]
GeoType = Literal["Point", "Polygon", "LineString"]

ID_RX = {
    "report": r"^RPT-[0-9]{8}-[0-9]{4}$",
    "source": r"^SRC-\d{4}$",
    "document": r"^DOC-\d{4}$",
    "finding": r"^CLM-\d{4}$",
    "event": r"^EVT-\d{4}$",
    "actor": r"^ACT-\d{4}$",
    "relationship": r"^REL-\d{4}$",
    "indicator": r"^IND-\d{4}$",
    "geofeature": r"^GEO-\d{4}$",
}

DATE_ISO_RX = r"^\d{4}-\d{2}-\d{2}$"


# =========================
# ID helpers
# =========================

def new_id(prefix: str, seq: int) -> str:
    """Genera un ID breve e monotono: prefix-0001, prefix-0002, ..."""
    return f"{prefix}-{seq:04d}"

def new_report_id(ts: Optional[datetime] = None, seq: int = 1) -> str:
    """ID report: RPT-YYYYMMDD-####"""
    ts = ts or datetime.utcnow()
    return f"RPT-{ts.strftime('%Y%m%d')}-{seq:04d}"

def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


# =========================
# Core models
# =========================

class LLMInfo(BaseModel):
    name: Optional[str] = None
    params: Optional[Dict[str, object]] = None


class ReportMetadata(BaseModel):
    report_id: constr(regex=ID_RX["report"]) = Field(..., example="RPT-20251105-0001")
    title: str
    query: Optional[str] = None
    generated_at: datetime
    analyst: Optional[str] = None
    tool_version: str = "osint-pipeline 2.1"
    llm: Optional[LLMInfo] = None


class TimeWindow(BaseModel):
    from_: date = Field(..., alias="from")
    to: date

    @validator("to")
    def check_order(cls, v, values):
        if "from_" in values and v < values["from_"]:
            raise ValueError("'to' must be >= 'from'")
        return v


class Scope(BaseModel):
    time_window: TimeWindow
    geo_focus: Optional[List[str]] = None
    languages: Optional[List[str]] = None


class Source(BaseModel):
    id: constr(regex=ID_RX["source"])
    type: SourceType
    domain: Optional[str] = None
    author: Optional[str] = None
    title: Optional[str] = None
    published_at: Optional[str] = None  # YYYY-MM-DD o ISO
    accessed_at: Optional[datetime] = None
    url: HttpUrl
    reliability: Optional[ReliabilityGrade] = None
    notes: Optional[str] = None


class Document(BaseModel):
    id: constr(regex=ID_RX["document"])
    source_id: constr(regex=ID_RX["source"])
    url: HttpUrl
    title: Optional[str] = None
    published_at: Optional[str] = None
    text: Optional[str] = None
    hash: Optional[str] = None
    lang: Optional[str] = None

    @validator("hash", always=True, pre=True)
    def ensure_hash(cls, v, values):
        if v:
            return v
        txt = (values.get("text") or "").strip()
        if txt:
            return sha256_text(txt)
        return v


class Citation(BaseModel):
    source_id: constr(regex=ID_RX["source"])
    document_id: Optional[constr(regex=ID_RX["document"])] = None
    locator: Optional[str] = Field(
        None, description="paragrafo/riga/pagina es: p4; l35-38"
    )


class Finding(BaseModel):
    id: constr(regex=ID_RX["finding"])
    text: str
    support: SupportLevel
    confidence: float = Field(..., ge=0.0, le=1.0)
    citations: conlist(Citation, min_items=1)
    limitations: Optional[str] = None


class Event(BaseModel):
    id: constr(regex=ID_RX["event"])
    date_iso: constr(regex=DATE_ISO_RX)
    title: str
    summary: Optional[str] = None
    citations: Optional[List[Citation]] = None


class Actor(BaseModel):
    id: constr(regex=ID_RX["actor"])
    name: str
    kind: ActorKind
    aliases: Optional[List[str]] = None
    notes: Optional[str] = None


class Relationship(BaseModel):
    id: constr(regex=ID_RX["relationship"])
    from_: constr(regex=ID_RX["actor"]) = Field(..., alias="from")
    to: constr(regex=ID_RX["actor"])
    type: RelationshipType
    strength: Optional[float] = Field(0.5, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(0.5, ge=0.0, le=1.0)
    citations: Optional[List[Citation]] = None


class IndicatorPoint(BaseModel):
    date_iso: constr(regex=DATE_ISO_RX)
    value: float
    citations: Optional[List[Citation]] = None


class Indicator(BaseModel):
    id: constr(regex=ID_RX["indicator"])
    name: str
    definition: Optional[str] = None
    unit: Optional[str] = None
    series: Optional[List[IndicatorPoint]] = None


class Narrative(BaseModel):
    topics: Optional[List[str]] = None
    sentiment: Optional[SentimentEnum] = "neutral"
    bias_notes: Optional[str] = None
    source_mix: Optional[Dict[str, int]] = None


class GeoGeometry(BaseModel):
    type: GeoType
    coordinates: List  # GeoJSON-like


class GeoProperties(BaseModel):
    label: Optional[str] = None
    date_iso: Optional[str] = None
    citations: Optional[List[Citation]] = None


class GeoFeature(BaseModel):
    id: constr(regex=ID_RX["geofeature"])
    geometry: GeoGeometry
    properties: Optional[GeoProperties] = None


class BibliographyItem(BaseModel):
    source_id: constr(regex=ID_RX["source"])
    citation_text: Optional[str] = None
    doi: Optional[str] = None


class Methodology(BaseModel):
    collectors: Optional[List[str]] = None
    queries: Optional[List[str]] = None
    engines_profile: Optional[str] = None
    dedup: Optional[str] = None
    ranking: Optional[str] = None
    ethics: Optional[str] = None
    limitations: Optional[str] = None


class Attachment(BaseModel):
    title: str
    kind: Literal["pdf", "image", "html", "text", "audio", "video"]
    path: str
    source_id: Optional[constr(regex=ID_RX["source"])] = None
    document_id: Optional[constr(regex=ID_RX["document"])] = None


class ReportModel(BaseModel):
    metadata: ReportMetadata
    scope: Scope
    sources: List[Source]
    documents: List[Document]
    findings: List[Finding]
    timeline: Optional[List[Event]] = None
    actors: Optional[List[Actor]] = None
    relationships: Optional[List[Relationship]] = None
    indicators: Optional[List[Indicator]] = None
    narrative: Optional[Narrative] = None
    geospatial: Optional[List[GeoFeature]] = None
    bibliography: Optional[List[BibliographyItem]] = None
    methodology: Optional[Methodology] = None
    annex: Optional[List[Attachment]] = None

    # -------------------------
    # Validazioni incrociate
    # -------------------------
    @root_validator
    def cross_refs_exist(cls, values):
        src_ids = {s.id for s in values.get("sources", [])}
        doc_ids = {d.id for d in values.get("documents", [])}

        def _check_citations(citations: Optional[List[Citation]], where: str):
            if not citations:
                return
            for c in citations:
                if c.source_id not in src_ids:
                    raise ValueError(f"[{where}] source_id non presente: {c.source_id}")
                if c.document_id and c.document_id not in doc_ids:
                    raise ValueError(f"[{where}] document_id non presente: {c.document_id}")

        for f in values.get("findings", []) or []:
            _check_citations(f.citations, f"Finding {f.id}")

        for e in values.get("timeline", []) or []:
            _check_citations(e.citations, f"Event {e.id}")

        for r in values.get("relationships", []) or []:
            _check_citations(r.citations, f"Relationship {r.id}")

        for ind in values.get("indicators", []) or []:
            for p in ind.series or []:
                _check_citations(p.citations, f"Indicator {ind.id} point {p.date_iso}")

        for gf in values.get("geospatial", []) or []:
            if gf.properties:
                _check_citations(gf.properties.citations, f"GeoFeature {gf.id}")

        # actor cross checks
        act_ids = {a.id for a in values.get("actors", []) or []}
        for rel in values.get("relationships", []) or []:
            if rel.from_ not in act_ids or rel.to not in act_ids:
                raise ValueError(f"[Relationship {rel.id}] attori inesistenti in 'from'/'to'")

        return values

    # -------------------------
    # Helper
    # -------------------------
    def to_json(self, **kwargs) -> str:
        return self.json(by_alias=True, exclude_none=True, **kwargs)

    def to_dict(self) -> Dict:
        return self.dict(by_alias=True, exclude_none=True)

    def bibliography_from_sources(self) -> List[BibliographyItem]:
        items: List[BibliographyItem] = []
        for s in self.sources:
            cit = s.title or s.domain or str(s.url)
            items.append(BibliographyItem(source_id=s.id, citation_text=cit))
        return items


# =========================
# Esempio rapido d'uso
# =========================

if __name__ == "__main__":
    # Mini esempio costruzione modello
    rpt = ReportModel(
        metadata=ReportMetadata(
            report_id=new_report_id(seq=1),
            title="Donald Trump e Cina — Impatti commerciali",
            query='Donald Trump China trade 2025 site:ustr.gov',
            generated_at=datetime.utcnow(),
            analyst="Valerio Bascerano",
            llm=LLMInfo(name="vllm/llama3.1-8b", params={"temperature": 0.2})
        ),
        scope=Scope(
            time_window=TimeWindow(**{"from": date(2025,10,1)}, to=date(2025,11,4)),
            geo_focus=["USA","Cina","APAC"],
            languages=["en","it"]
        ),
        sources=[
            Source(
                id=new_id("SRC", 1),
                type="Gov",
                domain="ustr.gov",
                author="Office of the USTR",
                title="Ambassador statement on Chinese coercion",
                published_at="2025-10-20",
                accessed_at=datetime.utcnow(),
                url="https://ustr.gov/about-us/policy-offices/press-office/press-releases/2025-10-20",
                reliability="A"
            )
        ],
        documents=[
            Document(
                id=new_id("DOC", 1),
                source_id="SRC-0001",
                url="https://ustr.gov/about-us/policy-offices/press-office/press-releases/2025-10-20",
                title="Ambassador statement on Chinese coercion",
                published_at="2025-10-20",
                text="The Ambassador stated that ...",
                lang="en"
            )
        ],
        findings=[
            Finding(
                id=new_id("CLM", 1),
                text="USTR ha avviato iniziative su Section 301 riguardo pratiche cinesi.",
                support="Supported",
                confidence=0.8,
                citations=[Citation(source_id="SRC-0001", document_id="DOC-0001", locator="p2")]
            )
        ],
        timeline=[
            Event(
                id=new_id("EVT", 1),
                date_iso="2025-10-20",
                title="Statement USTR su presunte coercizioni cinesi",
                summary="L'Ambasciatore rilascia nota ufficiale.",
                citations=[Citation(source_id="SRC-0001", document_id="DOC-0001")]
            )
        ],
        actors=[
            Actor(id=new_id("ACT", 1), name="Donald J. Trump", kind="PERSON"),
            Actor(id=new_id("ACT", 2), name="USTR", kind="ORG"),
            Actor(id=new_id("ACT", 3), name="PRC / Cina", kind="STATE")
        ],
        relationships=[
            Relationship(
                id=new_id("REL", 1),
                **{"from": "ACT-0002"},
                to="ACT-0003",
                type="investigates",
                strength=0.6, confidence=0.7,
                citations=[Citation(source_id="SRC-0001", document_id="DOC-0001")]
            )
        ],
        indicators=[
            Indicator(
                id=new_id("IND", 1),
                name="Tariffe mediane su import Cina (%)",
                unit="%",
                series=[IndicatorPoint(date_iso="2025-10-01", value=12.5,
                                       citations=[Citation(source_id="SRC-0001")])]
            )
        ],
        narrative=Narrative(
            topics=["tariffs","Section 301","coercion"],
            sentiment="neutral",
            bias_notes="Prevalenza di fonti governative USA.",
            source_mix={"Gov": 1}
        ),
        geospatial=[],
        bibliography=None,  # possiamo derivarla da sources
        methodology=Methodology(
            collectors=["searxng:web,news", "manual:add USTR"],
            queries=["Donald Trump China trade 2025 site:ustr.gov"],
            engines_profile="light",
            dedup="canonical+simhash(H=6)",
            ranking="0.35 freshness + 0.35 authority + 0.2 completeness + 0.1 coherence (+bonus qualità)",
            ethics="No PII; rispetto robots/ToS.",
            limitations="CAPTCHA e blocchi su alcuni domini media."
        ),
        annex=[]
    )

    # Costruisci bibliografia se mancante
    if not rpt.bibliography:
        rpt.bibliography = rpt.bibliography_from_sources()

    print(rpt.to_json(indent=2))
