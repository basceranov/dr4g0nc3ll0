import re, urllib.parse, math
from config import SIMHASH_BITS, NEAR_DUP_HAMMING
from provenance import log_event

UTM_PARAMS = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","gclid","fbclid"}

def canonical_url(url: str) -> str:
    if not url: return url
    u = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(u.query, keep_blank_values=True)
    q = [(k,v) for k,v in q if k.lower() not in UTM_PARAMS]
    new_q = urllib.parse.urlencode(q, doseq=True)
    new = urllib.parse.urlunsplit((u.scheme, u.netloc, u.path, new_q, ""))  # drop fragment
    return new

def _tokens(text: str):
    text = re.sub(r"\s+", " ", text.lower())
    return re.findall(r"[a-zà-ù0-9]{2,}", text)

def simhash(text: str, bits: int = SIMHASH_BITS):
    if not text: return 0
    v = [0]*bits
    for tok in _tokens(text):
        h = hash(tok)
        for i in range(bits):
            v[i] += 1 if (h >> i) & 1 else -1
    out = 0
    for i in range(bits):
        if v[i] > 0: out |= (1 << i)
    return out

def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()

def cluster_near_duplicates(items, bits=SIMHASH_BITS, th=NEAR_DUP_HAMMING):
    clusters = []
    used = set()
    for i, it in enumerate(items):
        if i in used: continue
        sh = it.get("simhash")
        group = [it]
        for j in range(i+1, len(items)):
            if j in used: continue
            if hamming(sh, items[j].get("simhash")) <= th:
                group.append(items[j]); used.add(j)
        used.add(i)
        clusters.append(group)
    log_event("dedup_clusters", {"clusters": len(clusters), "items": len(items)})
    return clusters

def prepare_for_dedup(docs):
    for d in docs:
        d["url"] = canonical_url(d.get("url"))
        d["simhash"] = simhash(d.get("text",""))
    return docs
