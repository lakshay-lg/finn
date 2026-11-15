"""List Groq models and read rate-limit headers from one tiny request. Never prints the key."""
import os, json, httpx
H = {"Authorization": "Bearer " + os.environ["GROQ_API_KEY"]}
B = "https://api.groq.com/openai/v1"
r = httpx.get(B + "/models", headers=H, timeout=30)
print("models http", r.status_code)
models = sorted(r.json().get("data", []), key=lambda m: m["id"])
for m in models:
    print(f"  {m['id']:48s} ctx={m.get('context_window')} max_out={m.get('max_completion_tokens')} active={m.get('active')}")
for mid in ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]:
    if not any(m["id"] == mid for m in models):
        print(mid, "-> not in list"); continue
    r = httpx.post(B + "/chat/completions", headers=H, timeout=60,
                   json={"model": mid, "messages": [{"role": "user", "content": "Reply with the word ok."}], "max_tokens": 5})
    lim = {k[12:]: v for k, v in r.headers.items() if k.startswith("x-ratelimit-")}
    body = r.json()
    print(f"\n{mid}: http {r.status_code} usage={body.get('usage', {}).get('total_tokens')} err={(body.get('error') or {}).get('message')}")
    print("   limits:", lim)
