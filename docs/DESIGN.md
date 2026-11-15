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

## 7. Frontend: no build step

Plain HTML, CSS and ES modules in `web/`, served by the API. Three destinations: Brief, Research,
Thresholds. Chosen over React + Vite because nothing has to compile before a deploy and the UI is
small. Cost: no component library, hand-written SVG charts.

## 8. Things the UI is deliberately honest about

- **Results numbers:** a results card shows figures only when screener carries the quarter the
  filing reports (found when KAYNES' Sep-quarter filing was about to show Jun-quarter numbers).
  Otherwise it says the numbers are pending. They are labelled as screener's standardised table,
  not parsed from the filing; parsing the filing itself is not built.
- **Summaries:** the one-line text under each filing is screener's, and is labelled so. The
  exchange's own title leads.
- **Price moves outside the window** are listed separately and not counted in the opening sentence.
- **Coverage** is stated on the Brief screen as partial.
- **Banks:** net interest income replaces EBITDA; leverage and cash conversion are not shown.

## 9. Classifier accuracy

Rules only, no model. Hand-checked on the 100 seeded filings: about 87 tiers right on the first
pass. General rule fixes corrected the errors found except one left as is (IndiGo's results press
release is tagged as an update, not results). The rules were tuned on this same sample, so
accuracy on new filings is unmeasured.

## 9a. Promise ledger

- **Model does extraction only.** Groq free tier, `openai/gpt-oss-120b`, 8,000 tokens per minute.
  A keyword filter keeps the 22-33% of each transcript that carries forward-looking statements
  with numbers, so a call fits in one or two requests. Infosys, six calls: about 5 minutes and
  roughly 118k tokens in total across three runs; replies are cached, so a rebuild is instant.
- **Every quote is checked verbatim against the transcript in code.** Unmatched items are dropped
  (4 of 44 for Infosys).
- **Verdicts are arithmetic, not model output.** Operating margin is scored on
  (operating profit - depreciation) / revenue, because management guides EBIT margin and
  screener's margin is before depreciation.
- **No verdict when the bases differ.** Revenue guided in constant currency is shown next to
  rupee growth and marked "not comparable".
- **The model's tags are not trusted alone.** It mislabels deal-level impacts as company guidance,
  so the ledger also requires a plausible range and prefers quotes that say "guidance".
- **Strict JSON mode rejected valid work** on 2 of 6 calls; the client falls back to plain mode and
  parses the reply itself.
- **Second company: Kaynes, on the smaller model.** The large model's free allowance is
  200,000 tokens a day and ran out, so Kaynes was extracted on `gpt-oss-20b` (six calls,
  about 2.5 minutes). Its tagging is worse, so the ledger leans on rules, not the model's labels:
  a scored statement must be worded as a promise ("expect", "target", "guided", "will"...), and
  a company revenue target below half of last year's revenue is treated as a segment figure.
  Every Kaynes row was checked by hand against its quote. Result: revenue guided Rs 4,500 cr,
  cut to Rs 4,100 cr, delivered Rs 3,626 cr (missed); EBITDA margin "15.6% or so", delivered 15.9%.
- **Model failure found and fixed:** at its default reasoning effort the model sometimes spent its
  entire output allowance thinking and returned nothing; reasoning effort is now low and a cut-off
  reply is detected.
- **Still unproven** on companies that only give directional commentary.

## 10. Not built yet

Bull vs bear, business snapshot; ledgers for companies other than Infosys; results
parsed from the filing PDF; management-change background; RSS poller for live announcements
(its item format could not be observed on a weekend); push notifications; deployment.

## 11. Security review (against a 25-item app checklist)

No logins, payments, uploads or per-user data, so 16 items do not apply. Of the rest:
secrets, parameterised SQL, HTML escaping and error responses passed. Fixed after the review:

- **Fetch cap:** each uncached company costs a request to screener.in, so new-company lookups are
  capped at 12 per 10 minutes across all visitors (429 beyond that). Saved companies are unaffected.
- **Input bounds** on every query parameter (422 outside range).
- **Link scheme guard:** links from scraped pages render only if they are http(s).
- **Security headers:** content security policy, no-sniff, no framing, no referrer.
- **Container runs as a non-root user.**

Not done: per-visitor rate limiting (the cap is global), and nothing limits model spend because
the hosted app makes no model calls.

## 12. Launch checklist pass (20-item site checklist)

Twelve items apply. Passed as built: no horizontal overflow at 360px, sampled links resolve
(8 of 8; not all 102 were tested), bottom-tab navigation, favicon, working controls, no
placeholder text. Fixed: per-screen page titles, a meta description, a custom not-found page
(unknown API paths still answer in JSON), a message when a search matches nothing, and 44px
tap targets on filing and document links. Found along the way: browsers kept stale page files
after an update, so page files are now sent with `Cache-Control: no-cache`.
