import time
from dateutil import parser as dateparser
from config import DOMAIN_SCORES, FRESHNESS_HALF_LIFE_DAYS
from quality import is_low_quality

def _epoch(dtiso):
    try:
        return dateparser.parse(dtiso).timestamp()
    except Exception:
        return None

def _freshness(now_ts, dtiso):
    if not dtiso: return 0.5
    ts = _epoch(dtiso)
    if not ts: return 0.5
    days = max(0.0, (now_ts - ts) / 86400.0)
    # decadimento esponenziale
    half = float(FRESHNESS_HALF_LIFE_DAYS)
    return 0.5 ** (days/half)

def score_item(item, now_ts):
    domain = item.get("domain", "")
    authority = DOMAIN_SCORES.get(domain, 0.30)

    # completezza: lunghezza testo normalizzata (cap a 1.0)
    completeness = min(len(item.get("text", "")) / 8000.0, 1.0)

    # freschezza time-aware (già definita altrove)
    freshness = _freshness(now_ts, item.get("detected_date"))

    # coerenza cross-fonte (se assente, default 0.5)
    coherence = item.get("cross_agree", 0.50)

    # punteggio base pesato
    base = 0.35 * freshness + 0.35 * authority + 0.20 * completeness + 0.10 * coherence

    # bonus/malus qualità sorgente
    bonus = source_quality_bonus(item.get("url", ""))

    # score finale clampato [0,1]
    score = base + bonus
    score = max(0.0, min(1.0, score))

    return round(score, 4)

def source_quality_bonus(url: str) -> float:
    """Bonus/malus semplice basato su qualità e 'detail-ness' dell'URL."""
    if not url:
        return 0.0
    u = url.lower()
    # malus per domini/opinion/aggregatori di bassa qualità
    if is_low_quality(u):
        return -0.40
    # piccolo bonus per pagine 'di dettaglio' e siti istituzionali noti
    if any(k in u for k in ["/press-releases/", "/fact-sheet", "/readout", "/statement",
                            "whitehouse.gov", "ustr.gov", "un.org", "oecd.org"]):
        return 0.15
    return 0.0