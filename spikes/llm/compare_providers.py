"""Re-run guidance extraction on the calls behind the shipped, hand-checked ledgers with another
provider/model, and compare. Writes to data/cache/guidance-<model>/ so shipped ledgers are untouched.

    FINN_PROVIDER=gemini FINN_MODEL=gemini-2.5-flash PYTHONPATH=backend uv run python spikes/llm/compare_providers.py INFY KAYNES
"""
import json, re, sys, time
from finn import config, guidance, ledger, llm, screener

def key(r):
    return (r["metric"], r["period"])

out_dir = config.CACHE_DIR / ("guidance-" + re.sub(r"[^a-z0-9.-]+", "-", llm.STRONG.lower()))
out_dir.mkdir(parents=True, exist_ok=True)
print(f"provider={llm.PROVIDER} model={llm.STRONG}")
for sym in sys.argv[1:]:
    shipped = json.loads((config.CACHE_DIR / "guidance" / f"{sym}.json").read_text())
    company = screener.fetch_company(sym)
    calls = {c["label"]: c["transcript"] for c in company["documents"]["concalls"] if c["transcript"]}
    t0, runs, failed = time.time(), [], []
    led0 = sum(1 for _ in open(config.CACHE_DIR / "llm_ledger.jsonl")) if (config.CACHE_DIR / "llm_ledger.jsonl").exists() else 0
    for c in shipped["calls"]:
        try:
            runs.append(guidance.extract(calls[c["call"]], c["call"]))
        except Exception as e:
            failed.append(f"{c['call']}: {type(e).__name__}: {str(e)[:120]}")
    secs = time.time() - t0
    lines = open(config.CACHE_DIR / "llm_ledger.jsonl").read().splitlines()[led0:]
    toks = sum(json.loads(l).get("total_tokens", 0) for l in lines if json.loads(l)["model"] == llm.STRONG)
    (out_dir / f"{sym}.json").write_text(json.dumps({"symbol": sym, "calls": runs}, indent=1))
    new, old = ledger.build(company, runs), ledger.build(company, shipped["calls"])
    items = [it for r in runs for it in r["items"]]
    claimed = [it for it in items if it.get("kind") == "explicit_guidance" and it.get("scope", "company") == "company"]
    kept = [it for it in claimed if ledger._scoreable(it) and ledger._company_sized(company, it)]
    print(f"\n=== {sym}: {len(runs)}/{len(shipped['calls'])} calls read in {secs:.0f}s, {toks:,} tokens"
          + (f"; FAILED {failed}" if failed else ""))
    print(f"  items {len(items)}, quotes failing the word-for-word check {sum(r['dropped_unverified'] for r in runs)}, "
          f"model said 'company guidance' for {len(claimed)}, of which the rules kept {len(kept)}")
    o, n = {key(r): r for r in old["rows"]}, {key(r): r for r in new["rows"]}
    for k in sorted(set(o) | set(n), key=str):
        a, b = o.get(k), n.get(k)
        fmt = lambda r: "-" if r is None else f"{r['verdict']:14s} " + " -> ".join(f"{h['call']} {h['low']}-{h['high']}" for h in r["guided"])
        same = "SAME " if a and b and a["verdict"] == b["verdict"] and a["guided"][-1]["low"] == b["guided"][-1]["low"] else "DIFF "
        print(f"  {same}{k[0]:16s} {k[1]:6s} checked: {fmt(a)}\n  {'':5s}{'':23s} {llm.STRONG.split('/')[-1][:7]}: {fmt(b)}")
