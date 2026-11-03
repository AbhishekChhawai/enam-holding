"""Unusual-move detection on end-of-day data. Pure arithmetic: no model involved.

A day is flagged when |close-to-close move| >= price_move_pct, or volume >= volume_multiple x
its trailing 20-session average (excluding that day). Thresholds are the investor's to set.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import PriceBar

LOOKBACK = 20


def _bars(s: Session, symbol: str, limit: int = 300) -> list[PriceBar]:
    rows = list(s.scalars(select(PriceBar).where(PriceBar.symbol == symbol).order_by(PriceBar.date.desc()).limit(limit)))
    return rows[::-1]


def day_stats(bars: list[PriceBar], i: int) -> dict | None:
    if i < 1:
        return None
    b, p = bars[i], bars[i - 1]
    pct = (b.close / p.close - 1) * 100 if p.close else None
    window = [x.volume for x in bars[max(0, i - LOOKBACK):i] if x.volume]
    avg = sum(window) / len(window) if len(window) >= 5 else None
    vmult = (b.volume / avg) if (avg and b.volume) else None
    year = [x.close for x in bars[max(0, i - 252):i]]
    return {
        "date": b.date, "close": round(b.close, 2), "prev_close": round(p.close, 2),
        "pct": round(pct, 2) if pct is not None else None,
        "volume": b.volume, "avg_volume_20d": round(avg) if avg else None,
        "volume_multiple": round(vmult, 2) if vmult else None,
        "high_52w": max(year) if len(year) > 100 else None,
        "low_52w": min(year) if len(year) > 100 else None,
    }


def flags_for(stat: dict, price_pct: float, vol_mult: float) -> list[str]:
    f = []
    if stat.get("pct") is not None and abs(stat["pct"]) >= price_pct:
        f.append("price")
    if stat.get("volume_multiple") is not None and stat["volume_multiple"] >= vol_mult:
        f.append("volume")
    if stat.get("high_52w") and stat["close"] > stat["high_52w"]:
        f.append("52w_high")
    if stat.get("low_52w") and stat["close"] < stat["low_52w"]:
        f.append("52w_low")
    return f


def describe(stat: dict, flags: list[str]) -> str:
    parts = []
    pct = stat.get("pct")
    if pct is not None:
        parts.append(f"{'up' if pct >= 0 else 'down'} {abs(pct):.1f}% to ₹{stat['close']:,.2f}")
    if "volume" in flags and stat.get("volume_multiple"):
        parts.append(f"on {stat['volume_multiple']:.1f}× its 20-day average volume")
    if "52w_high" in flags:
        parts.append("a new 52-week high")
    if "52w_low" in flags:
        parts.append("a new 52-week low")
    return ", ".join(parts).capitalize() if parts else ""


def moves_in_window(s: Session, symbols: list[str], since: date, prefs: dict) -> list[dict]:
    """Every flagged trading day per symbol on or after `since` (EOD data has no intraday)."""
    out = []
    for sym in symbols:
        bars = _bars(s, sym)
        for i in range(len(bars) - 1, 0, -1):
            if bars[i].date < since.isoformat():
                break
            st = day_stats(bars, i)
            if not st:
                continue
            fl = flags_for(st, prefs["price_move_pct"], prefs["volume_multiple"])
            if fl and ("price" in fl or "volume" in fl):
                out.append({"symbol": sym, "flags": fl, "text": describe(st, fl), **st})
    out.sort(key=lambda m: (m["date"], abs(m.get("pct") or 0)), reverse=True)
    return out


def latest_snapshot(s: Session, symbol: str, prefs: dict) -> dict | None:
    bars = _bars(s, symbol, limit=300)
    if len(bars) < 2:
        return None
    st = day_stats(bars, len(bars) - 1)
    if st is None:
        return None
    st["flags"] = flags_for(st, prefs["price_move_pct"], prefs["volume_multiple"])
    st["spark"] = [round(b.close, 2) for b in bars[-30:]]
    first = bars[-252].close if len(bars) >= 252 else bars[0].close
    st["pct_1y"] = round((bars[-1].close / first - 1) * 100, 1) if first else None
    return st


def window_start(hours: int, now: datetime | None = None) -> datetime:
    return (now or datetime.utcnow()) - timedelta(hours=hours)
