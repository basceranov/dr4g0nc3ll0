# quality.py
import tldextract

LOW_QUALITY_KEYWORDS = ["opinion", "blog", "press-release-index", "archive"]
LOW_QUALITY_DOMAINS = {
    "ckh.enc.edu", "medium.com", "substack.com",
}
INDEX_URL_HINTS = {
    "/press-releases/2025-0", "/press-releases/2024-0", "/press-releases/2023-0",
    "/newsroom/press-releases?page=", "/press?page=", "/archive"
}

PREFER_DETAIL_PATTERNS = {
    "/press-releases/", "/fact-sheet", "/readout", "/statement",
}

def domain(url: str) -> str:
    e = tldextract.extract(url or "")
    return e.registered_domain or ""

def is_low_quality(url: str) -> bool:
    d = domain(url)
    if d in LOW_QUALITY_DOMAINS:
        return True
    u = (url or "").lower()
    if any(k in u for k in LOW_QUALITY_KEYWORDS):
        return True
    return False

def is_index_page(url: str) -> bool:
    u = (url or "").lower()
    return any(h in u for h in INDEX_URL_HINTS)

def looks_like_detail(url: str) -> bool:
    u = (url or "").lower()
    return any(p in u for p in PREFER_DETAIL_PATTERNS)
