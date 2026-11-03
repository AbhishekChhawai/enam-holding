"""Narrative vs numbers: does management's description of performance match what was reported?

Different from the promise tracker: these are claims about results already delivered ("a strong
quarter", "margins improved"), not forward guidance. The cheap model only extracts the claim, its
verbatim quote and page; code measures the matching reported figure and classifies the fit with
fixed thresholds. The interpretation is a template, never a model's opinion, and a divergence is
framed as a question to ask, not an accusation.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from .. import llm, store
from ..db import kv_get_row, kv_set, session_scope, utcnow
from ..sources.pdf import with_page_markers
from . import periods as P
from .citations import quote_on_page
from .promises import SYSTEM, Tables, measure, transcripts

log = logging.getLogger("finn.narrative")

Metric = Literal["revenue", "ebitda_margin", "profit", "volume", "demand", "order_book", "cash_flow", "debt", "other"]
Direction = Literal["up", "strong", "flat", "down", "weak", "none"]


class NClaim(BaseModel):
    statement: str = Field(description="Plain-English paraphrase, <= 25 words")
    quote: str = Field(description="Verbatim words from the transcript, <= 40 words")
    page: int
    speaker: str | None = None
    metric: Metric
    direction: Direction = Field(description="What the claim asserts about the metric")
    period: Literal["reported_quarter", "year_to_date", "last_year", "not_specified"]


class NClaimList(BaseModel):
    items: list[NClaim]


LABEL = {"revenue": "revenue", "ebitda_margin": "EBITDA margin", "profit": "profit", "volume": "volumes",
         "demand": "demand", "order_book": "order book", "cash_flow": "cash flow", "debt": "debt", "other": "this"}
VERDICT_TEXT = {
    "supported": "The reported figures are consistent with this.",
    "partly": "The figures point the same way, but less strongly than the wording suggests.",
    "divergent": ("The reported figures point the other way. The transcript doesn't establish exactly how management "
                  "defines this, so treat it as a question to ask management, not a conclusion."),
    "not_measurable": "This isn't directly measurable from reported financial statements.",
    "insufficient": "The reported numbers needed to check this aren't available.",
}


def classify_growth(direction: str, v: float) -> str:
    if direction == "strong":
        return "supported" if v >= 10 else "partly" if v >= 0 else "divergent"
    if direction == "up":
        return "supported" if v > 0 else "divergent"
    if direction in ("down", "weak"):
        return "supported" if v < 0 else "partly" if v <= 5 else "divergent"
    if direction == "flat":
        return "supported" if abs(v) <= 3 else "partly" if abs(v) <= 8 else "divergent"
    return "not_measurable"


def classify_margin(direction: str, pp: float) -> str:
    if direction in ("up", "strong"):
        return "supported" if pp > 0.3 else "partly" if pp >= -0.3 else "divergent"
    if direction in ("down", "weak"):
        return "supported" if pp < -0.3 else "partly" if pp <= 0.3 else "divergent"
    if direction == "flat":
        return "supported" if abs(pp) <= 0.5 else "partly" if abs(pp) <= 1.5 else "divergent"
    return "not_measurable"


def judge(c: dict, call: dict, T: Tables) -> dict:
    out = {"verdict": "not_measurable", "numbers": None}
    metric, direction = c["metric"], c["direction"]
    if metric not in ("revenue", "ebitda_margin", "profit") or direction == "none" or not call.get("fy"):
        return out
    fy, q = call["fy"], call["q"]
    annual = c["period"] == "last_year" and q == 4
    qs = [(fy, x) for x in range(1, q + 1)] if c["period"] == "year_to_date" else [(fy, q)]
    if metric == "ebitda_margin":
        now = measure("ebitda_margin", [], T, annual_fy=fy) if annual else measure("ebitda_margin", qs, T)
        prev = measure("ebitda_margin", [], T, annual_fy=fy - 1) if annual else measure("ebitda_margin", [(a - 1, b) for a, b in qs], T)
        if not now or not prev:
            return {**out, "verdict": "insufficient"}
        pp = round(now["value"] - prev["value"], 1)
        numbers = {"value": pp, "unit": "pp", "period": now["period"], "text": f"EBITDA margin {now['value']}% vs {prev['value']}% a year earlier ({pp:+.1f} pp)",
                   "formula": "operating profit / sales, this period vs same period a year earlier", "inputs": prev["inputs"] + now["inputs"],
                   "source_url": now.get("source_url")}
        return {"verdict": classify_margin(direction, pp), "numbers": numbers}
    key = "revenue_growth" if metric == "revenue" else "pat_growth"
    m = measure(key, [], T, annual_fy=fy) if annual else measure(key, qs, T)
    if not m:
        return {**out, "verdict": "insufficient"}
    noun = "Revenue" if metric == "revenue" else "Net profit"
    numbers = {**m, "text": f"{noun} {m['value']:+.1f}% year on year ({m['period']})"}
    return {"verdict": classify_growth(direction, m["value"]), "numbers": numbers}


def explain(c: dict, verdict: str) -> str:
    return VERDICT_TEXT[verdict]


PROMPT = """{ctx}

Extract up to 8 statements where company management DESCRIBES PERFORMANCE ALREADY ACHIEVED
(e.g. "we delivered a strong quarter", "margins improved", "demand stayed weak", "volumes grew").
Rules:
- Only management's own words, never analysts' questions.
- Not forward-looking guidance; that is tracked separately.
- 'quote' must be copied verbatim from the page you cite.
- direction: what the statement asserts (strong/up/flat/down/weak), or none if it asserts no direction.
- period: reported_quarter (default for results commentary), year_to_date, last_year, or not_specified.

TRANSCRIPT:
{text}"""


def run(symbol: str, *, force: bool = False, max_age_hours: float = 24, calls_to_read: int = 2) -> dict:
    symbol = symbol.upper()
    key = f"narrative:{symbol}"
    if not force:
        with session_scope() as s:
            row = kv_get_row(s, key)
            if row and row.updated_at > utcnow() - timedelta(hours=max_age_hours):
                return row.value
    if not llm.available():
        return {"symbol": symbol, "status": "llm_disabled", "claims": []}
    company = store.get_screener(symbol)
    T = Tables(company)
    calls = transcripts(symbol, company)[-calls_to_read:]
    claims = []
    for c in calls:
        meta, pages = store.load_pages(c["doc_id"])
        if meta["status"] != "ok" or not pages:
            c["status"] = meta["status"]
            continue
        c["status"] = "ok"
        ctx = (f"This call was held in {c['period']} and discusses {P.short(c['fy'], c['q'])} results." if c.get("fy") else "")
        try:
            res = llm.generate(NClaimList, tier="fast", purpose="narrative_extract", system=SYSTEM,
                               prompt=PROMPT.format(ctx=ctx, text=with_page_markers(pages, max_chars=140000)), max_output_tokens=4000)
        except Exception as e:  # noqa: BLE001
            log.warning("narrative extraction failed for %s %s: %s", symbol, c["period"], e)
            c["status"] = "extract_failed"
            continue
        for j, cl in enumerate(res.items):
            d = cl.model_dump()
            ok = 1 <= cl.page <= len(pages) and quote_on_page(cl.quote, pages[cl.page - 1])
            if not ok:
                for i, t in enumerate(pages, start=1):
                    if quote_on_page(cl.quote, t):
                        d["page"], ok = i, True
                        break
            if not ok:
                continue  # an unverifiable quote is dropped, not shown
            d.update(id=f"{c['doc_id']}-n{j}", doc_id=c["doc_id"], call_period=c["period"], call_quarter=c["quarter"],
                     metric_label=LABEL.get(cl.metric, cl.metric))
            d.update(judge(d, c, T))
            d["interpretation"] = explain(d, d["verdict"])
            claims.append(d)
    order = {"divergent": 0, "partly": 1, "supported": 2, "insufficient": 3, "not_measurable": 4}
    claims.sort(key=lambda x: (order[x["verdict"]], x["call_period"]))
    tally = {k: sum(1 for x in claims if x["verdict"] == k) for k in order}
    measurable = tally["supported"] + tally["partly"] + tally["divergent"]
    headline = None
    if measurable:
        headline = f"{tally['supported']} of {measurable} measurable claims are backed by the reported numbers"
        if tally["divergent"]:
            headline += f"; {tally['divergent']} {'points' if tally['divergent'] == 1 else 'point'} the other way"
    result = {"symbol": symbol, "status": "ok", "generated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
              "basis": company.get("basis"), "headline": headline, "tally": tally, "claims": claims,
              "transcripts": [{k: c.get(k) for k in ("doc_id", "period", "quarter", "status")} for c in calls]}
    with session_scope() as s:
        kv_set(s, key, result)
    return result
