"""Company registry: symbol normalisation, validation and on-demand ingestion for unseen tickers.

Resolution rules (documented in docs/handoff.md):
  RELIANCE, RELIANCE.NS, NSE:RELIANCE  -> NSE symbol RELIANCE
  RELIANCE.BO, BSE:RELIANCE            -> same company, BSE preferred for the price fallback
  500325                               -> BSE scrip code, mapped back to the symbol via BSE lookup
A BSE lookup that returns a *different* symbol is treated as ambiguous and never silently accepted.
"""
from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timedelta

from sqlalchemy import func, select

from .db import Company, PriceBar, kv_get, kv_set, session_scope, utcnow
from .sources import bse_filings, screener
from .sources import prices as px

log = logging.getLogger("finn.registry")

SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]{1,20}$")
COOLDOWN_HOURS = 6
_job_slots = threading.BoundedSemaphore(2)  # at most two unseen-ticker ingestions at once
_sym_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class ResolveError(ValueError):
    def __init__(self, message: str, status: int = 404, candidate: dict | None = None):
        super().__init__(message)
        self.status, self.candidate = status, candidate


def normalize(raw: str) -> dict:
    s = re.sub(r"\s+", "", (raw or "").upper())
    exchange = "NSE"
    for prefix, ex in (("NSE:", "NSE"), ("BSE:", "BSE")):
        if s.startswith(prefix):
            s, exchange = s[len(prefix):], ex
    if s.endswith(".NS"):
        s = s[:-3]
    elif s.endswith(".BO"):
        s, exchange = s[:-3], "BSE"
    if re.fullmatch(r"\d{6}", s):
        return {"kind": "bse_code", "value": s, "exchange": "BSE"}
    if not SYMBOL_RE.match(s):
        raise ResolveError(f"'{raw}' is not a valid NSE/BSE symbol", status=422)
    return {"kind": "symbol", "value": s, "exchange": exchange}


def _bse_lookup(text: str) -> tuple[dict | None, str | None]:
    bse = None
    try:
        bse = bse_filings.client()
        return bse.lookup(text), None
    except Exception as e:  # noqa: BLE001
        return None, f"BSE lookup unavailable: {e}"
    finally:
        if bse is not None:
            bse.exit()


def validate(norm: dict) -> dict:
    ident = {"symbol": None, "name": None, "isin": None, "bse_code": None, "sources": [], "warnings": []}
    res, warn = _bse_lookup(norm["value"])
    if warn:
        ident["warnings"].append(warn)
    if res:
        same = (res.get("bse_code") == norm["value"]) if norm["kind"] == "bse_code" else (str(res.get("symbol", "")).upper() == norm["value"])
        if same:
            ident.update(symbol=str(res["symbol"]).upper(), name=res.get("company_name"), isin=res.get("isin"), bse_code=res.get("bse_code"))
            ident["sources"].append("bse_lookup")
        else:
            ident["candidate"] = res
    if not ident["symbol"] and norm["kind"] == "symbol":
        try:
            if px.fetch_eod([norm["value"]], period="5d").get(norm["value"]):
                ident["symbol"] = norm["value"]
                ident["sources"].append("yahoo_quote")
                if ident.get("candidate"):
                    ident["warnings"].append("BSE returned a different symbol; filings not linked to avoid a wrong match")
        except Exception as e:  # noqa: BLE001
            ident["warnings"].append(f"Yahoo check failed: {e}")
    if not ident["symbol"]:
        cand = ident.get("candidate")
        hint = f" Did you mean {cand.get('symbol')} ({cand.get('company_name')})?" if cand else ""
        raise ResolveError(f"Could not validate '{norm['value']}' on BSE or Yahoo Finance.{hint}", candidate=cand)
    if not ident["name"]:
        for hit in screener.search(ident["symbol"]):
            if hit["symbol"] == ident["symbol"]:
                ident["name"] = hit["name"]
                ident["sources"].append("screener_search")
                break
    return ident


def company_dict(c: Company, s=None) -> dict:
    out = {"symbol": c.symbol, "name": c.name, "sector": c.sector or None, "bse_code": c.bse_code, "isin": c.isin,
           "yahoo_symbol": f"{c.symbol}.NS", "in_portfolio": c.in_portfolio, "kind": c.kind or "stock",
           "asset_class": c.asset_class or "Equity", "weight": c.weight, "meta": c.meta or {}, "identity_sources": c.identity_sources or [],
           "validated_at": c.validated_at.strftime("%Y-%m-%dT%H:%M:%SZ") if c.validated_at else None}
    if s is not None:
        out["price_bars"] = s.scalar(select(func.count()).select_from(PriceBar).where(PriceBar.symbol == c.symbol)) or 0
        out["job"] = kv_get(s, f"job:{c.symbol}")
    return out


def _lock_for(sym: str) -> threading.Lock:
    with _locks_guard:
        return _sym_locks.setdefault(sym, threading.Lock())


def _set_job(sym: str, **kw) -> None:
    with session_scope() as s:
        job = kv_get(s, f"job:{sym}", {}) or {}
        job.update(kw)
        kv_set(s, f"job:{sym}", job)


def ingest(sym: str) -> dict:
    """Prices (1y) + BSE filings (90d) for one company. Idempotent; each step reports its own outcome."""
    from .push import refresh  # local import: refresh imports registry-free modules only
    steps = {}
    _set_job(sym, status="running", started_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"), steps=steps)
    try:
        n = 0
        data = px.fetch_eod([sym], period="1y")
        with session_scope() as s:
            for b in data.get(sym, []):
                s.merge(PriceBar(symbol=sym, **b))
                n += 1
        steps["prices"] = {"status": "ok" if n else "empty", "records": n}
    except Exception as e:  # noqa: BLE001
        steps["prices"] = {"status": "failed", "error": str(e)[:200]}
    with session_scope() as s:
        code = s.get(Company, sym).bse_code
    if code:
        try:
            steps["filings"] = {"status": "ok", "new_records": refresh.refresh_announcements(days=90, symbols=[sym])}
        except Exception as e:  # noqa: BLE001
            steps["filings"] = {"status": "failed", "error": str(e)[:200]}
    else:
        steps["filings"] = {"status": "unavailable", "error": "No confidently matched BSE code"}
    ok = any(v.get("status") == "ok" for v in steps.values())
    _set_job(sym, status="done" if ok else "failed", steps=steps, finished_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
    return steps


def resolve(raw: str, *, background: bool = True) -> dict:
    norm = normalize(raw)
    with session_scope() as s:
        if norm["kind"] == "bse_code":
            c = s.scalar(select(Company).where(Company.bse_code == norm["value"]))
        else:
            c = s.get(Company, norm["value"])
        existing = c is not None
        job = kv_get(s, f"job:{c.symbol}") if c else None
    if not existing:
        ident = validate(norm)
        with session_scope() as s:
            c = s.get(Company, ident["symbol"]) or Company(symbol=ident["symbol"], in_portfolio=False)
            c.name = ident["name"] or c.name or ident["symbol"]
            c.bse_code, c.isin = ident["bse_code"] or c.bse_code, ident["isin"] or c.isin
            c.identity_sources, c.validated_at, c.updated_at = ident["sources"], utcnow(), utcnow()
            s.merge(c)
        warnings = ident["warnings"]
    else:
        warnings = []
    sym = c.symbol
    recent = job and job.get("finished_at") and \
        datetime.strptime(job["finished_at"], "%Y-%m-%dT%H:%M:%SZ") > datetime.utcnow() - timedelta(hours=COOLDOWN_HOURS)
    with session_scope() as s:
        bars = s.scalar(select(func.count()).select_from(PriceBar).where(PriceBar.symbol == sym)) or 0
        portfolio = s.get(Company, sym).in_portfolio
    needs = not portfolio and not recent and not (job and job.get("status") in ("queued", "running")) and bars < 200
    if needs:
        _set_job(sym, status="queued", steps={})

        def work():
            lock = _lock_for(sym)
            if not lock.acquire(blocking=False):
                return
            try:
                with _job_slots:
                    ingest(sym)
            finally:
                lock.release()

        if background:
            threading.Thread(target=work, daemon=True).start()
        else:
            work()
    with session_scope() as s:
        out = company_dict(s.get(Company, sym), s)
    out.update(created=not existing, ingestion_started=needs, warnings=warnings, normalized=norm)
    return out
