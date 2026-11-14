"""End-of-day prices from NSE's full bhavcopy archive.

Two verified traps drive this module (docs/DESIGN.md section 3):
  * the archive can answer 200 with the PREVIOUS session's file for a date that had no
    session, so rows are keyed on the DATE1 column inside the file, never on the URL date;
  * weekdays can be closed and weekends can trade, so every calendar day is tried.
"""
import csv
import io
import time
from datetime import date, datetime, timedelta

import httpx

from . import config

URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{d}.csv"


def _num(s: str):
    s = s.strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def parse_bhavcopy(text: str):
    """Return (session_date_iso, rows) or (None, []) if this is not a bhavcopy.

    Only EQ-series rows are kept. The session date comes from DATE1.
    """
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 15 or rows[0][0].strip() != "SYMBOL":
        return None, []
    out, dates = [], set()
    for r in rows[1:]:
        if len(r) < 15 or r[1].strip() != "EQ":
            continue
        d = datetime.strptime(r[2].strip(), "%d-%b-%Y").date().isoformat()
        dates.add(d)
        vol = _num(r[10])
        out.append({
            "symbol": r[0].strip(), "date": d,
            "prev_close": _num(r[3]), "open": _num(r[4]), "high": _num(r[5]),
            "low": _num(r[6]), "close": _num(r[8]),
            "volume": int(vol) if vol is not None else None,
            "delivery_pct": _num(r[14]),
        })
    if len(dates) != 1:
        return None, []
    return dates.pop(), out


def fetch_day(client: httpx.Client, day: date):
    """Fetch one calendar day. Returns (session_date_iso, rows); (None, []) when no file."""
    r = client.get(URL.format(d=day.strftime("%d%m%Y")))
    if r.status_code != 200:
        return None, []
    return parse_bhavcopy(r.text)


def ingest(con, days_back: int = 200, today: date | None = None, pause: float = 0.4) -> dict:
    """Walk calendar days backwards and store every session not already present."""
    today = today or date.today()
    have = {r["date"] for r in con.execute("SELECT date FROM sessions")}
    stats = {"fetched": 0, "new_sessions": 0, "stale_duplicates": 0, "no_file": 0}
    with httpx.Client(headers={"User-Agent": config.USER_AGENT}, timeout=30) as client:
        for i in range(days_back + 1):
            day = today - timedelta(days=i)
            if day.isoformat() in have:
                continue
            session, rows = fetch_day(client, day)
            stats["fetched"] += 1
            time.sleep(pause)
            if session is None:
                stats["no_file"] += 1
                continue
            if session != day.isoformat():
                # the archive served another session's file under this URL
                stats["stale_duplicates"] += 1
                continue
            con.executemany(
                "INSERT OR REPLACE INTO prices VALUES "
                "(:symbol,:date,:open,:high,:low,:close,:prev_close,:volume,:delivery_pct)", rows)
            con.execute("INSERT OR REPLACE INTO sessions VALUES (?,?)", (session, len(rows)))
            con.commit()
            have.add(session)
            stats["new_sessions"] += 1
    return stats
