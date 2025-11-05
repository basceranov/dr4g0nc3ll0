#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OSINT Report Generator (dinamico dalla query)
- Interroga SearXNG (API JSON)
- Scarica/estrapola testo semplice dalle pagine (BS4)
- Costruisce ReportModel (Pydantic)
- (opz.) Agenti LLM: Executive Summary, Claims, Attori/Relazioni
- Emette report.md + report.json in ./out/
"""

from __future__ import annotations
import os, sys, json, argparse, time, re
from datetime import datetime, date
from urllib.parse import urlparse
from typing import List, Dict, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

# === importa i modelli pydantic che mi avevi dato ===
#   Salva quel file come models.py nella stessa cartella del progetto
from models import (
    ReportModel, ReportMetadata, LLMInfo, Scope, TimeWindow,
    Source, Document, Finding, Citation, Event, Actor, Relationship, Indicator, IndicatorPoint,
    Narrative, Methodology, Attachment,
    new_id, new_report_id
)

# -------------------------------
# Config
# -------------------------------
DEFAULT_SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8880")  # es: http://127.0.0.1:8089
DEFAULT_CATEGORIES = os.getenv("SEARXNG_CATEGORIES", "news,web")
DEFAULT_LANG = os.getenv("SEARXNG_LANG", "it-IT")
USER_AGENT = "osint-report/2.1 (+https://local)"

OUT_DIR = "./out"
os.makedirs(OUT_DIR, exist_ok=True)

# -------------------------------
# LLM Config (OpenAI-compatible) & client
# -------------------------------
USE_LLM = os.getenv("USE_LLM", "true").lower() in ("1", "true", "yes")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1").strip()  # es. http://localhost:8000/v1 (vLLM/LM Studio) o Ollama /v1
LLM_API_KEY = os.getenv("LLM_API_KEY", "EMPTY")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-oss:20b")  # cambia col served-name

class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60):
        self._endpoint = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 1200) -> str:
        payload = {
            "model": self._model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key and self._api_key != "EMPTY":
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            r = requests.post(self._endpoint, headers=headers, json=payload, timeout=self._timeout)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[WARN] LLM call failed: {e}", file=sys.stderr)
            return ""

# -------------------------------
# Utility
# -------------------------------
def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s[:n] + ("…" if len(s) > n else "")

def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def http_get(url: str, timeout: int = 15) -> Optional[str]:
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        if r.status_code == 200 and r.text:
            return r.text
    except requests.RequestException:
        return None
    return None

def extract_text_html(html: str) -> str:
    # Estrattore minimalista (senza readability / lxml_html_clean)
    soup = BeautifulSoup(html, "html.parser")
    # Rimuovi script/style/nav/aside
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside", "form"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    # normalizza spazi
    text = re.sub(r"\s+", " ", text).strip()
    # limita per non esplodere
    return text[:30000]

def parse_date_soft(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    try:
        return dateparser.parse(s, dayfirst=True, fuzzy=True).date().isoformat()
    except Exception:
        return None

def safe_filename(stem: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", stem)[:80]

# -------------------------------
# SearXNG Collector
# -------------------------------
def searxng_search(q: str, *, searxng_url: str, categories: str, lang: str, max_results: int = 20) -> List[Dict]:
    """Chiama /search?format=json e normalizza i risultati."""
    url = f"{searxng_url.rstrip('/')}/search"
    params = {
        "q": q,
        "format": "json",
        "language": lang,
        "safesearch": 0,
        "categories": categories,
        "pageno": 1,
        "time_range": None,
    }
    try:
        resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("results", [])[:max_results]
        norm = []
        for it in items:
            norm.append({
                "title": it.get("title"),
                "url": it.get("url"),
                "content": it.get("content"),
                "publishedDate": it.get("publishedDate") or it.get("publishedDateParsed")
            })
        return norm
    except Exception as e:
        print(f"[WARN] SearXNG error: {e}", file=sys.stderr)
        return []

# -------------------------------
# Heuristics: tipo fonte & reliability
# -------------------------------
def classify_source_type(dom: str) -> str:
    dom = (dom or "").lower()
    if dom.endswith("un.org") or "reliefweb.int" in dom or "oecd.org" in dom or dom.endswith("europa.eu"):
        return "UN"
    if dom.endswith("who.int") or "savethechildren" in dom or "hrw.org" in dom or "icrc.org" in dom:
        return "ONG"
    if dom.endswith("whitehouse.gov") or dom.endswith("ustr.gov") or dom.endswith("gov"):
        return "Gov"
    intl_media = ("cnn.com","bbc.co.uk","reuters.com","apnews.com","aljazeera.com","ft.com","bloomberg.com")
    it_media = ("repubblica.it","corriere.it","ansa.it","ilpost.it","tg24.sky.it")
    if any(dom.endswith(x) for x in intl_media):
        return "Media-Intl"
    if any(dom.endswith(x) for x in it_media):
        return "Media-IT"
    thinktanks = ("csis.org","brookings.edu","rand.org","carnegieendowment.org")
    if any(dom.endswith(x) for x in thinktanks):
        return "ThinkTank"
    return "Other"

def reliability_guess(src_type: str) -> Optional[str]:
    return {
        "UN":"A","ONG":"B","Gov":"A","Media-Intl":"B","Media-IT":"C","ThinkTank":"B","Other":"D"
    }.get(src_type, None)

# -------------------------------
# Timeline extraction (semplice)
# -------------------------------
DATE_RX = re.compile(r"\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|(?:\d{1,2}\s+\w+\s+20\d{2}))\b", re.I)

def extract_timeline_from_docs(docs: List[Document], limit: int = 10) -> List[Event]:
    seen = set()
    events: List[Event] = []
    seq = 0
    for d in docs:
        txt = (d.text or "")[:2000]
        for m in DATE_RX.finditer(txt):
            iso = parse_date_soft(m.group(0))
            if not iso:
                continue
            # frase circostante
            start = txt.rfind('.', 0, m.start()) + 1
            end = txt.find('.', m.end())
            if end == -1:
                end = min(len(txt), m.end() + 180)
            sentence = re.sub(r"\s+", " ", txt[start:end]).strip()
            if len(sentence) < 25:
                continue
            key = (iso, sentence)
            if key in seen:
                continue
            seen.add(key)
            seq += 1
            events.append(Event(
                id=new_id("EVT", seq),
                date_iso=iso,
                title=sentence[:140],
                summary=None,
                citations=[Citation(source_id=d.source_id, document_id=d.id)]
            ))
            if len(events) >= limit:
                return sorted(events, key=lambda x: x.date_iso)
    return sorted(events, key=lambda x: x.date_iso)

# -------------------------------
# Findings (fallback minimale)
# -------------------------------
def generate_fallback_findings(docs: List[Document], max_items: int = 5) -> List[Finding]:
    out: List[Finding] = []
    seq = 0
    for i, d in enumerate(docs[:max_items], start=1):
        title = (d.title or "").strip()
        if not title:
            # prendi prime frasi dal testo
            title = (d.text or "")[:140]
        if not title:
            continue
        seq += 1
        out.append(Finding(
            id=new_id("CLM", seq),
            text=title,
            support="Unknown",
            confidence=0.5,
            citations=[Citation(source_id=d.source_id, document_id=d.id)]
        ))
    return out

# -------------------------------
# Agenti LLM: Executive summary, Claims, Attori/Relazioni
# -------------------------------
def _pack_docs_for_llm(docs: List[Dict], hard_limit: int = 12000) -> str:
    """Confeziona un contesto testuale compatto per l'LLM (title + snippet testo)."""
    buf, total = [], 0
    for d in docs:
        block = "# " + (d.get("title","") or "") + "\n" + _clip(d.get("text",""), 3500) + "\n\n"
        if total + len(block) > hard_limit:
            break
        buf.append(block)
        total += len(block)
    return "".join(buf)

def llm_executive_summary(llm: LLMClient, query: str, docs: List[Dict]) -> str:
    sys_p = ("Sei un analista OSINT. Produce un executive summary conciso (5–8 bullet) in italiano, "
             "con riferimenti alle fonti usando gli ID tra parentesi quadre (es. [SRC-0003]) se forniti. "
             "Evidenzia: situazione, driver, impatti umanitari, attori, trend temporali. Niente opinioni.")
    ctx = _pack_docs_for_llm(docs)
    id_map_lines = []
    for d in docs:
        sid = d.get("source_id")
        ttl = _clip(d.get("title",""), 90)
        id_map_lines.append(f"- {sid}: {ttl}")
    usr_p = (
        "Query: " + query + "\n\n"
        "Fonti (ID→Titolo):\n" + "\n".join(id_map_lines) + "\n\n"
        "Estratti:\n" + ctx + "\n\n"
        "Scrivi solo bullet list, massimo 120 parole."
    )
    return llm.chat(sys_p, usr_p, temperature=0.1, max_tokens=500)

def llm_extract_claims(llm: LLMClient, docs: List[Dict], k: int = 8) -> List[Dict]:
    sys_p = ("Sei un sistema di fact extraction OSINT. Estrai fino a "
             f"{k} affermazioni verificabili in JSON compatto con schema: "
             "[{\"text\":\"...\",\"support\":\"supported|contested|unknown\","
             "\"confidence\":0.0-1.0,\"citations\":[\"SRC-0001\",\"SRC-0005\"]}]. "
             "Usa più fonti quando possibile. Niente testo fuori dal JSON.")
    ctx = _pack_docs_for_llm(docs)
    usr_p = "Estratti documenti:\n" + ctx + "\n\nRespondi SOLO col JSON."
    raw = llm.chat(sys_p, usr_p, temperature=0.0, max_tokens=900)
    try:
        m = re.search(r"\[.*\]", raw, re.S)
        data = json.loads(m.group(0) if m else raw)
        if isinstance(data, list):
            out = []
            for it in data[:k]:
                out.append({
                    "text": _clip(it.get("text",""), 400),
                    "support": (it.get("support","unknown") or "unknown").lower(),
                    "confidence": float(it.get("confidence", 0.6)),
                    "citations": [c for c in it.get("citations", []) if isinstance(c, str)]
                })
            return out
    except Exception as e:
        print(f"[WARN] parse claims failed: {e}", file=sys.stderr)
    return []

def llm_extract_actors_relations(llm: LLMClient, docs: List[Dict]) -> Dict:
    sys_p = ("Sei un NER+RE per OSINT. Estrai attori (people/org/loc) e relazioni chiave (subject,relation,object) "
             "in JSON: {\"actors\":[{\"name\":\"...\",\"type\":\"person|org|loc\"}],"
             "\"relations\":[{\"s\":\"ActorName\",\"p\":\"relazione\",\"o\":\"ActorName\",\"confidence\":0-1}]}."
             "Niente testo extra.")
    ctx = _pack_docs_for_llm(docs)
    usr_p = "Estratti documenti:\n" + ctx + "\n\nRespondi SOLO col JSON."
    raw = llm.chat(sys_p, usr_p, temperature=0.0, max_tokens=1000)
    try:
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0) if m else raw)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[WARN] parse ner/re failed: {e}", file=sys.stderr)
        return {}

# -------------------------------
# Composer Markdown (sezione base)
# -------------------------------
def render_markdown(report: ReportModel) -> str:
    md = []
    md.append("# " + report.metadata.title)
    md.append("**Generato:** " + report.metadata.generated_at.isoformat() + " • **Query:** " + (report.metadata.query or "-"))
    md.append("")
    md.append("## Executive Summary")
    # Se abbiamo messo il summary LLM in narrative.topics[0], mostralo
    if report.narrative and report.narrative.topics:
        md.append(report.narrative.topics[0])
    elif report.findings:
        top = report.findings[:3]
        for f in top:
            cites = ", ".join({c.source_id for c in f.citations})
            md.append("- " + f.text + " *(conf. " + f"{f.confidence:.2f}" + ", " + f.support + ")* — " + cites)
    else:
        md.append("- (in costruzione)")
    md.append("\n---\n")

    if report.findings:
        md.append("## Key Findings — con citazioni")
        md.append("| # | Claim | Supporto | Confidenza | Fonti |")
        md.append("|---|-------|----------|------------|-------|")
        for i, f in enumerate(report.findings, start=1):
            cites = ", ".join([c.source_id for c in f.citations])
            md.append("| " + str(i) + " | " + f.text.replace("|","\\|") + " | " + f.support + " | " + f"{f.confidence:.2f}" + " | " + cites + " |")
        md.append("")

    if report.timeline:
        md.append("## Timeline")
        for e in report.timeline:
            # prendi primo link citato
            url = None
            if e.citations and len(e.citations) and e.citations[0].document_id:
                doc = next((d for d in report.documents if d.id == e.citations[0].document_id), None)
                url = doc.url if doc else None
            line = "- **" + e.date_iso + "** — " + e.title
            if url:
                line += " ([fonte](" + url + "))"
            md.append(line)
        md.append("")

    # Fonti (bibliografia breve)
    if report.sources:
        md.append("## Fonti (bibliografia breve)")
        md.append("| ID | Tipo | Dominio | Titolo | Pubblicato | URL |")
        md.append("|----|------|---------|--------|------------|-----|")
        for s in report.sources:
            md.append("| " + s.id + " | " + s.type + " | " + (s.domain or "") + " | " + (s.title or "").replace("|","\\|") + " | " + (s.published_at or "") + " | " + s.url + " |")
        md.append("")

    # Annex: attori/relazioni (se presenti)
    for a in (report.annex or []):
        if a.get("type") == "actors_relations":
            md.append("## Attori & Relazioni (estratto)")
            data = a.get("data", {})
            actors = data.get("actors", [])
            rels = data.get("relations", [])
            if actors:
                md.append("**Attori (top):** " + ", ".join(sorted({_clip(x.get('name',''),60) for x in actors})[:12]))
            if rels:
                md.append("**Relazioni (esempi):**")
                for r in rels[:8]:
                    s = r.get("s","?")
                    p = r.get("p","?")
                    o = r.get("o","?")
                    conf = r.get("confidence", 0)
                    md.append("- " + s + " — " + p + " → " + o + " *(conf. " + f"{conf:.2f}" + ")*")
            md.append("")

    # Metodologia (breve)
    if report.methodology:
        m = report.methodology
        md.append("## Metodologia")
        if m.queries:
            md.append("- Query: " + ", ".join(m.queries))
        if m.engines_profile:
            md.append("- Profilo motori: " + m.engines_profile)
        if m.dedup:
            md.append("- Dedup: " + m.dedup)
        if m.ranking:
            md.append("- Ranking: " + m.ranking)
        if m.limitations:
            md.append("- Limitazioni: " + m.limitations)
        md.append("")

    return "\n".join(md)

# -------------------------------
# Build dinamico del Report
# -------------------------------
def build_report_from_query(
    query: str,
    time_from: Optional[str],
    time_to: Optional[str],
    searxng_url: str,
    categories: str,
    lang: str,
    max_results: int = 20
) -> ReportModel:

    # 1) Cerca
    results = searxng_search(query, searxng_url=searxng_url, categories=categories, lang=lang, max_results=max_results)

    # 2) Normalizza -> Sources + Documents (1:1 semplificato)
    sources: List[Source] = []
    documents: List[Document] = []
    seq_src = seq_doc = 0

    for r in results:
        url = r.get("url")
        if not url:
            continue
        dom = domain_of(url)
        seq_src += 1; seq_doc += 1
        src_id = new_id("SRC", seq_src)
        doc_id = new_id("DOC", seq_doc)

        stype = classify_source_type(dom)
        pub = parse_date_soft(r.get("publishedDate"))

        sources.append(Source(
            id=src_id,
            type=stype,
            domain=dom,
            author=None,
            title=r.get("title") or dom,
            published_at=pub,
            accessed_at=datetime.utcnow(),
            url=url,
            reliability=reliability_guess(stype)
        ))

        html = http_get(url)
        text = extract_text_html(html) if html else None

        documents.append(Document(
            id=doc_id,
            source_id=src_id,
            url=url,
            title=r.get("title") or dom,
            published_at=pub,
            text=text,
            lang=None
        ))

    # 2b) Prepara top docs per LLM (se attivo)
    top_docs_for_llm = [
        {
            "source_id": d.source_id,
            "title": d.title,
            "text": d.text or "",
            "published_at": d.published_at
        }
        for d in documents[:10] if (d.text or "").strip()
    ]

    used_llm = False
    llm_summary_md = ""
    llm_claims = []
    llm_actors = {}

    if USE_LLM and LLM_BASE_URL and top_docs_for_llm:
        llm = LLMClient(LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, timeout=90)
        llm_summary_md = llm_executive_summary(llm, query, top_docs_for_llm)
        llm_claims = llm_extract_claims(llm, top_docs_for_llm, k=8)
        llm_actors = llm_extract_actors_relations(llm, top_docs_for_llm)
        used_llm = True

    # 3) Findings + Timeline
    if used_llm and llm_claims:
        findings = []
        seq = 0
        for c in llm_claims:
            seq += 1
            cites = []
            for sid in c.get("citations", []):
                cites.append(Citation(source_id=sid, document_id=None))
            sup = (c.get("support","unknown") or "unknown").capitalize()
            conf = float(c.get("confidence", 0.6))
            findings.append(Finding(
                id=new_id("CLM", seq),
                text=c.get("text",""),
                support=sup if sup in ("Supported","Contested","Unknown") else "Unknown",
                confidence=conf if 0 <= conf <= 1 else 0.6,
                citations=cites or []
            ))
    else:
        findings = generate_fallback_findings(documents, max_items=5)

    timeline = extract_timeline_from_docs(documents, limit=10)

    # 4) Metadata & Scope
    #   finestra temporale: se non passata, default ultimi 30 giorni
    if time_from and time_to:
        win = TimeWindow(**{"from": date.fromisoformat(time_from), "to": date.fromisoformat(time_to)})
    else:
        today = date.today()
        from_ = date.fromtimestamp(time.time() - 30 * 86400)
        win = TimeWindow(**{"from": from_, "to": today})

    metadata = ReportMetadata(
        report_id=new_report_id(seq=1),
        title="OSINT Report — " + query,
        query=query,
        generated_at=datetime.utcnow(),
        analyst=os.getenv("OSINT_ANALYST") or "Auto",
        llm=LLMInfo(name=None, params=None),
        tool_version="osint-pipeline 2.1"
    )

    methodology = Methodology(
        collectors=["searxng:api"],
        queries=[query],
        engines_profile="light",
        dedup="(n/a minimal)",
        ranking="(n/a minimal)",
        limitations="Collector semplice; estrazione testo HTML basilare; LLM opzionale."
    )

    report = ReportModel(
        metadata=metadata,
        scope=Scope(time_window=win, geo_focus=None, languages=[lang]),
        sources=sources,
        documents=documents,
        findings=findings,
        timeline=timeline,
        actors=None,
        relationships=None,
        indicators=None,
        narrative=Narrative(
            topics=None, sentiment="neutral", bias_notes=None,
            source_mix=_mix_by_type(sources)
        ),
        geospatial=None,
        bibliography=None,
        methodology=methodology,
        annex=[]
    )

    # 4b) Tracciabilità LLM + annex
    if used_llm:
        report.metadata.llm = LLMInfo(name=LLM_MODEL, params={"base_url": LLM_BASE_URL})
        if llm_summary_md:
            report.narrative = report.narrative or Narrative(sentiment="neutral")
            report.narrative.topics = [llm_summary_md]
        if llm_actors:
            report.annex.append({"type": "actors_relations", "data": llm_actors})
        if report.methodology:
            prev = report.methodology.ranking or ""
            report.methodology.ranking = (prev + " + LLM claims fusion").strip()

    # bibliografia se mancante
    if not report.bibliography:
        report.bibliography = report.bibliography_from_sources()

    return report

def _mix_by_type(sources: List[Source]) -> Dict[str, int]:
    c: Dict[str, int] = {}
    for s in sources:
        c[s.type] = c.get(s.type, 0) + 1
    return c

# -------------------------------
# CLI
# -------------------------------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="OSINT report dinamico dalla query (SearXNG + opz. LLM).")
    ap.add_argument("-q", "--query", required=True, help="Domanda/Query iniziale (es: 'Sudan El-Fasher humanitarian')")
    ap.add_argument("--from", dest="time_from", help="Data inizio ISO (YYYY-MM-DD)")
    ap.add_argument("--to", dest="time_to", help="Data fine ISO (YYYY-MM-DD)")
    ap.add_argument("--searxng-url", default=DEFAULT_SEARXNG_URL, help=f"URL base SearXNG (default: {DEFAULT_SEARXNG_URL})")
    ap.add_argument("--categories", default=DEFAULT_CATEGORIES, help=f"Categorie SearXNG (default: {DEFAULT_CATEGORIES})")
    ap.add_argument("--lang", default=DEFAULT_LANG, help=f"Lingua (default: {DEFAULT_LANG})")
    ap.add_argument("--max", type=int, default=20, help="Max risultati da SearXNG")
    return ap.parse_args()

def main():
    args = parse_args()

    report = build_report_from_query(
        query=args.query,
        time_from=args.time_from,
        time_to=args.time_to,
        searxng_url=args.searxng_url,
        categories=args.categories,
        lang=args.lang,
        max_results=args.max
    )

    # Salva JSON
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = safe_filename("report_" + ts)
    json_path = os.path.join(OUT_DIR, stem + ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(report.to_json(indent=2))
    print("[OK] Salvato JSON: " + json_path)

    # Salva Markdown
    md = render_markdown(report)
    md_path = os.path.join(OUT_DIR, stem + ".md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    print("[OK] Salvato Markdown: " + md_path)

    print("\nPronto ✅  (puoi aprire l'MD in un viewer o generare PDF con il tuo exporter)")

if __name__ == "__main__":
    main()
