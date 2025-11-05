# classification.py
import tldextract
from config import SOURCE_TYPE_BY_DOMAIN

def domain_of(url: str) -> str:
    if not url: return ""
    d = tldextract.extract(url)
    return d.registered_domain or ""

def classify_source(url: str) -> str:
    dom = domain_of(url)
    return SOURCE_TYPE_BY_DOMAIN.get(dom, "Other")
