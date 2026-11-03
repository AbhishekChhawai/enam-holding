"""Unified financial timeline for one company: filings, market observations, reported quarters and
concalls in one chronology, each carrying its provenance.

Evidence connections link events that happened in the same window as a results filing (a day before
to five days after). They are presented as co-occurrence only, never as cause.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select

from .db import Announcement, PriceBar, kv_get, session_scope
from .pull import periods as P
from .push import alerts, classify
from .sources import screener

TYPE_OF_CATEGORY = {
    "results": "results", "dividend": "corporate_action", "bonus_split": "corporate_action",
    "management_change": "management", "earnings_call": "concall",
}
FILTERS = {
    "filings": {"filing", "management", "corporate_action"},
    "results": {"results", "financials"},
    "corporate_actions": {"corporate_action"},
    "market": {"market"},
    "documents": {"concall"},
}


def _ev(eid, ts, etype, title, *, detail=None, metrics=None, source=None, url=None, provenance="direct",
        precision="exact", doc_id=None, status=None, category=None):
    return {"id": eid, "timestamp": ts, "date_precision": precision, "type": etype, "category": category,
            "title": title, "detail": detail, "metrics": metrics or {}, "source": source, "url": url,
            "provenance": provenance, "doc_id": doc_id, "status": status, "related": []}


def build(symbol: str, *, start: date | None = None, end: date | None = None, types: set[str] | None = None,
          prefs: dict | None = None) -> dict:
    symbol = symbol.upper()
    end = end or date.today()
    start = start or end - timedelta(days=365)
    prefs = prefs or {"price_move_pct": 5.0, "volume_multiple": 2.0}
    events: list[dict] = []
    with session_scope() as s:
        anns = list(s.scalars(select(Announcement).where(
            Announcement.symbol == symbol,
            Announcement.published_at >= datetime.combine(start, datetime.min.time()),
            Announcement.published_at <= datetime.combine(end, datetime.max.time()))))
        for a in anns:
            et = TYPE_OF_CATEGORY.get(a.category, "filing")
            if a.category == "unclassified":
                continue  # paperwork stays in the filings API, not the narrative timeline
            metrics = {}
            enr = a.enrichment if a.enrichment_status == "ok" else None
            if enr and enr.get("type") == "results":
                for r in enr["rows"]:
                    if r["key"] in ("revenue", "pat"):
                        metrics[r["label"]] = {"value": r["current"], "yoy_pct": r["yoy_pct"], "unit": "₹ cr"}
            events.append(_ev(f"ann:{a.id}", a.published_at.strftime("%Y-%m-%dT%H:%M:%SZ"), et, a.headline or a.subject,
                              detail=a.summary, metrics=metrics, source="BSE", url=a.attachment_url,
                              provenance="direct", status=a.enrichment_status, category=classify.LABELS.get(a.category)))
        bars = list(s.scalars(select(PriceBar).where(PriceBar.symbol == symbol).order_by(PriceBar.date)))
        snap = kv_get(s, f"screener:{symbol}")
    # market observations: flagged EOD sessions (derived, not a source event)
    for i in range(1, len(bars)):
        if not (start.isoformat() <= bars[i].date <= end.isoformat()):
            continue
        st = alerts.day_stats(bars, i)
        if not st:
            continue
        fl = alerts.flags_for(st, prefs["price_move_pct"], prefs["volume_multiple"])
        if "price" in fl or "volume" in fl:
            events.append(_ev(f"mkt:{bars[i].date}", f"{bars[i].date}T10:00:00Z", "market", alerts.describe(st, fl),
                              metrics={"pct": st["pct"], "volume_multiple": st["volume_multiple"], "close": st["close"]},
                              source=bars[i].source or "yfinance", provenance="derived", precision="day"))
    # reported quarters (period-end dated) and concalls (month precision) from screener's primary-document index
    if snap:
        q = snap["tables"].get("quarters")
        if q:
            _, sales = screener.row(q, "sales", "revenue")
            _, pat = screener.row(q, "net profit")
            for j, h in enumerate(q["headers"]):
                qq = P.quarter_of(h)
                pe = P.parse_label(h)
                if not qq or not pe or sales[j] is None:
                    continue
                m, y = pe
                d = date(y, m, 30 if m in (6, 9) else 31)
                if not (start <= d <= end):
                    continue
                yoy = (sales[j] / sales[j - 4] - 1) * 100 if j >= 4 and sales[j - 4] else None
                link = q["pdf_links"][j] if j < len(q.get("pdf_links") or []) else None
                events.append(_ev(f"qtr:{h}", f"{d.isoformat()}T00:00:00Z", "financials", f"{P.short(*qq)} quarter closed",
                                  metrics={"Revenue": {"value": sales[j], "yoy_pct": round(yoy, 1) if yoy is not None else None, "unit": "₹ cr"},
                                           "PAT": {"value": pat[j] if pat else None, "unit": "₹ cr"}},
                                  source=f"screener.in ({snap.get('basis')})", url=link, provenance="normalized", precision="period_end"))
        filed_months = {e["timestamp"][:7] for e in events if e["type"] == "concall"}
        for c in snap["documents"].get("concalls", []):
            pe = P.parse_label(c.get("period", ""))
            if not pe or not c.get("transcript"):
                continue
            m, y = pe
            d = date(y, m, 1)
            if not (start <= d <= end) or d.isoformat()[:7] in filed_months:
                continue
            qq = P.call_month_to_quarter(c["period"])
            from .store import doc_id_for
            events.append(_ev(f"call:{c['period']}", f"{d.isoformat()}T00:00:00Z", "concall",
                              f"Earnings call{f' on {P.short(*qq)}' if qq else ''}", source="Transcript via screener.in index",
                              url=c["transcript"], provenance="direct", precision="month", doc_id=doc_id_for(c["transcript"])))
    events.sort(key=lambda e: e["timestamp"], reverse=True)
    _connect(events)
    if types:
        allowed = set().union(*(FILTERS.get(t, {t}) for t in types))
        events = [e for e in events if e["type"] in allowed]
    counts: dict[str, int] = {}
    for e in events:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    return {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat(), "count": len(events),
            "counts_by_type": counts, "events": events,
            "note": "Quarter-closed events are dated at period end; the results filing follows within about 45 days. "
                     "Related events share a time window around a results filing; this is not a causal claim."}


def _connect(events: list[dict]) -> None:
    results = [e for e in events if e["type"] == "results" and e["date_precision"] == "exact"]
    for r in results:
        t = datetime.strptime(r["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
        lo, hi = t - timedelta(days=1), t + timedelta(days=5)
        for e in events:
            if e is r or e["type"] not in ("market", "concall", "management"):
                continue
            et = datetime.strptime(e["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
            if e["date_precision"] == "month":
                continue
            if lo <= et <= hi:
                r["related"].append(e["id"])
                e["related"].append(r["id"])
