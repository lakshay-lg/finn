"""Promise ledger: management's guidance set against reported numbers.

The model only extracted the statements (guidance.py). Everything here is arithmetic and
rules, so every verdict can be traced: guided range, reported figure, how it was computed.
A verdict is given only when the guided metric and the reported figure are the same thing;
otherwise the row says why it cannot be scored.
"""
import re

MONTHS = {"Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6, "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12}
Q_END = {1: "Jun", 2: "Sep", 3: "Dec", 4: "Mar"}


def _ym(label: str):
    m, y = label.split()
    return int(y) * 12 + MONTHS[m]


def parse_period(text: str):
    """'FY26' -> ('year', 2026); 'Q3 FY26' -> ('quarter', 'Dec 2025'); else None."""
    t = text.upper().replace("FISCAL YEAR", "FY").replace("FISCAL", "FY")
    fy = re.search(r"FY\s*'?(20)?(\d{2})\b", t)
    if not fy:
        return None
    year = 2000 + int(fy.group(2))
    q = re.search(r"\bQ([1-4])\b", t)
    if q:
        n = int(q.group(1))
        return ("quarter", f"{Q_END[n]} {year if n == 4 else year - 1}")
    return ("year", year)


def _row(table, name):
    return table["rows"].get(name) if table else None


def _at(table, name, period):
    row = _row(table, name)
    if row is None or period not in table["periods"]:
        return None
    return row[table["periods"].index(period)]


def _fy_quarters(q, year):
    """Reported quarters belonging to fiscal year `year` (Apr of year-1 to Mar of year)."""
    want = [f"Jun {year - 1}", f"Sep {year - 1}", f"Dec {year - 1}", f"Mar {year}"]
    return [p for p in want if q and p in q["periods"]]


def actual(company, metric: str, period):
    """Reported figure for a guided metric. Returns dict(value, basis, partial) or None."""
    pl, q = company["tables"].get("profit_loss"), company["tables"].get("quarters")
    kind, key = period
    rev = "Sales" if _row(q, "Sales") or _row(pl, "Sales") else "Revenue"

    def margin(s, op, dep, ebit):
        if None in (s, op) or not s or (ebit and dep is None):
            return None
        return round(((op - dep) if ebit else op) / s * 100, 1)

    if metric in ("operating_margin", "ebitda_margin"):
        ebit = metric == "operating_margin"
        how = "(operating profit - depreciation) / revenue" if ebit else "operating profit / revenue"
        if kind == "quarter":
            v = margin(_at(q, rev, key), _at(q, "Operating Profit", key), _at(q, "Depreciation", key), ebit)
            return {"value": v, "unit": "%", "basis": f"{key} quarter, {how}", "partial": False} if v is not None else None
        fy = f"Mar {key}"
        if pl and fy in pl["periods"]:
            v = margin(_at(pl, rev, fy), _at(pl, "Operating Profit", fy), _at(pl, "Depreciation", fy), ebit)
            return {"value": v, "unit": "%", "basis": f"FY{key % 100} full year, {how}", "partial": False} if v is not None else None
        qs = _fy_quarters(q, key)
        if not qs:
            return None
        s, op, dep = (sum(_at(q, n, p) or 0 for p in qs) for n in (rev, "Operating Profit", "Depreciation"))
        v = margin(s, op, dep, ebit)
        return {"value": v, "unit": "%", "basis": f"FY{key % 100} first {len(qs)} quarter{'s' if len(qs) != 1 else ''}, {how}", "partial": True} if v is not None else None

    if metric == "revenue_growth":
        if kind == "quarter":
            now, y, m = _at(q, rev, key), int(key.split()[1]), key.split()[0]
            prev = _at(q, rev, f"{m} {y - 1}")
            if None in (now, prev) or not prev:
                return None
            return {"value": round((now / prev - 1) * 100, 1), "unit": "%", "basis": f"{key} quarter vs a year earlier, reported rupees", "partial": False}
        fy, last = f"Mar {key}", f"Mar {key - 1}"
        if pl and fy in pl["periods"] and last in pl["periods"]:
            a, b = _at(pl, rev, fy), _at(pl, rev, last)
            if None in (a, b) or not b:
                return None
            return {"value": round((a / b - 1) * 100, 1), "unit": "%", "basis": f"FY{key % 100} vs FY{(key - 1) % 100}, reported rupees", "partial": False}
        qs = _fy_quarters(q, key)
        prior = [f"{p.split()[0]} {int(p.split()[1]) - 1}" for p in qs]
        if not qs or any(_at(q, rev, p) is None for p in qs + prior):
            return None
        a, b = sum(_at(q, rev, p) for p in qs), sum(_at(q, rev, p) for p in prior)
        return {"value": round((a / b - 1) * 100, 1), "unit": "%", "basis": f"FY{key % 100} first {len(qs)} quarter{'s' if len(qs) != 1 else ''} vs same quarters a year earlier, reported rupees", "partial": True}
    return None


PLAUSIBLE = {"operating_margin": (0, 80), "ebitda_margin": (0, 80), "revenue_growth": (-50, 200)}
CC = re.compile(r"constant currency|\bcc\b|organic|dollar|usd", re.I)


def _is_cc(it) -> bool:
    return it.get("basis") == "constant_currency" or bool(CC.search(f"{it.get('quote', '')} {it.get('summary', '')}"))


def _rank(it) -> tuple:
    return (bool(re.search(r"guid", it.get("quote", ""), re.I)), it["low"] != it["high"])


def _scoreable(it) -> bool:
    lo, hi = it.get("low"), it.get("high")
    if it.get("kind") != "explicit_guidance" or it.get("scope", "company") != "company" or it["metric"] not in PLAUSIBLE:
        return False
    if lo is None or hi is None or parse_period(str(it.get("target_period", ""))) is None:
        return False
    a, b = PLAUSIBLE[it["metric"]]
    return a <= lo <= hi <= b


def verdict(item, act, constant_currency=False):
    """One of: delivered, beat, missed, on track, behind, not comparable, no reported figure."""
    lo, hi = item.get("low"), item.get("high")
    if act is None or lo is None or hi is None:
        return "no reported figure", "No matching reported number, or no numeric target was given."
    if item["metric"] == "revenue_growth" and (constant_currency or _is_cc(item)):
        return "not comparable", "Guided in constant currency or dollars; the reported figure is rupee growth, which also includes currency moves."
    v = act["value"]
    if lo <= v <= hi:
        return ("on track" if act["partial"] else "delivered"), "Reported figure is inside the guided range."
    if v > hi:
        return ("on track" if act["partial"] else "beat"), "Reported figure is above the guided range."
    return ("behind" if act["partial"] else "missed"), "Reported figure is below the guided range."


def build(company, guidance_calls: list[dict]) -> dict:
    """Group guidance by metric and target period, oldest call first, and score the latest."""
    groups = {}
    for call in sorted(guidance_calls, key=lambda c: _ym(c["call"])):
        per_call = {}
        for it in call["items"]:
            if not _scoreable(it):
                continue
            k = (it["metric"], parse_period(str(it["target_period"])))
            # one statement per call: prefer a quote that says "guidance", then a range over a point
            if k not in per_call or _rank(it) > _rank(per_call[k]):
                per_call[k] = it
        for k, it in per_call.items():
            groups.setdefault(k, []).append(it)
    rows = []
    for (metric, period), items in groups.items():
        act = actual(company, metric, period)
        # if any call states the basis is constant currency, the whole history is on that basis
        v, why = verdict(items[-1], act, constant_currency=any(_is_cc(i) for i in items))
        hist = []
        for it in items:
            if not hist or (hist[-1]["low"], hist[-1]["high"]) != (it.get("low"), it.get("high")):
                hist.append({"call": it["call"], "low": it.get("low"), "high": it.get("high"), "unit": it.get("unit", ""),
                             "quote": it["quote"], "speaker": it.get("speaker", "")})
        rows.append({"metric": metric, "period": f"FY{period[1] % 100}" if period[0] == "year" else period[1],
                     "guided": hist, "reported": act, "verdict": v, "why": why,
                     "revisions": len(hist) - 1, "_sort": period[1] if period[0] == "year" else _ym(period[1]) / 12})
    rows.sort(key=lambda r: (r["_sort"], r["metric"]))
    for r in rows:
        del r["_sort"]
    other = [it for c in guidance_calls for it in c["items"] if not _scoreable(it)]
    scored = [r for r in rows if r["verdict"] in ("delivered", "beat", "missed")]
    return {"rows": rows, "other_statements": other,
            "calls_read": [c["call"] for c in sorted(guidance_calls, key=lambda c: _ym(c["call"]))],
            "scored": len(scored), "kept": sum(1 for r in scored if r["verdict"] != "missed"),
            "dropped_unverified": sum(c.get("dropped_unverified", 0) for c in guidance_calls)}
