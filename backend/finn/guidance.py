"""Guidance extraction from earnings-call transcripts.

Pipeline: keyword filter (no model) -> one model call per ~4.5k-token chunk -> every item's
quote is checked verbatim against the transcript in code. Items whose quote is not found
are dropped, so nothing reaches the screen that the transcript does not say.
"""
import re

from . import docs, llm

CHUNK_CHARS = 16000  # ~4,000 tokens, leaves room for the prompt and a 3,000-token answer under 8k/min

SYSTEM = """You extract management guidance from an Indian company's earnings-call transcript excerpt.
Use ONLY the excerpt. Do not use anything you know about the company.
Return JSON: {"items": [ ... ]}. Each item:
- "metric": one of revenue (an absolute revenue amount), revenue_growth (a growth %), operating_margin (EBIT margin), ebitda_margin, pat, capex, headcount, order_book, deal_wins, volume, cash_flow, other
- "target_period": the period the statement is about, as said (e.g. "FY27", "Q3 FY27", "next 2 years"); "" if not stated
- "low" and "high": numbers if a numeric target or range is given, else null (a single number goes in both)
- "unit": "%", "Rs crore", "USD million", etc; "" if none
- "summary": at most 20 words, plain, what management committed to or expects
- "quote": a VERBATIM run of 8 to 30 consecutive words copied exactly from the excerpt that supports it
- "speaker": name or role if clear, else ""
- "kind": "explicit_guidance" (a stated target, range or commitment) or "commentary" (directional expectation without a number)
- "scope": "company" if the number is the target for the WHOLE company's metric (e.g. full-year revenue growth guidance, the margin band); "component" if it is the effect of one deal, acquisition, segment or cost item (e.g. "the acquisition adds 1%", "50 bps impact")
- "basis": "constant_currency" if the excerpt says the guidance is in constant currency, "reported" if it says reported/rupee terms, else "unspecified"
Include only forward-looking statements by management about the company's own headline numbers.
Skip reported results (what the period already delivered), analyst questions, and anything vague.
If management recalls guidance it gave earlier ("we had guided X, now we expect Y"), extract the CURRENT expectation, and use the quote that states it. At most 8 items; prefer explicit_guidance."""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9%.]+", " ", s.lower()).strip()


def _chunks(paras: list[str]) -> list[str]:
    out, cur, n = [], [], 0
    for p in paras:
        if n + len(p) > CHUNK_CHARS and cur:
            out.append("\n\n".join(cur)); cur, n = [], 0
        cur.append(p); n += len(p)
    if cur:
        out.append("\n\n".join(cur))
    return out


def is_earnings_call(pages: list[str]) -> bool:
    head = " ".join(" ".join(pages[:2]).split())[:1500].lower()
    return bool(re.search(r"earnings (call|conference)|results (call|conference)|conference call|financial results", head))


def extract(url: str, label: str) -> dict:
    """Guidance items for one transcript, each verified against the source text."""
    pages = docs.fetch_text(url)
    paras = docs.forward_looking(pages)
    haystack = _norm(" ".join(docs.paragraphs(pages)))
    kept, dropped = [], 0
    for i, chunk in enumerate(_chunks(paras)):
        res = llm.chat_json([{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": f"Call: {label}. Excerpt part {i + 1}:\n\n{chunk}"}])
        for it in res.get("items", []):
            q = _norm(str(it.get("quote", "")))
            if len(q.split()) >= 6 and q in haystack:
                it["call"] = label
                kept.append(it)
            else:
                dropped += 1
    return {"call": label, "url": url, "items": kept, "dropped_unverified": dropped,
            "chunks": len(_chunks(paras)), "earnings_call": is_earnings_call(pages)}
