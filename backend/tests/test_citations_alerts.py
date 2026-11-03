from finn.pull.citations import verify_numbers, quote_on_page, check_citations
from finn.push.alerts import day_stats, flags_for


def test_numbers_must_appear_in_sources():
    src = ["Revenue grew 18.2% to Rs 1,560 crore while EBITDA margin was 11.2%."]
    assert verify_numbers("Revenue rose 18.2% to ₹1,560 cr", src) == []
    assert verify_numbers("Margin expanded to 14.5%", src) == ["14.5"]
    assert verify_numbers("In FY2026 and Q3 the company...", src) == []  # years/small ints ignored
    assert verify_numbers("Revenue ~18%", src) == []  # rounding allowed


def test_quotes_fuzzy_match():
    page = "We expect   EBITDA margins of 12 to 13% \n for FY27, driven by mobile volumes."
    assert quote_on_page("We expect EBITDA margins of 12 to 13% for FY27", page)
    assert not quote_on_page("We expect revenue to double next year", page)


def test_citations_restricted_to_shown_pages():
    allowed = {("d1", 3): "text"}
    kept, texts = check_citations([{"doc_id": "d1", "page": 3}, {"doc_id": "d1", "page": 9}], allowed)
    assert kept == [{"doc_id": "d1", "page": 3}] and texts == ["text"]


class Bar:
    def __init__(self, d, c, v):
        self.date, self.close, self.volume = d, c, v


def test_move_flags():
    bars = [Bar(f"2026-10-{i:02d}", 100, 1000) for i in range(1, 22)] + [Bar("2026-10-22", 106.5, 3100)]
    st = day_stats(bars, len(bars) - 1)
    assert st["pct"] == 6.5 and st["volume_multiple"] == 3.1
    assert flags_for(st, 5.0, 2.0) == ["price", "volume"]
    assert flags_for(st, 7.0, 4.0) == []
