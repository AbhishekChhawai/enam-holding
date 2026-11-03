"""Alert rules and triggered alerts.

Rules are the single source of truth for "what counts as unusual". The portfolio-wide rules also
drive the digest's move flags (mirrored into prefs), so there is never a second, disagreeing setting.

Evaluation is deterministic and idempotent: each alert has a dedupe key of rule x company x session
(market) or rule x filing (filings), so re-running never duplicates. Market rules only look at
completed EOD sessions (quality.expected_session), never a half-formed intraday bar.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import DEFAULT_PREFS
from ..db import Alert, AlertRule, Announcement, Company, PriceBar, iso, kv_get, kv_set, portfolio_symbols, session_scope, utcnow
from . import classify

TIER_RANK = {"routine": 0, "worth_a_look": 1, "needs_you": 2}
KINDS = ("price_move", "volume", "filing")
IST = timedelta(hours=5, minutes=30)


# ------------------------------------------------------------------ CRUD
def rule_dict(r: AlertRule) -> dict:
    return {"id": r.id, "name": r.name, "profile": r.profile or "demo", "symbol": r.symbol, "scope": r.symbol or "portfolio", "kind": r.kind,
            "direction": r.direction, "threshold": r.threshold, "window": r.window, "categories": r.categories,
            "min_tier": r.min_tier, "enabled": r.enabled, "description": describe(r),
            "created_at": iso(r.created_at), "updated_at": iso(r.updated_at), "last_evaluated_at": iso(r.last_evaluated_at)}


def describe(r: AlertRule) -> str:
    who = r.symbol or "any holding"
    if r.kind == "price_move":
        arrow = {"up": "rises", "down": "falls", "either": "moves"}[r.direction or "either"]
        return f"When {who} {arrow} {r.threshold:g}% or more in a day"
    if r.kind == "volume":
        return f"When {who} trades {r.threshold:g}× its {r.window or 20}-session average volume"
    cats = ", ".join(classify.LABELS.get(c, c) for c in (r.categories or []))
    floor = {"routine": "any", "worth_a_look": "non-routine", "needs_you": "top-priority"}[r.min_tier or "worth_a_look"]
    return f"When {who} files {floor} {cats or 'filings'}"


def validate(p: dict, partial: bool = False) -> dict:
    out = {}
    if not partial or "kind" in p:
        if p.get("kind") not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        out["kind"] = p["kind"]
    if "symbol" in p:
        sym = (p["symbol"] or "").strip().upper() or None
        if sym and not sym.replace("&", "").replace("-", "").isalnum():
            raise ValueError("symbol must be an NSE symbol or empty for the whole portfolio")
        out["symbol"] = sym
    if "threshold" in p and p["threshold"] is not None:
        t = float(p["threshold"])
        if not (0 < t <= 100):
            raise ValueError("threshold must be between 0 and 100")
        out["threshold"] = t
    if "direction" in p:
        if p["direction"] not in ("either", "up", "down", None):
            raise ValueError("direction must be either, up or down")
        out["direction"] = p["direction"]
    if "window" in p and p["window"] is not None:
        w = int(p["window"])
        if not (5 <= w <= 120):
            raise ValueError("window must be 5-120 sessions")
        out["window"] = w
    if "categories" in p:
        bad = [c for c in (p["categories"] or []) if c not in classify.CATEGORIES]
        if bad:
            raise ValueError(f"unknown categories: {', '.join(bad)}")
        out["categories"] = list(p["categories"] or [])
    if "min_tier" in p:
        if p["min_tier"] not in TIER_RANK:
            raise ValueError("min_tier must be routine, worth_a_look or needs_you")
        out["min_tier"] = p["min_tier"]
    for k in ("name", "enabled"):
        if k in p:
            out[k] = p[k]
    kind = out.get("kind")
    if not partial:
        if kind in ("price_move", "volume") and out.get("threshold") is None:
            raise ValueError("threshold is required for price and volume rules")
        if kind == "filing" and not out.get("categories"):
            raise ValueError("choose at least one filing category")
        out.setdefault("direction", "either" if kind == "price_move" else None)
        out.setdefault("window", 20 if kind == "volume" else None)
        out.setdefault("min_tier", "worth_a_look" if kind == "filing" else None)
        out.setdefault("enabled", True)
    return out


def ensure_defaults(s: Session) -> None:
    if s.scalar(select(AlertRule.id).limit(1)) is not None:
        return
    p = {**DEFAULT_PREFS, **(kv_get(s, "prefs", {}) or {})}
    s.add_all([
        AlertRule(name="Big daily move", kind="price_move", direction="either", threshold=float(p["price_move_pct"])),
        AlertRule(name="Unusual volume", kind="volume", threshold=float(p["volume_multiple"]), window=20),
        AlertRule(name="Material filings", kind="filing", categories=list(p["alert_categories"]), min_tier="worth_a_look"),
    ])
    s.flush()


def _portfolio_rule(s: Session, kind: str) -> AlertRule | None:
    return s.scalar(select(AlertRule).where(AlertRule.kind == kind, AlertRule.symbol.is_(None)).order_by(AlertRule.id))


def sync_prefs(s: Session) -> None:
    """Mirror the portfolio-wide rules into prefs, which the digest and portfolio views read."""
    p = kv_get(s, "prefs", {}) or {}
    pr, vr, fr = (_portfolio_rule(s, k) for k in KINDS)
    if pr and pr.enabled:
        p["price_move_pct"] = pr.threshold
    if vr and vr.enabled:
        p["volume_multiple"] = vr.threshold
    if fr:
        p["alert_categories"] = (fr.categories or []) if fr.enabled else []
    kv_set(s, "prefs", p)


def apply_pref_patch(s: Session, patch: dict) -> None:
    """Command-bar shortcuts ('vol 3x', 'price 4%') edit the portfolio-wide rules."""
    ensure_defaults(s)
    for key, kind, field in (("price_move_pct", "price_move", "threshold"), ("volume_multiple", "volume", "threshold"),
                             ("alert_categories", "filing", "categories")):
        if key in patch:
            r = _portfolio_rule(s, kind)
            if r:
                setattr(r, field, float(patch[key]) if field == "threshold" else list(patch[key]))
                r.updated_at = utcnow()


# ------------------------------------------------------------------ evaluation
def _completed_session() -> str:
    from ..quality import expected_session
    return expected_session().isoformat()


def _scope(s: Session, r: AlertRule) -> list[str]:
    if r.symbol:
        return [r.symbol] if s.get(Company, r.symbol) else []
    muted = set((kv_get(s, "prefs", {}) or {}).get("muted_symbols") or [])
    return [x for x in portfolio_symbols(s) if x not in muted]


def _add(s: Session, **kw) -> bool:
    if s.scalar(select(Alert.id).where(Alert.dedupe_key == kw["dedupe_key"])) is not None:
        return False
    try:
        with s.begin_nested():
            s.add(Alert(created_at=utcnow(), **kw))
        return True
    except IntegrityError:
        return False


def _eval_market(s: Session, r: AlertRule, sessions: int, last_ok: str) -> int:
    n = 0
    window = r.window or 20
    for sym in _scope(s, r):
        bars = list(s.scalars(select(PriceBar).where(PriceBar.symbol == sym, PriceBar.date <= last_ok)
                              .order_by(PriceBar.date.desc()).limit(sessions + window + 1)))[::-1]
        for i in range(max(1, len(bars) - sessions), len(bars)):
            b, prev = bars[i], bars[i - 1]
            if r.kind == "price_move":
                if not prev.close:
                    continue
                pct = (b.close / prev.close - 1) * 100
                hit = {"up": pct >= r.threshold, "down": pct <= -r.threshold}.get(r.direction or "either", abs(pct) >= r.threshold)
                if not hit:
                    continue
                observed, verb = round(pct, 2), ("rose" if pct > 0 else "fell")
                msg = f"{sym} {verb} {abs(pct):.1f}% to ₹{b.close:,.2f}, beyond your {r.threshold:g}% rule."
                sev = "high" if abs(pct) >= 2 * r.threshold else "medium"
                prov = {"source": b.source, "formula": "close / previous close - 1", "close": b.close, "previous_close": prev.close, "previous_date": prev.date}
            else:
                hist = [x.volume for x in bars[max(0, i - window):i] if x.volume]
                if len(hist) < min(5, window) or not b.volume:
                    continue  # insufficient history: no alert rather than a guess
                avg = sum(hist) / len(hist)
                ratio = b.volume / avg if avg else None
                if ratio is None or ratio < r.threshold:
                    continue
                observed = round(ratio, 2)
                msg = f"{sym} traded {ratio:.1f}× its {len(hist)}-session average volume, above your {r.threshold:g}× rule."
                sev = "high" if ratio >= 1.5 * r.threshold else "medium"
                prov = {"source": b.source, "formula": f"volume / mean(previous {len(hist)} sessions)", "volume": b.volume, "average": round(avg)}
            key = f"r{r.id}:{sym}:{b.date}"
            if s.scalar(select(Alert.id).where(Alert.dedupe_key == key)) is not None:
                continue
            from .digest import _nearby_filings
            prov["nearby"] = _nearby_filings(s, {"symbol": sym, "date": b.date}, {}, {"category_weights": {}, "alert_categories": []})
            prov["context"] = ("Filed around this session; shown for context, not as the cause." if prov["nearby"]
                               else "No non-routine filings from this company in the 3 days before or the day after this session.")
            n += _add(s, rule_id=r.id, dedupe_key=key, symbol=sym, kind="market", session_date=b.date,
                      observed=observed, threshold=r.threshold, severity=sev, title=f"{sym}: {r.name or describe(r)}",
                      message=msg, provenance=prov)
    return n


def _eval_filings(s: Session, r: AlertRule, days: int) -> int:
    n = 0
    since = utcnow() - timedelta(days=days)
    weights = (kv_get(s, "prefs", {}) or {}).get("category_weights") or {}
    syms = _scope(s, r)
    if not syms:
        return 0
    window = list(s.scalars(select(Announcement).where(Announcement.symbol.in_(syms), Announcement.published_at >= since - timedelta(hours=36))))
    # one alert per results day: companion filings bundled in the digest don't alert separately
    from .digest import cluster, item_dict
    standing = {it["id"] for it in cluster([item_dict(a, {}, {"category_weights": weights, "alert_categories": []}) for a in window])}
    rows = [a for a in window if a.published_at >= since and a.category in (r.categories or []) and a.id in standing]
    for a in rows:
        score = max(0, min(100, a.base_score + int(weights.get(a.category, 0))))
        t = classify.tier(score)
        if TIER_RANK[t] < TIER_RANK[r.min_tier or "worth_a_look"]:
            continue
        label = classify.LABELS.get(a.category, a.category)
        when = (a.published_at + IST).strftime("%d %b, %H:%M")
        n += _add(s, rule_id=r.id, dedupe_key=f"r{r.id}:ann:{a.id}", symbol=a.symbol, kind="filing", announcement_id=a.id,
                  severity="high" if t == "needs_you" else "medium", title=f"{a.symbol}: {label}",
                  message=f"{(a.summary or a.headline or a.subject)[:220]} (filed {when} IST)",
                  provenance={"source": "BSE", "url": a.attachment_url, "category": a.category, "score": score, "tier": t})
    return n


def evaluate(rule_ids: list[int] | None = None, *, sessions: int = 3, filing_days: int = 3) -> dict:
    """Evaluate enabled rules against completed sessions and recent filings. Safe to re-run."""
    created, checked = 0, 0
    last_ok = _completed_session()
    with session_scope() as s:
        ensure_defaults(s)
        q = select(AlertRule).where(AlertRule.enabled.is_(True))
        if rule_ids:
            q = q.where(AlertRule.id.in_(rule_ids))
        failures = []
        for r in list(s.scalars(q)):
            try:
                with s.begin_nested():
                    created += _eval_filings(s, r, filing_days) if r.kind == "filing" else _eval_market(s, r, sessions, last_ok)
                r.last_evaluated_at = utcnow()
            except Exception as e:  # noqa: BLE001  one bad rule must not block the rest
                failures.append({"rule_id": r.id, "error": str(e)[:200]})
            checked += 1
        at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        kv_set(s, "stamp:alerts_evaluated", at)
        run = {"at": at, "rules_checked": checked, "created": created, "failures": failures, "completed_session": last_ok,
               "scope": "selected rules" if rule_ids else "all enabled rules"}
        kv_set(s, "alert_runs", ([run] + (kv_get(s, "alert_runs", []) or []))[:20])
    try:   # important new alerts also go to WhatsApp, when configured
        from ..notify import whatsapp
        wa = whatsapp.dispatch() if created else {"sent": 0}
    except Exception as e:  # noqa: BLE001 - notifications must never break evaluation
        wa = {"sent": 0, "error": type(e).__name__}
    return {"created": created, "rules_checked": checked, "evaluated_at": at, "completed_session": last_ok, "failures": failures, "whatsapp": wa}


def alert_dict(a: Alert, rule_kind: str | None = None) -> dict:
    return {"id": a.id, "rule_id": a.rule_id, "rule_kind": rule_kind, "symbol": a.symbol, "kind": a.kind, "session_date": a.session_date,
            "announcement_id": a.announcement_id, "observed": a.observed, "threshold": a.threshold, "severity": a.severity,
            "title": a.title, "message": a.message, "provenance": a.provenance, "created_at": iso(a.created_at), "read": a.read}
