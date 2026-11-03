"""Management change -> who is coming or going, and where they came from.

SEBI's disclosure rules require a listed company to include a brief profile of a newly
appointed director/KMP in the exchange filing itself, so the bio is extracted from the
primary document (no scraping). We add a LinkedIn search link for one-tap follow-up.
"""
from __future__ import annotations

from typing import Literal
from urllib.parse import quote_plus

from pydantic import BaseModel, Field

from .. import llm
from ..sources.pdf import is_scanned, with_page_markers


class Person(BaseModel):
    name: str
    role: str = Field(description="Designation, e.g. 'Chief Financial Officer'")
    change: Literal["appointed", "resigned", "retired", "re-designated", "re-appointed", "ceased", "other"]
    effective_date: str | None = None
    reason: str | None = Field(default=None, description="Reason given, only if stated")
    profile: str | None = Field(default=None, description="<= 60 words, only from the filing's brief profile")
    previous_roles: list[str] = Field(default_factory=list, description="Earlier employers/roles named in the filing")
    page: int | None = None


class MgmtChange(BaseModel):
    people: list[Person]
    is_top_role: bool = Field(description="True if CEO, CFO, MD, Chair, COO or whole-time director")


PROMPT = """This is an Indian listed company's exchange filing about a change in directors or key
managerial personnel. Extract every person whose position changes. Use only what the filing says;
leave fields null rather than guessing. Keep 'profile' to the facts in the filing's brief profile
(education, prior employers, years of experience)."""


def enrich(pdf_path, pages: list[str] | None, company_name: str) -> dict | None:
    if not llm.available():
        return None
    if pages and not is_scanned(pages):
        res = llm.generate(MgmtChange, tier="fast", purpose="mgmt_extract",
                           prompt=PROMPT + "\n\nDOCUMENT:\n" + with_page_markers(pages[:12], max_chars=40000))
    else:
        data = open(pdf_path, "rb").read()
        if len(data) > 18 * 1024 * 1024:
            return None
        res = llm.generate(MgmtChange, tier="fast", purpose="mgmt_extract_pdf", prompt=PROMPT, pdf_bytes=[data])
    if not res.people:
        return None
    people = []
    for p in res.people:
        d = p.model_dump()
        d["linkedin_search"] = ("https://www.linkedin.com/search/results/people/?keywords="
                                + quote_plus(f"{p.name} {company_name}"))
        people.append(d)
    return {"type": "management_change", "people": people, "is_top_role": res.is_top_role}
