from finn import alerts, prices

HDR = "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"


def test_parse_keeps_eq_and_reads_date_from_file():
    txt = HDR + "M&M, EQ, 11-Nov-2026, 3290.60, 3340.00, 3465.00, 3339.90, 3465.00, 3465.00, 3418.97, 5574796, 190600.79, 304245, 3294780, 59.10\n" \
              + "21STCENMGM, BE, 11-Nov-2026, 54.53, 57.20, 57.25, 56.10, 57.00, 56.58, 57.06, 25557, 14.58, 151, -, -\n"
    d, rows = prices.parse_bhavcopy(txt)
    assert d == "2026-11-11" and len(rows) == 1
    assert rows[0]["symbol"] == "M&M" and rows[0]["volume"] == 5574796 and rows[0]["delivery_pct"] == 59.10


def test_parse_rejects_html_error_page():
    assert prices.parse_bhavcopy("<!DOCTYPE html><html>") == (None, [])


def _hist(vols, last_close=100.0, prev=100.0):
    rows = [{"symbol": "X", "date": f"d{i}", "close": 100.0, "prev_close": 100.0, "volume": v, "delivery_pct": 50.0} for i, v in enumerate(vols)]
    rows[-1]["close"], rows[-1]["prev_close"] = last_close, prev
    return rows


def test_volume_spike_triggers():
    r = alerts.evaluate(_hist([1000] * 20 + [2500]))
    assert r["triggered"] and r["reasons"] == ["volume"] and r["volume_multiple"] == 2.5


def test_median_baseline_ignores_one_prior_spike():
    r = alerts.evaluate(_hist([1000] * 19 + [50000] + [2500]))
    assert r["volume_multiple"] == 2.5


def test_price_move_and_configurable_threshold():
    assert alerts.evaluate(_hist([1000] * 21, last_close=95.0))["reasons"] == ["price"]
    assert not alerts.evaluate(_hist([1000] * 21, last_close=95.0), {"price_move_pct": 6})["triggered"]


def test_not_enough_history():
    assert alerts.evaluate(_hist([1000] * 5)) is None


def _co(rows, bank=False):
    periods = ["Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"]
    return {"name": "X", "consolidated": True, "top_ratios": {},
            "tables": {"quarters": {"periods": periods, "rows": rows}, "profit_loss": None,
                       "balance_sheet": None, "cash_flow": None, "ratios": None}}


def test_headline_qoq_yoy():
    from finn import metrics
    h = metrics.headline(_co({"Sales": [100, 0, 0, 200, 220], "Operating Profit": [10, 0, 0, 20, 33],
                              "OPM %": [10, 0, 0, 10, 15], "Profit before tax": [8, 0, 0, 16, 20], "Net Profit": [6, 0, 0, 12, 9]}))
    rev = h["lines"][0]
    assert (rev["qoq_pct"], rev["yoy_pct"]) == (10.0, 120.0)
    assert [l["label"] for l in h["lines"]] == ["Revenue", "EBITDA", "PBT", "PAT"]
    assert h["lines"][3]["qoq_pct"] == -25.0


def test_bank_headline_uses_net_interest_income():
    from finn import metrics
    h = metrics.headline(_co({"Revenue": [90, 0, 0, 95, 100], "Interest": [50, 0, 0, 52, 54],
                              "Financing Profit": [-5, 0, 0, -6, -7], "Financing Margin %": [-5, 0, 0, -6, -7],
                              "Profit before tax": [20, 0, 0, 22, 23], "Net Profit": [15, 0, 0, 16, 17]}))
    nii = h["lines"][1]
    assert nii["label"] == "Net interest income" and nii["value"] == 46 and nii["prev"] == 43
    assert h["margin_pct"] is None
