# timeline.py
from __future__ import annotations
import re
from typing import List, Dict, Any, Optional, Tuple
from utils_date import to_iso_date

IT_MONTHS = "gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre"
EN_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"

DATE_RX = re.compile(
    rf"\b(\d{{4}}[-/]\d{{1,2}}[-/]\d{{1,2}}|\d{{1,2}}\s+(?:{IT_MONTHS}|{EN_MONTHS})\s+\d{{4}})\b",
    re.IGNORECASE
)

def _sentences_near(text: str, start: int, end: int, span: int = 180) -> str:
    left = text.rfind(".", 0, start)
    left = 0 if left == -1 else left + 1
    right = text.find(".", end)
    if right == -1:
        right = min(len(text), end + span)
    snippet = " ".join(text[left:right].split())
    return snippet.strip()

def _in_window(iso: Optional[str], from_iso: Optional[str], to_iso: Optional[str]) -> bool:
    if not iso:
        return False
    if from_iso and iso < from_iso:
        return False
    if to_iso and iso > to_iso:
        return False
    return True

def _is_noisy_live(d: Dict[str, Any], snippet: str) -> bool:
    if d.get("is_live"):
        s = snippet.lower()
        # tante ore/aggiornamenti => scarta
        if s.count(":") >= 2 or "live" in s or "diretta" in s:
            return True
    return False

def extract_timeline(
    docs: List[Dict[str, Any]],
    refs_map: Dict[int, str],
    from_iso: Optional[str],
    to_iso: Optional[str],
    max_events: int = 12
) -> List[Dict[str, Any]]:
    """
    Eventi: [{"date":"YYYY-MM-DD","text":"...","sources":[n,...]}]
    Regole:
      - headline per documento: usa detected_date/published se nel periodo
      - poi date nel testo (regex IT/EN) con snippet
      - filtra live rumorosi, dedup per (date,text_lower), max 2 eventi/giorno
    """
    events: List[Tuple[str, str, List[int]]] = []
    seen = set()

    # mappa URL -> ID [n]
    url2id = {u: i for i, u in refs_map.items()}

    # 1) Evento headline (meta)
    for d in docs:
        iso = to_iso_date(d.get("detected_date") or d.get("published"))
        if not _in_window(iso, from_iso, to_iso):
            continue
        title = (d.get("title") or "").strip()
        if not title:
            continue
        key = (iso, title.lower())
        if key in seen:
            continue
        seen.add(key)
        sid = url2id.get(d.get("url"))
        events.append((iso, title[:200], [sid] if sid else []))

    # 2) Date dal corpo
    for d in docs[:30]:
        t = (d.get("text") or "")[:6000]
        for m in DATE_RX.finditer(t):
            iso = to_iso_date(m.group(0))
            if not _in_window(iso, from_iso, to_iso):
                continue
            snippet = _sentences_near(t, m.start(), m.end())
            if len(snippet) < 40:
                continue
            if _is_noisy_live(d, snippet):
                continue
            key = (iso, snippet.lower())
            if key in seen:
                continue
            seen.add(key)
            sid = url2id.get(d.get("url"))
            events.append((iso, snippet[:220], [sid] if sid else []))
            if len(events) >= max_events * 2:
                break

    # 3) Max 2 eventi per giorno
    from collections import defaultdict
    by_day: Dict[str, List[Tuple[str, str, List[int]]]] = defaultdict(list)
    for e in events:
        by_day[e[0]].append(e)

    out: List[Dict[str, Any]] = []
    for day in sorted(by_day.keys()):
        for _, text, srcs in by_day[day][:2]:
            out.append({"date": day, "text": text, "sources": srcs})

    if len(out) > max_events:
        out = out[:max_events]
    return out
