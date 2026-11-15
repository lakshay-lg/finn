"""FINN HTTP API. Run: PYTHONPATH=backend uv run uvicorn finn.main:app --port 8000"""
import csv
import io
import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import alerts, announcements, config, db, ledger, metrics, prices, screener

app = FastAPI(title="FINN")
IST = timezone(timedelta(hours=5, minutes=30))
SYMBOLS_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
_symbols: list[dict] = []


def symbol_master() -> list[dict]:
    """NSE's own symbol list, cached on disk. This is what makes any NSE ticker resolvable."""
    global _symbols
    if _symbols:
        return _symbols
    path = config.CACHE_DIR / "EQUITY_L.csv"
    if not path.exists():
        r = httpx.get(SYMBOLS_URL, headers={"User-Agent": config.USER_AGENT}, timeout=30)
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(r.text)
    rows = list(csv.reader(io.StringIO(path.read_text())))
    _symbols = [{"symbol": r[0].strip(), "name": r[1].strip()} for r in rows[1:] if len(r) > 2]
    return _symbols


def reported_quarter(ts: str) -> str:
    """The quarter a results filing made at `ts` reports: the latest quarter that had ended."""
    d = datetime.fromisoformat(ts)
    y, m = d.year, d.month
    for qm, name in ((12, "Dec"), (9, "Sep"), (6, "Jun"), (3, "Mar")):
        if m > qm:
            return f"{name} {y}"
    return f"Dec {y - 1}"


def _headline_for(symbol: str, ts: str) -> dict:
    """Headline numbers only if screener already carries the quarter this filing reports.

    Screener lags new results by days; attaching its latest quarter blindly would show the
    previous quarter's numbers on a card about the new one.
    """
    want = reported_quarter(ts)
    try:
        h = metrics.headline(screener.fetch_company(symbol))
    except Exception:
        h = None
    if h and h["period"] == want:
        return {"status": "ok", "headline": h}
    return {"status": "pending", "headline": None, "expected_period": want,
            "have_period": h["period"] if h else None}


@app.get("/api/brief")
def brief(hours: int = 24):
    """Windowed digest: what matters first, routine collapsed, coverage stated."""
    con = db.connect()
    announcements.coverage(con)  # ensures the table exists
    now = datetime.now(IST)
    since = (now - timedelta(hours=hours)).isoformat()
    rows = [dict(r) for r in con.execute("SELECT * FROM announcements WHERE ts>=? ORDER BY ts DESC", (since,))]
    for r in rows:
        if r["category"] == "results" and r["tier"] == "high":
            r["numbers"] = _headline_for(r["symbol"], r["ts"])
    latest = con.execute("SELECT MAX(date) d FROM sessions").fetchone()["d"]
    moves = [a for a in alerts.scan(con, config.PORTFOLIO) if a["triggered"]]
    last_high = con.execute("SELECT symbol, ts, title, category FROM announcements WHERE tier='high' ORDER BY ts DESC LIMIT 1").fetchone()
    return {
        "generated_at": now.isoformat(timespec="seconds"), "window_hours": hours,
        "counts": {t: sum(1 for r in rows if r["tier"] == t) for t in ("high", "medium", "routine")} | {"total": len(rows)},
        "high": [r for r in rows if r["tier"] == "high"],
        "medium": [r for r in rows if r["tier"] == "medium"],
        "routine": [r for r in rows if r["tier"] == "routine"],
        "moves": moves, "price_session": latest,
        "moves_in_window": bool(latest and latest >= since[:10]),
        "last_high": dict(last_high) if last_high else None,
        "coverage": announcements.coverage(con),
    }


@app.get("/api/alerts")
def price_alerts(volume_multiple: float = 2.0, price_move_pct: float = 4.0, on_date: str | None = None):
    con = db.connect()
    t = {"volume_multiple": volume_multiple, "price_move_pct": price_move_pct}
    return {"thresholds": t, "results": alerts.scan(con, config.PORTFOLIO, t, on_date)}


@app.get("/api/prices/{symbol}")
def price_series(symbol: str, sessions: int = 60):
    con = db.connect()
    rows = [dict(r) for r in con.execute(
        "SELECT date, close, volume FROM prices WHERE symbol=? ORDER BY date DESC LIMIT ?", (symbol.upper(), sessions))]
    if not rows:
        raise HTTPException(404, f"no price data for {symbol}")
    return {"symbol": symbol.upper(), "series": rows[::-1]}


@app.get("/api/symbols")
def symbols(q: str = ""):
    q = q.strip().upper()
    if not q:
        return [s for s in symbol_master() if s["symbol"] in config.PORTFOLIO]
    hits = [s for s in symbol_master() if s["symbol"].startswith(q)]
    hits += [s for s in symbol_master() if q in s["name"].upper() and s not in hits]
    return hits[:12]


@app.get("/api/research/{symbol}")
def research(symbol: str):
    symbol = symbol.upper()
    if not any(s["symbol"] == symbol for s in symbol_master()):
        raise HTTPException(404, f"{symbol} is not an NSE symbol")
    try:
        c = screener.fetch_company(symbol)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"could not reach screener.in: {type(e).__name__}")
    d = c["documents"]
    out = metrics.research_numbers(c)
    out["documents"] = {
        "annual_reports": d["annual_reports"][:3],
        "transcripts": [x for x in d["concalls"] if x["transcript"]][:5],
    }
    gpath = config.CACHE_DIR / "guidance" / f"{symbol.replace('&', '_')}.json"
    if gpath.exists():
        g = json.loads(gpath.read_text())
        out["ledger"] = {"status": "ready", **ledger.build(c, g["calls"])}
    else:
        out["ledger"] = {"status": "not_built",
                         "message": "Guidance has not been extracted for this company yet. On the free model tier it takes several minutes per company."}
    return out


_refresh = {"last_run": None, "prices": None, "announcements": None, "error": None}


def refresh_once():
    """Top up prices and announcements. A failing source leaves the stored data in place."""
    con = db.connect()
    _refresh["last_run"] = datetime.now(IST).isoformat(timespec="seconds")
    _refresh["error"] = None
    try:
        _refresh["prices"] = prices.ingest(con, days_back=10)
    except Exception as e:
        _refresh["prices"], _refresh["error"] = None, f"prices: {type(e).__name__}"
    try:
        _refresh["announcements"] = announcements.seed_from_screener(con, config.PORTFOLIO, force=True)
    except Exception as e:
        _refresh["announcements"], _refresh["error"] = None, f"announcements: {type(e).__name__}"


def _refresh_loop():
    while True:
        refresh_once()
        time.sleep(3 * 3600)


@app.on_event("startup")
def _start_refresh():
    if os.environ.get("FINN_REFRESH", "1") == "1":
        threading.Thread(target=_refresh_loop, daemon=True).start()


@app.get("/api/status")
def status():
    """What the app holds and when it last managed to refresh."""
    con = db.connect()
    return {"refresh": _refresh, "price_session": con.execute("SELECT MAX(date) d FROM sessions").fetchone()["d"],
            "sessions": con.execute("SELECT COUNT(*) n FROM sessions").fetchone()["n"],
            "coverage": announcements.coverage(con)}


_web = config.ROOT / "web"
if _web.exists():
    app.mount("/", StaticFiles(directory=_web, html=True), name="web")
