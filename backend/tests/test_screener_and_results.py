from conftest import FIXTURES
from finn.sources import screener
from finn.push.results import card_from_screener, to_crore, reconcile
from finn.pull import metrics


def company():
    c = screener.parse_company((FIXTURES / "screener_company.html").read_text())
    c.update(symbol="DIXON", basis="consolidated", url="https://www.screener.in/company/DIXON/consolidated/")
    return c


def test_tables_and_documents_parse():
    c = company()
    q = c["tables"]["quarters"]
    assert q["headers"][-1] == "Sep 2026"
    assert q["rows"]["sales"][-1] == 1560
    assert q["rows"]["opm %"][0] == 10
    assert q["pdf_links"][0].startswith("https://www.screener.in/company/source/quarter/")
    d = c["documents"]
    assert [a["year"] for a in d["annual_reports"]] == [2026, 2025]
    periods = [x["period"] for x in d["concalls"]]
    assert periods == ["Oct 2026", "Jul 2026", "May 2026"]
    assert d["concalls"][0]["transcript"].endswith("T_Oct2026.pdf")
    assert "transcript" not in d["concalls"][2]  # inactive transcript is not a link
    assert c["top_ratios"]["Market Cap"] == "95,000"


def test_results_card_qoq_yoy():
    card = card_from_screener(company())
    rev = card["rows"][0]
    assert card["periods"] == ["Sep 2026", "Jun 2026", "Sep 2025"]
    assert rev["current"] == 1560 and rev["previous"] == 1450 and rev["year_ago"] == 1300
    assert rev["qoq_pct"] == 7.6 and rev["yoy_pct"] == 20.0
    assert card["rows"][1]["label"] == "EBITDA"


def test_units_and_reconcile():
    assert to_crore(150000, "Rs in lakhs") == 1500
    assert to_crore(15000, "Rs million") == 1500
    scr = card_from_screener(company())
    filing = {**scr, "rows": [dict(r) for r in scr["rows"]], "source": "results filing"}
    assert reconcile(filing, scr)["check"]["status"] == "match"
    filing["rows"][0]["current"] = 1700
    assert reconcile(filing, scr)["check"]["status"] == "mismatch"


def test_metrics_have_formulas():
    m = metrics.compute(company())
    labels = {x["label"]: x for g in ("snapshot", "trajectory", "balance", "cash") for x in m[g]}
    assert labels["Revenue"]["value"] == 5380  # TTM column skipped
    assert labels["Revenue CAGR 5y"]["value"] == round(((5380 / 2500) ** (1 / 5) - 1) * 100, 1)
    assert labels["Debt / Equity"]["value"] == round(240 / 1630, 2)
    assert "CFO / PAT (5y cumulative)" in labels
    assert all(x["formula"] for x in labels.values())
