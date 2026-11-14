# FINN — design decisions log

Running log of non-obvious choices: what, why, cost, rejected alternatives.
Facts marked **verified** were observed from this machine on 15 Nov 2026 (scripts in `spikes/recon/`).

## 1. Product point of view

FINN is an editor, not a feed. Push is a ranked brief ("N filings read, M matter") with
type-specific cards; routine filings are collapsed but counted. Pull is a research view whose
hero is a Promise Ledger: what management guided vs. what the reported numbers delivered.

## 2. Access policy: plain client, open endpoints only

Every request uses a self-identifying User-Agent (`finn-prototype/0.1`) and accepts the server's
answer. No browser impersonation, no cookie warm-up, no spoofed referers.

- **Why:** NSE and BSE put their JSON APIs behind Akamai bot protection (**verified**: 403
  "Access Denied" for a plain client). Getting in means pretending to be a browser. That is a
  cat-and-mouse dependency that breaks from cloud IPs and is not ours to bypass.
- **Cost:** no complete announcement history (see §4).
- **Also:** screener's `robots.txt` disallows `?q=` URLs and `/company/source/quarter/*`, so
  ticker search is resolved locally from NSE's symbol master and the "Raw PDF" links are not used.

## 3. Prices: NSE full bhavcopy, not yfinance

`https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_DDMMYYYY.csv` — one ~400 KB
file per session covering every NSE symbol, with delivery %. **Verified** back to Nov 2025.

- **Why not yfinance:** Yahoo returned 429 from this machine; it is an unofficial API. The
  bhavcopy is the exchange's own file and makes "any NSE ticker" free.
- **Trap 1 (verified):** the URL date cannot be trusted. 10-Nov-2026 returns a 200 whose
  content is byte-identical to 09-Nov. Rows are keyed on the `DATE1` column inside the file.
  In the first real ingest (71 calendar days) this happened on 13 of the 24 non-session days;
  the other 11 were 404s. Result: 47 sessions, 7 Sep to 13 Nov, prev_close chain consistent.
- **Trap 2 (verified):** weekday ≠ trading day. Sunday 08-Nov-2026 has a real session (0.11–0.28×
  normal volume, consistent with Muhurat trading); Saturday 07-Nov is a 404. The ingest walks
  every calendar day and lets the file decide.
- **Consequence:** the volume baseline is the **median** of the previous 20 sessions, not the
  mean, so one special session or one prior spike does not distort "unusual".
- **Known limit:** bhavcopy prices are unadjusted for splits/bonuses.

## 4. Announcements: what is and is not available

| Source | Verified behaviour |
|---|---|
| NSE RSS `Online_announcements.xml` | Live, rebuilt every 5 min, **no history** (0 items at 00:09 Sunday) |
| screener company page | 5 most recent per company, full timestamps, one-line summary |
| NSE / BSE JSON APIs | Refuse a plain client |

Decision: seed from screener (labelled partial), accumulate from RSS going forward. The app
states its coverage instead of implying completeness.

## 5. Fundamentals and documents

- screener company page → five tables parse cleanly (**verified** on KAYNES). Screener lags new
  results by days (KAYNES latest quarter was Jun 2026 on 15 Nov).
- Transcript and annual-report PDFs on bseindia.com download with a plain client (**verified**, 4 files).
- Text via poppler `pdftotext` (0.1 s for a 30-page transcript ≈ 25k tokens; 0.7 s for a 322-page
  annual report ≈ 472k tokens). Chosen over PyMuPDF (AGPL) and pypdf (slow). Annual reports need
  section selection before any model reads them.

## 6. LLM use

Numbers are computed deterministically; models are used for language only, routed cheap → strong,
cached by content hash. Groq key only for now; OpenAI unused until a spend cap is set.
