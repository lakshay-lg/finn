"""Ingest EOD prices and print the portfolio scan. Usage: python backend/run_ingest.py [days_back]"""
import sys
from finn import alerts, config, db, prices

con = db.connect()
print("ingest:", prices.ingest(con, days_back=int(sys.argv[1]) if len(sys.argv) > 1 else 70))
s = [r["date"] for r in con.execute("SELECT date FROM sessions ORDER BY date")]
print(f"sessions stored: {len(s)}  first={s[0]}  last={s[-1]}")
print("around Diwali:", [d for d in s if "2026-11-05" <= d <= "2026-11-12"])
missing = [x for x in config.PORTFOLIO if not con.execute("SELECT 1 FROM prices WHERE symbol=? LIMIT 1", (x,)).fetchone()]
print("portfolio symbols with no price rows:", missing)
res = alerts.scan(con, config.PORTFOLIO)
print(f"\nscan of latest session ({len(res)} symbols evaluated, defaults {config.DEFAULT_THRESHOLDS}):")
for r in res:
    print(f"  {'ALERT' if r['triggered'] else '     '} {r['symbol']:11s} {r['date']} close={r['close']:>9.2f} move={r['move_pct']:+6.2f}% vol={r['volume_multiple']:.2f}x deliv={r['delivery_pct']} {r['reasons']}")
