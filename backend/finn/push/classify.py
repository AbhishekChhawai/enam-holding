"""Announcement classification + materiality scoring.

Rules first (free, instant, explainable); the cheap LLM only sees what the rules can't place,
in one batched call. Each score carries human-readable reasons so the UI can say *why*
something was surfaced or collapsed.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from .. import llm

CATEGORIES = [
    "results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading",
    "earnings_call", "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex",
    "press_release", "postal_ballot", "agm_egm", "pledging", "unclassified",
]
CategoryLit = Literal[
    "results", "M&A", "fund_raise", "management_change", "litigation", "insider_trading",
    "earnings_call", "investor_meetings", "credit_rating", "dividend", "bonus_split", "capex",
    "press_release", "postal_ballot", "agm_egm", "pledging", "unclassified",
]

LABELS = {
    "results": "Results", "M&A": "M&A", "fund_raise": "Fund raise", "management_change": "Management",
    "litigation": "Legal & regulatory", "insider_trading": "Insider trade", "earnings_call": "Earnings call",
    "investor_meetings": "Investor meeting", "credit_rating": "Credit rating", "dividend": "Dividend",
    "bonus_split": "Bonus / split", "capex": "Capex", "press_release": "Business update",
    "postal_ballot": "Postal ballot", "agm_egm": "AGM / EGM", "pledging": "Pledge", "unclassified": "Paperwork",
}

BASE_SCORE = {
    "results": 80, "M&A": 75, "management_change": 62, "fund_raise": 65, "litigation": 58,
    "credit_rating": 50, "capex": 55, "pledging": 55, "bonus_split": 50, "press_release": 40,
    "dividend": 35, "insider_trading": 32, "earnings_call": 25, "investor_meetings": 12,
    "agm_egm": 15, "postal_ballot": 18, "unclassified": 5,
}

# Ordered: the first matching rule wins. Routine paperwork is caught early so that
# words like "allotment" or "certificate" don't masquerade as material events.
RULES: list[tuple[str, re.Pattern]] = [(c, re.compile(p, re.I)) for c, p in [
    ("unclassified", r"esop|esos|employee stock|stock option|reg(ulation)?\.?\s*74\s*\(5\)|loss of (share )?certificate|"
                     r"duplicate (share )?certificate|trading window|compliance certificate|reg(ulation)?\.?\s*39|"
                     r"investor (grievance|complaint)|business responsibility|\bbrsr\b|\besg\b|sustainability report|"
                     r"secretarial|statutory auditor|cost auditor|internal auditor|scrutini[sz]er.s report on agm|"
                     r"change in (registrar|rta)|xbrl|reg(ulation)?\.?\s*23\s*\(9\)|related party transactions? for the half"),
    ("pledging", r"pledg|encumbr|reg(ulation)?\.?\s*31\s*\("),
    ("insider_trading", r"insider trading|\bsast\b|reg(ulation)?\.?\s*7\s*\(|reg(ulation)?\.?\s*29\s*\("),
    ("credit_rating", r"credit rating|\bcrisil\b|\bicra\b|care ratings|india ratings|acuit[eé]|brickwork|"
                      r"rating (agency|action|reaffirm)|reaffirm"),
    ("earnings_call", r"earnings call|conference call|con-?call|audio recording|transcript|"
                      r"recording of (the )?(call|meet)"),
    ("results", r"financial results|un-?audited|audited (standalone|consolidated|financial)|results for the (quarter|half|year)|"
                r"quarterly results|outcome of board meeting.*result|investor presentation|earnings (release|presentation)|"
                r"shareholders?.? letter|press release.*result"),
    ("bonus_split", r"\bbonus\b|stock split|sub-?division|split of (equity )?shares"),
    ("dividend", r"dividend"),
    ("M&A", r"acqui|merger|amalgamat|demerg|joint venture|\bjv\b|scheme of arrangement|divest|slump sale|"
            r"business transfer|stake in|incorporation of .*subsidiar|wholly.owned subsidiary|share purchase agreement"),
    ("fund_raise", r"rights issue|\bqip\b|qualified institution|preferential (issue|allotment)|buy-?back|"
                   r"commercial paper|non-convertible|\bncds?\b|debentures?|fund ?rais|raising of funds|warrants"),
    ("management_change", r"change in (directors?|key managerial|kmp|management|senior management)|appoint|resign|cessation|"
                          r"re-?designat|retire|chief (executive|financial|operating|technology)|managing director|"
                          r"\bcfo\b|\bceo\b|\bcoo\b|whole.?time director|company secretary|compliance officer"),
    ("litigation", r"litigation|penalt|show cause|\border\b.*(sebi|court|tribunal|authority|commissioner)|court|tribunal|"
                   r"\bnclt\b|insolvency|\bgst\b.*(demand|order|notice)|tax demand|income.tax|warning letter|usfda|"
                   r"form 483|observations|search (and|&) seizure|arbitra|regulatory action|fine of"),
    ("capex", r"capex|capital expenditure|capacity expansion|new (plant|facility|unit)|greenfield|brownfield|"
              r"commissioning|commercial production"),
    ("postal_ballot", r"postal ballot|e-?voting result|remote e-?voting"),
    ("agm_egm", r"annual general meeting|\bagm\b|\begm\b|extra-?ordinary general"),
    ("investor_meetings", r"analyst|investor (meet|conference|day)|institutional investor|meeting with (funds|investors)|"
                          r"one.on.one|group meet"),
    ("press_release", r"press release|media release|order|contract|launch|partnership|collaborat|clarification|"
                      r"\bwins?\b|\bbags?\b|secures?|award|agreement|\bmou\b"),
    ("unclassified", r"newspaper|publication|advertisement|intimation under reg"),
]]

BSE_CATEGORY_HINT = {
    "Result": "results", "Insider Trading / SAST": "insider_trading", "AGM/EGM": "agm_egm",
}


def rule_classify(subject: str, headline: str, bse_category: str | None, bse_subcategory: str | None) -> str | None:
    text = " | ".join(x for x in (bse_subcategory, subject, headline) if x)
    for cat, pat in RULES:
        if pat.search(text):
            return cat
    if bse_category in BSE_CATEGORY_HINT:
        return BSE_CATEGORY_HINT[bse_category]
    return None


# ---------------------------------------------------------------- scoring
_TOP_ROLE = re.compile(r"\b(ceo|cfo|coo|managing director|chief executive|chief financial|chairman|chairperson|whole.?time director)\b", re.I)
_LOW_ROLE = re.compile(r"company secretary|compliance officer|independent director|nominee director|senior management personnel", re.I)
_NOTICE = re.compile(r"intimation|to consider|will be held|prior notice|schedule of|is scheduled|notice of (board|meeting)|"
                     r"board meeting (date|intimation)", re.I)
_PAPER = re.compile(r"newspaper|advertisement|publication of", re.I)


def score(category: str, subject: str, headline: str, critical: bool = False) -> tuple[int, list[str]]:
    text = f"{subject} {headline}"
    s = BASE_SCORE.get(category, 5)
    reasons = [f"{LABELS.get(category, category)} filings start at {s}"]
    if category == "management_change":
        if _TOP_ROLE.search(text):
            s += 18; reasons.append("involves a top role (CEO/CFO/MD/Chair)")
        elif _LOW_ROLE.search(text):
            s -= 30; reasons.append("secretarial or independent-director change")
        if re.search(r"resign|cessation", text, re.I):
            s += 6; reasons.append("a departure")
    if category == "credit_rating":
        if re.search(r"downgrad|negative|watch", text, re.I):
            s += 20; reasons.append("downgrade or negative outlook")
        elif re.search(r"upgrad|positive", text, re.I):
            s += 10; reasons.append("upgrade")
        elif re.search(r"reaffirm", text, re.I):
            s -= 20; reasons.append("simple reaffirmation")
    if category == "press_release" and re.search(r"order|contract", text, re.I) and re.search(r"crore|cr\b|million|billion|bn\b", text, re.I):
        s += 18; reasons.append("an order win with a stated value")
    if category == "insider_trading" and re.search(r"promoter", text, re.I):
        s += 12; reasons.append("promoter transaction")
    if category == "litigation" and re.search(r"penalt|demand|order|warning letter|483", text, re.I):
        s += 8; reasons.append("an order, demand or warning")
    if category == "results" and re.search(r"investor presentation|shareholders?.? letter|press release", text, re.I):
        s -= 25; reasons.append("companion material to results")
    if _NOTICE.search(text) and category not in ("unclassified",):
        s -= 45; reasons.append("only a date notice")
    if _PAPER.search(text):
        s -= 55; reasons.append("newspaper copy of an earlier filing")
    if critical:
        s += 10; reasons.append("flagged critical by the exchange")
    return max(0, min(100, s)), reasons


def tier(score_value: int) -> str:
    if score_value >= 70:
        return "needs_you"
    if score_value >= 40:
        return "worth_a_look"
    return "routine"


# ---------------------------------------------------------------- LLM fallback
class _Item(BaseModel):
    i: int
    category: CategoryLit


class _Batch(BaseModel):
    items: list[_Item]


def llm_classify(items: list[tuple[int, str]]) -> dict[int, str]:
    """Classify leftovers in a single cheap call. items = [(index, 'subject | headline'), ...]."""
    if not items or not llm.available():
        return {}
    lines = "\n".join(f"{i}: {t[:300]}" for i, t in items)
    prompt = (
        "Classify each Indian stock-exchange announcement into exactly one category.\n"
        "Categories: results, M&A, fund_raise, management_change, litigation, insider_trading, earnings_call, "
        "investor_meetings, credit_rating, dividend, bonus_split, capex, press_release, postal_ballot, agm_egm, "
        "pledging, unclassified (routine compliance paperwork that does not move the stock).\n"
        "When unsure between a material category and unclassified, choose unclassified.\n\n" + lines
    )
    out = llm.generate(_Batch, tier="fast", purpose="classify_batch", prompt=prompt, max_output_tokens=2048)
    return {it.i: it.category for it in out.items}
