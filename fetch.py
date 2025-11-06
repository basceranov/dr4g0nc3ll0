# fetch.py
import requests, hashlib, re, tldextract
from bs4 import BeautifulSoup
import trafilatura
from langdetect import detect
from dateutil import parser as dateparser
from config import HTTP_TIMEOUT, USER_AGENT
from provenance import log_event

LIVE_PATTERNS = ("live", "diretta", "liveblog", "live-blog", "in-diretta")


HEADERS = {"User-Agent": USER_AGENT}

def _looks_live(url: str, title: str) -> bool:
    u = (url or "").lower()
    t = (title or "").lower()
    return any(p in u for p in LIVE_PATTERNS) or any(p in t for p in LIVE_PATTERNS)

def fetch_and_extract(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
    r.raise_for_status()

    ctype = (r.headers.get("Content-Type") or "").lower()

    # PDF handling (come nella tua versione migliorata)
    if "application/pdf" in ctype or url.lower().endswith(".pdf"):
        # ... come già fornito in precedenza ...
        out = {
            "url": url,
            "title": title[:200],
            "text": text,
            "lang": lang,
            "domain": domain,
            "hash": h,
            "detected_date": None,
            "mime": "application/pdf",
            "is_live": False,
        }
        log_event("fetch_ok_pdf", {...})
        return out

    html = r.text
    text = _clean_html_trafilatura(html)
    title = None
    if not text or len(text) < 400:
        title_rd, text2 = _clean_html_readability(html)
        if text2 and len(text2) > len(text or ""):
            text = text2
            title = title_rd or title

    if not title:
        m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        title = (m.group(1).strip() if m else url)[:200]

    try:
        lang = detect((text or "")[:1000]) if text else "unknown"
    except Exception:
        lang = "unknown"

    domain = tldextract.extract(url).registered_domain
    h = hashlib.md5((text or "").encode("utf-8", errors="ignore")).hexdigest()
    dt = _extract_meta_datetime(html)

    out = {
        "url": url,
        "title": title,
        "text": text or "",
        "lang": lang,
        "domain": domain,
        "hash": h,
        "detected_date": dt,
        "mime": "text/html",
        "is_live": _looks_live(url, title),
    }
    log_event("fetch_ok", {"url": url, "domain": domain, "hash": h, "len": len(text or ""), "is_live": out["is_live"]})
    return out

def _clean_html_readability(html: str):
    """Prova Readability solo se disponibile; altrimenti (None, None)."""
    try:
        from readability import Document  # lazy import
        doc = Document(html)
        cleaned_html = doc.summary()
        title = doc.short_title()
        soup = BeautifulSoup(cleaned_html, "html.parser")
        text = soup.get_text("\n", strip=True)
        return title, text
    except Exception:
        return None, None

def _clean_html_trafilatura(html: str) -> str:
    return trafilatura.extract(html, include_comments=False, include_tables=False) or ""

def _extract_meta_datetime(html: str) -> str | None:
    """Cerca meta date (OG, JSON-LD semplice, time tag) e cade su pattern ISO-like."""
    try:
        soup = BeautifulSoup(html, "html.parser")

        # Og: article:published_time
        tag = soup.find("meta", attrs={"property": "article:published_time"})
        if tag and tag.get("content"):
            return dateparser.parse(tag["content"]).isoformat()

        # schema.org JSON-LD (molto semplificato)
        for s in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
            try:
                import json
                data = json.loads(s.string or "")
                # può essere dict o list
                candidates = data if isinstance(data, list) else [data]
                for d in candidates:
                    v = d.get("datePublished") or d.get("dateCreated") or d.get("uploadDate")
                    if v:
                        return dateparser.parse(str(v)).isoformat()
            except Exception:
                continue

        # meta name="date" / "published_time"
        for name in ("date", "pubdate", "publishdate", "published_time", "datePublished"):
            tag = soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return dateparser.parse(tag["content"]).isoformat()

        # <time datetime="...">
        ttag = soup.find("time", attrs={"datetime": True})
        if ttag:
            return dateparser.parse(ttag["datetime"]).isoformat()

        # fallback regex ISO-ish nel markup
        m = re.search(r'(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?)', html)
        if m:
            return dateparser.parse(m.group(1)).isoformat()
    except Exception:
        pass
    return None

def _extract_pdf_text(resp: requests.Response) -> str:
    """
    Prova ad estrarre testo da PDF se disponibili librerie locali.
    Priorità: PyMuPDF (fitz) -> pdfminer.six -> fallback vuoto.
    """
    try:
        # PyMuPDF
        import fitz  # type: ignore
        with fitz.open(stream=resp.content, filetype="pdf") as doc:
            return "\n".join(page.get_text() or "" for page in doc)
    except Exception:
        pass
    try:
        # pdfminer.six (estrazione semplice)
        from io import BytesIO
        from pdfminer.high_level import extract_text
        return extract_text(BytesIO(resp.content)) or ""
    except Exception:
        return ""

def fetch_and_extract(url: str) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
    r.raise_for_status()

    ctype = (r.headers.get("Content-Type") or "").lower()

    # PDF handling
    if "application/pdf" in ctype or url.lower().endswith(".pdf"):
        text = _extract_pdf_text(r) or ""
        title = url
        lang = "unknown"
        domain = tldextract.extract(url).registered_domain
        h = hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()
        out = {
            "url": url,
            "title": title[:200],
            "text": text,
            "lang": lang,
            "domain": domain,
            "hash": h,
            "detected_date": None,  # impossibile senza metadati PDF; potresti leggerli se serve
            "mime": "application/pdf",
        }
        log_event("fetch_ok_pdf", {"url": url, "domain": domain, "hash": h, "len": len(text)})
        return out

    # HTML path
    html = r.text

    # 1) Trafilatura
    text = _clean_html_trafilatura(html)
    title = None

    # 2) Readability se poco testo
    if not text or len(text) < 400:
        title_rd, text2 = _clean_html_readability(html)
        if text2 and len(text2) > len(text or ""):
            text = text2
            title = title_rd or title

    # 3) Titolo fallback
    if not title:
        m = re.search(r"<title>(.*?)</title>", html, re.I | re.S)
        title = (m.group(1).strip() if m else url)[:200]

    # 4) Lingua
    try:
        lang = detect((text or "")[:1000]) if text else "unknown"
    except Exception:
        lang = "unknown"

    # 5) Dominio, hash
    domain = tldextract.extract(url).registered_domain
    h = hashlib.md5((text or "").encode("utf-8", errors="ignore")).hexdigest()

    # 6) Data (meta & fallback)
    dt = _extract_meta_datetime(html)

    out = {
        "url": url,
        "title": title,
        "text": text or "",
        "lang": lang,
        "domain": domain,
        "hash": h,
        "detected_date": dt,   # ISO o None
        "mime": "text/html",
    }
    log_event("fetch_ok", {"url": url, "domain": domain, "hash": h, "len": len(text or "")})
    return out
