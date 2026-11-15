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


def test_classifier_rules():
    from finn.announcements import classify as c
    assert c("Regulation 30 Capacity Addition", "Board approves 11,871 crore investment in 1,800 MW")["category"] == "capex"
    assert c("Intimation of Repayment of Commercial Paper (CP)", "fully redeemed 1,000 crore")["tier"] == "routine"
    assert c("Announcement under Regulation 30 (LODR)-Allotment of ESOP / ESPS", "")["tier"] == "routine"
    assert c("Announcement under Regulation 30 (LODR)-Analyst / Investor Meet - Intimation", "filed Q2 FY27 earnings-call transcript")["category"] == "earnings_call"
    assert c("Announcement under Regulation 30 (LODR)-Change in Management", "X appointed CEO")["tier"] == "high"
    assert c("Announcement under Regulation 30 (LODR)-Credit Rating", "S&P reaffirmed A- stable rating")["tier"] == "routine"
    assert c("Disclosure Under Regulation 30", "DoT levied penalties of Rs.1.60 lakh")["tier"] == "routine"


def test_board_outcome_is_results_only_when_it_says_results():
    from finn.announcements import classify as c
    assert c("Board Meeting Outcome for Outcome Of The Meeting Of Special Committee", "Approved issue of 5.74 crore warrants to parent")["category"] == "fund_raise"
    assert c("Board Meeting Outcome for Outcome Of The Board Meeting", "Approved Q2 and H1 results, JV with X")["category"] == "results"


def test_reported_quarter():
    from finn.main import reported_quarter as q
    assert q("2026-11-14T23:54:00+05:30") == "Sep 2026"
    assert q("2026-10-01T09:00:00+05:30") == "Sep 2026"
    assert q("2026-09-30T09:00:00+05:30") == "Jun 2026"
    assert q("2027-01-20T09:00:00+05:30") == "Dec 2026"
    assert q("2026-02-10T09:00:00+05:30") == "Dec 2025"


def _infy():
    return {"tables": {
        "profit_loss": {"periods": ["Mar 2025", "Mar 2026", "TTM"], "rows": {
            "Sales": [162990.0, 178650.0, 189336.0], "Operating Profit": [39236.0, 42280.0, 44899.0], "Depreciation": [4812.0, 4902.0, 5184.0]}},
        "quarters": {"periods": ["Jun 2025", "Sep 2025", "Jun 2026", "Sep 2026"], "rows": {
            "Sales": [42279.0, 44490.0, 48211.0, 49244.0], "Operating Profit": [9943.0, 10535.0, 11409.0, 11689.0], "Depreciation": [1140.0, 1182.0, 1246.0, 1359.0]}}}}


def test_ledger_periods():
    from finn import ledger
    assert ledger.parse_period("FY26") == ("year", 2026)
    assert ledger.parse_period("Q3 FY26") == ("quarter", "Dec 2025")
    assert ledger.parse_period("Q4 FY26") == ("quarter", "Mar 2026")
    assert ledger.parse_period("next two years") is None


def test_ledger_margin_is_ebit_and_scored():
    from finn import ledger
    act = ledger.actual(_infy(), "operating_margin", ("year", 2026))
    assert act["value"] == 20.9 and not act["partial"]
    it = {"metric": "operating_margin", "low": 20, "high": 22, "quote": "margin guidance 20% to 22%", "summary": ""}
    assert ledger.verdict(it, act)[0] == "delivered"
    assert ledger.verdict({**it, "low": 22, "high": 24}, act)[0] == "missed"


def test_ledger_constant_currency_is_not_scored_and_partial_year():
    from finn import ledger
    act = ledger.actual(_infy(), "revenue_growth", ("year", 2026))
    assert act["value"] == 9.6
    it = {"metric": "revenue_growth", "low": 2, "high": 3, "quote": "growth between 2% and 3% in constant currency terms", "summary": ""}
    assert ledger.verdict(it, act)[0] == "not comparable"
    part = ledger.actual(_infy(), "operating_margin", ("year", 2027))
    assert part["partial"] and part["value"] == round((11409 + 11689 - 1246 - 1359) / (48211 + 49244) * 100, 1)
    assert ledger.verdict({"metric": "operating_margin", "low": 20, "high": 22, "quote": "", "summary": ""}, part)[0] == "on track"


def test_ledger_ignores_component_impacts_and_inherits_constant_currency():
    from finn import ledger
    g = lambda call, lo, hi, quote, **kw: {"metric": "revenue_growth", "target_period": "FY26", "low": lo, "high": hi, "unit": "%",
                                           "kind": "explicit_guidance", "quote": quote, "summary": "", "scope": "company", "call": call, **kw}
    calls = [
        {"call": "Jul 2025", "items": [g("Jul 2025", 1, 3, "growth of 1% to 3% in constant currency")]},
        {"call": "Oct 2025", "items": [g("Oct 2025", 2, 3, "we have guided for 2% to 3% for the year"),
                                       g("Oct 2025", 1, 1, "this deal adds 1%", scope="component"),
                                       {"metric": "operating_margin", "target_period": "FY26", "low": -0.5, "high": -0.5, "unit": "%",
                                        "kind": "explicit_guidance", "quote": "50 bps impact", "summary": "", "scope": "company", "call": "Oct 2025"}]},
    ]
    L = ledger.build(_infy(), calls)
    assert len(L["rows"]) == 1
    row = L["rows"][0]
    assert [(h["low"], h["high"]) for h in row["guided"]] == [(1, 3), (2, 3)]
    assert row["verdict"] == "not comparable" and len(L["other_statements"]) == 2


def test_ledger_prefers_the_statement_that_says_guidance():
    from finn import ledger
    mk = lambda lo, hi, quote: {"metric": "revenue_growth", "target_period": "FY27", "low": lo, "high": hi, "unit": "%", "call": "Oct 2026",
                                "kind": "explicit_guidance", "quote": quote, "summary": "", "scope": "company"}
    calls = [{"call": "Oct 2026", "items": [mk(-2, -1.8, "both of them put together were in the range of 1.8% to 2% impact"),
                                            mk(1, 2, "our revenue growth guidance is 1% to 2% YoY in constant currency terms")]}]
    row = ledger.build(_infy(), calls)["rows"][0]
    assert (row["guided"][-1]["low"], row["guided"][-1]["high"]) == (1, 2)


def test_new_company_fetches_are_capped():
    from finn import main
    main._fetch_times.clear()
    assert all(main._allow_fetch(limit=3) for _ in range(3))
    assert not main._allow_fetch(limit=3)
    main._fetch_times.clear()


def test_api_rejects_out_of_range_inputs_and_sets_headers(monkeypatch):
    import os
    os.environ["FINN_REFRESH"] = "0"
    from fastapi.testclient import TestClient
    from finn import main
    c = TestClient(main.app)
    assert c.get("/api/brief?hours=-5").status_code == 422
    assert c.get("/api/brief?hours=999999999").status_code == 422
    assert c.get("/api/alerts?on_date=x';--").status_code == 422
    r = c.get("/api/status")
    assert r.status_code == 200 and r.headers["x-content-type-options"] == "nosniff" and "default-src 'self'" in r.headers["content-security-policy"]


def test_unknown_page_gets_html_and_unknown_api_gets_json():
    import os
    os.environ["FINN_REFRESH"] = "0"
    from fastapi.testclient import TestClient
    from finn import main
    c = TestClient(main.app)
    r = c.get("/some/missing/page")
    assert r.status_code == 404 and "text/html" in r.headers["content-type"] and "does not exist" in r.text
    r = c.get("/api/nope")
    assert r.status_code == 404 and r.json() == {"detail": "Not Found"}
    assert c.get("/api/research/NOTAREALTICKER").status_code == 404
