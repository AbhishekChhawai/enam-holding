"""Indian fiscal-period arithmetic. FY26 = Apr 2025 - Mar 2026; Q1 ends Jun, Q2 Sep, Q3 Dec, Q4 Mar.
Screener labels quarter columns by quarter-end month ("Sep 2025") and years by "Mar 2025"."""
from __future__ import annotations

import re

MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
Q_END = {1: "Jun", 2: "Sep", 3: "Dec", 4: "Mar"}


def parse_label(label: str) -> tuple[int, int] | None:
    m = re.match(r"\s*([A-Z][a-z]{2})\w*\s+(\d{4})", label or "")
    if not m or m.group(1) not in MONTHS:
        return None
    return MONTHS[m.group(1)], int(m.group(2))


def quarter_of(label: str) -> tuple[int, int] | None:
    """'Sep 2025' -> (2026, 2)  i.e. (fiscal year, quarter)."""
    p = parse_label(label)
    if not p:
        return None
    month, year = p
    q = {6: 1, 9: 2, 12: 3, 3: 4}.get(month)
    if q is None:
        return None
    fy = year + 1 if q in (1, 2, 3) else year
    return fy, q


def quarter_label(fy: int, q: int) -> str:
    return f"{Q_END[q]} {fy - 1 if q in (1, 2, 3) else fy}"


def fy_label(fy: int) -> str:
    return f"Mar {fy}"


def short(fy: int, q: int | None = None) -> str:
    return f"Q{q} FY{fy % 100:02d}" if q else f"FY{fy % 100:02d}"


def call_month_to_quarter(call_period: str) -> tuple[int, int] | None:
    """A concall held in 'Jul 2025' discusses the quarter that ended Jun 2025 -> (2026, 1)."""
    p = parse_label(call_period)
    if not p:
        return None
    month, year = p
    # most recent quarter-end strictly before the call month
    for back in range(1, 4):
        m, y = month - back, year
        if m <= 0:
            m += 12
            y -= 1
        if m in (3, 6, 9, 12):
            return quarter_of(f"{list(MONTHS)[m - 1]} {y}")
    return None


def _fy(text: str) -> int:
    v = int(text)
    return v + 2000 if v < 100 else v


def parse_horizon(text: str) -> dict:
    """Turn management's horizon wording into something we can evaluate."""
    t = (text or "").upper().replace("’", "'").replace("‘", "'")
    t = re.sub(r"\s+", " ", t)
    m = re.search(r"\bQ([1-4])\s*'?\s*FY\s*'?(\d{2,4})\b", t) or re.search(r"\bFY\s*'?(\d{2,4})\s*Q([1-4])\b", t)
    if m:
        a, b = m.groups()
        if m.re.pattern.startswith(r"\bQ"):
            return {"kind": "quarter", "fy": _fy(b), "q": int(a)}
        return {"kind": "quarter", "fy": _fy(a), "q": int(b)}
    m = re.search(r"\bH([12])\s*'?\s*FY\s*'?(\d{2,4})\b", t)
    if m:
        return {"kind": "half", "fy": _fy(m.group(2)), "h": int(m.group(1))}
    m = re.search(r"\bFY\s*'?(\d{2,4})\s*[-–/TO ]+\s*(?:FY)?\s*'?(\d{2,4})\b", t)
    if m:
        return {"kind": "multi_year", "fy": _fy(m.group(2)), "from_fy": _fy(m.group(1))}
    m = re.search(r"\bFY\s*'?(\d{2,4})\b", t) or re.search(r"\b(?:FISCAL|FINANCIAL YEAR)\s*(?:YEAR\s*)?'?(\d{2,4})\b", t)
    if m:
        return {"kind": "fy", "fy": _fy(m.group(1))}
    if re.search(r"NEXT (FEW|COUPLE|2|3|TWO|THREE)|MEDIUM|LONG|YEARS", t):
        return {"kind": "multi_year"}
    if re.search(r"THIS YEAR|CURRENT YEAR|FULL YEAR|FOR THE YEAR", t):
        return {"kind": "current_fy"}
    if re.search(r"NEXT YEAR", t):
        return {"kind": "next_fy"}
    if re.search(r"NEXT QUARTER|COMING QUARTER", t):
        return {"kind": "next_quarter"}
    return {"kind": "vague"}
