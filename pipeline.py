# pipeline.py (solo parti cambiate/rilevanti)
import json, time
from datetime import date, timedelta
from urllib.parse import urlparse
from collections import defaultdict

from searxng import searxng_search
from fetch import fetch_and_extract
from dedup import prepare_for_dedup, cluster_near_duplicates
from rank import score_item
from llm import chat
from prompts import PLANNER_PROMPT, NER_PROMPT, SUMMARIZE_PROMPT, FACTCHECK_PROMPT, COMPOSE_PROMPT
from provenance import log_event
from timeline import extract_timeline

# ---------------------------
# Planner (unchanged)
# ---------------------------
def planner(query: str):
    msg = [{"role":"system","content":PLANNER_PROMPT},{"role":"user","content":query}]
    out = chat(msg, max_tokens=900)
    try:
        plan = json.loads(out)
    except Exception:
        plan = {
            "subgoals": ["Mappare attori","Raccogliere timeline","Identificare indicatori"],
            "queries": [query, f'"{query}" site:reuters.com', f'{query} filetype:pdf'],
            "criteria": {"freshness_days": 30, "need_institutional": True, "need_diversity": True}
        }
    log_event("planner_plan", plan)
    return plan

# ---------------------------
# Ricerca / Crawl (unchanged)
# ---------------------------
def search(plan):
    agg = []
    for q in plan["queries"]:
        agg += searxng_search(q)
    # dedup url base
    seen = set(); uniq = []
    for r in agg:
        u = r.get("url")
        if u and u not in seen:
            uniq.append(r); seen.add(u)
    log_event("search_uniq", {"count": len(uniq)})
    return uniq[:80]

def crawl(seeds):
    docs = []
    for s in seeds[:40]:
        try:
            ext = fetch_and_extract(s["url"])
            # merge seed (published normalizzato da searxng) + estratto
            docs.append({**s, **ext})
        except Exception as e:
            log_event("fetch_err", {"url": s.get("url"), "err": str(e)})
            continue
    log_event("crawl_done", {"docs": len(docs)})
    return docs

# ---------------------------
# Dedup + Ranking (migliorato solo sort)
# ---------------------------
def dedup_rank(docs):
    now_ts = time.time()
    prepare_for_dedup(docs)
    clusters = cluster_near_duplicates(docs)
    picked = []
    for group in clusters:
        group = sorted(
            group,
            key=lambda d: (len(d.get("text","")), _safe_epoch(d)),
            reverse=True
        )
        picked.append(group[0])
    for d in picked:
        d["score"] = score_item(d, now_ts)
    ranked = sorted(picked, key=lambda d: d["score"], reverse=True)
    log_event("rank_done", {"kept": len(ranked)})
    return ranked

def _safe_epoch(d):
    from utils_date import to_epoch_seconds
    return to_epoch_seconds(d.get("detected_date") or d.get("published"))

# ---------------------------
# NER con budget & validazione
# ---------------------------
def ner_top(docs, topk=12, char_budget=12000):
    # ... come versione hardening (budget + validazione + log) ...
    buf, n = [], 0
    for d in docs[:topk]:
        title = (d.get("title") or "")
        text = (d.get("text") or "")[:2000]
        chunk = f"{title}\n{text}\n\n"
        if n + len(chunk) > char_budget:
            break
        buf.append(chunk); n += len(chunk)
    msg = [
        {"role":"system","content": NER_PROMPT},
        {"role":"user","content": "".join(buf)}
    ]
    out = chat(msg, max_tokens=900)
    try:
        raw = json.loads(out)
        ents = [e for e in raw if isinstance(e, dict) and e.get("entity") and e.get("type")]
        seen=set(); clean=[]
        for e in ents:
            ent = e["entity"].strip()
            typ = e["type"].strip().upper()
            if not ent: continue
            k=(ent.lower(), typ)
            if k in seen: continue
            seen.add(k); clean.append({"entity": ent, "type": typ, "freq": int(e.get("freq",1))})
        log_event("ner_ok", {"entities": len(clean)})
        return clean
    except Exception:
        log_event("ner_fail", {})
        return []

def analyze_sentiment_emotions(docs, topk=12, char_budget=12000):
    # prepara testo concatenato controllando la lunghezza
    buf, n = [], 0
    for d in docs[:topk]:
        title = (d.get("title") or "")
        text = (d.get("text") or "")[:2000]
        chunk = f"{title}\n{text}\n\n"
        if n + len(chunk) > char_budget:
            break
        buf.append(chunk); n += len(chunk)

    from prompts import SENTIMENT_EMO_PROMPT
    msg = [
        {"role": "system", "content": SENTIMENT_EMO_PROMPT},
        {"role": "user", "content": "".join(buf)}
    ]
    out = chat(msg, max_tokens=600)
    try:
        data = json.loads(out)
        # validazione minimale
        overall = (data.get("overall_sentiment") or "neutral").lower()
        if overall not in {"positive","neutral","negative"}:
            overall = "neutral"
        conf = float(data.get("confidence", 0.5))
        em = data.get("emotions") or {}
        def _clip01(x):
            try:
                return max(0.0, min(1.0, float(x)))
            except Exception:
                return 0.0
        emotions = {
            "anger":   _clip01(em.get("anger", 0.0)),
            "fear":    _clip01(em.get("fear", 0.0)),
            "joy":     _clip01(em.get("joy", 0.0)),
            "sadness": _clip01(em.get("sadness", 0.0)),
            "surprise":_clip01(em.get("surprise", 0.0)),
        }
        out_obj = {
            "overall_sentiment": overall,
            "confidence": max(0.0, min(1.0, conf)),
            "emotions": emotions,
            "notes": (data.get("notes") or "")[:240]
        }
        log_event("sentiment_ok", {"overall": overall, "conf": out_obj["confidence"]})
        return out_obj
    except Exception:
        log_event("sentiment_fail", {})
        return {
            "overall_sentiment": "neutral",
            "confidence": 0.5,
            "emotions": {"anger":0.0,"fear":0.0,"joy":0.0,"sadness":0.0,"surprise":0.0},
            "notes":""
        }

def summarize_with_citations(ranked, topk=8):
    pack = []
    refs = {}
    for i, d in enumerate(ranked[:topk], start=1):
        refs[i] = d["url"]
        pack.append({"id": i, "title": d.get("title"), "excerpt": (d.get("text","")[:3000])})
    msg = [
        {"role":"system","content":SUMMARIZE_PROMPT},
        {"role":"user","content":json.dumps({"sources": pack}, ensure_ascii=False)}
    ]
    out = chat(msg, max_tokens=1800)
    try:
        data = json.loads(out)
    except Exception:
        data = {"per_source_summary": {}, "cross_summary": "", "claims": []}
    log_event("summ_ok", {"claims": len(data.get("claims", []))})
    return data, refs

def factcheck(claims, sources_map):
    # ... identico alla versione hardening ...
    payload = {"claims": claims, "sources": sources_map}
    msg = [{"role":"system","content":FACTCHECK_PROMPT},
           {"role":"user","content":json.dumps(payload, ensure_ascii=False)}]
    out = chat(msg, max_tokens=1800)
    try:
        checks = json.loads(out)
    except Exception:
        checks = [{"claim": c.get("text",""), "support":"unknown", "confidence":0.4, "notes":"insufficient evidence"} for c in claims]
    log_event("factcheck_ok", {"checks": len(checks)})
    return checks

def _domains_of(ids, refs):
    doms=set()
    for i in ids:
        url = refs.get(i)
        if not url: continue
        try:
            doms.add(urlparse(url).lower().netloc)
        except Exception:
            continue
    return doms

def enrich_and_filter_claims(original_claims, checks, refs, min_support_domains=2, min_conf=0.55):
    kept_claims, kept_checks = [], []
    for c, chk in zip(original_claims, checks):
        src_ids = c.get("sources", [])
        doms = _domains_of(src_ids, refs)
        support_ok = chk.get("support") in {"supported","partial"} and float(chk.get("confidence",0)) >= min_conf
        if len(doms) >= min_support_domains and support_ok:
            c["cross_agree"] = min(1.0, len(doms)/4.0)
            kept_claims.append(c)
            kept_checks.append(chk)
    log_event("claims_filtered", {"in": len(original_claims), "kept": len(kept_claims)})
    return kept_claims, kept_checks

def compose_report(query, checks, ents, refs, per_source_summary, cross_summary, timeline, today_iso, from_iso, senti):
    persons = sorted({e["entity"] for e in ents if e.get("type")=="PERSON"})[:12]
    orgs    = sorted({e["entity"] for e in ents if e.get("type")=="ORG"})[:12]
    locs    = sorted({e["entity"] for e in ents if e.get("type")=="LOC"})[:12]
    indicators = sorted({e["entity"] for e in ents if e.get("type")=="INDICATOR"})[:12]
    key_findings = [{"claim": x.get("claim") or x.get("text",""), "confidence": x.get("confidence",0.5)} for x in checks]

    payload = {
        "query": query,
        "key_findings": key_findings,
        "entities": {"persons": persons, "orgs": orgs, "locs": locs, "indicators": indicators},
        "refs": refs,
        "per_source_summary": per_source_summary or {},
        "timeline": timeline or [],
        "cross_summary": cross_summary or "",
        "today_iso": today_iso,
        "from_iso": from_iso,
        # >>> NUOVO BLOCCO
        "sentiment": {
            "overall": senti.get("overall_sentiment","neutral"),
            "confidence": senti.get("confidence",0.5),
            "emotions": senti.get("emotions", {}),
            "notes": senti.get("notes","")
        }
    }
    msg = [{"role":"system","content":COMPOSE_PROMPT},
           {"role":"user","content":json.dumps(payload, ensure_ascii=False)}]
    md = chat(msg, max_tokens=2400)
    return md

def run_pipeline(query: str, topk: int = 8):
    plan = planner(query)
    seeds = search(plan)
    docs = crawl(seeds)

    freshness_days = int(plan.get("criteria", {}).get("freshness_days", 30) or 30)
    today_iso = date.today().isoformat()
    from_iso = (date.today() - timedelta(days=freshness_days)).isoformat()

    def _date_of(d):
        return (d.get("detected_date") or d.get("published") or "")[:10]

    before_filter = len(docs)
    docs = [d for d in docs if not _date_of(d) or _date_of(d) >= from_iso]
    log_event("freshness_filter", {"from": from_iso, "before": before_filter, "after": len(docs)})

    ranked = dedup_rank(docs)
    ents = ner_top(ranked, topk=topk)
    summ, refs = summarize_with_citations(ranked, topk=topk)

    original_claims = summ.get("claims", [])
    checks = factcheck(original_claims, refs)
    kept_claims, kept_checks = enrich_and_filter_claims(original_claims, checks, refs)

    # Timeline robusta (già presente se hai integrato la timeline.py)
    timeline = extract_timeline(ranked, refs, from_iso, today_iso, max_events=12)

    # >>> NUOVO: sentiment & emozioni
    senti = analyze_sentiment_emotions(ranked, topk=topk)

    md = compose_report(
        query,
        kept_checks,
        ents,
        refs,
        summ.get("per_source_summary", {}),
        summ.get("cross_summary", ""),
        timeline,
        today_iso,
        from_iso,
        senti  # <-- nuovo argomento
    )

    # extra snellito e serializzabile
    extra_ranked = []
    for d in ranked[:50]:
        extra_ranked.append({
            "url": d.get("url"),
            "title": d.get("title"),
            "domain": d.get("domain"),
            "detected_date": d.get("detected_date"),
            "published": d.get("published"),
            "score": d.get("score"),
            "len_text": len(d.get("text","")),
            "is_live": bool(d.get("is_live")),
        })

    return md, {
        "ranked": extra_ranked,
        "entities": ents,
        "refs": refs,
        "checks": kept_checks,
        "plan": plan,
        "freshness_from": from_iso,
        "timeline": timeline
    }
