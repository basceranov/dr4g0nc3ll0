import json, os, time
from datetime import datetime
from config import LOG_DIR

os.makedirs(LOG_DIR, exist_ok=True)

def _log_path():
    date = datetime.utcnow().strftime("%Y%m%d")
    return os.path.join(LOG_DIR, f"provenance_{date}.jsonl")

def log_event(kind: str, payload: dict):
    rec = {
        "ts": time.time(),
        "kind": kind,
        **payload
    }
    with open(_log_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")