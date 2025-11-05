# timeline_extractor.py
import re
from dateutil import parser as dateparser

DATE_PAT = re.compile(r'\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|(?:\d{1,2}\s+\w+\s+20\d{2}))\b', re.I)

def _clean_sentence(s: str) -> str:
    s = (s or "").strip()
    # collassa whitespace e a-capo ripetuti
    s = re.sub(r'\s+', ' ', s)
    return s

def extract_events(docs, max_events=12):
    """Trova date + frase contigua, elimina duplicati (date+frase, o date+url)."""
    seen = set()
    events = []
    for d in docs:
        txt = (d.get("text") or "")[:2000]
        url = d.get("url")
        for m in DATE_PAT.finditer(txt):
            date_raw = m.group(0)
            try:
                iso = dateparser.parse(date_raw, dayfirst=True, fuzzy=True).date().isoformat()
            except Exception:
                continue
            # estrai frase circostante
            start = txt.rfind('.', 0, m.start()) + 1
            end = txt.find('.', m.end())
            if end == -1:
                end = min(len(txt), m.end() + 180)
            sent = _clean_sentence(txt[start:end])
            # scarta frasi troppo corte / solo data
            if len(sent) < 25 or re.fullmatch(r'\d{4}-\d{2}-\d{2}', sent):
                continue
            key = (iso, sent)
            if key in seen:
                continue
            seen.add(key)
            events.append({
                "date": iso,
                "event": sent[:240],
                "url": url
            })
            if len(events) >= max_events:
                break
        if len(events) >= max_events:
            break
    # ordina e ritorna
    events.sort(key=lambda x: x["date"])
    return events
