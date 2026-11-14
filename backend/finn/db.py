"""SQLite storage. One file, stdlib only."""
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    symbol TEXT NOT NULL,
    date TEXT NOT NULL,            -- ISO date taken from DATE1 inside the bhavcopy
    open REAL, high REAL, low REAL, close REAL, prev_close REAL,
    volume INTEGER, delivery_pct REAL,
    PRIMARY KEY (symbol, date)
);
CREATE TABLE IF NOT EXISTS sessions (
    date TEXT PRIMARY KEY,         -- trading sessions actually seen in the archive
    rows INTEGER
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path) if path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con
