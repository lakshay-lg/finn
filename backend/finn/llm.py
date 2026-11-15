"""Minimal model client: Groq's OpenAI-compatible API, disk cache, rate-limit aware.

Free-tier limit observed on this key: 8,000 tokens per minute per model. Every response is
cached by a hash of (model, messages), so a document is only ever read once.
"""
import hashlib
import json
import os
import time

import httpx

from . import config

URL = "https://api.groq.com/openai/v1/chat/completions"
STRONG = "openai/gpt-oss-120b"
CACHE = config.CACHE_DIR / "llm"
LEDGER = config.CACHE_DIR / "llm_ledger.jsonl"


class ModelUnavailable(RuntimeError):
    pass


def chat_json(messages: list[dict], model: str = STRONG, max_tokens: int = 1800) -> dict:
    """Return the parsed JSON object the model produced. Cached on disk."""
    key = hashlib.sha256(json.dumps([model, messages], sort_keys=True).encode()).hexdigest()[:24]
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ModelUnavailable("GROQ_API_KEY is not set")
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0,
            "response_format": {"type": "json_object"}}
    for attempt in range(5):
        r = httpx.post(URL, headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=120)
        if r.status_code == 429:
            wait = float(r.headers.get("retry-after", 20))
            time.sleep(min(wait + 1, 65))
            continue
        if r.status_code == 400 and "json_validate_failed" in r.text and attempt < 3:
            # the model produced malformed JSON; a little sampling noise usually clears it
            body["temperature"] = 0.2 + 0.1 * attempt
            continue
        if r.status_code >= 400:
            raise ModelUnavailable(f"{r.status_code}: {r.text[:300]}")
        data = r.json()
        out = json.loads(data["choices"][0]["message"]["content"])
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out))
        with LEDGER.open("a") as f:
            f.write(json.dumps({"t": int(time.time()), "model": model, **data.get("usage", {})}) + "\n")
        return out
    raise ModelUnavailable("rate limited after 5 attempts")
