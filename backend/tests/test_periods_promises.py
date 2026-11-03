from conftest import FIXTURES
from finn.pull import periods as P
from finn.pull.promises import Tables, judge, verdict
from finn.sources import screener


def test_fiscal_mapping():
    assert P.quarter_of("Sep 2025") == (2026, 2)
    assert P.quarter_of("Mar 2026") == (2026, 4)
    assert P.quarter_label(2026, 3) == "Dec 2025"
    assert P.call_month_to_quarter("Jul 2025") == (2026, 1)
    assert P.call_month_to_quarter("Feb 2026") == (2026, 3)
    assert P.call_month_to_quarter("May 2026") == (2026, 4)


def test_horizon_parsing():
    assert P.parse_horizon("FY26") == {"kind": "fy", "fy": 2026}
    assert P.parse_horizon("Q3 FY26") == {"kind": "quarter", "fy": 2026, "q": 3}
    assert P.parse_horizon("H2FY27") == {"kind": "half", "fy": 2027, "h": 2}
    assert P.parse_horizon("FY26-FY28")["kind"] == "multi_year"
    assert P.parse_horizon("next 2-3 years")["kind"] == "multi_year"
    assert P.parse_horizon("unspecified")["kind"] == "vague"


def test_verdict_rules():
    assert verdict(16.0, 15, 17, True)[0] == "delivered"
    assert verdict(14.6, 15, 17, True)[0] == "delivered"   # within 0.5pp tolerance
    assert verdict(13.5, 15, 17, True)[0] == "partly"
    assert verdict(9.0, 15, 17, True)[0] == "missed"
    assert verdict(25.0, 15, 17, True)[1] == "beat the top of the range"


def _T():
    c = screener.parse_company((FIXTURES / "screener_company.html").read_text())
    return Tables(c)


def test_judge_against_reported_numbers():
    T = _T()
    call = {"fy": 2026, "q": 1, "period": "Jul 2025"}
    # FY26 revenue growth: 5380 vs 4550 = 18.2%
    g = {"metric": "revenue_growth", "target_low": 15, "target_high": 17, "unit": "%", "horizon": "FY26"}
    r = judge(g, call, T)
    assert r["verdict"] == "delivered" and r["actual"]["value"] == 18.2 and r["judged_by"] == "numbers"
    # Q2 FY27 margin: 175/1560 = 11.2% vs target 12-13%
    g2 = {"metric": "ebitda_margin", "target_low": 12, "target_high": 13, "unit": "%", "horizon": "Q2 FY27"}
    assert judge(g2, {"fy": 2027, "q": 1, "period": "Jul 2026"}, T)["verdict"] == "partly"
    # FY27 not finished -> in progress (H1 FY27 data available)
    g3 = {"metric": "revenue_growth", "target_low": 20, "target_high": None, "unit": "%", "horizon": "FY27"}
    r3 = judge(g3, {"fy": 2027, "q": 1, "period": "Jul 2026"}, T)
    assert r3["verdict"] == "in_progress"
    # a future quarter -> too early
    g4 = {"metric": "revenue_growth", "target_low": 20, "target_high": None, "unit": "%", "horizon": "Q4 FY27"}
    assert judge(g4, {"fy": 2027, "q": 2, "period": "Oct 2026"}, T)["verdict"] == "too_early"
    # USD-guided absolute revenue is not comparable
    g5 = {"metric": "revenue", "target_low": 500, "target_high": None, "unit": "USD million", "horizon": "FY26"}
    assert judge(g5, call, T)["verdict"] == "unverifiable"
