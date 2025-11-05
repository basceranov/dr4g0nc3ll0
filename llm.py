import requests, os
from config import BASE_URL, API_KEY, MODEL, LLM_TEMPERATURE
from provenance import log_event

def chat(messages, model: str = MODEL, temperature: float = LLM_TEMPERATURE, max_tokens: int = 1200):
    url = f"{BASE_URL.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    log_event("llm_request", {"url": url, "model": model, "payload": {"messages": messages[-2:]}})
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    out = data["choices"][0]["message"]["content"]
    log_event("llm_response", {"content_preview": out[:500]})
    return out