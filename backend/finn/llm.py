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
# 200,000 tokens per day per model on the free tier; FINN_MODEL switches model when one runs out
STRONG = os.environ.get("FINN_MODEL", "openai/gpt-oss-120b")
CACHE = config.CACHE_DIR / "llm"
LEDGER = config.CACHE_DIR / "llm_ledger.jsonl"


class ModelUnavailable(RuntimeError):
    pass


def _parse(text: str) -> dict:
    """Parse a JSON object from a reply that may wrap it in prose or a code fence."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        i, j = text.find("{"), text.rfind("}")
        if i < 0 or j <= i:
            raise ModelUnavailable("model reply contained no JSON object")
        try:
            return json.loads(text[i:j + 1])
        except json.JSONDecodeError as e:
            raise ModelUnavailable(f"model reply was not valid JSON: {e}")


def chat_json(messages: list[dict], model: str = STRONG, max_tokens: int = 3000) -> dict:
    """Return the parsed JSON object the model produced. Cached on disk."""
    key = hashlib.sha256(json.dumps([model, messages], sort_keys=True).encode()).hexdigest()[:24]
    path = CACHE / f"{key}.json"
    if path.exists():
        return json.loads(path.read_text())
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ModelUnavailable("GROQ_API_KEY is not set")
    # reasoning_effort low: at the default the model can spend its whole output allowance thinking
    # and return an empty answer (seen on Kaynes: 1,798 of 1,800 tokens went to reasoning)
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0,
            "reasoning_effort": "low", "response_format": {"type": "json_object"}}
    for attempt in range(5):
        r = httpx.post(URL, headers={"Authorization": f"Bearer {api_key}"}, json=body, timeout=120)
        if r.status_code == 429:
            wait = float(r.headers.get("retry-after", 20))
            time.sleep(min(wait + 1, 65))
            continue
        if r.status_code == 400 and "json_validate_failed" in r.text and "response_format" in body:
            # Groq's strict JSON mode rejected the reply; ask again in plain mode and parse it here
            del body["response_format"]
            continue
        if r.status_code >= 400:
            raise ModelUnavailable(f"{r.status_code}: {r.text[:300]}")
        data = r.json()
        if data["choices"][0].get("finish_reason") == "length":
            raise ModelUnavailable("model ran out of output tokens before finishing its answer")
        out = _parse(data["choices"][0]["message"]["content"] or "")
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out))
        with LEDGER.open("a") as f:
            f.write(json.dumps({"t": int(time.time()), "model": model, **data.get("usage", {})}) + "\n")
        return out
    raise ModelUnavailable("rate limited after 5 attempts")
