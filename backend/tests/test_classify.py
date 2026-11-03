from finn.push.classify import rule_classify, score, tier

CASES = [
    ("Outcome of Board Meeting", "Unaudited Financial Results for the quarter ended September 30, 2026", "results"),
    ("Change in Directors/ Key Managerial Personnel", "Resignation of Mr. A as Chief Financial Officer", "management_change"),
    ("Credit Rating", "ICRA reaffirms long term rating AA+", "credit_rating"),
    ("Allotment of ESOP / ESPS", "Allotment of 12,000 equity shares under ESOP 2021", "unclassified"),
    ("Analysts/Institutional Investor Meet/Con. Call Updates", "Transcript of earnings conference call", "earnings_call"),
    ("Acquisition", "Acquisition of 51% stake in XYZ Pvt Ltd", "M&A"),
    ("Disclosure of creation of pledge", "Regulation 31(1) disclosure by promoter", "pledging"),
    ("Press Release / Media Release", "Company bags order worth Rs 1,250 crore from NHAI", "press_release"),
    ("Board Meeting Intimation", "Intimation of board meeting to consider financial results", "results"),
    ("Newspaper Publication", "Newspaper publication of financial results", "results"),
]


def test_rules_place_common_filings():
    for subcat, headline, expected in CASES:
        assert rule_classify(subcat, headline, None, subcat) == expected, (subcat, headline)


def test_scores_separate_signal_from_routine():
    s_results, _ = score("results", "Outcome of Board Meeting", "Unaudited Financial Results for the quarter")
    s_notice, why = score("results", "Board Meeting Intimation", "Intimation of board meeting to consider financial results")
    s_paper, _ = score("results", "Newspaper Publication", "Newspaper publication of financial results")
    s_cfo, _ = score("management_change", "Change in KMP", "Resignation of Chief Financial Officer")
    s_cs, _ = score("management_change", "Change in KMP", "Appointment of Company Secretary and Compliance Officer")
    s_order, _ = score("press_release", "Press Release", "Company bags order worth Rs 1,250 crore")
    assert tier(s_results) == "needs_you"
    assert tier(s_cfo) == "needs_you"
    assert tier(s_notice) == "routine" and any("date notice" in r for r in why)
    assert tier(s_paper) == "routine"
    assert tier(s_cs) == "routine"
    assert s_order > score("press_release", "Press Release", "Company launches new website")[0]
