"""Extract guidance from a company's recent earnings calls. Usage: run_guidance.py SYMBOL [n_calls]"""
import json, sys, time
from finn import config, docs, guidance, screener

sym = sys.argv[1].upper(); n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
c = screener.fetch_company(sym)
out, t0 = [], time.time()
for x in [v for v in c["documents"]["concalls"] if v["transcript"]]:
    if len(out) >= n:
        break
    try:
        if not guidance.is_earnings_call(docs.fetch_text(x["transcript"])):
            print(f"{x['label']}: skipped, not an earnings call", flush=True); continue
        r = guidance.extract(x["transcript"], x["label"])
    except Exception as e:
        print(f"{x['label']}: FAILED {type(e).__name__}: {str(e)[:200]}", flush=True); continue
    out.append(r)
    print(f"{x['label']}: chunks={r['chunks']} kept={len(r['items'])} dropped_unverified={r['dropped_unverified']} t+{time.time()-t0:.0f}s", flush=True)
path = config.CACHE_DIR / "guidance" / f"{sym.replace('&', '_')}.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps({"symbol": sym, "calls": out, "built_at": int(time.time())}, indent=1))
print("saved", path, "items", sum(len(r["items"]) for r in out), flush=True)
