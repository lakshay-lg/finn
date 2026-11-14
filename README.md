# FINN

Mobile-first investment agent prototype for a 20-stock NSE portfolio.

## Run

```
PYTHONPATH=backend uv run python backend/run_ingest.py 70      # prices, about a minute
PYTHONPATH=backend uv run python -c "from finn import announcements as a, config, db; print(a.seed_from_screener(db.connect(), config.PORTFOLIO, force=True))"
PYTHONPATH=backend uv run uvicorn finn.main:app --port 8000
```

Open http://localhost:8000 at phone width. Tests: `uv run pytest`.

Needs poppler (`pdftotext`) for document text. Decisions and known gaps: `docs/DESIGN.md`.
