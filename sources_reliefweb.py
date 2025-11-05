# sources_reliefweb.py
import requests
from datetime import datetime, timedelta
from provenance import log_event
from config import RELIEFWEB_API, RELIEFWEB_LIMIT, RELIEFWEB_QUERY, HTTP_TIMEOUT, USER_AGENT

HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

def fetch_reliefweb_reports(query=RELIEFWEB_QUERY, days=30, limit=RELIEFWEB_LIMIT):
    # ReliefWeb API docs: https://apidoc.reliefweb.int/
    since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT00:00:00Z")
    payload = {
        "appname": "osint-multiagent",
        "query": {
            "value": query,
            "operator": "AND"
        },
        "filter": {
            "conditions": [
                {"field": "date.created", "value": since, "operator": ">="}
            ]
        },
        "fields": {"include": ["title", "url", "date", "source", "country", "disaster", "body"]},
        "limit": limit,
        "sort": ["-date.created"]
    }
    r = requests.post(RELIEFWEB_API, json=payload, headers=HEADERS, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    out = []
    for i in data.get("data", []):
        f = i.get("fields", {})
        out.append({
            "url": f.get("url"),
            "title": f.get("title"),
            "snippet": None,
            "published": (f.get("date") or {}).get("created"),
            "engine": "reliefweb",
            "source": ",".join([s.get("name","") for s in f.get("source", []) if s.get("name")]),
            "text_hint": (f.get("body") or "")[:2000] if isinstance(f.get("body"), str) else None,
        })
    log_event("reliefweb_results", {"count": len(out)})
    return out
