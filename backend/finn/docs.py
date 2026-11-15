"""Primary documents: download once, extract text with poppler, cache by URL hash."""
import hashlib
import re
import subprocess

import httpx

from . import config

DOC_DIR = config.CACHE_DIR / "docs"

# Words that mark a forward-looking or guidance-bearing statement in an earnings call.
FORWARD = re.compile(
    r"guidance|guid(e|ed|ing)\b|outlook|expect|anticipat|target|aspir|we will|we would|going forward|"
    r"next (quarter|year|fiscal)|full[- ]year|by (the )?end of|FY ?\d\d|H[12] ?FY|medium[- ]term|"
    r"band|range of|trajectory|on track|confident|visibility|pipeline|capex|headcount|margin", re.I)
NUMBER = re.compile(r"\d")


def fetch_text(url: str) -> list[str]:
    """Return the document as a list of page texts. Raises on download or extraction failure."""
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()[:20]
    txt = DOC_DIR / f"{key}.txt"
    if not txt.exists():
        pdf = DOC_DIR / f"{key}.pdf"
        with httpx.Client(headers={"User-Agent": config.USER_AGENT}, timeout=120, follow_redirects=True) as c:
            r = c.get(url)
            r.raise_for_status()
            if not r.content.startswith(b"%PDF"):
                raise ValueError(f"not a PDF: {url}")
            pdf.write_bytes(r.content)
        out = subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], capture_output=True)
        pdf.unlink(missing_ok=True)  # keep the text, not the PDF
        if out.returncode != 0 or not txt.exists():
            raise RuntimeError(f"pdftotext failed: {out.stderr.decode()[:200]}")
    return txt.read_text("utf-8", "replace").split("\f")


def paragraphs(pages: list[str]) -> list[str]:
    """Join wrapped lines into paragraphs; drop page furniture."""
    paras, cur = [], []
    for page in pages:
        for line in page.splitlines():
            s = re.sub(r"\s+", " ", line).strip()
            if not s:
                if cur:
                    paras.append(" ".join(cur)); cur = []
                continue
            if re.fullmatch(r"(Page )?\d+( of \d+)?", s):
                continue
            cur.append(s)
    if cur:
        paras.append(" ".join(cur))
    return [p for p in paras if len(p) > 60]


def forward_looking(pages: list[str]) -> list[str]:
    """Paragraphs that carry a forward-looking word AND a number: where guidance lives."""
    return [p for p in paragraphs(pages) if FORWARD.search(p) and NUMBER.search(p)]
