"""Regression fixtures for screener.in layout changes observed on the live page (1 Nov 2026):
'Annual Report 2026' titles, BSE viewer links for transcripts, a Free Cash Flow row, half-year balance-sheet columns."""
import copy

from bs4 import BeautifulSoup

from conftest import FIXTURES
from finn.pull import metrics
from finn.sources import screener
from finn.sources.bse_filings import ATTACH_HIS, ATTACH_LIVE, attachment_candidates

LIVE_DOCS = """
<section id="documents"><div class="documents annual-reports"><h3>Annual reports</h3><ul class="list-links">
<li><a href="https://www.bseindia.com/xml-data/corpfiling/AttachHis/5ef88e3c-352d-4223-a8ec-bdd7d3aa31c1.pdf">Annual Report 2026<div class="ink-600 smaller">from bse</div></a></li>
<li><a href="https://www.bseindia.com/bseplus/AnnualReport/540699/74024540699.pdf">Annual Report 2022<div>from bse</div></a></li></ul></div>
<div class="documents concalls"><h3>Concalls</h3><ul class="list-links">
<li><div class="ink-600 font-size-15">Oct 2026</div><div class="concall-link inactive">Transcript</div><a class="concall-link" href="https://d1iixm87htyovw.cloudfront.net/x.mp3">REC</a></li>
<li><div class="ink-600 font-size-15">Aug 2026</div><a class="concall-link" href="https://www.bseindia.com/stockinfo/AnnPdfOpen.aspx?Pname=7ce2ca16-3043-48f4-97f9-a62a6a086c2f.pdf" title="Raw Transcript">Transcript</a>
<a class="concall-link" href="https://dixon-website.s3.ap-south-1.amazonaws.com/uploads/q1.pdf">PPT</a></li></ul></div></section>"""


def test_live_document_layout():
    d = screener.parse_documents(BeautifulSoup(LIVE_DOCS, "lxml"))
    assert [(a["title"], a["year"]) for a in d["annual_reports"]] == [("Annual Report 2026", 2026), ("Annual Report 2022", 2022)]
    assert [c["period"] for c in d["concalls"] if c.get("transcript")] == ["Aug 2026"]          # Oct 2026 has no transcript yet
    assert d["concalls"][0]["period"] == "Oct 2026" and "transcript" not in d["concalls"][0]


def test_bse_viewer_links_fall_back_to_direct_files():
    url = "https://www.bseindia.com/stockinfo/AnnPdfOpen.aspx?Pname=7ce2ca16-3043-48f4-97f9-a62a6a086c2f.pdf"
    assert attachment_candidates(url) == [url, ATTACH_LIVE + "7ce2ca16-3043-48f4-97f9-a62a6a086c2f.pdf", ATTACH_HIS + "7ce2ca16-3043-48f4-97f9-a62a6a086c2f.pdf"]
    other = "https://dixon-website.s3.ap-south-1.amazonaws.com/uploads/q1.pdf"
    assert attachment_candidates(other) == [other]


def _company_with_live_rows():
    c = screener.parse_company((FIXTURES / "screener_company.html").read_text())
    t = copy.deepcopy(c["tables"])
    t["cash_flow"]["rows"]["free cash flow"] = [28, 8, 10, -9, -72, -405]
    t["cash_flow"]["labels"]["free cash flow"] = "Free Cash Flow"
    bs = t["balance_sheet"]
    bs["headers"] = bs["headers"] + ["Sep 2026"]                   # half-year column, as on the live page
    for k in bs["rows"]:
        bs["rows"][k] = bs["rows"][k] + [bs["rows"][k][-1]]
    bs["rows"]["borrowings"][-1] = 999
    c["tables"] = t
    return c


def test_free_cash_flow_row_and_fiscal_year_comparisons():
    m = metrics.compute(_company_with_live_rows())
    cash = {x["label"]: x for x in m["cash"]}
    assert cash["Free cash flow"]["value"] == -405 and "Negative in 3 of the last 3 years" in cash["Free cash flow"]["note"]
    assert "CFO + CFI" not in cash                                   # proxy only when screener has no FCF row
    chg = next(x for x in m["balance"] if x["label"] == "Borrowings change 3y")
    assert chg["formula"] == "Borrowings Mar 2026 - Borrowings Mar 2023"   # fiscal year-ends, not the Sep half-year
