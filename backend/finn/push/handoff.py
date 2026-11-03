"""'Research this': the documented context a Push event hands to the Pull research agent.

Contract (stable): symbol, company, event_id, category, headline, summary, published_at,
related_filing_ids, document_ids, reporting_period, suggested_question, target_tab.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select

from ..db import Announcement, Company, iso, session_scope
from .. import store
from . import classify
from .digest import cluster, item_dict

QUESTIONS = {
    "results": ("promises", "How do the {period} results compare with what management guided earlier, and what did they say about the next quarter?"),
    "earnings_call": ("promises", "What did management guide on this call, and how does it compare with what they delivered?"),
    "management_change": ("ask", "What has management said about leadership and succession, and does this change affect any stated plans?"),
    "M&A": ("ask", "What has management said about acquisitions and capital allocation, and how large is this deal relative to the business?"),
    "fund_raise": ("ask", "Why is the company raising funds, and what has management said about debt, capex and funding needs?"),
    "capex": ("ask", "What capex has management guided, and what returns or timelines have they committed to?"),
    "litigation": ("ask", "What contingent liabilities and legal or regulatory risks does the annual report disclose?"),
    "credit_rating": ("numbers", "How have borrowings, leverage and cash flow moved over the last few years?"),
}


def research_context(announcement_id: str) -> dict:
    with session_scope() as s:
        a = s.get(Announcement, announcement_id)
        if a is None:
            raise KeyError(announcement_id)
        c = s.get(Company, a.symbol)
        nearby = list(s.scalars(select(Announcement).where(
            Announcement.symbol == a.symbol,
            Announcement.published_at >= a.published_at - timedelta(hours=36),
            Announcement.published_at <= a.published_at + timedelta(hours=36))))
        items = [item_dict(x, {}, {"category_weights": {}, "alert_categories": []}) for x in nearby]
        cluster(items)
        mine = next((it for it in items if it["id"] == a.id), None)
        anchor = mine if mine and mine.get("related") else next((it for it in items if any(r["id"] == a.id for r in it.get("related", []))), mine)
        related_ids = [r["id"] for r in (anchor or {}).get("related", [])] + ([anchor["id"]] if anchor and anchor["id"] != a.id else [])
        urls = [x.attachment_url for x in nearby if x.id in set(related_ids) | {a.id} and x.attachment_url]
        period = None
        if a.enrichment_status == "ok" and (a.enrichment or {}).get("type") == "results":
            period = (a.enrichment.get("periods") or [None])[0]
        tab, q = QUESTIONS.get(a.category, ("ask", "What has management said in recent calls and the annual report that bears on this filing?"))
        return {
            "symbol": a.symbol, "company": c.name if c else a.symbol, "event_id": a.id, "category": a.category,
            "category_label": classify.LABELS.get(a.category, a.category), "headline": a.headline or a.subject,
            "summary": a.summary, "published_at": iso(a.published_at), "related_filing_ids": related_ids,
            "document_ids": [store.doc_id_for(u) for u in urls], "reporting_period": period,
            "suggested_question": q.format(period=period or "latest"), "target_tab": tab,
        }
