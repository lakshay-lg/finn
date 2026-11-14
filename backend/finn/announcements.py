"""Announcements: storage, rules-first classification, materiality tier.

Coverage is partial by construction (docs/DESIGN.md section 4): the seed is the five most
recent items per company from screener. `coverage()` reports exactly what is held.
"""
import re
import time

from . import screener

SCHEMA = """
CREATE TABLE IF NOT EXISTS announcements (
    url TEXT PRIMARY KEY, symbol TEXT NOT NULL, ts TEXT NOT NULL,
    title TEXT, note TEXT, category TEXT, tier TEXT, why TEXT, source TEXT
);
CREATE INDEX IF NOT EXISTS ann_ts ON announcements(ts);
"""

# First match wins. Routine paperwork is tested first so that, e.g., an ESOP allotment is
# not mistaken for a fund raise.
RULES = [
    ("unclassified", r"esop|esos|employee.{0,12}stock|stock option|newspaper|trading window|loss of share|duplicate share|"
                     r"compliance certificate|certificate under|reg(ulation)?\.? ?74|investor complaints|esg|"
                     r"business responsibility|secretarial|statement of deviation|monitoring agency|change in registrar|"
                     r"prize|awards? 20\d\d|award ceremony|csr|code of conduct"),
    ("results", r"financial results?|results? for the (quarter|half|year|period)|unaudited|audited results|"
                r"shareholders?.? letter|q[1-4] ?(and h1 ?)?fy ?\d\d (unaudited |audited )?results|approved q[1-4]"),
    ("earnings_call", r"earnings call|con(ference)? ?call|transcript|audio recording|video recording"),
    ("investor_meetings", r"analyst ?/ ?investor meet|investor meet|investor conference|institutional investor|one-on-one"),
    ("management_change", r"change in director|change in management|appoint|resign|cessation|retire|key managerial|"
                          r"chief (executive|financial|operating)|managing director|\bceo\b|\bcfo\b"),
    ("M&A", r"acqui|merger|amalgamation|demerger|joint venture|\bjv\b|term sheet|scheme of arrangement|"
            r"stake (sale|purchase)|divest|slump sale|subsidiary|restructuring"),
    ("credit_rating", r"credit rating|rating (action|update|reaffirm|upgrade|downgrade)|\b(crisil|icra|care ratings|india ratings|s&p|moody)"),
    ("litigation", r"litigation|penalt|show cause|tax demand|gst (order|demand)|income tax order|\bsebi order|nclt|insolvency|"
                   r"arbitration|court|dispute|regulatory (action|order)|fine imposed"),
    ("fund_raise", r"\bqip\b|qualified institution|preferential|rights issue|buy-?back|commercial paper|non-convertible|"
                   r"\bncd|debenture|fund ?rais|warrants?|allotment of (equity|shares|securities)"),
    ("pledging", r"pledge|encumbrance"),
    ("insider_trading", r"insider|sast|regulation 29|reg\.? ?7\(2\)|acquisition of shares by promoter"),
    ("dividend", r"dividend"),
    ("bonus_split", r"bonus|stock split|sub-?division"),
    ("capex", r"capex|capacity (expansion|addition)|new plant|greenfield|brownfield|commission(ed|ing)|capital expenditure|"
              r"expansion of|investment in|\bmw\b"),
    ("postal_ballot", r"postal ballot"),
    ("agm_egm", r"annual general meeting|extra-?ordinary general|\bagm\b|\begm\b|voting results"),
    ("press_release", r"press release|media release|order (win|received|inflow)|bags|contract|launch|partnership|"
                      r"collaborat|clarification|rumour|award of|report for the month|monthly (sales|business|volume)"),
]
_COMPILED = [(c, re.compile(p, re.I)) for c, p in RULES]

HIGH = {"results", "M&A", "management_change", "litigation", "fund_raise", "pledging"}
MEDIUM = {"capex", "press_release", "dividend", "bonus_split", "credit_rating", "insider_trading", "earnings_call"}


def classify(title: str, note: str = "") -> dict:
    """Return category, tier (high / medium / routine) and a one-line reason for the tier."""
    text = f"{title} {note}"
    if re.search(r"board meeting outcome|outcome of (the )?(board )?meeting", title, re.I):
        # the heading says nothing about substance; a board outcome is "results" only if it says so
        cat = "results" if re.search(r"results", text, re.I) else \
            next((c for c, rx in _COMPILED if c != "unclassified" and rx.search(note)), "unclassified")
    else:
        cat = next((c for c, rx in _COMPILED if rx.search(title)), None) or \
            next((c for c, rx in _COMPILED if rx.search(note)), "unclassified")
    tier = "high" if cat in HIGH else "medium" if cat in MEDIUM else "routine"
    why = {"high": f"{cat} is a category that can move the stock", "medium": f"{cat}: worth a look",
           "routine": "routine disclosure"}[tier]
    low = text.lower()
    if cat == "management_change" and re.search(r"independent director|re-?appoint|company secretary|compliance officer", low) \
            and not re.search(r"\bceo\b|\bcfo\b|chief (executive|financial)|managing director", low):
        tier, why = "medium", "board-level change that does not involve the CEO, CFO or MD"
    if cat == "credit_rating":
        if re.search(r"downgrad|upgrad|negative|watch", low):
            tier, why = "high", "rating changed or placed on watch"
        elif re.search(r"reaffirm|affirm", low):
            tier, why = "routine", "rating reaffirmed, no change"
    if cat == "results" and re.search(r"intimation|notice of board meeting|to consider", low) and "outcome" not in low:
        tier, why = "medium", "notice that results are coming, not the results themselves"
    if cat == "investor_meetings" and re.search(r"transcript|recording|earnings (call|discussion|conference)", low):
        cat, tier, why = "earnings_call", "medium", "earnings-call material filed under the investor-meet heading"
    if cat == "fund_raise" and re.search(r"repay|redeem|redemption|maturity", low):
        tier, why = "routine", "repayment of existing borrowing, not a new raise"
    if cat == "litigation" and re.search(r"lakh", low) and not re.search(r"crore|insolvency|nclt|nclat", low):
        tier, why = "routine", "penalty stated in lakhs, immaterial at this size"
    if cat == "earnings_call" and not re.search(r"transcript", low):
        tier, why = "routine", "call logistics or recording link"
    return {"category": cat, "tier": tier, "why": why}


def seed_from_screener(con, symbols, pause: float = 1.2, force: bool = False) -> dict:
    con.executescript(SCHEMA)
    stats = {"companies": 0, "items": 0, "failed": []}
    for s in symbols:
        try:
            c = screener.fetch_company(s, force=force)
        except Exception as e:  # one company failing must not stop the seed
            stats["failed"].append(f"{s}: {type(e).__name__}")
            continue
        stats["companies"] += 1
        for a in c["documents"]["announcements"]:
            k = classify(a["title"], a["note"])
            con.execute("INSERT OR REPLACE INTO announcements VALUES (?,?,?,?,?,?,?,?,?)",
                        (a["url"], s, a["ts"], a["title"], a["note"], k["category"], k["tier"], k["why"], "screener"))
            stats["items"] += 1
        con.commit()
        if force:
            time.sleep(pause)
    return stats


def coverage(con) -> dict:
    con.executescript(SCHEMA)
    r = con.execute("SELECT COUNT(*) n, COUNT(DISTINCT symbol) c, MIN(ts) a, MAX(ts) b FROM announcements").fetchone()
    per = {x["symbol"]: x["a"] for x in con.execute("SELECT symbol, MIN(ts) a FROM announcements GROUP BY symbol")}
    return {"items": r["n"], "companies": r["c"], "oldest": r["a"], "newest": r["b"], "oldest_per_symbol": per,
            "complete": False,
            "statement": "Partial: the five most recent filings per company. Older filings in a window may be missing."}
