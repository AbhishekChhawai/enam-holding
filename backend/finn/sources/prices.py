"""End-of-day price & volume from Yahoo Finance (one batched call for the whole portfolio)."""
from __future__ import annotations

import logging
import math

import pandas as pd
import yfinance as yf
from sqlalchemy.orm import Session

from ..db import PriceBar

log = logging.getLogger("finn.prices")


def _frame_for(df: pd.DataFrame, ticker: str, multi: bool) -> pd.DataFrame | None:
    try:
        sub = df[ticker] if multi else df
    except KeyError:
        return None
    sub = sub.dropna(subset=["Close"]) if "Close" in sub else None
    return sub if sub is not None and len(sub) else None


def fetch_eod(symbols: list[str], period: str = "1y") -> dict[str, list[dict]]:
    """Return {symbol: [bar, ...]} using NSE (.NS) with a BSE (.BO) fallback per symbol."""
    out: dict[str, list[dict]] = {}
    if not symbols:
        return out
    tickers = [s if s.startswith("^") else f"{s}.NS" for s in symbols]
    df = yf.download(tickers, period=period, interval="1d", group_by="ticker",
                     auto_adjust=True, progress=False, threads=True)
    multi = isinstance(df.columns, pd.MultiIndex)
    missing = []
    for sym, tk in zip(symbols, tickers):
        sub = _frame_for(df, tk, multi)
        if sub is None:
            missing.append(sym)
            continue
        out[sym] = _bars(sub, "yfinance:INDEX" if sym.startswith("^") else "yfinance:NSE")
    for sym in [m for m in missing if not m.startswith("^")]:  # retry on BSE individually (indices have no BSE listing)
        try:
            sub = yf.download(f"{sym}.BO", period=period, interval="1d", auto_adjust=True, progress=False)
            if isinstance(sub.columns, pd.MultiIndex):
                sub.columns = sub.columns.get_level_values(0)
            if len(sub):
                out[sym] = _bars(sub.dropna(subset=["Close"]), "yfinance:BSE")
            else:
                log.warning("No price data for %s on NSE or BSE", sym)
        except Exception as e:  # noqa: BLE001
            log.warning("Price fetch failed for %s: %s", sym, e)
    return out


def _f(v) -> float | None:
    try:
        v = float(v)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _bars(sub: pd.DataFrame, source: str) -> list[dict]:
    bars = []
    for idx, row in sub.iterrows():
        close = _f(row.get("Close"))
        if close is None:
            continue
        bars.append({
            "date": pd.Timestamp(idx).strftime("%Y-%m-%d"),
            "open": _f(row.get("Open")), "high": _f(row.get("High")), "low": _f(row.get("Low")),
            "close": close, "volume": _f(row.get("Volume")), "source": source,
        })
    return bars


def store_bars(s: Session, symbol: str, bars: list[dict]) -> int:
    for b in bars:
        s.merge(PriceBar(symbol=symbol, **b))
    return len(bars)
