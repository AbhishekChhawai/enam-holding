"""Quarterly results -> headline numbers (Revenue, EBITDA, PBT, PAT), this quarter vs last (QoQ)
and vs the same quarter last year (YoY).

Primary path: the results filing itself. Indian results filings (SEBI format) already carry three
quarter columns: current, previous and year-ago. The cheap model only *reads* those
columns; all arithmetic (EBITDA, growth, margins, unit conversion) is done here in code.

Cross-check: screener.in's standardised quarterly table. Agreement is shown as a badge; when
the filing is unreadable we fall back to screener and say so.
"""
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from .. import llm
from ..sources import screener
from ..sources.pdf import is_scanned, with_page_markers

log = logging.getLogger("finn.results")

UNIT_TO_CRORE = {"crore": 1.0, "lakh": 0.01, "million": 0.1, "thousand": 0.0001, "billion": 100.0, "rupees": 1e-7}


def to_crore(value: float | None, unit: str) -> float | None:
    if value is None:
        return None
    u = (unit or "").lower()
    for k, f in UNIT_TO_CRORE.items():
        if k in u:
            return value * f
    if re.search(r"\bmn\b", u):
        return value * 0.1
    if re.search(r"\bcr\b", u):
        return value
    return value  # assume crore; flagged via unit field in output


def pct_change(cur: float | None, base: float | None) -> float | None:
    if cur is None or base is None or base == 0:
        return None
    if base < 0:  # growth off a loss is not meaningful as a %
        return None
    return round((cur / base - 1) * 100, 1)


def build_card(metrics: dict[str, list[float | None]], periods: list[str], *, basis: str, source: str,
               source_url: str | None, unit_note: str = "₹ crore", is_lender: bool = False) -> dict:
    """metrics: {revenue|ebitda|pbt|pat: [current, previous, year_ago]} in ₹ crore."""
    rows = []
    for key, label in (("revenue", "Revenue"), ("ebitda", "Pre-provision profit" if is_lender else "EBITDA"),
                       ("pbt", "PBT"), ("pat", "PAT")):
        vals = list(metrics.get(key) or [])[:3]
        cur, prev, yago = vals + [None] * (3 - len(vals))
        rows.append({
            "key": key, "label": label,
            "current": _r(cur), "previous": _r(prev), "year_ago": _r(yago),
            "qoq_pct": pct_change(cur, prev), "yoy_pct": pct_change(cur, yago),
        })
    rev = metrics.get("revenue") or [None] * 3
    ebitda = metrics.get("ebitda") or [None] * 3
    margins = [round(e / r * 100, 1) if (e is not None and r) else None for e, r in zip(ebitda, rev)]
    return {
        "type": "results", "basis": basis, "unit": unit_note, "periods": periods,
        "rows": rows, "ebitda_margin": margins, "source": source, "source_url": source_url,
        "is_lender": is_lender,
        "ebitda_note": None if is_lender else "EBITDA = PBT + finance costs + depreciation - other income",
    }


def _r(v: float | None) -> float | None:
    return round(v, 2) if v is not None else None


# ------------------------------------------------------------ screener path
def card_from_screener(company: dict) -> dict | None:
    q = company["tables"].get("quarters")
    if not q:
        return None
    _, rev = screener.row(q, "sales", "revenue")
    ebitda_key, ebitda = screener.row(q, "operating profit", "financing profit")
    _, pbt = screener.row(q, "profit before tax")
    _, pat = screener.row(q, "net profit")
    if not rev:
        return None
    idx = max((i for i, v in enumerate(rev) if v is not None), default=None)
    if idx is None:
        return None
    pick = lambda arr, j: arr[j] if (arr and 0 <= j < len(arr)) else None  # noqa: E731
    cols = [idx, idx - 1, idx - 4]
    metrics = {k: [pick(arr, j) for j in cols] for k, arr in
               (("revenue", rev), ("ebitda", ebitda), ("pbt", pbt), ("pat", pat))}
    periods = [q["headers"][j] if 0 <= j < len(q["headers"]) else "" for j in cols]
    pdf = q["pdf_links"][idx] if idx < len(q.get("pdf_links") or []) else None
    return build_card(metrics, periods, basis=company.get("basis", ""), source="screener.in",
                      source_url=pdf or company.get("url"),
                      is_lender=bool(ebitda_key and ebitda_key.startswith("financing")))


# ------------------------------------------------------------ filing path
class _Col(BaseModel):
    current: float | None = None
    previous: float | None = None
    year_ago: float | None = None


class FilingNumbers(BaseModel):
    is_results_filing: bool = Field(description="False if this document does not contain a results table")
    basis: str = Field(description="'consolidated' or 'standalone' - prefer consolidated if both are present")
    unit: str = Field(description="Unit stated in the table header, e.g. 'Rs in crore', 'Rs in lakhs', 'Rs million'")
    period_current: str = Field(description="e.g. 'Quarter ended 30.09.2026'")
    period_previous: str
    period_year_ago: str
    revenue_from_operations: _Col
    other_income: _Col
    finance_costs: _Col
    depreciation_and_amortisation: _Col
    profit_before_exceptional_items_and_tax: _Col
    profit_before_tax: _Col
    profit_after_tax: _Col = Field(description="Net profit for the period (before other comprehensive income)")
    page: int | None = Field(default=None, description="PDF page number of the table used")


PROMPT = """You are reading an Indian listed company's quarterly financial results filing.
Copy numbers exactly as printed for the three QUARTER columns: current quarter, previous (immediately
preceding) quarter, and the same quarter of the previous year. Ignore half-year/nine-month/annual columns.
Use the consolidated table if both consolidated and standalone are present. Numbers in brackets are negative.
Do not compute anything. If a line item is absent, return null for it.
"""


def card_from_filing(pdf_path, pages: list[str] | None) -> dict | None:
    if not llm.available():
        return None
    if pages and not is_scanned(pages):
        res = llm.generate(FilingNumbers, tier="fast", purpose="results_extract",
                           prompt=PROMPT + "\n\nDOCUMENT:\n" + with_page_markers(pages, max_chars=60000))
    else:
        data = open(pdf_path, "rb").read()
        if len(data) > 18 * 1024 * 1024:
            return None
        res = llm.generate(FilingNumbers, tier="fast", purpose="results_extract_pdf", prompt=PROMPT, pdf_bytes=[data])
    if not res.is_results_filing:
        return None
    u = res.unit
    def col(c: _Col) -> list[float | None]:
        return [to_crore(c.current, u), to_crore(c.previous, u), to_crore(c.year_ago, u)]
    rev, oi, fin, dep = col(res.revenue_from_operations), col(res.other_income), col(res.finance_costs), col(res.depreciation_and_amortisation)
    pbt_pre = col(res.profit_before_exceptional_items_and_tax)
    pbt, pat = col(res.profit_before_tax), col(res.profit_after_tax)
    base_pbt = [a if a is not None else b for a, b in zip(pbt_pre, pbt)]
    ebitda = [
        (p + (f or 0) + (d or 0) - (o or 0)) if p is not None else None
        for p, f, d, o in zip(base_pbt, fin, dep, oi)
    ]
    card = build_card({"revenue": rev, "ebitda": ebitda, "pbt": pbt, "pat": pat},
                      [res.period_current, res.period_previous, res.period_year_ago],
                      basis=res.basis, source="results filing", source_url=None)
    card["source_page"] = res.page
    card["unit_as_filed"] = u
    return card


def reconcile(filing: dict | None, scr: dict | None) -> dict | None:
    """Prefer the filing; mark whether screener agrees on revenue and PAT (within 2%)."""
    if filing is None:
        if scr:
            scr["check"] = {"status": "screener_only", "note": "Filing could not be read; figures from screener.in"}
        return scr
    if scr is None:
        filing["check"] = {"status": "unverified", "note": "No screener.in figures to cross-check"}
        return filing
    def close(a, b):
        return a is not None and b is not None and abs(a - b) <= max(abs(b) * 0.02, 0.5)
    rev_f, rev_s = filing["rows"][0]["current"], scr["rows"][0]["current"]
    pat_f, pat_s = filing["rows"][3]["current"], scr["rows"][3]["current"]
    if close(rev_f, rev_s) and close(pat_f, pat_s):
        filing["check"] = {"status": "match", "note": "Revenue and PAT match screener.in"}
    elif filing["basis"] != scr["basis"]:
        filing["check"] = {"status": "basis_differs", "note": f"Filing is {filing['basis']}, screener is {scr['basis']}"}
    else:
        filing["check"] = {"status": "mismatch",
                           "note": f"screener.in shows revenue {rev_s} / PAT {pat_s}; treat with care"}
    return filing
