"""Load REAL NSE end-of-day prices for the portfolio from the open eod2_data archive (no API key needed).

    python scripts/import_eod2.py            # into the database at FINN_DB_URL
    python scripts/export_snapshot.py --note-file data/eod2_note.txt

Source: https://github.com/BennyThadikaran/eod2_data, compiled from NSE's official daily bhavcopy files
(prices adjusted for splits and bonuses). Downloaded, never typed. Rows are tagged "nse-bhavcopy:eod2_data".
It covers prices only; filings, reports and AI research come from `python -m finn.ingest`.
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import requests
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from finn.config import PORTFOLIO_FILE  # noqa: E402
from finn.db import Company, PriceBar, init_db, kv_set, session_scope  # noqa: E402

RAW = "https://raw.githubusercontent.com/BennyThadikaran/eod2_data/main/daily/{}.csv"
SOURCE = "nse-bhavcopy:eod2_data"
SINCE = "2025-01-01"           # enough for 1Y horizons and charts


def fetch(name: str) -> list[dict]:
    r = requests.get(RAW.format(name), timeout=60)
    r.raise_for_status()
    return [row for row in csv.DictReader(io.StringIO(r.text)) if row["Date"] >= SINCE and row.get("Close")]


def main() -> int:
    cfg = yaml.safe_load(open(PORTFOLIO_FILE))
    init_db()
    last, report = None, []
    with session_scope() as s:
        for c in cfg["portfolio"]:
            sym = c["symbol"].upper()
            row = s.get(Company, sym) or Company(symbol=sym)
            row.name, row.sector, row.in_portfolio = c.get("name", sym), c.get("sector", ""), True
            row.bse_code = None if c.get("kind") == "etf" else str(c.get("bse") or "") or None
            row.kind, row.asset_class, row.weight = c.get("kind", "stock"), c.get("asset_class", "Equity"), c.get("weight")
            row.meta = {k: c[k] for k in ("tracks", "underlying", "underlying_name", "note") if k in c} or None
            s.merge(row)
        targets = [(c["symbol"].upper(), c["symbol"].lower()) for c in cfg["portfolio"]]
        bench = (cfg.get("mock") or {}).get("benchmark") or {}
        if bench.get("symbol") == "^NSEI":
            targets.append(("^NSEI", "nifty 50"))
        for sym, fname in targets:
            rows = fetch(fname)
            for r in rows:
                s.merge(PriceBar(symbol=sym, date=r["Date"], open=float(r["Open"]), high=float(r["High"]), low=float(r["Low"]),
                                 close=float(r["Close"]), volume=float(r["Volume"] or 0), source=SOURCE))
            last = max(last or "", rows[-1]["Date"]) if rows else last
            report.append(f"{sym}: {len(rows)} sessions to {rows[-1]['Date'] if rows else 'none'}")
        kv_set(s, "stamp:prices", f"{last}T12:00:00Z")
    note = (f"Prices: official NSE end-of-day data (bhavcopy) via the open eod2_data archive, up to {last}. "
            "This snapshot has no exchange filings, reports or AI research; the daily GitHub run adds them.")
    Path("data").mkdir(exist_ok=True)
    Path("data/eod2_note.txt").write_text(note)
    print("\n".join(report))
    print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
