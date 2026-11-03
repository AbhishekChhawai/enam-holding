import json
from conftest import FIXTURES
from finn.sources.bse_filings import normalize, attachment_candidates


def test_normalize_real_bse_row():
    row = json.loads((FIXTURES / "bse_announcements.json").read_text())["Table"][0]
    n = normalize(row, "PANELEC")
    assert n["id"] == "6fb57b5e-a05f-4e05-b2da-6e2b5bfe32ae"
    assert n["subject"].startswith("Compliances-Reg. 39")
    assert n["attachment_url"].endswith("aab502e1-3e05-4fdc-bc10-ecbb436cab8d.pdf")
    # 23:44 IST -> 18:14 UTC
    assert n["published_at"].strftime("%Y-%m-%d %H:%M") == "2023-10-20 18:14"
    assert len(attachment_candidates(n["attachment_url"])) == 2
