# evidence.py
from collections import defaultdict
from classification import classify_source, domain_of
from config import REQUIRED_INDEPENDENT_SOURCES, MIN_SUPPORTING_SOURCES

def independence(domains):
    """Conta domini distinti (proxy d'indipendenza)."""
    return len(set(domains))

def label_support(supporting_sources, ref_map):
    """
    supporting_sources: lista di interi [n] riferimenti dal tuo summarize/factcheck
    ref_map: {n: url}
    """
    urls = [ref_map.get(n) for n in supporting_sources if ref_map.get(n)]
    domains = [domain_of(u) for u in urls if u]
    indep = independence(domains)
    if len(urls) >= MIN_SUPPORTING_SOURCES and indep >= REQUIRED_INDEPENDENT_SOURCES:
        return "supported", indep
    if len(urls) >= 1:
        return "partial", indep
    return "unknown", indep

def classify_sources(ref_map):
    """Ritorna conteggio per tipologia fonte."""
    buckets = defaultdict(int)
    details = []
    for i, url in ref_map.items():
        t = classify_source(url)
        buckets[t] += 1
        details.append({"id": i, "url": url, "type": t})
    return dict(buckets), details
