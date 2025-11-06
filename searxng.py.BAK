import requests, time
from urllib.parse import urlencode
from config import (
    SEARXNG_URL, SEARXNG_DEFAULT_CATEGORIES, SEARXNG_ENGINES, SEARXNG_TIME_RANGE,
    SEARXNG_LANGUAGE, SEARXNG_PAGE_SIZE, SEARXNG_PAGES
)
from provenance import log_event

def searxng_search(query: str, time_range=SEARXNG_TIME_RANGE, language=SEARXNG_LANGUAGE,
                   engines=SEARXNG_ENGINES, categories=SEARXNG_DEFAULT_CATEGORIES,
                   page_size=SEARXNG_PAGE_SIZE, pages=SEARXNG_PAGES):
    results = []
    for p in range(1, pages + 1):
        params = {
            "format": "json", "q": query, "time_range": time_range,
            "language": language, "categories": categories,
            "engines": engines, "pageno": p
        }
        log_event("searxng_query", {"params": params})
        r = requests.get(SEARXNG_URL, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        res = data.get("results", [])[:page_size]
        for x in res:
            results.append({
                "url": x.get("url"),
                "title": x.get("title"),
                "snippet": x.get("content") or x.get("snippet"),
                "published": x.get("publishedDate") or x.get("published") or x.get("published_parsed"),
                "engine": x.get("engine"),
                "source": x.get("source")
            })
        time.sleep(0.7)  # rate-limit gentile
    log_event("searxng_results", {"count": len(results)})
    return results
