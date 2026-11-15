"""Unusual end-of-day moves, judged against thresholds the investor sets."""
from statistics import median

from . import config


def evaluate(history: list[dict], thresholds: dict | None = None) -> dict | None:
    """history: one symbol's rows, oldest first. Judges the LAST row.

    Returns None when there is not enough history to form a baseline.
    """
    t = {**config.DEFAULT_THRESHOLDS, **(thresholds or {})}
    n = int(t["baseline_sessions"])
    if len(history) < n + 1:
        return None
    last, prior = history[-1], history[-1 - n:-1]
    vols = [r["volume"] for r in prior if r["volume"]]
    if not vols or not last["volume"] or not last["prev_close"] or last["close"] is None:
        return None
    base = median(vols)
    vol_x = last["volume"] / base if base else None
    move = (last["close"] / last["prev_close"] - 1) * 100
    reasons = []
    if vol_x is not None and vol_x > t["volume_multiple"]:
        reasons.append("volume")
    if abs(move) > t["price_move_pct"]:
        reasons.append("price")
    return {
        "symbol": last["symbol"], "date": last["date"], "close": last["close"],
        "move_pct": round(move, 2), "volume": last["volume"],
        "volume_multiple": round(vol_x, 2) if vol_x is not None else None,
        "baseline_volume": int(base), "delivery_pct": last["delivery_pct"],
        "triggered": bool(reasons), "reasons": reasons,
        # unrounded, so a client re-applying other thresholds gets exactly the same answer
        "move_pct_raw": move, "volume_multiple_raw": vol_x,
    }


def scan(con, symbols: list[str], thresholds: dict | None = None, on_date: str | None = None) -> list[dict]:
    """Evaluate each symbol on `on_date` (default: its latest session)."""
    out = []
    for s in symbols:
        q = "SELECT * FROM prices WHERE symbol=?" + (" AND date<=?" if on_date else "") + " ORDER BY date"
        rows = [dict(r) for r in con.execute(q, (s, on_date) if on_date else (s,))]
        res = evaluate(rows, thresholds)
        if res:
            out.append(res)
    return sorted(out, key=lambda r: (not r["triggered"], -abs(r["move_pct"])))
