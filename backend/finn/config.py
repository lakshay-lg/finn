"""Static configuration: paths, the demo portfolio, default alert thresholds."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("FINN_DATA_DIR", ROOT / "data"))
CACHE_DIR = DATA_DIR / "cache"
DB_PATH = DATA_DIR / "finn.db"

# Self-identifying client. See docs/DESIGN.md section 2.
USER_AGENT = "Mozilla/5.0 (compatible; finn-prototype/0.1)"

PORTFOLIO = [
    "RELIANCE", "HDFCBANK", "INFY", "BHARTIARTL", "ITC", "LT", "SUNPHARMA", "M&M",
    "BAJFINANCE", "TITAN", "DIXON", "POLYCAB", "PERSISTENT", "ETERNAL", "TATAPOWER",
    "INDIGO", "KAYNES", "IEX", "HAL", "TATASTEEL",
]

DEFAULT_THRESHOLDS = {
    "volume_multiple": 2.0,   # alert when volume > this x the baseline
    "price_move_pct": 4.0,    # alert when |close / prev_close - 1| exceeds this
    "baseline_sessions": 20,  # sessions in the volume baseline (median)
}
