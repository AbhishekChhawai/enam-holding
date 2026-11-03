"""Push ingestion pipeline: portfolio seed -> prices -> announcements -> classify -> enrich.

Safe to run repeatedly: announcements are upserted by BSE NEWSID, enrichment runs once per
filing, and every LLM output is cached.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import yaml
from pydantic import BaseModel, Field
from sqlalchemy import select

from .. import llm, store
from ..config import PORTFOLIO_FILE
from ..db import Announcement, Company, portfolio_symbols, session_scope, utcnow
from ..sources import bse_filings, prices
from ..sources.pdf import is_scanned, with_page_markers
from . import classify, mgmt, results

log = logging.getLogger("finn.refresh")


def load_portfolio_file() -> dict:
    with open(PORTFOLIO_FILE) as f:
        return yaml.safe_load(f)


def seed_companies(verify_codes: bool = True) -> list[str]:
    cfg = load_portfolio_file()
    bse = bse_filings.client() if verify_codes else None
    syms = []
    with session_scope() as s:
        for c in cfg.get("portfolio", []):
            sym = c["symbol"].upper()
            code = str(c.get("bse") or "") or None
            is_etf = c.get("kind") == "etf"
            if bse is not None and not is_etf:
                found = bse_filings.lookup_code(bse, sym)
                if found and found != code:
                    log.warning("BSE code for %s corrected: %s -> %s", sym, code, found)
                    code = found
            row = s.get(Company, sym) or Company(symbol=sym)
            row.name, row.sector, row.bse_code, row.in_portfolio = c.get("name", sym), c.get("sector", ""), (None if is_etf else code), True
            row.kind, row.asset_class, row.weight = c.get("kind", "stock"), c.get("asset_class", "Equity"), c.get("weight")
            row.meta = {k: c[k] for k in ("tracks", "underlying", "underlying_name", "note") if k in c} or None
            row.identity_sources = ["portfolio.yaml"] + (["bse_lookup"] if bse is not None else [])
            if bse is not None:
                row.validated_at = utcnow()
            row.updated_at = utcnow()
            s.merge(row)
            syms.append(sym)
    if bse is not None:
        bse.exit()
    return syms


def refresh_prices(symbols: list[str] | None = None, period: str = "1y") -> int:
    with session_scope() as s:
        symbols = symbols or portfolio_symbols(s)
        # benchmark and the indices behind international ETFs, for portfolio analysis and global context
        extra = {c.meta["underlying"] for c in s.scalars(select(Company)) if c.meta and c.meta.get("underlying")}
    cfg = load_portfolio_file().get("mock") or {}
    if cfg.get("benchmark", {}).get("symbol"):
        extra.add(cfg["benchmark"]["symbol"])
    data = prices.fetch_eod(list(symbols) + sorted(extra - set(symbols)), period=period)
    n = 0
    with session_scope() as s:
        for sym, bars in data.items():
            n += prices.store_bars(s, sym, bars)
    store.stamp("stamp:prices")
    log.info("Stored %d price bars for %d symbols", n, len(data))
    return n


def refresh_announcements(days: int = 2, symbols: list[str] | None = None) -> int:
    end = datetime.now()
    start = end - timedelta(days=days)
    with session_scope() as s:
        q = select(Company).where(Company.symbol.in_(symbols)) if symbols else select(Company).where(Company.in_portfolio.is_(True))
        companies = [(c.symbol, c.bse_code) for c in s.scalars(q)]
    bse = bse_filings.client()
    new_rows: list[dict] = []
    try:
        for sym, code in companies:
            if not code:
                continue
            try:
                raw = bse_filings.fetch(bse, code, start, end)
            except Exception as e:  # noqa: BLE001
                log.warning("Announcements failed for %s: %s", sym, e)
                continue
            for r in raw:
                n = bse_filings.normalize(r, sym)
                if n["published_at"] is None or not n["id"]:
                    continue
                new_rows.append(n)
    finally:
        bse.exit()

    added = 0
    leftovers: list[tuple[int, str]] = []
    with session_scope() as s:
        fresh = []
        for n in new_rows:
            if s.get(Announcement, n["id"]) is not None:
                continue
            cat = classify.rule_classify(n["subject"], n["headline"], n["bse_category"], n["bse_subcategory"])
            n["_cat"] = cat
            fresh.append(n)
        for i, n in enumerate(fresh):
            if n["_cat"] is None:
                leftovers.append((i, f"{n['subject']} | {n['headline']}"))
        llm_cats = {}
        try:
            llm_cats = classify.llm_classify(leftovers)
        except Exception as e:  # noqa: BLE001
            log.warning("LLM classification skipped: %s", e)
        for i, n in enumerate(fresh):
            cat, method = n["_cat"], "rule"
            if cat is None:
                cat, method = (llm_cats.get(i), "llm") if i in llm_cats else ("unclassified", "default")
            score, reasons = classify.score(cat, n["subject"], n["headline"], n.get("critical", False))
            s.add(Announcement(
                id=n["id"], symbol=n["symbol"], published_at=n["published_at"], headline=n["headline"],
                subject=n["subject"], bse_category=n["bse_category"], bse_subcategory=n["bse_subcategory"],
                attachment_url=n["attachment_url"], source_url=n["source_url"], category=cat,
                category_method=method, base_score=score, reasons=reasons, retrieved_at=utcnow(),
            ))
            added += 1
    if symbols:
        for sym in symbols:
            store.stamp(f"stamp:announcements:{sym}")
    else:
        store.stamp("stamp:announcements")
    log.info("Added %d new announcements (%d needed the model)", added, len(leftovers))
    return added


# ------------------------------------------------------------------ enrichment
class _OneLine(BaseModel):
    summary: str = Field(description="One sentence, <= 30 words, what happened and the key number if any")


def _summarise(pages: list[str], headline: str) -> str | None:
    if not llm.available() or not pages or is_scanned(pages):
        return None
    prompt = ("Summarise this Indian stock-exchange filing for a portfolio manager in one sentence. "
              "State what happened and any key number (amount, %, date). No adjectives, no advice.\n"
              f"Headline: {headline}\n\nFILING:\n" + with_page_markers(pages[:3], max_chars=9000))
    return llm.generate(_OneLine, tier="fast", purpose="filing_summary", prompt=prompt, max_output_tokens=200).summary


def enrich_pending(limit: int = 25, since_days: int = 30, ids: list[str] | None = None) -> int:
    since = utcnow() - timedelta(days=since_days)
    with session_scope() as s:
        q = select(Announcement).where(Announcement.enrichment_status == "none", Announcement.attachment_url.is_not(None))
        q = q.where(Announcement.id.in_(ids)) if ids else q.where(Announcement.published_at >= since, Announcement.base_score >= 40)
        rows = list(s.scalars(q.order_by(Announcement.base_score.desc(), Announcement.published_at.desc()).limit(limit)))
        names = {c.symbol: c.name for c in s.scalars(select(Company))}
        todo = [(a.id, a.symbol, a.category, a.attachment_url, a.headline, a.base_score) for a in rows]
    done = 0
    for aid, sym, cat, url, headline, sc in todo:
        enrichment, status, summary = None, "unsupported", None
        try:
            did = store.register_doc(sym, "filing", url, title=headline[:280])
            meta, pages = store.load_pages(did)
            path = store.file_path_for(did)
            if meta["status"] == "failed":
                status = "failed"
            elif cat == "results" and sc >= 60:
                scr = None
                try:
                    scr = results.card_from_screener(store.get_screener(sym))
                except Exception as e:  # noqa: BLE001
                    log.info("screener unavailable for %s: %s", sym, e)
                filing = None
                try:
                    filing = results.card_from_filing(path, pages) if path else None
                except Exception as e:  # noqa: BLE001
                    log.warning("Results extraction failed for %s: %s", sym, e)
                enrichment = results.reconcile(filing, scr)
                if enrichment:
                    enrichment["doc_id"] = did
                status = "ok" if enrichment else "failed"
            elif cat == "management_change":
                enrichment = mgmt.enrich(path, pages, names.get(sym, sym)) if path else None
                if enrichment:
                    enrichment["doc_id"] = did
                status = "ok" if enrichment else "failed"
            if sc >= 55 and cat not in ("results",):
                summary = _summarise(pages, headline)
        except Exception as e:  # noqa: BLE001
            log.warning("Enrichment failed for %s (%s): %s", sym, aid, e)
            status = "failed"
        with session_scope() as s:
            a = s.get(Announcement, aid)
            a.enrichment, a.enrichment_status = enrichment, status
            if summary:
                a.summary = summary
        done += 1
    return done
