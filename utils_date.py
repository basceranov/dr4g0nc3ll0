# utils_date.py
from __future__ import annotations
from typing import Optional, Any
from dateutil import parser as dateparser

# Nota: userai dateparser (dateparser==1.x) con SETTINGS robusti.
# Forziamo lingue IT/EN e ordine DMY per evitare 04/11 -> April 11.
try:
    import dateparser as dp  # libreria "dateparser" (diversa da dateutil)
except Exception:
    dp = None  # fallback a dateutil se non disponibile

DEF_SETTINGS = {
    "PREFER_DAY_OF_MONTH": "first",
    "PREFER_DATES_FROM": "past",
    "DATE_ORDER": "DMY",
    "RELATIVE_BASE": None,
    "RETURN_AS_TIMEZONE_AWARE": False,
}

def to_iso_date(value: Any) -> Optional[str]:
    """Converte in YYYY-MM-DD (no tempo). Supporta IT/EN, forza DMY.
    Ritorna None se non parsabile.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None

    # 1) Prova con `dateparser` (se installato) con lingua forzata
    if dp is not None:
        try:
            dt = dp.parse(s, languages=["it", "en"], settings=DEF_SETTINGS)
            if dt:
                return dt.date().isoformat()
        except Exception:
            pass

    # 2) Fallback a dateutil (meno affidabile per “novembre”, ma meglio di niente)
    try:
        dt2 = dateparser.parse(s, dayfirst=True, fuzzy=True)
        return dt2.date().isoformat()
    except Exception:
        return None


def to_epoch_seconds(iso_like: Optional[str]) -> float:
    """Converte ISO/qualsiasi data parsabile in epoch seconds (0.0 se non parsabile)."""
    if not iso_like:
        return 0.0
    try:
        # Tenta prima con dateparser (coerente con to_iso_date)
        if dp is not None:
            dt = dp.parse(str(iso_like), languages=["it", "en"], settings=DEF_SETTINGS)
            if dt:
                return float(dt.timestamp())
        # fallback dateutil
        return dateparser.parse(str(iso_like), dayfirst=True, fuzzy=True).timestamp()
    except Exception:
        return 0.0
