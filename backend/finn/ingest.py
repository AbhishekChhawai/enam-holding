"""Ingestion CLI. Run on your own machine (Indian residential IPs are welcome at BSE/screener),
then commit backend/data/finn.db so the deployed app starts with real data.

    python -m finn.ingest                  # everything: seed, prices, 30d filings, enrich, research demo
    python -m finn.ingest --step prices
    python -m finn.ingest --step filings --days 30
    python -m finn.ingest --step enrich
    python -m finn.ingest --step research --symbols DIXON KAYNES
"""
from __future__ import annotations

import argparse
import logging
import time

from . import llm
from .db import init_db
from .pull import agent, promises
from .push import refresh, rules

log = logging.getLogger("finn.ingest")


def research(symbols: list[str]) -> None:
    for sym in symbols:
        t = time.time()
        try:
            agent.overview(sym)
            log.info("[%s] overview ok", sym)
            if llm.available():
                pr = promises.run(sym, force=True)
                log.info("[%s] promises: %s", sym, (pr.get("scorecard") or {}).get("headline"))
                agent.business(sym, force=True)
                log.info("[%s] business snapshot ok", sym)
                agent.bull_bear(sym, pr, force=True)
                log.info("[%s] bull/bear ok", sym)
                from .pull import narrative
                nr = narrative.run(sym, force=True)
                log.info("[%s] narrative: %s", sym, nr.get("headline"))
        except Exception as e:  # noqa: BLE001
            log.warning("[%s] research failed: %s", sym, e)
        log.info("[%s] done in %.0fs", sym, time.time() - t)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", choices=["all", "seed", "prices", "filings", "enrich", "research"], default="all")
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--symbols", nargs="*")
    args = ap.parse_args()
    init_db()
    if not llm.available():
        log.warning("GEMINI_API_KEY not set: running deterministic steps only")
    if args.step in ("all", "seed"):
        log.info("Seeded %d companies", len(refresh.seed_companies(verify_codes=True)))
    if args.step in ("all", "prices"):
        refresh.refresh_prices(period="1y")
    if args.step in ("all", "filings"):
        refresh.refresh_announcements(days=args.days)
    if args.step in ("all", "enrich"):
        log.info("Enriched %d filings", refresh.enrich_pending(limit=60, since_days=args.days))
    if args.step in ("all", "enrich", "filings", "prices"):
        log.info("Alert rules: %s", rules.evaluate(sessions=5, filing_days=min(args.days, 7)))
    if args.step in ("all", "research"):
        syms = args.symbols or refresh.load_portfolio_file().get("research_demo", [])
        research([s.upper() for s in syms])
    log.info("LLM usage: %s", llm.usage_summary())


if __name__ == "__main__":
    main()
