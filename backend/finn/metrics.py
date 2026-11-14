"""Deterministic numbers for the research view and the results card.

Everything here is arithmetic on screener's standardised tables; no model is involved.
Rows are looked up by label because banks use different labels from other companies.
"""

REVENUE = ("Sales", "Revenue")
OPERATING = ("Operating Profit", "Financing Profit")
MARGIN = ("OPM %", "Financing Margin %")


def _row(table, names):
    if not table:
        return None
    for n in names if isinstance(names, tuple) else (names,):
        if n in table["rows"]:
            return table["rows"][n]
    return None


def _pct(new, old):
    if new is None or old in (None, 0):
        return None
    return round((new - old) / abs(old) * 100, 1)


def _series(table, names, drop_ttm=True):
    row = _row(table, names)
    if row is None:
        return []
    pts = [{"period": p, "value": v} for p, v in zip(table["periods"], row)]
    return [p for p in pts if not (drop_ttm and p["period"] == "TTM")]


def _cagr(series, years):
    vals = [p["value"] for p in series]
    if len(vals) <= years or vals[-1] is None or vals[-1 - years] in (None, 0):
        return None
    a, b = vals[-1 - years], vals[-1]
    if a <= 0 or b <= 0:
        return None
    return round(((b / a) ** (1 / years) - 1) * 100, 1)


def is_bank(company) -> bool:
    q = company["tables"].get("quarters")
    return bool(q and "Financing Profit" in q["rows"])


def headline(company) -> dict | None:
    """Revenue, operating profit (EBITDA), PBT, PAT for the latest quarter vs QoQ and YoY."""
    q = company["tables"].get("quarters")
    if not q or len(q["periods"]) < 5:
        return None
    bank = is_bank(company)
    items = [
        ("Revenue", REVENUE),
        ("Net interest income" if bank else "EBITDA", OPERATING),
        ("PBT", "Profit before tax"),
        ("PAT", "Net Profit"),
    ]
    lines = []
    for label, names in items:
        row = _row(q, names)
        if bank and label == "Net interest income":
            rev, intr = _row(q, REVENUE), _row(q, "Interest")
            row = [None if None in (a, b) else a - b for a, b in zip(rev, intr)] if rev and intr else None
        if row is None:
            continue
        lines.append({"label": label, "value": row[-1], "prev": row[-2], "year_ago": row[-5],
                      "qoq_pct": _pct(row[-1], row[-2]), "yoy_pct": _pct(row[-1], row[-5])})
    m = None if bank else _row(q, MARGIN)
    return {
        "period": q["periods"][-1], "prev_period": q["periods"][-2], "year_ago_period": q["periods"][-5],
        "unit": "Rs crore", "consolidated": company["consolidated"], "lines": lines,
        "margin_pct": {"now": m[-1], "prev": m[-2], "year_ago": m[-5]} if m else None,
        "note": "EBITDA is operating profit before other income, as standardised by screener.in."
                if not bank else "Banks have no EBITDA; net interest income (interest earned less interest paid) is shown instead.",
    }


def trajectory(company) -> dict:
    pl = company["tables"].get("profit_loss")
    rev, pat = _series(pl, REVENUE), _series(pl, "Net Profit")
    opm = [] if is_bank(company) else _series(pl, MARGIN)
    return {
        "revenue": rev, "pat": pat, "margin_pct": opm,
        "revenue_cagr_3y": _cagr(rev, 3), "revenue_cagr_5y": _cagr(rev, 5),
        "pat_cagr_3y": _cagr(pat, 3), "pat_cagr_5y": _cagr(pat, 5),
        "margin_change_3y_pts": round(opm[-1]["value"] - opm[-4]["value"], 1)
        if len(opm) >= 4 and None not in (opm[-1]["value"], opm[-4]["value"]) else None,
    }


def balance_sheet(company) -> dict:
    bs, rt = company["tables"].get("balance_sheet"), company["tables"].get("ratios")
    cap, res, debt = _row(bs, "Equity Capital"), _row(bs, "Reserves"), _row(bs, ("Borrowings", "Borrowing"))
    out = {"period": bs["periods"][-1] if bs else None, "bank": is_bank(company)}
    if cap and res and debt and None not in (cap[-1], res[-1], debt[-1]):
        equity = cap[-1] + res[-1]
        out.update(equity=equity, borrowings=debt[-1],
                   debt_to_equity=None if out["bank"] else (round(debt[-1] / equity, 2) if equity else None),
                   borrowings_series=_series(bs, ("Borrowings", "Borrowing")))
    for key, label in (("debtor_days", "Debtor Days"), ("inventory_days", "Inventory Days"),
                       ("payable_days", "Days Payable"), ("cash_conversion_cycle", "Cash Conversion Cycle"),
                       ("working_capital_days", "Working Capital Days"), ("roce_pct", ("ROCE %", "ROE %"))):
        out[key] = _series(rt, label)[-4:]
    return out


def cash_quality(company) -> dict:
    cf, pl = company["tables"].get("cash_flow"), company["tables"].get("profit_loss")
    cfo, fcf = _series(cf, "Cash from Operating Activity"), _series(cf, "Free Cash Flow")
    pat = {p["period"]: p["value"] for p in _series(pl, "Net Profit")}
    years = [dict(period=c["period"], cfo=c["value"], pat=pat.get(c["period"]),
                  fcf=next((f["value"] for f in fcf if f["period"] == c["period"]), None)) for c in cfo]
    last3 = [y for y in years[-3:] if y["cfo"] is not None and y["pat"] is not None]
    spat, scfo = sum(y["pat"] for y in last3), sum(y["cfo"] for y in last3)
    if is_bank(company):
        return {"years": [], "cfo_to_pat_3y_pct": None, "fcf_3y": None, "bank": True,
                "note": "Operating cash flow of a bank is driven by deposits and lending, so cash conversion is not assessed."}
    return {
        "years": years[-6:],
        "cfo_to_pat_3y_pct": round(scfo / spat * 100) if last3 and spat > 0 else None,
        "fcf_3y": round(sum(y["fcf"] for y in years[-3:] if y["fcf"] is not None), 1) if years else None,
        "bank": False,
    }


def research_numbers(company) -> dict:
    return {
        "symbol": company.get("symbol"), "name": company["name"], "top_ratios": company["top_ratios"],
        "headline": headline(company), "trajectory": trajectory(company),
        "balance_sheet": balance_sheet(company), "cash_quality": cash_quality(company),
    }
