# FINN

A mobile-first investment agent for an Indian equity investor. It reads the filings and
end-of-day moves across a 20-stock NSE portfolio and shows the few that matter, and it
researches any NSE company from its own reports and earnings calls.

**Try it on a phone:** https://finn-buy3.onrender.com
(free hosting: if nobody has opened it for a while, the first load can take up to a minute)
On Android, Chrome offers "Install app" (or menu, then "Add to Home screen"); on iPhone, Safari's
Share, then "Add to Home Screen". It then opens full screen like an app.

Built for the ENAM Holdings AI Engineer build challenge, November 2026.

## What to look at

| Screen | What it does |
|---|---|
| **Brief** | Opens with one sentence: how many filings arrived in the window you pick (24 hours to 30 days) and how many need attention. Material filings and unusual price moves come first; routine paperwork is collapsed into one line you can open. Results cards show revenue, EBITDA, PBT and PAT against last quarter and last year. |
| **Research** | Any of the 2,635 NSE equity symbols: latest quarter, multi-year trajectory, cash quality, balance sheet, links to transcripts and annual reports. For **Infosys** and **Kaynes** it also shows a promise ledger (below). |
| **Thresholds** | Set what "unusual" means (volume multiple, price move) and see which stocks would have alerted on the last session. |

Suggested path: Brief at 7 days, then Research for **KAYNES**, then **INFY**, then a company
outside the portfolio such as **ASIANPAINT** or **TRENT**, then Thresholds.

### The promise ledger

The brief's most valued output is "what management promised vs what they delivered". FINN
reads the last six earnings calls, extracts each numeric guidance statement, and sets it
against the reported number:

- **Kaynes, FY26 revenue:** guided Rs 4,500 cr (Aug 2025), cut to Rs 4,100 cr (Feb 2026),
  delivered Rs 3,626 cr. Missed.
- **Infosys, FY26 operating margin:** guided 20-22%, delivered 20.9%. Revenue growth is shown
  but marked *not comparable*, because Infosys guides in constant currency and the reported
  figure is in rupees.

Every quote shown is checked word for word against the transcript in code, and every verdict
is arithmetic on reported numbers, not model output.

## How it works

```
NSE price archive ──► prices + alerts ─────────────┐
screener.in pages ──► financials, filings, docs ───┼──► FastAPI ──► phone UI (web/)
filing classifier (rules) ──► tiers ───────────────┘       ▲
                                                           │ saved ledgers
transcripts ──► keyword filter ──► Groq model ──► quote check ──► ledger rules
                      (offline, on the developer's machine)
```

- **Prices:** NSE's own daily price files ("bhavcopy"), which cover every listed symbol, not an
  unofficial price API.
- **Filings:** classified by rules into the reference document's categories, then into three
  tiers: needs attention, worth a look, routine.
- **Model use:** one job only, extracting guidance from transcripts. It runs offline on Groq's
  free tier; results ship with the app, so the hosted site makes no model calls. Spend: $0.
- **Hosting:** one Docker image on Render, with a data snapshot so it has content on a cold start,
  and a refresh every three hours.

## Decisions worth knowing

- **Open sources only.** NSE's and BSE's announcement APIs sit behind bot protection. FINN does
  not impersonate a browser to get past it, so filing coverage is partial (the five most recent
  per company) and the Brief says so on screen.
- **Numbers before language.** All financial figures are computed in code; the model only reads
  text. Where a comparison isn't like for like (constant currency vs rupees, banks vs EBITDA),
  the app says so instead of giving a verdict.
- **Results cards check the quarter.** Numbers appear only when the data source already has the
  quarter the filing reports; otherwise the card says they are pending.
- **No build step for the frontend.** Plain HTML, CSS and JavaScript served by the API.

The full reasoning, with what was tried and rejected, is in [`docs/DESIGN.md`](docs/DESIGN.md).

## Known limits

- Promise ledgers exist for two companies. Other companies show "not extracted yet"; building one
  takes a few minutes on the free tier and is done offline.
- Filing coverage is partial, as above, and the classifier was tuned on the same 100 filings it
  was checked against.
- Results numbers come from screener.in's standardised tables, not from parsing the filing PDF.
- Not built: the management-change background card, bull vs bear, live filing alerts, push
  notifications, an editable portfolio.

## Run it locally

Needs Python 3.11+, [uv](https://docs.astral.sh/uv/) and poppler (`pdftotext`).

```
cp -r seed data                                   # the shipped data snapshot (fresh clone only)
PYTHONPATH=backend uv run uvicorn finn.main:app --port 8000
```

Open http://localhost:8000 at phone width. On start it refreshes prices and filings in the
background; if a source doesn't answer, the snapshot is used as is.

Or with Docker: `docker build -t finn . && docker run -p 8000:8000 finn`.

Other commands:

```
uv run pytest                                                   # 21 tests
PYTHONPATH=backend uv run python backend/run_ingest.py 70       # backfill ~70 days of prices
GROQ_API_KEY=... PYTHONPATH=backend uv run python backend/run_guidance.py INFY 6   # build a ledger
./make_seed.sh                                                  # refresh the shipped snapshot
```

## Layout

```
backend/finn/   prices, alerts, announcements, screener, metrics, guidance, ledger, llm, main (API)
web/            the phone UI
seed/           data snapshot shipped in the image
docs/DESIGN.md  decision log
spikes/         early scripts used to test the data sources
```
