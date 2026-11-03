"""The windowed digest: every filing across the portfolio for a chosen window, ranked and tiered,
plus EOD moves that crossed the investor's thresholds."""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import Announcement, Company, PriceBar, iso, kv_get, portfolio_symbols, utcnow
from . import alerts, classify


def _title(a: Announcement) -> str:
    h = (a.headline or "").strip()
    if len(h) >= 20:
        return h
    return (a.subject or h or "Filing").strip()


def item_dict(a: Announcement, names: dict[str, str], prefs: dict) -> dict:
    weight = int((prefs.get("category_weights") or {}).get(a.category, 0))
    sc = max(0, min(100, a.base_score + weight))
    reasons = list(a.reasons or [])
    if weight:
        reasons.append(f"{'+' if weight > 0 else ''}{weight} from your feedback on {classify.LABELS.get(a.category, a.category)}")
    t = classify.tier(sc)
    return {
        "id": a.id, "symbol": a.symbol, "company": names.get(a.symbol, a.symbol),
        "published_at": iso(a.published_at), "category": a.category,
        "category_label": classify.LABELS.get(a.category, a.category),
        "classified_by": a.category_method, "title": _title(a), "subject": a.subject,
        "summary": a.summary, "score": sc, "tier": t, "reasons": reasons,
        "attachment_url": a.attachment_url, "exchange_url": a.source_url,
        "enrichment": a.enrichment if a.enrichment_status == "ok" else None,
        "enrichment_status": a.enrichment_status,
        "alert": a.category in prefs["alert_categories"] and t != "routine",
    }


# ------------------------------------------------------------------ clustering
# A results day typically brings 3-5 filings: the outcome, the results, a presentation, a press release,
# a call schedule. They become one card with the rest one tap away. Deterministic and conservative:
# same company, within 36h of a real results filing, and only results-family documents.
import re as _re
from datetime import datetime as _dt

_RESULTS_WORDS = _re.compile(r"result|quarter|financial|earnings|performance|presentation", _re.I)


def _t(it: dict) -> _dt:
    return _dt.strptime(it["published_at"], "%Y-%m-%dT%H:%M:%SZ")


def _joins(member: dict, anchor: dict) -> bool:
    gap = abs((_t(member) - _t(anchor)).total_seconds()) / 3600
    c = member["category"]
    if c in ("results", "earnings_call", "investor_meetings"):
        return gap <= 36
    if c == "press_release":
        return gap <= 36 and bool(_RESULTS_WORDS.search(member["title"] + " " + (member.get("subject") or "")))
    if c == "dividend":
        return gap <= 6  # declared at the same board meeting
    return False


def cluster(items: list[dict]) -> list[dict]:
    """Attach results-day companion filings to their anchor. Returns the items left standing."""
    anchors = sorted([it for it in items if it["category"] == "results" and it["score"] >= 60],
                     key=lambda x: (-x["score"], x["published_at"]))
    taken: set[str] = set()
    for a in anchors:
        if a["id"] in taken:
            continue
        a.setdefault("related", [])
        for m in items:
            if m is a or m["id"] in taken or m["symbol"] != a["symbol"] or m in anchors and m["id"] in taken:
                continue
            if _joins(m, a):
                taken.add(m["id"])
                a["related"].append({k: m[k] for k in ("id", "title", "category_label", "published_at", "attachment_url", "tier", "summary")})
        a["related"].sort(key=lambda x: x["published_at"])
    return [it for it in items if it["id"] not in taken]


def _nearby_filings(s: Session, move: dict, names: dict, prefs: dict) -> list[dict]:
    """Why-now context: non-routine filings from the same company in the days around a move."""
    d = _dt.strptime(move["date"], "%Y-%m-%d")
    rows = s.scalars(select(Announcement).where(
        Announcement.symbol == move["symbol"],
        Announcement.published_at >= d - timedelta(days=3), Announcement.published_at <= d + timedelta(days=1, hours=18)))
    out = []
    for a in rows:
        it = item_dict(a, names, prefs)
        if it["tier"] != "routine":
            out.append({k: it[k] for k in ("id", "title", "category_label", "published_at", "attachment_url", "tier")})
    return sorted(out, key=lambda x: x["published_at"], reverse=True)[:3]


def _sessions_since(s: Session, hours: int) -> str | None:
    """EOD data is per trading session: a 24h window on a Sunday should still show Friday."""
    n = max(1, round(hours / 24))
    dates = list(s.scalars(select(PriceBar.date).distinct().order_by(PriceBar.date.desc()).limit(n)))
    return dates[-1] if dates else None


def build(s: Session, hours: int, prefs: dict) -> dict:
    since = utcnow() - timedelta(hours=hours)
    syms = [x for x in portfolio_symbols(s) if x not in set(prefs.get("muted_symbols") or [])]
    names = {c.symbol: c.name for c in s.scalars(select(Company))}
    rows = list(s.scalars(
        select(Announcement).where(Announcement.symbol.in_(syms), Announcement.published_at >= since)
        .order_by(Announcement.published_at.desc())
    ))
    items = [item_dict(a, names, prefs) for a in rows]
    standing = cluster(items)
    tiers = {"needs_you": [], "worth_a_look": [], "routine": []}
    for it in standing:
        tiers[it["tier"]].append(it)
    for k in ("needs_you", "worth_a_look"):
        tiers[k].sort(key=lambda x: (x["score"], x["published_at"]), reverse=True)

    first_session = _sessions_since(s, hours)
    moves = []
    if first_session:
        from datetime import date
        moves = alerts.moves_in_window(s, syms, date.fromisoformat(first_session), prefs)
        for m in moves:
            m["company"] = names.get(m["symbol"], m["symbol"])
            m["nearby"] = _nearby_filings(s, m, names, prefs)
            co = s.get(Company, m["symbol"])
            und = (co.meta or {}).get("underlying") if co else None
            if und:
                ub = list(s.scalars(select(PriceBar).where(PriceBar.symbol == und, PriceBar.date <= m["date"]).order_by(PriceBar.date.desc()).limit(2)))
                if len(ub) == 2 and ub[1].close:
                    m["index_context"] = {"name": co.meta.get("underlying_name", und), "date": ub[0].date,
                                          "pct": round((ub[0].close / ub[1].close - 1) * 100, 2)}
            if m["nearby"]:
                m["context_note"] = "Filed around this session. Shown for context; FINN does not infer cause."

    triggered = [it for it in tiers["needs_you"] + tiers["worth_a_look"] if it["alert"]]
    last_session = s.scalar(select(PriceBar.date).order_by(PriceBar.date.desc()).limit(1))
    return {
        "window_hours": hours,
        "since": iso(since),
        "as_of": {
            "announcements": kv_get(s, "stamp:announcements"),
            "prices": kv_get(s, "stamp:prices"),
            "last_session": last_session,
            "moves_from_session": first_session,
        },
        "counts": {
            "total": len(items), "needs_you": len(tiers["needs_you"]),
            "worth_a_look": len(tiers["worth_a_look"]), "routine": len(tiers["routine"]),
            "moves": len(moves), "companies": len(syms), "grouped": len(items) - len(standing),
        },
        "triggered": triggered,
        "alerts_evaluated_at": kv_get(s, "stamp:alerts_evaluated"),
        "moves": moves,
        "tiers": tiers,
        "ticks": [{"id": it["id"], "symbol": it["symbol"], "tier": it["tier"], "published_at": it["published_at"]}
                  for it in sorted(items, key=lambda x: x["published_at"])],
    }
