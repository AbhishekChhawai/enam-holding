"""Source confidence and data freshness.

Confidence is a small set of explainable labels, never a made-up percentage:
  verified     two independent sources agree (e.g. results filing vs screener.in)
  direct       taken straight from the source, not independently checked
  derived      computed in code from direct or verified data
  partial      some of the expected data is missing
  conflicting  sources disagree; both values are kept and shown
  unavailable  the source could not be reached or has no data
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select

from .db import Announcement, Company, Document, PriceBar, kv_get, kv_get_row, session_scope, utcnow
from . import llm

LEGEND = {
    "verified": "Two independent sources agree",
    "direct": "Taken straight from the source, not independently checked",
    "derived": "Computed in code from direct or verified data",
    "partial": "Some expected data is missing",
    "conflicting": "Sources disagree; both values are shown",
    "unavailable": "Source unreachable or has no data",
}
IST = timedelta(hours=5, minutes=30)


def expected_session(now_utc: datetime | None = None) -> date:
    """Latest session whose EOD data should exist. Weekends are modelled; exchange holidays are not."""
    ist = (now_utc or datetime.utcnow()) + IST
    d = ist.date()
    if ist.hour < 18:  # Yahoo's EOD bar settles in the evening IST
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def weekdays_between(a: date, b: date) -> int:
    """Weekdays strictly after a, up to and including b."""
    n, d = 0, a
    while d < b:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n


def price_freshness(last: str | None, now_utc: datetime | None = None) -> tuple[str, str]:
    exp = expected_session(now_utc)
    if not last:
        return "missing", exp.isoformat()
    behind = weekdays_between(date.fromisoformat(last), exp)
    status = "fresh" if behind == 0 else "possibly_stale" if behind == 1 else "stale"
    return status, exp.isoformat()


def price_checks(bars: list[PriceBar]) -> list[dict]:
    checks = []
    bad = [b.date for b in bars if None not in (b.open, b.high, b.low) and
           (b.low - 1e-6 > min(b.open, b.close) or b.high + 1e-6 < max(b.open, b.close) or b.low > b.high)]
    checks.append({"name": "OHLC consistency", "status": "fail" if bad else "pass",
                   "detail": f"{len(bad)} sessions where low/high do not bracket open/close: {', '.join(bad[:5])}" if bad else f"{len(bars)} sessions checked"})
    neg = [b.date for b in bars if b.volume is not None and b.volume < 0]
    zero = [b.date for b in bars if b.volume == 0]
    checks.append({"name": "Volume sanity", "status": "fail" if neg else "warn" if zero else "pass",
                   "detail": f"{len(neg)} negative, {len(zero)} zero-volume sessions" if (neg or zero) else "No negative or zero volumes"})
    gaps = []
    for a, b in zip(bars, bars[1:]):
        g = weekdays_between(date.fromisoformat(a.date), date.fromisoformat(b.date)) - 1
        if g >= 3:
            gaps.append(f"{a.date} to {b.date}")
    checks.append({"name": "Session gaps", "status": "warn" if gaps else "pass",
                   "detail": f"Gaps of 3+ weekdays (holidays or missing data): {'; '.join(gaps[:3])}" if gaps else "No multi-day gaps beyond weekends"})
    return checks


def company_quality(symbol: str, now_utc: datetime | None = None) -> dict:
    symbol = symbol.upper()
    with session_scope() as s:
        c = s.get(Company, symbol)
        if c is None:
            raise KeyError(symbol)
        bars = list(s.scalars(select(PriceBar).where(PriceBar.symbol == symbol).order_by(PriceBar.date)))
        since = utcnow() - timedelta(days=90)
        anns = list(s.scalars(select(Announcement).where(Announcement.symbol == symbol, Announcement.published_at >= since)))
        ann_stamp = kv_get(s, f"stamp:announcements:{symbol}") or (kv_get(s, "stamp:announcements") if c.in_portfolio else None)
        px_stamp = kv_get(s, "stamp:prices") if c.in_portfolio else (kv_get(s, f"job:{symbol}") or {}).get("finished_at")
        scr_row = kv_get_row(s, f"screener:{symbol}")
        docs = list(s.scalars(select(Document).where(Document.symbol == symbol)))
        identity = {"bse_code": c.bse_code, "isin": c.isin, "sources": c.identity_sources or [],
                    "validated_at": c.validated_at.strftime("%Y-%m-%dT%H:%M:%SZ") if c.validated_at else None}

    sources, checks, conflicts = [], [], []
    last = bars[-1].date if bars else None
    status, exp = price_freshness(last, now_utc)
    sources.append({"key": "prices", "label": "End-of-day prices", "provider": (bars[-1].source if bars else "yfinance"),
                    "status": status, "confidence": "direct" if bars else "unavailable", "last_record": last,
                    "expected_session": exp, "records": len(bars), "retrieved_at": px_stamp,
                    "note": "Split- and dividend-adjusted closes. Exchange holidays are not modelled, so one session behind may just be a holiday."})
    checks += price_checks(bars) if bars else [{"name": "Price history", "status": "fail", "detail": "No price data stored"}]

    if not c.bse_code:
        f_status, f_conf = "not_mapped", "unavailable"
    elif ann_stamp is None:
        f_status, f_conf = "never_synced", "unavailable"
    else:
        f_status, f_conf = "ok", "direct"
    no_attach = sum(1 for a in anns if not a.attachment_url)
    latest = max((a.published_at for a in anns), default=None)
    sources.append({"key": "filings", "label": "Exchange filings", "provider": "BSE", "status": f_status, "confidence": f_conf,
                    "last_sync": ann_stamp, "records_90d": len(anns), "latest_filing": latest.strftime("%Y-%m-%dT%H:%M:%SZ") if latest else None,
                    "note": None if c.bse_code else "No BSE code confidently matched to this symbol, so filings are not linked."})
    if no_attach:
        checks.append({"name": "Filing attachments", "status": "warn", "detail": f"{no_attach} of {len(anns)} recent filings have no attached document"})

    if scr_row:
        snap = scr_row.value
        age_h = (utcnow() - scr_row.updated_at).total_seconds() / 3600
        q = (snap.get("tables") or {}).get("quarters") or {}
        sources.append({"key": "financials", "label": "Standardised financials", "provider": "screener.in",
                        "status": "stale" if snap.get("stale") or age_h > 72 else "fresh", "confidence": "direct",
                        "retrieved_at": snap.get("retrieved_at"), "basis": snap.get("basis"),
                        "latest_quarter": (q.get("headers") or [None])[-1]})
    else:
        sources.append({"key": "financials", "label": "Standardised financials", "provider": "screener.in", "status": "missing",
                        "confidence": "unavailable", "note": "Fetched when research is opened for this company."})

    by = {}
    for d in docs:
        by[d.status] = by.get(d.status, 0) + 1
    sources.append({"key": "documents", "label": "Primary documents", "provider": "BSE and company sites (screener.in index)",
                    "status": "ok" if by.get("ok") else ("partial" if docs else "missing"),
                    "confidence": "direct" if by.get("ok") else "partial" if docs else "unavailable", "counts": by,
                    "scanned": [d.title for d in docs if d.status == "scanned"][:5],
                    "failed": [{"title": d.title, "error": d.error} for d in docs if d.status == "failed"][:5]})
    if by.get("scanned"):
        checks.append({"name": "Scanned documents", "status": "warn", "detail": f"{by['scanned']} documents have no text layer (OCR not run)"})

    for a in anns:
        e = a.enrichment if a.enrichment_status == "ok" else None
        chk = (e or {}).get("check")
        if not chk:
            continue
        name = f"Results cross-check, {(a.published_at + IST):%d %b %Y}"
        if chk["status"] == "match":
            checks.append({"name": name, "status": "pass", "detail": "Filing and screener.in agree on revenue and PAT (verified)"})
        elif chk["status"] == "mismatch":
            checks.append({"name": name, "status": "fail", "detail": chk["note"]})
            conflicts.append({"what": "Quarterly revenue and PAT", "announcement_id": a.id, "note": chk["note"],
                              "values": [{"source": "results filing", "revenue": e["rows"][0]["current"], "pat": e["rows"][3]["current"]}],
                              "resolution": "unresolved: both kept; check basis (standalone/consolidated), units and restatements"})
        else:
            checks.append({"name": name, "status": "warn", "detail": chk["note"]})
    checks.append({"name": "Identity", "status": "pass" if identity["validated_at"] else "warn",
                   "detail": f"Validated via {', '.join(identity['sources']) or 'config only'}" + ("" if c.bse_code else "; no BSE code")})
    return {"symbol": symbol, "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), "identity": identity,
            "sources": sources, "checks": checks, "conflicts": conflicts, "legend": LEGEND}


def source_health() -> dict:
    with session_scope() as s:
        out = {
            "companies": s.scalar(select(func.count()).select_from(Company)) or 0,
            "portfolio": s.scalar(select(func.count()).select_from(Company).where(Company.in_portfolio.is_(True))) or 0,
            "last_price_session": s.scalar(select(func.max(PriceBar.date))),
            "prices_refreshed_at": kv_get(s, "stamp:prices"),
            "filings_synced_at": kv_get(s, "stamp:announcements"),
            "last_refresh_error": kv_get(s, "stamp:refresh_error"),
            "announcements": s.scalar(select(func.count()).select_from(Announcement)) or 0,
            "documents": dict(s.execute(select(Document.status, func.count()).group_by(Document.status)).all()),
        }
    status, exp = price_freshness(out["last_price_session"])
    out.update(price_status=status, expected_session=exp, llm_enabled=llm.available(),
               providers=[{"name": "Yahoo Finance (yfinance)", "used_for": "EOD prices"},
                          {"name": "BSE (via the bse package)", "used_for": "Corporate announcements and attachments"},
                          {"name": "screener.in", "used_for": "Standardised financials and document links"}])
    return out
