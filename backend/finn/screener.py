"""screener.in company page -> standardised financial tables + primary-document links.

Only the public company page is read. Screener's own "about" text and AI summaries are
secondary commentary and are deliberately not parsed (docs/DESIGN.md section 5).
"""
import html
import json
import re
import time
from urllib.parse import quote

import httpx

from . import config

BASE = "https://www.screener.in/company/{sym}/{variant}"
TABLE_SECTIONS = {
    "quarters": "quarters", "profit_loss": "profit-loss", "balance_sheet": "balance-sheet",
    "cash_flow": "cash-flow", "ratios": "ratios",
}
CACHE_TTL = 12 * 3600


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def _num(s: str):
    s = s.replace(",", "").replace("%", "").replace("₹", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _section(page: str, sid: str) -> str | None:
    m = re.search(r'<section[^>]*\bid="%s".*?</section>' % re.escape(sid), page, re.S)
    return m.group(0) if m else None


def parse_table(section_html: str) -> dict | None:
    tb = re.search(r"<table.*?</table>", section_html, re.S)
    if not tb:
        return None
    trs = re.findall(r"<tr.*?</tr>", tb.group(0), re.S)
    rows = [[_clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S)] for tr in trs]
    if not rows or len(rows[0]) < 2:
        return None
    periods = rows[0][1:]
    out = {}
    for r in rows[1:]:
        label = r[0].rstrip("+").strip()
        if not label or label == "Raw PDF":
            continue
        vals = [_num(v) for v in r[1:]]
        out[label] = vals + [None] * (len(periods) - len(vals))
    return {"periods": periods, "rows": out}


def parse_documents(page: str) -> dict:
    doc = _section(page, "documents") or ""
    parts = {}
    for p in re.split(r"<h3[^>]*>", doc)[1:]:
        parts[_clean(p.split("</h3>")[0]).lower()] = p
    ann = []
    for li in re.findall(r"<li.*?</li>", parts.get("announcements", ""), re.S):
        a = re.search(r'<a[^>]*href="([^"]+)"', li)
        tm = re.search(r'<time[^>]*datetime="([^"]+)"', li)
        if not a or not tm:
            continue
        title = _clean(li.split("<div")[0])
        note = _clean(re.sub(r"<time.*?</time>", "", "<div" + li.split("<div", 1)[1]) if "<div" in li else "").lstrip("- ").strip()
        ann.append({"title": title, "ts": tm.group(1), "url": html.unescape(a.group(1)), "note": note})
    ars = []
    for li in re.findall(r"<li.*?</li>", parts.get("annual reports", ""), re.S):
        a = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', li, re.S)
        if a and (y := re.search(r"Annual Report (\d{4})", _clean(a.group(2)))):
            ars.append({"year": int(y.group(1)), "url": html.unescape(a.group(1))})
    calls = []
    for li in re.findall(r"<li.*?</li>", parts.get("concalls", ""), re.S):
        label = re.search(r"<div[^>]*>([^<]+)</div>", li)
        links = {_clean(t).lower(): html.unescape(h) for h, t in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', li, re.S)}
        if label:
            calls.append({"label": label.group(1).strip(), "transcript": links.get("transcript"), "ppt": links.get("ppt")})
    return {"announcements": ann, "annual_reports": ars, "concalls": calls}


def parse_company(page: str) -> dict:
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", page, re.S)
    info = re.search(r'<div[^>]*id="company-info"[^>]*>', page, re.S) or re.search(r'<div[^>]*data-consolidated[^>]*>', page, re.S)
    ratios = {}
    top = re.search(r'<ul id="top-ratios">.*?</ul>', page, re.S)
    for li in re.findall(r"<li.*?</li>", top.group(0) if top else "", re.S):
        name = re.search(r'<span class="name">(.*?)</span>', li, re.S)
        nums = re.findall(r'<span class="number">(.*?)</span>', li, re.S)
        if name and nums:
            vals = [_num(_clean(n)) for n in nums]
            ratios[_clean(name.group(1))] = vals[0] if len(vals) == 1 else vals
    tables = {}
    for key, sid in TABLE_SECTIONS.items():
        sec = _section(page, sid)
        tables[key] = parse_table(sec) if sec else None
    return {
        "name": _clean(h1.group(1)) if h1 else None,
        "consolidated": bool(info and 'data-consolidated="true"' in info.group(0)),
        "top_ratios": ratios, "tables": tables, "documents": parse_documents(page),
    }


def _has_numbers(c: dict) -> bool:
    q = c["tables"].get("quarters")
    return bool(q and q["periods"] and any(v is not None for row in q["rows"].values() for v in row))


def fetch_company(symbol: str, force: bool = False) -> dict:
    """Consolidated page first; standalone if the consolidated one carries no numbers."""
    symbol = symbol.upper().strip()
    cache = config.CACHE_DIR / "screener" / (re.sub(r"[^A-Z0-9]", "_", symbol) + ".json")
    if not force and cache.exists() and time.time() - cache.stat().st_mtime < CACHE_TTL:
        return json.loads(cache.read_text())
    out = None
    try:
        with httpx.Client(headers={"User-Agent": config.USER_AGENT}, timeout=30, follow_redirects=True) as client:
            for variant in ("consolidated/", ""):
                r = client.get(BASE.format(sym=quote(symbol, safe=""), variant=variant))
                if r.status_code == 404:
                    raise LookupError(f"{symbol}: not found on screener.in")
                r.raise_for_status()
                out = parse_company(r.text)
                if _has_numbers(out):
                    break
                time.sleep(1.0)
    except httpx.HTTPError:
        # the source refused or is unreachable: serve the last saved copy, marked stale
        if cache.exists():
            stale = json.loads(cache.read_text())
            stale["stale"] = True
            return stale
        raise
    out["symbol"] = symbol
    out["fetched_at"] = int(time.time())
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out
