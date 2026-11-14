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
