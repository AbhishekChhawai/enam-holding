"""Portfolio analysis for the mock portfolio of real securities.

Cost basis is derived, not invented: the configured amount is split by weight and 'bought' at each holding's
real close on the first trading day on/after the configured start date. Everything else follows from real
EOD prices: current value, returns, allocation by asset class and sector, value history, and the benchmark.
"""
from __future__ import annotations

from bisect import bisect_right

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import Company, PriceBar

ASSET_ORDER = ["Equity", "Debt", "Gold", "International"]
ASSET_LABEL = {"Equity": "Stocks", "Debt": "Debt", "Gold": "Gold", "International": "International"}


def _bars(s: Session, sym: str) -> list[PriceBar]:
    return list(s.scalars(select(PriceBar).where(PriceBar.symbol == sym).order_by(PriceBar.date)))


def _pct(a: float, b: float) -> float | None:
    return round((a / b - 1) * 100, 2) if b else None


HORIZONS = [("1W", 5), ("1M", 21), ("3M", 63), ("6M", 126), ("YTD", None), ("1Y", 252)]


def horizon_returns(dates: list[str], values: list[float]) -> dict:
    """Return over each horizon from a dated series (sessions, not calendar days). None when history is too short."""
    out: dict = {}
    if len(values) < 2:
        return {k: None for k, _ in HORIZONS}
    for k, n in HORIZONS:
        if n is None:
            year = dates[-1][:4]
            prior = [i for i, d in enumerate(dates) if d < f"{year}-01-01"]
            base = prior[-1] if prior else (0 if dates[0][:4] == year else None)   # last close of the previous year
            out[k] = {"pct": _pct(values[-1], values[base]), "from": dates[base]} if base is not None else None
        else:
            out[k] = {"pct": _pct(values[-1], values[-1 - n]), "from": dates[-1 - n]} if len(values) > n else None
    return out


def analyse(s: Session, cfg: dict) -> dict:
    amount = float(cfg.get("amount", 1_000_000))
    start = str(cfg.get("start", "2026-01-01"))
    holdings = list(s.scalars(select(Company).where(Company.in_portfolio.is_(True)).order_by(Company.symbol)))
    if not holdings:
        return {"status": "empty", "holdings": []}
    weights = {c.symbol: (c.weight if c.weight else 100 / len(holdings)) for c in holdings}
    total_w = sum(weights.values()) or 1
    rows, missing, series_in = [], [], {}
    for c in holdings:
        bars = _bars(s, c.symbol)
        after = [b for b in bars if b.date >= start]
        if not after:
            missing.append(c.symbol)
            continue
        buy, last = after[0], bars[-1]
        invested = amount * weights[c.symbol] / total_w
        qty = invested / buy.close
        current = qty * last.close
        prev = bars[-2].close if len(bars) >= 2 else None
        row = {"symbol": c.symbol, "name": c.name, "kind": c.kind or "stock", "asset_class": c.asset_class or "Equity",
               "sector": c.sector or "Other", "weight": round(weights[c.symbol] / total_w * 100, 2),
               "bought_on": buy.date, "avg_cost": round(buy.close, 2), "quantity": round(qty, 4), "last_close": round(last.close, 2),
               "last_date": last.date, "invested": round(invested, 2), "current": round(current, 2),
               "returns": round(current - invested, 2), "returns_pct": _pct(current, invested),
               "day_pct": _pct(last.close, prev) if prev else None, "meta": c.meta or {},
               "horizons": horizon_returns([b.date for b in bars], [b.close for b in bars])}
        und = (c.meta or {}).get("underlying")
        if und:
            ub = _bars(s, und)
            ua = [b for b in ub if b.date >= buy.date]
            if len(ub) >= 2 and ua:
                row["underlying"] = {"symbol": und, "name": (c.meta or {}).get("underlying_name", und), "last_date": ub[-1].date,
                                     "day_pct": _pct(ub[-1].close, ub[-2].close), "since_start_pct": _pct(ub[-1].close, ua[0].close),
                                     "source": ub[-1].source}
        rows.append(row)
        series_in[c.symbol] = ([b.date for b in after], [b.close for b in after], qty)
    if not rows:
        return {"status": "no_prices", "holdings": [], "missing": missing}
    invested = sum(r["invested"] for r in rows)
    current = sum(r["current"] for r in rows)
    for r in rows:
        r["allocation_pct"] = round(r["current"] / current * 100, 2)

    def group(key: str, order: list[str] | None = None):
        g: dict[str, dict] = {}
        for r in rows:
            k = r[key]
            e = g.setdefault(k, {"name": ASSET_LABEL.get(k, k) if key == "asset_class" else k, "key": k, "count": 0, "invested": 0.0, "current": 0.0})
            e["count"] += 1; e["invested"] += r["invested"]; e["current"] += r["current"]
        out = []
        for e in g.values():
            e.update(invested=round(e["invested"], 2), current=round(e["current"], 2), returns=round(e["current"] - e["invested"], 2),
                     returns_pct=_pct(e["current"], e["invested"]), allocation_pct=round(e["current"] / current * 100, 2))
            out.append(e)
        return sorted(out, key=lambda e: (order.index(e["key"]) if order and e["key"] in order else 99, -e["current"]))

    # daily value history: each holding valued at its latest close on or before the date (holidays carry forward)
    dates = sorted({d for ds, _, _ in series_in.values() for d in ds})
    history = []
    for d in dates:
        v = 0.0
        for ds, cs, q in series_in.values():
            i = bisect_right(ds, d) - 1
            if i >= 0:
                v += q * cs[i]
        history.append({"date": d, "value": round(v, 2)})
    def series_for(keep) -> tuple[list[str], list[float]]:
        vals = []
        for d in dates:
            v = 0.0
            for sym, (ds, cs, q) in series_in.items():
                if keep(sym):
                    i = bisect_right(ds, d) - 1
                    if i >= 0:
                        v += q * cs[i]
            vals.append(v)
        return dates, vals

    cls = {r["symbol"]: r["asset_class"] for r in rows}
    port_h = horizon_returns(*series_for(lambda _sym: True))
    asset_h = {k: horizon_returns(*series_for(lambda sym, k=k: cls[sym] == k)) for k in {r["asset_class"] for r in rows}}
    bench = None
    bcfg = cfg.get("benchmark") or {}
    if bcfg.get("symbol"):
        bb = [b for b in _bars(s, bcfg["symbol"]) if b.date >= start]
        if len(bb) >= 2:
            br = _pct(bb[-1].close, bb[0].close)
            pr = _pct(current, invested)
            ball = _bars(s, bcfg["symbol"])
            bench = {"symbol": bcfg["symbol"], "name": bcfg.get("name", bcfg["symbol"]), "from": bb[0].date, "to": bb[-1].date,
                     "returns_pct": br, "difference_pp": round(pr - br, 2) if (pr is not None and br is not None) else None,
                     "horizons": horizon_returns([b.date for b in ball], [b.close for b in ball])}
    return {"status": "ok", "mock": {"amount": amount, "start": start, "bought_on": min(r["bought_on"] for r in rows),
            "method": "Mock: the amount is split by weight and bought at each holding's real close on the first trading day on/after the start date."},
            "as_of": max(r["last_date"] for r in rows), "invested": round(invested, 2), "current": round(current, 2),
            "returns": round(current - invested, 2), "returns_pct": _pct(current, invested), "benchmark": bench,
            "by_asset": group("asset_class", ASSET_ORDER), "by_sector": group("sector"),
            "holdings": sorted(rows, key=lambda r: -r["current"]), "history": history, "missing": missing,
            "horizons": {"portfolio": port_h, "by_asset": asset_h, "order": [k for k, _ in HORIZONS],
                         "note": "Portfolio and asset-class returns start from the mock purchase date; holdings and the benchmark use their full price history."}}
