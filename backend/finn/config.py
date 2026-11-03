"""Central configuration. Everything is environment-driven so the same code runs
locally (ingestion on a laptop) and on the deployed server (read-mostly)."""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

DATA_DIR = Path(os.getenv("FINN_DATA_DIR", BACKEND_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR = DATA_DIR / "files"
FILES_DIR.mkdir(parents=True, exist_ok=True)

DB_URL = os.getenv("FINN_DB_URL", f"sqlite:///{DATA_DIR / 'finn.db'}")
# Hosted Postgres (e.g. Neon) URLs come as postgres:// or postgresql://; use the psycopg 3 driver.
for _p in ("postgres://", "postgresql://"):
    if DB_URL.startswith(_p):
        DB_URL = "postgresql+psycopg://" + DB_URL[len(_p):]
PORTFOLIO_FILE = Path(os.getenv("FINN_PORTFOLIO", Path(__file__).parent / "portfolio.yaml"))
FRONTEND_DIST = Path(os.getenv("FINN_FRONTEND_DIST", REPO_DIR / "frontend" / "dist"))

# --- LLM routing -----------------------------------------------------------
# Cheap model for bulk extraction (classification, guidance, filing numbers);
# stronger model only where reasoning is needed (Q&A, bull/bear, judgement calls).
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_FAST = os.getenv("FINN_MODEL_FAST", "gemini-3.5-flash-lite")
MODEL_REASON = os.getenv("FINN_MODEL_REASON", "gemini-3.6-flash")

# --- Live refresh on the server -------------------------------------------
# When on, read endpoints kick off a background refresh if data is stale.
LIVE_REFRESH = os.getenv("FINN_LIVE_REFRESH", "1") == "1"
ANNOUNCEMENT_TTL_MIN = int(os.getenv("FINN_ANNOUNCEMENT_TTL_MIN", "30"))
PRICE_TTL_MIN = int(os.getenv("FINN_PRICE_TTL_MIN", "240"))

LLM_TIMEOUT_S = int(os.getenv("FINN_LLM_TIMEOUT_S", "90"))

# --- Security --------------------------------------------------------------
# /api/cron and admin-only routes require this secret (header X-Cron-Secret, or ?key=).
# Unset = those routes are disabled, never open.
CRON_SECRET = os.getenv("FINN_CRON_SECRET", "")
# Cross-origin access. Empty = same-origin only (the default deployment serves UI and API together).
CORS_ORIGINS = [o.strip() for o in os.getenv("FINN_CORS_ORIGINS", "").split(",") if o.strip()]
# Model budget for public visitors, so nobody can exhaust the free quota during review.
ASK_PER_IP_HOUR = int(os.getenv("FINN_ASK_PER_IP_HOUR", "20"))
RESEARCH_PER_IP_HOUR = int(os.getenv("FINN_RESEARCH_PER_IP_HOUR", "6"))
LLM_RUNS_PER_DAY = int(os.getenv("FINN_LLM_RUNS_PER_DAY", "150"))

# Hard caps that keep cost and latency bounded.
MAX_PDF_MB = int(os.getenv("FINN_MAX_PDF_MB", "60"))
MAX_TRANSCRIPTS = int(os.getenv("FINN_MAX_TRANSCRIPTS", "5"))
MAX_LLM_VERIFY = int(os.getenv("FINN_MAX_LLM_VERIFY", "6"))

DEFAULT_PREFS = {
    "price_move_pct": 5.0,
    "volume_multiple": 2.0,
    "default_window_hours": 24,
    "alert_categories": [
        "results", "M&A", "management_change", "fund_raise",
        "litigation", "credit_rating", "pledging",
    ],
    # Per-category score nudges learned from "more/less like this" feedback.
    "category_weights": {},
    "muted_symbols": [],
}
