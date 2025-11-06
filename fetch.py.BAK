# fetch.py (patch robusta)
import requests, hashlib, time, re, tldextract
from bs4 import BeautifulSoup
import trafilatura
from langdetect import detect
from dateutil import parser as dateparser
from config import HTTP_TIMEOUT, USER_AGENT
from provenance import log_event

HEADERS = {"User-Agent": USER_AGENT}

def _clean_html_readability(html):
    """Prova Readability solo se disponibile; altrimenti None."""
    try:
        from readability import Document  # import pigro: evita ImportError all’avvio
        doc = Document(html)
        cleaned_html = doc.summary()
        title = doc.short_title()
        soup = BeautifulSoup(cleaned_html, "html.parser")
        text = soup.get_text("\n", strip=True)
        return title, text
    except Exception:
        return None, None

def _clean_html_trafilatura(html):
    return trafilatura.extract(html, include_comments=False, include_tables=False) or ""

def fetch_and_extract(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    html = r.text

    # 1) Trafilatura prima scelta
    text = _clean_html_trafilatura(html)
    title = None

    # 2) Se testo insufficiente, prova Readability (se presente)
    if not text or len(text) < 400:
        title, text2 = _clean_html_readability(html)
        if text2 and len(text2) > len(text):
            text = text2

    # 3) Titolo di riserva
    if not title:
        m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        title = (m.group(1).strip() if m else url)[:200]

    # 4) Metadati
    try:
        lang = detect(text[:1000]) if text else "unknown"
    except Exception:
        lang = "unknown"

    domain = tldextract.extract(url).registered_domain
    h = hashlib.md5((text or "").encode("utf-8", errors="ignore")).hexdigest()

    # 5) Best-effort data
    dt = None
    try:
        m = re.search(r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?)', html)
        if m:
            dt = dateparser.parse(m.group(1)).isoformat()
    except Exception:
        dt = None

    out = {"url": url, "title": title, "text": text or "", "lang": lang, "domain": domain, "hash": h, "detected_date": dt}
    log_event("fetch_ok", {"url": url, "domain": domain, "hash": h, "len": len(text or "")})
    return out
