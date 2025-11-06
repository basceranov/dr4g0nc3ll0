# pipeline.py
# OSINT multi-agent pipeline (v2) con fonti istituzionali, stato della prova, timeline, e grafici.

from __future__ import annotations

import json
import time
from typing import Dict, List, Any, Tuple

from searxng import searxng_search
from fetch import fetch_and_extract
from dedup import prepare_for_dedup, cluster_near_duplicates
from rank import score_item
from llm import chat
from prompts import (
    PLANNER_PROMPT,
    NER_PROMPT,
    SUMMARIZE_PROMPT,
    FACTCHECK_PROMPT,
    COMPOSE_PROMPT,  # tenuto per retrocompatibilità se servisse
)
from provenance import log_event

# --- Nuovi moduli integrati ---
from sources_reliefweb import fetch_reliefweb_reports
from evidence import label_support, classify_sources as classify_sources_counts
from timeline_extractor import extract_events
from visualization import chart_source_mix, chart_indicator_timeseries, map_events  # map_events al momento opzionale
from config import (
    USE_RELIEFWEB,
    ENGINES_PROFILE_LIGHT,
    FRESHNESS_HALF_LIFE_DAYS,
    LLM_TEMPERATURE,
)
from quality import is_low_quality, is_index_page


# ============================================================
# Agenti LLM “logici” (planner, ner, summarize/factcheck)
# ============================================================

def planner(query: str) -> Dict[str, Any]:
    """Crea un piano di ricerca (subgoals, queries, criteria) via LLM."""
    msg = [{"role": "system", "content": PLANNER_PROMPT},
           {"role": "user", "content": query}]
    out = chat(msg, max_tokens=900)
    try:
        plan = json.loads(out)
    except Exception:
        # Fallback minimale se il parsing fallisce
        plan = {
            "subgoals": ["Mappare attori", "Raccogliere timeline", "Identificare indicatori"],
            "queries": [query, f'"{query}" site:reuters.com', f'{query} filetype:pdf'],
            "criteria": {"freshness_days": 60, "need_institutional": True, "need_diversity": True}
        }
    log_event("planner_plan", plan)
    return plan


def ner_top(docs: List[Dict[str, Any]], topk: int = 12) -> List[Dict[str, Any]]:
    payload = []
    for d in docs[:topk]:
        title = (d.get("title") or "")[:200]
        text = (d.get("text") or "")[:1200]
        payload.append({"title": title, "text": text})
    msg = [{"role": "system", "content": NER_PROMPT},
           {"role": "user", "content": json.dumps({"docs": payload}, ensure_ascii=False)}]
    out = chat(msg, max_tokens=1200)
    try:
        ents = json.loads(out)
        if isinstance(ents, list):
            return ents
    except Exception:
        pass
    return []


def summarize_with_citations(ranked: List[Dict[str, Any]], topk: int = 8) -> Tuple[Dict[str, Any], Dict[int, str]]:
    pack = []
    refs = {}
    for i, d in enumerate(ranked[:topk], start=1):
        refs[i] = d["url"]
        pack.append({"id": i, "title": d.get("title"), "excerpt": d.get("text", "")[:3000]})

    msg = [
        {"role": "system", "content": SUMMARIZE_PROMPT},
        {"role": "user", "content": json.dumps({"sources": pack}, ensure_ascii=False)}
    ]
    out = chat(msg, max_tokens=1800)
    data = {"per_source_summary": {}, "cross_summary": "", "claims": []}
    try:
        parsed = json.loads(out)
        if isinstance(parsed, dict):
            data.update(parsed)
    except Exception:
        pass

    # --- Fallback: se non ci sono claim, generane 3-5 dai titoli top ---
    if not data.get("claims"):
        fallback_claims = []
        for i, d in enumerate(ranked[:min(5, len(ranked))], start=1):
            title = (d.get("title") or "").strip()
            if not title:
                continue
            fallback_claims.append({
                "text": title,
                "sources": [i]  # attribuisci almeno la fonte primaria
            })
        data["claims"] = fallback_claims

    # Fallback per cross_summary
    if not data.get("cross_summary"):
        titles = [ (d.get("title") or "").strip() for d in ranked[:5] if d.get("title") ]
        data["cross_summary"] = " • ".join(titles[:4])[:800]

    return data, refs



def factcheck(claims: List[Dict[str, Any]], sources_map: Dict[int, str]) -> List[Dict[str, Any]]:
    """Valuta i claim con un fact-check LLM-guidato (schema minimo)."""
    payload = {"claims": claims, "sources": sources_map}
    msg = [{"role": "system", "content": FACTCHECK_PROMPT},
           {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    out = chat(msg, max_tokens=1800)
    try:
        checks = json.loads(out)
    except Exception:
        checks = [{"claim": c.get("text", ""), "support": "unknown", "confidence": 0.4,
                   "notes": "insufficient evidence"} for c in claims]
    return checks


# ============================================================
# Ricerca, crawl, dedup/ranking
# ============================================================

def search(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    agg: List[Dict[str, Any]] = []

    for q in plan.get("queries", []):
        agg += searxng_search(q, engines=ENGINES_PROFILE_LIGHT)

    if USE_RELIEFWEB:
        try:
            agg += fetch_reliefweb_reports()
        except Exception as e:
            log_event("reliefweb_err", {"err": str(e)})

    # Dedup base per URL + Filtro qualità
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for r in agg:
        u = r.get("url")
        if not u or u in seen:
            continue
        if is_low_quality(u) or is_index_page(u):
            # scarta pagine indice e domini “opinion”
            continue
        uniq.append(r)
        seen.add(u)

    log_event("search_uniq", {"count": len(uniq), "reliefweb": USE_RELIEFWEB})
    return uniq[:100]


def crawl(seeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Scarica e pulisce i contenuti HTML testuali."""
    docs: List[Dict[str, Any]] = []
    for s in seeds[:40]:
        try:
            ext = fetch_and_extract(s["url"])
            # merge metadata seed + estrazione
            docs.append({**s, **ext})
        except Exception as e:
            log_event("fetch_err", {"url": s.get("url"), "err": str(e)})
            continue
    return docs


def dedup_rank(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Near-duplicate detection (SimHash) e ranking time-aware.
    Tiene il documento più completo/recente per cluster.
    """
    now_ts = time.time()
    prepare_for_dedup(docs)
    clusters = cluster_near_duplicates(docs)
    picked: List[Dict[str, Any]] = []

    for group in clusters:
        # tieni il più “ricco” del cluster
        group_sorted = sorted(
            group,
            key=lambda d: (len(d.get("text", "")), d.get("detected_date") or ""),
            reverse=True
        )
        picked.append(group_sorted[0])

    # ranking
    for d in picked:
        d["score"] = score_item(d, now_ts)

    ranked = sorted(picked, key=lambda d: d["score"], reverse=True)
    log_event("rank_done", {"kept": len(ranked)})
    return ranked


# ============================================================
# Composer v2 (con stato della prova, timeline, visual)
# ============================================================

def compose_report_v2(
    query: str,
    evidence_rows: List[Dict[str, Any]],
    ents: List[Dict[str, Any]],
    refs: Dict[int, str],
    cross_summary: str,
    timeline: List[Dict[str, Any]],
    source_counts: Dict[str, int],
    source_details: List[Dict[str, Any]],
    charts: Dict[str, str]
) -> str:
    """Genera il Markdown finale (versione arricchita)."""

    # Liste entità
    persons = sorted({e["entity"] for e in ents if e.get("type") == "PERSON"})[:12]
    orgs = sorted({e["entity"] for e in ents if e.get("type") == "ORG"})[:12]
    locs = sorted({e["entity"] for e in ents if e.get("type") == "LOC"})[:12]
    indicators = sorted({e["entity"] for e in ents if e.get("type") == "INDICATOR"})[:12]

    # Fonti formattate (tabella)
    ref_lines = "\n".join([f"| {i} | {u} |" for i, u in refs.items()])
    ref_table = "\n".join([
        "| # | URL |",
        "|---|-----|",
        ref_lines if ref_lines else "| - | - |"
    ])

    # Tabella evidenze (stato della prova)
    ev_lines = []
    for i, row in enumerate(evidence_rows, start=1):
        srcs = ", ".join([f"[{n}]" for n in row.get("sources", [])])
        ev_lines.append(f"| {i} | {row.get('claim','').strip()} | {row.get('support_state','unknown')} | {row.get('independence',0)} | {srcs} |")
    ev_table = "\n".join([
        "| # | Claim | Stato prova | Indip. fonti | Citazioni |",
        "|---|---|---|---|---|",
        *ev_lines
    ]) if ev_lines else "_Nessun claim estratto._"

    # Timeline (bullets)
    if timeline:
        timeline_items = [f"- {e['date']} — {e['event']} ([fonte]({e.get('url','#')}))" for e in timeline]
        timeline_md = "\n".join(timeline_items)
    else:
        timeline_md = "- Nessun evento estratto -"

    # Chart: mix tipologie fonti
    mix_img = charts.get("mix")
    mix_md = f"![Mix tipologie di fonte]({mix_img})" if mix_img else "-"

    # PRECALCOLA elenco conteggi fonti (evita backslash nelle espressioni f-string)
    if source_counts:
        source_count_lines = [f"- {k}: {v}" for k, v in source_counts.items()]
        source_counts_md = "\n".join(source_count_lines)
    else:
        source_counts_md = "-"

    md = f"""# OSINT Report — {query}
**Data:** {{today}} (Europe/Rome) • **Scope:** Analisi basata su fonti istituzionali/ONG/Media e verifica incrociata.

## Executive Summary
{cross_summary or "- Sintesi non disponibile -"}

---

## Key Findings — Stato della prova
{ev_table}

---

## Timeline (estratta)
{timeline_md}

---

## Attori ed Entità
- **Persone:** {", ".join(persons) or "-"}
- **Organizzazioni:** {", ".join(orgs) or "-"}
- **Luoghi:** {", ".join(locs) or "-"}
- **Indicatori menzionati:** {", ".join(indicators) or "-"}

---

## Tipologie di fonte (conteggio)
{mix_md}

{source_counts_md}

---

## Fonti
{ref_table}

---

## Metodologia & Provenance
- Ricerca: SearXNG (profilo 'light'), pagine=1, categorie=news/web; + ReliefWeb API.
- Dedup: canonical URL + SimHash (Hamming ≤ {{hamming}}).
- Ranking: freschezza (t½={{half_life}} gg), autorità dominio, completezza, coerenza.
- LLM: NER/sintesi/fact-check; temperature={{temp}}.
- Snapshot/hash: ove possibile.
- Etica: niente PII non necessarie; rispetto robots/ToS.

"""
    # Sostituzioni runtime basilari
    from datetime import datetime
    md = md.replace("{today}", datetime.now().strftime("%Y-%m-%d"))
    from config import FRESHNESS_HALF_LIFE_DAYS, LLM_TEMPERATURE
    md = md.replace("{half_life}", str(FRESHNESS_HALF_LIFE_DAYS))
    md = md.replace("{hamming}", "6")
    md = md.replace("{temp}", str(LLM_TEMPERATURE))
    return md



# ============================================================
# Colla di pipeline
# ============================================================

def run_pipeline(query: str, topk: int = 8) -> Tuple[str, Dict[str, Any]]:
    """
    Esegue l'intera pipeline e restituisce:
      - md: Markdown finale
      - extra: diagnostica/artefatti utili
    """
    # Planning
    plan = planner(query)

    # Search
    seeds = search(plan)

    # Crawl & extract
    docs = crawl(seeds)

    # Dedup & ranking
    ranked = dedup_rank(docs)

    # NER
    ents = ner_top(ranked, topk=topk)

    # Sintesi con citazioni [n]
    summ, refs = summarize_with_citations(ranked, topk=topk)

    # Fact-check dei claim
    checks = factcheck(summ.get("claims", []), refs)

    # === Stato della prova per i claim (con indipendenza fonti) ===
    enriched_checks = []
    for c in summ.get("claims", []):
        sources = c.get("sources", [])
        state, indep = label_support(sources, refs)
        enriched_checks.append({
            "claim": c.get("text", ""),
            "support_state": state,
            "independence": indep,
            "sources": sources
        })

    # === Classificazione tipologie fonte ===
    counts, source_details = classify_sources_counts(refs)

    # === Timeline estratta (heuristica) ===
    timeline = extract_events(ranked, max_events=12)

    # === Grafico: mix tipologie di fonte ===
    mix_png = chart_source_mix(counts)

    # (Opzionale) KPI numerici se disponibili:
    # es. serie = [("2025-10-15", 6.9), ("2025-10-30", 7.1)]
    # kpi_png = chart_indicator_timeseries(serie, title="IDP (milioni)")

    # Compose MD (v2)
    md = compose_report_v2(
        query=query,
        evidence_rows=enriched_checks,
        ents=ents,
        refs=refs,
        cross_summary=summ.get("cross_summary", ""),
        timeline=timeline,
        source_counts=counts,
        source_details=source_details,
        charts={"mix": mix_png},
    )

    extra = {
        "ranked": ranked,
        "entities": ents,
        "refs": refs,
        "checks_raw": checks,
        "plan": plan,
        "evidence": enriched_checks,
        "timeline": timeline,
        "source_counts": counts,
        "source_details": source_details,
        "charts": {"mix": mix_png},
    }
    return md, extra
