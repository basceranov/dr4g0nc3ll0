# searxng.py
import requests, time
from urllib.parse import urljoin
from config import (
    SEARXNG_URL, SEARXNG_DEFAULT_CATEGORIES, SEARXNG_ENGINES, SEARXNG_TIME_RANGE,
    SEARXNG_LANGUAGE, SEARXNG_PAGE_SIZE, SEARXNG_PAGES
)
from provenance import log_event
from utils_date import to_iso_date

def _endpoint(base: str) -> str:
    # consente sia .../search che base host con reverse
    if base.rstrip("/").endswith("/search"):
        return base
    return urljoin(base if base.endswith("/") else base + "/", "search")

def searxng_search(
    query: str,
    time_range=SEARXNG_TIME_RANGE,
    language=SEARXNG_LANGUAGE,
    engines=SEARXNG_ENGINES,
    categories=SEARXNG_DEFAULT_CATEGORIES,
    page_size=SEARXNG_PAGE_SIZE,
    pages=SEARXNG_PAGES
):
    results = []
    url = _endpoint(SEARXNG_URL)
    for p in range(1, pages + 1):
        params = {
            "format": "json",
            "q": query,
            "time_range": time_range,
            "language": language,
            "categories": categories,
            "engines": engines,
            "pageno": p,
        }
        log_event("searxng_query", {"params": params})
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json() if r.content else {}
        res = (data.get("results") or [])[:page_size]
        for x in res:
            pub = to_iso_date(
                x.get("publishedDate") or x.get("published") or x.get("published_parsed")
            )
            results.append({
                "url": x.get("url"),
                "title": x.get("title"),
                "snippet": x.get("content") or x.get("snippet"),
                "published": pub,                  # <-- normalizzata
                "engine": x.get("engine"),
                "source": x.get("source"),
            })
        time.sleep(0.7)  # rate-limit gentile
    log_event("searxng_results", {"count": len(results)})
    return results
