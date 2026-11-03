"""HTTP API. One process serves the JSON API under /api and the built React app at /."""
from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select

from datetime import date, timedelta

from . import llm, quality, registry, store, timeline
from .config import (ANNOUNCEMENT_TTL_MIN, ASK_PER_IP_HOUR, CORS_ORIGINS, CRON_SECRET, FRONTEND_DIST, LIVE_REFRESH,
                     LLM_RUNS_PER_DAY, PRICE_TTL_MIN, RESEARCH_PER_IP_HOUR)
from .db import Announcement, Company, PriceBar, init_db, portfolio_symbols, session_scope
from .prefs import apply_feedback, get_prefs, update_prefs
from .pull import agent, promises
from .push import alerts, classify, digest, rules
from .push import refresh as push_refresh
from .sources import screener
from .sources.http import FetchError

log = logging.getLogger("finn.api")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

_refresh_lock = threading.Lock()
MANUAL_MIN_INTERVAL_S = 120  # protects BSE/Yahoo from refresh-button hammering
_refresh_state: dict = {"status": "idle", "trigger": None, "started_at": None, "finished_at": None,
                        "new_filings": None, "prices_refreshed": False, "error": None}


def _now() -> str:
    from datetime import datetime as _dt
    return _dt.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _start_refresh(need_ann: bool, need_px: bool, trigger: str) -> bool:
    """Run one refresh in the background. Requests never wait on it; cached data is served meanwhile."""
    if _refresh_lock.locked() or _refresh_state["status"] == "running" or not (need_ann or need_px):
        return False
    # set synchronously so a fast worker can never be overwritten by the caller
    _refresh_state.update(status="running", trigger=trigger, started_at=_now(), finished_at=None,
                          new_filings=None, new_alerts=None, prices_refreshed=False, error=None)

    def work():
        with _refresh_lock:
            try:
                if need_px:
                    push_refresh.refresh_prices(period="3mo")
                    _refresh_state["prices_refreshed"] = True
                if need_ann:
                    _refresh_state["new_filings"] = push_refresh.refresh_announcements(days=2)
                    push_refresh.enrich_pending(limit=10, since_days=3)
                _refresh_state["new_alerts"] = rules.evaluate()["created"]  # new data in -> rules evaluated
                _refresh_state["status"] = "done"
            except Exception as e:  # noqa: BLE001
                log.warning("Refresh failed (serving cached data): %s", e)
                store.stamp("stamp:refresh_error", str(e)[:300])
                _refresh_state.update(status="failed", error=str(e)[:300])
            finally:
                _refresh_state["finished_at"] = _now()

    threading.Thread(target=work, daemon=True).start()
    return True


def _maybe_refresh() -> None:
    """TTL-gated refresh triggered by reads and by the scheduled /api/cron ping."""
    if not LIVE_REFRESH:
        return
    ann_age = store.stamp_age_minutes("stamp:announcements")
    px_age = store.stamp_age_minutes("stamp:prices")
    _start_refresh(ann_age is None or ann_age > ANNOUNCEMENT_TTL_MIN,
                   px_age is None or px_age > PRICE_TTL_MIN, trigger="auto")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with session_scope() as s:
        empty = not portfolio_symbols(s)
    if empty:
        try:
            push_refresh.seed_companies(verify_codes=False)
        except Exception as e:  # noqa: BLE001
            log.warning("Seeding failed: %s", e)
    with session_scope() as s:
        rules.ensure_defaults(s)
        rules.sync_prefs(s)
    yield


app = FastAPI(title="FINN API", version="0.1.0", lifespan=lifespan)
if CORS_ORIGINS:  # the default deployment is same-origin and needs no CORS at all
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Content-Type"])


# ------------------------------------------------------------------ guards
import hmac
import time as _time
from collections import defaultdict, deque

_hits: dict[str, deque] = defaultdict(deque)
_day = {"date": "", "count": 0}
_guard_lock = threading.Lock()


def _require_secret(x_cron_secret: str | None, key: str | None) -> None:
    if not CRON_SECRET:
        raise HTTPException(503, "Disabled: set FINN_CRON_SECRET on the server to enable this route")
    supplied = x_cron_secret or key or ""
    if not hmac.compare_digest(supplied.encode(), CRON_SECRET.encode()):
        log.warning("Rejected unauthorised call to a protected route")
        raise HTTPException(403, "Forbidden")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown")


def _budget(request: Request, kind: str, per_hour: int) -> None:
    """Per-visitor hourly cap plus a global daily cap on model-backed work. Cached answers are never counted."""
    if not llm.available():
        return
    now = _time.time()
    today = _time.strftime("%Y-%m-%d", _time.gmtime(now))
    with _guard_lock:
        if _day["date"] != today:
            _day.update(date=today, count=0)
        if _day["count"] >= LLM_RUNS_PER_DAY:
            raise HTTPException(429, "Today's AI budget for this demo is used up. Cached research and all numbers still work.")
        q = _hits[f"{kind}:{_client_ip(request)}"]
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= per_hour:
            raise HTTPException(429, f"Limit of {per_hour} per hour reached for this device. Try again later.")
        q.append(now)
        _day["count"] += 1


def _fresh(key: str, hours: float) -> bool:
    from datetime import timedelta as _td
    from .db import kv_get_row, utcnow as _now_utc
    with session_scope() as s:
        row = kv_get_row(s, key)
        return bool(row and row.updated_at > _now_utc() - _td(hours=hours))


# ------------------------------------------------------------------ meta
@app.get("/api/health")
def health():
    return {"ok": True, "llm": llm.available()}


@app.get("/api/meta/usage")
def usage():
    return llm.usage_summary()


def _refresh_view() -> dict:
    return {**_refresh_state, "filings_checked_at": _stamp("stamp:announcements"), "prices_refreshed_at": _stamp("stamp:prices")}


def _stamp(key: str):
    with session_scope() as s:
        from .db import kv_get
        return kv_get(s, key)


@app.post("/api/refresh")
def manual_refresh():
    """The Refresh button: check BSE for new filings now (prices too, if older than an hour)."""
    if _refresh_state["status"] == "running":
        return {**_refresh_view(), "note": "A refresh is already running"}
    fin = _refresh_state.get("finished_at")
    if fin and _refresh_state.get("trigger") == "manual":
        from datetime import datetime as _dt
        age = (_dt.utcnow() - _dt.strptime(fin, "%Y-%m-%dT%H:%M:%SZ")).total_seconds()
        if age < MANUAL_MIN_INTERVAL_S:
            return {**_refresh_view(), "note": f"Refreshed {int(age)}s ago; try again in {int(MANUAL_MIN_INTERVAL_S - age)}s"}
    px_age = store.stamp_age_minutes("stamp:prices")
    _start_refresh(True, px_age is None or px_age > 60, trigger="manual")
    return _refresh_view()


@app.get("/api/refresh")
def refresh_status():
    return _refresh_view()


@app.get("/api/cron")
def cron(x_cron_secret: str | None = Header(None), key: str | None = None):
    """Scheduled polling. Send the FINN_CRON_SECRET as header X-Cron-Secret (cron-job.org supports custom
    headers). TTL-gated and idempotent: a call while data is fresh does nothing."""
    _require_secret(x_cron_secret, key)
    _maybe_refresh()
    return {"ok": True, "refresh": _refresh_view()}


@app.get("/api/meta/categories")
def categories():
    return [{"key": c, "label": classify.LABELS[c]} for c in classify.CATEGORIES]


# ------------------------------------------------------------------ push
@app.get("/api/digest")
def get_digest(hours: int = Query(24, ge=1, le=24 * 90)):
    _maybe_refresh()
    with session_scope() as s:
        return digest.build(s, hours, get_prefs(s))


@app.get("/api/portfolio")
def get_portfolio():
    _maybe_refresh()
    with session_scope() as s:
        prefs = get_prefs(s)
        out = []
        for c in s.scalars(select(Company).where(Company.in_portfolio.is_(True)).order_by(Company.symbol)):
            snap = alerts.latest_snapshot(s, c.symbol, prefs)
            out.append({"symbol": c.symbol, "name": c.name, "sector": c.sector, "price": snap})
        return {"companies": out, "prefs": prefs}


@app.get("/api/notify/status")
def notify_status():
    from .notify import whatsapp
    return whatsapp.status()


@app.post("/api/notify/test")
def notify_test(x_cron_secret: str | None = Header(default=None)):
    """Sends one test WhatsApp message. Admin-only (same secret as cron), so a public deployment can't be used to spam."""
    _require_cron_secret(x_cron_secret)
    from .notify import whatsapp
    ok, err = whatsapp.send("*FINN test*\nWhatsApp alerts are working. You'll get important filings and big end-of-day moves here.")
    if not ok:
        raise HTTPException(400, err or "send failed")
    return {"sent": True, "to": whatsapp.status()["to"]}


@app.get("/api/portfolio/analysis")
def portfolio_analysis():
    """Mock portfolio of real securities: value, returns, allocation, history and benchmark from real EOD prices."""
    from . import portfolio_analysis as PA
    with session_scope() as s:
        return PA.analyse(s, push_refresh.load_portfolio_file().get("mock") or {})


@app.get("/api/announcements/{aid}")
def get_announcement(aid: str):
    with session_scope() as s:
        a = s.get(Announcement, aid)
        if not a:
            raise HTTPException(404, "Announcement not found")
        names = {c.symbol: c.name for c in s.scalars(select(Company))}
        return digest.item_dict(a, names, get_prefs(s))


@app.get("/api/announcements/{aid}/research-context")
def announcement_research_context(aid: str):
    """'Research this' handoff from Push to Pull. Documented in docs/handoff.md."""
    from .push.handoff import research_context
    return _guard(research_context, aid)


@app.post("/api/announcements/{aid}/enrich")
def enrich_announcement(aid: str, x_cron_secret: str | None = Header(None), key: str | None = None):
    """Admin: (re)enrich exactly one filing. Protected because it downloads a PDF and calls the model."""
    _require_secret(x_cron_secret, key)
    with session_scope() as s:
        a = s.get(Announcement, aid)
        if not a:
            raise HTTPException(404, "Announcement not found")
        if a.enrichment_status in ("failed", "unsupported"):
            a.enrichment_status = "none"
        a.base_score = max(a.base_score, 40)
    push_refresh.enrich_pending(limit=1, ids=[aid])
    return get_announcement(aid)


class Feedback(BaseModel):
    announcement_id: str
    signal: str  # "more" | "less"


@app.post("/api/feedback")
def feedback(fb: Feedback):
    if fb.signal not in ("more", "less"):
        raise HTTPException(400, "signal must be 'more' or 'less'")
    with session_scope() as s:
        a = s.get(Announcement, fb.announcement_id)
        if not a:
            raise HTTPException(404, "Announcement not found")
        p = apply_feedback(s, a.category, fb.signal)
        return {"category": a.category, "weight": p["category_weights"].get(a.category, 0), "prefs": p}


@app.get("/api/prefs")
def read_prefs():
    with session_scope() as s:
        return get_prefs(s)


@app.put("/api/prefs")
def write_prefs(patch: dict):
    with session_scope() as s:
        rules.apply_pref_patch(s, patch)  # thresholds live on the portfolio-wide rules
        update_prefs(s, patch)
        rules.sync_prefs(s)
        return get_prefs(s)


# ------------------------------------------------------------------ alerts
@app.get("/api/alerts")
def list_alerts(unread: bool | None = None, kind: str | None = None, symbol: str | None = None,
                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    """kind: market | filing | price | volume."""
    from .db import Alert, AlertRule, kv_get
    from sqlalchemy import func
    with session_scope() as s:
        q = select(Alert)
        if unread is not None:
            q = q.where(Alert.read.is_(not unread))
        if kind in ("price", "volume"):
            q = q.join(AlertRule, AlertRule.id == Alert.rule_id).where(AlertRule.kind == ("price_move" if kind == "price" else "volume"))
        elif kind:
            q = q.where(Alert.kind == kind)
        if symbol:
            q = q.where(Alert.symbol == _sym(symbol))
        total = s.scalar(select(func.count()).select_from(q.subquery()))
        rows = list(s.scalars(q.order_by(Alert.created_at.desc(), Alert.id.desc()).offset(offset).limit(limit)))
        kinds = dict(s.execute(select(AlertRule.id, AlertRule.kind)).all())
        return {"total": total, "unread_count": s.scalar(select(func.count()).select_from(Alert).where(Alert.read.is_(False))),
                "evaluated_at": kv_get(s, "stamp:alerts_evaluated"), "items": [rules.alert_dict(a, kinds.get(a.rule_id)) for a in rows]}


@app.get("/api/alerts/unread-count")
def unread_count():
    from .db import Alert, kv_get
    from sqlalchemy import func
    with session_scope() as s:
        return {"unread_count": s.scalar(select(func.count()).select_from(Alert).where(Alert.read.is_(False))),
                "evaluated_at": kv_get(s, "stamp:alerts_evaluated")}


@app.get("/api/alerts/runs")
def alert_runs():
    from .db import kv_get
    with session_scope() as s:
        return {"items": kv_get(s, "alert_runs", []) or []}


class AlertPatch(BaseModel):
    read: bool


@app.patch("/api/alerts/{alert_id}")
def patch_alert(alert_id: int, body: AlertPatch):
    from .db import Alert
    with session_scope() as s:
        a = s.get(Alert, alert_id)
        if not a:
            raise HTTPException(404, "Alert not found")
        a.read = body.read
        return rules.alert_dict(a)


@app.post("/api/alerts/mark-all-read")
@app.post("/api/alerts/read-all")
def read_all_alerts():
    from .db import Alert
    from sqlalchemy import update
    with session_scope() as s:
        n = s.execute(update(Alert).where(Alert.read.is_(False)).values(read=True)).rowcount
    return {"marked_read": n}


@app.get("/api/alerts/rules")
def list_rules():
    from .db import AlertRule
    with session_scope() as s:
        rules.ensure_defaults(s)
        return {"items": [rules.rule_dict(r) for r in s.scalars(select(AlertRule).order_by(AlertRule.id))]}


def _rule_evaluated(rule_id: int) -> dict:
    """Check a new or edited rule against the last 10 completed sessions and 7 days of filings."""
    return rules.evaluate([rule_id], sessions=10, filing_days=7)


@app.post("/api/alerts/rules")
def create_rule(body: dict):
    from .db import AlertRule, utcnow
    try:
        data = rules.validate(body)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    with session_scope() as s:
        if data.get("symbol"):
            if not s.get(Company, data["symbol"]):
                raise HTTPException(404, f"{data['symbol']} is not registered. Open it in Research first.")
        r = AlertRule(**data, created_at=utcnow(), updated_at=utcnow())
        if not r.name:
            r.name = rules.describe(r)
        s.add(r)
        s.flush()
        rid = r.id
        rules.sync_prefs(s)
    ev = _rule_evaluated(rid)
    with session_scope() as s:
        return {**rules.rule_dict(s.get(AlertRule, rid)), "evaluation": ev}


@app.patch("/api/alerts/rules/{rule_id}")
def update_rule(rule_id: int, body: dict):
    from .db import AlertRule, utcnow
    try:
        data = rules.validate(body, partial=True)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    with session_scope() as s:
        r = s.get(AlertRule, rule_id)
        if not r:
            raise HTTPException(404, "Rule not found")
        for k, v in data.items():
            setattr(r, k, v)
        r.updated_at = utcnow()
        rules.sync_prefs(s)
        enabled = r.enabled
    ev = _rule_evaluated(rule_id) if enabled else None
    with session_scope() as s:
        return {**rules.rule_dict(s.get(AlertRule, rule_id)), "evaluation": ev}


@app.delete("/api/alerts/rules/{rule_id}")
def delete_rule(rule_id: int):
    from .db import AlertRule
    with session_scope() as s:
        r = s.get(AlertRule, rule_id)
        if not r:
            raise HTTPException(404, "Rule not found")
        from .db import Alert
        from sqlalchemy import delete as sa_delete
        removed = s.execute(sa_delete(Alert).where(Alert.rule_id == rule_id)).rowcount
        s.delete(r)
        s.flush()
        rules.sync_prefs(s)
    return {"deleted": rule_id, "alerts_removed": removed}


@app.post("/api/alerts/evaluate")
def evaluate_alerts():
    """Deterministic and cheap (no network, no model), so safe to expose."""
    return rules.evaluate()


# ------------------------------------------------------------------ pull
def _sym(symbol: str) -> str:
    sym = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
    if not sym.replace("&", "").replace("-", "").isalnum():
        raise HTTPException(400, "Use an NSE symbol, e.g. DIXON")
    return sym


def _guard(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except FetchError as e:
        raise HTTPException(502, f"Source unavailable: {e}") from e
    except KeyError as e:
        raise HTTPException(404, f"Not found: {e}") from e


@app.get("/api/search")
def search_companies(q: str = Query(..., min_length=1)):
    ql = q.strip().upper()
    with session_scope() as s:
        local = [{"symbol": c.symbol, "name": c.name, "in_portfolio": c.in_portfolio}
                 for c in s.scalars(select(Company)) if ql in c.symbol or ql in (c.name or "").upper()]
    remote = [] if len(local) >= 5 else screener.search(q)
    seen = {x["symbol"] for x in local}
    return local + [{**r, "in_portfolio": False} for r in remote if r["symbol"] not in seen]


@app.get("/api/research/{symbol}/overview")
def research_overview(symbol: str):
    sym = _sym(symbol)
    try:  # any NSE ticker: register it and start price/filing ingestion in the background
        registry.resolve(sym, background=True)
    except Exception as e:  # noqa: BLE001
        log.info("resolve skipped for %s: %s", sym, e)
    data = _guard(agent.overview, sym)
    with session_scope() as s:
        data["price"] = alerts.latest_snapshot(s, sym, get_prefs(s))
        c = s.get(Company, sym)
        data["in_portfolio"] = bool(c and c.in_portfolio)
    return data


def _cached_or_run(key: str, hours: float, run: bool, request: Request, compute, note: str):
    """Opening a screen never spends model calls. Cached results return instantly (marked stale when old);
    an uncached analysis runs only when the investor asks for it, and only then counts against the budget."""
    from .db import iso, kv_get_row
    with session_scope() as s:
        row = kv_get_row(s, key)
        cached = (dict(row.value), row.updated_at) if row else None
    fresh = bool(cached) and _fresh(key, hours)
    if cached and (fresh or not run):
        return {**cached[0], "cached_at": iso(cached[1]), "stale": not fresh}
    if not run and llm.available():
        return {"status": "not_run", "note": note}
    _budget(request, "research", RESEARCH_PER_IP_HOUR)
    return _guard(compute)


@app.get("/api/research/{symbol}/promises")
@app.get("/api/research/{symbol}/promise-tracker")
def research_promises(symbol: str, request: Request, run: bool = False):
    sym = _sym(symbol)
    return _cached_or_run(f"promises:{sym}", 24, run, request, lambda: promises.run(sym, force=True),
                          "Reads the last five earnings-call transcripts and checks each promise against reported numbers. "
                          "About a minute the first time, then cached.")


@app.get("/api/research/{symbol}/narrative")
def research_narrative(symbol: str, request: Request, run: bool = False):
    from .pull import narrative
    sym = _sym(symbol)
    return _cached_or_run(f"narrative:{sym}", 24, run, request, lambda: narrative.run(sym, force=True),
                          "Reads the last two earnings calls and checks how management described results against the reported figures.")


@app.get("/api/research/{symbol}/business")
def research_business(symbol: str, request: Request, run: bool = False):
    sym = _sym(symbol)
    return _cached_or_run(f"business:{sym}", 24 * 7, run, request, lambda: agent.business(sym, force=True),
                          "Reads the latest annual report for segments, products and markets.")


@app.get("/api/research/{symbol}/bullbear")
@app.get("/api/research/{symbol}/bull-bear")
def research_bullbear(symbol: str, request: Request, run: bool = False):
    sym = _sym(symbol)

    def compute():
        pr = None
        try:
            pr = promises.run(sym, max_age_hours=24 * 30)
        except Exception:  # noqa: BLE001
            pass
        return agent.bull_bear(sym, pr, force=True)
    return _cached_or_run(f"bullbear:{sym}", 24, run, request, compute,
                          "Weighs the computed metrics, the promise track record and the annual report into a cited bull and bear case.")


class Ask(BaseModel):
    question: str
    history: list[dict] = []  # earlier {question, summary} turns in this session


@app.post("/api/research/{symbol}/ask")
def research_ask(symbol: str, body: Ask, request: Request):
    if not body.question.strip():
        raise HTTPException(400, "Ask a question")
    _budget(request, "ask", ASK_PER_IP_HOUR)
    return _guard(agent.ask, _sym(symbol), body.question, body.history[-3:])


@app.get("/api/docs/{doc_id}/page/{page}")
def doc_page(doc_id: str, page: int):
    meta, text = _guard(store.get_page, doc_id, page)
    if text is None:
        meta, pages = _guard(store.load_pages, doc_id)
        text = pages[page - 1] if 0 < page <= len(pages) else None
    if text is None:
        raise HTTPException(404, "Page not available")
    return {"doc": meta, "page": page, "text": text, "open_url": f"{meta['url']}#page={page}"}


# ------------------------------------------------------------------ data engine (Part 1 contracts)
PERIOD_DAYS = {"1m": 31, "3m": 92, "6m": 183, "1y": 366, "2y": 731, "5y": 1827, "max": None}


def _company_or_404(s, sym: str) -> Company:
    c = s.get(Company, sym)
    if c is None:
        raise HTTPException(404, f"{sym} is not registered. POST /api/companies/resolve to add it.")
    return c


@app.get("/health")
def health_alias():
    return health()


@app.get("/api/companies")
def list_companies(portfolio: bool | None = None):
    with session_scope() as s:
        q = select(Company).order_by(Company.symbol)
        if portfolio is not None:
            q = q.where(Company.in_portfolio.is_(portfolio))
        return {"items": [registry.company_dict(c) for c in s.scalars(q)]}


@app.get("/api/companies/search")
def companies_search(q: str = Query(..., min_length=1, max_length=40)):
    return {"items": search_companies(q)}


class Resolve(BaseModel):
    symbol: str


@app.post("/api/companies/resolve")
def companies_resolve(body: Resolve, request: Request):
    _budget(request, "resolve", 30)
    try:
        return registry.resolve(body.symbol, background=True)
    except registry.ResolveError as e:
        raise HTTPException(e.status, {"message": str(e), "candidate": e.candidate}) from e


@app.get("/api/companies/{ticker}")
def company_detail(ticker: str):
    sym = _sym(ticker)
    with session_scope() as s:
        return registry.company_dict(_company_or_404(s, sym), s)


@app.get("/api/companies/{ticker}/prices")
def company_prices(ticker: str, period: str = "1y", start: date | None = None, end: date | None = None):
    sym = _sym(ticker)
    if period not in PERIOD_DAYS:
        raise HTTPException(422, f"period must be one of {', '.join(PERIOD_DAYS)}")
    end = end or date.today()
    if start is None and PERIOD_DAYS[period]:
        start = end - timedelta(days=PERIOD_DAYS[period])
    if start and start > end:
        raise HTTPException(422, "start must be on or before end")
    with session_scope() as s:
        _company_or_404(s, sym)
        all_bars = list(s.scalars(select(PriceBar).where(PriceBar.symbol == sym).order_by(PriceBar.date)))
        rows = []
        for i, b in enumerate(all_bars):
            if (start and b.date < start.isoformat()) or b.date > end.isoformat():
                continue
            st = alerts.day_stats(all_bars, i) or {}
            rows.append({"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume,
                         "change": round(b.close - st["prev_close"], 2) if st.get("prev_close") else None,
                         "pct": st.get("pct"), "volume_multiple": st.get("volume_multiple")})
        fresh, exp = quality.price_freshness(all_bars[-1].date if all_bars else None)
        return {"symbol": sym, "currency": "INR", "interval": "1d", "provider": all_bars[-1].source if all_bars else None,
                "adjusted": True, "adjustment": "Split- and dividend-adjusted (yfinance auto_adjust); volume is split-adjusted",
                "freshness": fresh, "expected_session": exp, "count": len(rows),
                "from": rows[0]["date"] if rows else None, "to": rows[-1]["date"] if rows else None, "bars": rows}


@app.get("/api/companies/{ticker}/announcements")
def company_announcements(ticker: str, category: str | None = None, start: date | None = None, end: date | None = None,
                          has_document: bool | None = None, sort: str = "desc", limit: int = Query(50, ge=1, le=200),
                          offset: int = Query(0, ge=0)):
    sym = _sym(ticker)
    from datetime import datetime as dt
    with session_scope() as s:
        _company_or_404(s, sym)
        q = select(Announcement).where(Announcement.symbol == sym)
        if category:
            q = q.where(Announcement.category.in_(category.split(",")))
        if start:
            q = q.where(Announcement.published_at >= dt.combine(start, dt.min.time()))
        if end:
            q = q.where(Announcement.published_at <= dt.combine(end, dt.max.time()))
        if has_document is not None:
            q = q.where(Announcement.attachment_url.is_not(None) if has_document else Announcement.attachment_url.is_(None))
        rows = list(s.scalars(q.order_by(Announcement.published_at.asc() if sort == "asc" else Announcement.published_at.desc())))
        names = {c.symbol: c.name for c in s.scalars(select(Company))}
        prefs = get_prefs(s)
        items = []
        for a in rows[offset:offset + limit]:
            d = digest.item_dict(a, names, prefs)
            d.update(exchange="BSE", original_category=a.bse_category, original_subcategory=a.bse_subcategory,
                     retrieved_at=a.retrieved_at.strftime("%Y-%m-%dT%H:%M:%SZ") if a.retrieved_at else None)
            items.append(d)
        return {"symbol": sym, "total": len(rows), "limit": limit, "offset": offset, "items": items}


@app.get("/api/companies/{ticker}/documents")
def company_documents(ticker: str, kind: str | None = None):
    sym = _sym(ticker)
    discovery_error = None
    try:  # discovery is separate from retrieval: register links now, download on demand
        snap = store.get_screener(sym, max_age_hours=24)
        for a in snap["documents"]["annual_reports"]:
            store.register_doc(sym, "annual_report", a["url"], title=a["title"], period=f"FY{a.get('year') or ''}")
        for c in snap["documents"]["concalls"]:
            if c.get("transcript"):
                store.register_doc(sym, "transcript", c["transcript"], title=f"Concall transcript, {c['period']}", period=c["period"])
            if c.get("ppt"):
                store.register_doc(sym, "presentation", c["ppt"], title=f"Investor presentation, {c['period']}", period=c["period"])
    except Exception as e:  # noqa: BLE001
        discovery_error = str(e)
    docs = store.list_docs(sym, kind)
    order = {"annual_report": 0, "transcript": 1, "presentation": 2, "filing": 3}
    docs.sort(key=lambda d: (order.get(d["kind"], 9), d["period"] or ""), reverse=False)
    return {"symbol": sym, "count": len(docs), "discovery_error": discovery_error, "items": docs}


@app.get("/api/documents/{doc_id}")
def document_detail(doc_id: str, load: bool = False):
    if load:
        meta, pages = _guard(store.load_pages, doc_id)
    else:
        meta, _ = _guard(store.get_page, doc_id, 1)
        pages = None
    out = {**meta}
    if pages is not None:
        out["preview"] = [{"page": i + 1, "text": t[:400]} for i, t in enumerate(pages[:3])]
    return out


@app.get("/api/documents/{doc_id}/pages/{page}")
def document_page(doc_id: str, page: int):
    return doc_page(doc_id, page)


@app.get("/api/companies/{ticker}/timeline")
def company_timeline(ticker: str, types: str | None = None, start: date | None = None, end: date | None = None):
    sym = _sym(ticker)
    with session_scope() as s:
        _company_or_404(s, sym)
        prefs = get_prefs(s)
    return timeline.build(sym, start=start, end=end, types=set(types.split(",")) if types else None, prefs=prefs)


@app.get("/api/companies/{ticker}/data-quality")
def company_data_quality(ticker: str):
    return _guard(quality.company_quality, _sym(ticker))


@app.get("/api/system/source-health")
def system_source_health():
    return quality.source_health()


# ------------------------------------------------------------------ frontend
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
