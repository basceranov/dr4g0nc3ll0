import os

# -------- SearXNG --------
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8880/search")
SEARXNG_DEFAULT_CATEGORIES = os.getenv("SEARXNG_CATEGORIES", "news,science,web")
SEARXNG_ENGINES = os.getenv("SEARXNG_ENGINES", "google,bing,duckduckgo")
SEARXNG_TIME_RANGE = os.getenv("SEARXNG_TIME_RANGE", "month")  # day|week|month
SEARXNG_LANGUAGE = os.getenv("SEARXNG_LANGUAGE", "it-IT")
SEARXNG_PAGE_SIZE = int(os.getenv("SEARXNG_PAGE_SIZE", "15"))
SEARXNG_PAGES = int(os.getenv("SEARXNG_PAGES", "2"))  # quante pagine per query

# -------- LLM (OpenAI-compatible) --------
BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")  # vLLM/Ollama -> http://host:port/v1
API_KEY = os.getenv("OPENAI_API_KEY", "sk-...")  # per vLLM/Ollama puoi mettere placeholder se non serve
MODEL = os.getenv("LLM_MODEL", "gpt-oss:20b")    # oppure "llama-3.1-8b-instruct", ecc.
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# -------- Crawl/Extract --------
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))
USER_AGENT = os.getenv("USER_AGENT", "OSINT-AgentBot/1.0 (+https://example.local)")

# -------- Dedup --------
SIMHASH_BITS = int(os.getenv("SIMHASH_BITS", "64"))
NEAR_DUP_HAMMING = int(os.getenv("NEAR_DUP_HAMMING", "6"))

# -------- Ranking --------
FRESHNESS_HALF_LIFE_DAYS = int(os.getenv("FRESHNESS_HALF_LIFE_DAYS", "60"))
DOMAIN_SCORES = {
    # bonus autorità (0..1): aggiungi i tuoi preferiti
    "ansa.it": 0.9, "repubblica.it": 0.75, "ilsole24ore.com": 0.95,
    "reuters.com": 1.0, "bbc.com": 0.9, "apnews.com": 0.9, "who.int": 1.0, "europa.eu": 1.0
}

# -------- Output --------
DEFAULT_TOPK = int(os.getenv("DEFAULT_TOPK", "8"))
LOG_DIR = os.getenv("LOG_DIR", "logs")

# Profili motori SearXNG (stringhe di engines separati da virgola)
ENGINES_PROFILE_LIGHT = "google,qwant,startpage,wikipedia,wikinews"
ENGINES_PROFILE_INSTITUTIONAL = "wikipedia,wikinews"

# Toggle fonti istituzionali aggiuntive (API/feeds)
USE_RELIEFWEB = True
RELIEFWEB_API = "https://api.reliefweb.int/v1/reports"
RELIEFWEB_LIMIT = int(os.getenv("RELIEFWEB_LIMIT", "20"))
RELIEFWEB_QUERY = os.getenv("RELIEFWEB_QUERY", "Sudan")

# Visual
ASSETS_DIR = os.getenv("ASSETS_DIR", "assets")
CHART_STYLE = os.getenv("CHART_STYLE", "default")  # riservato per future opzioni

# Regole “stato della prova”
REQUIRED_INDEPENDENT_SOURCES = int(os.getenv("REQUIRED_INDEPENDENT_SOURCES", "2"))
MIN_SUPPORTING_SOURCES = int(os.getenv("MIN_SUPPORTING_SOURCES", "2"))

# Mappa “tipi fonte” per dominio (espandibile)
SOURCE_TYPE_BY_DOMAIN = {
    "reliefweb.int": "UN/OCHA",
    "unhcr.org": "UN/UNHCR",
    "who.int": "UN/WHO",
    "icrc.org": "ICRC",
    "msf.org": "NGO",
    "amnesty.org": "NGO",
    "hrw.org": "NGO",
    "reuters.com": "Media-Intl",
    "bbc.com": "Media-Intl",
    "ansa.it": "Media-IT",
    "repubblica.it": "Media-IT",
    "tg24.sky.it": "Media-IT",
}
