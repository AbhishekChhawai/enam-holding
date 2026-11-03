"""The real-data snapshot must never package fixtures as real, and must carry what the phone app needs."""
import json

import pytest

from finn.db import Company, PriceBar, init_db, session_scope


def test_real_export_refuses_fixture_rows(tmp_path):
    import sys
    sys.path.insert(0, "scripts")
    import export_snapshot as E
    init_db()
    with session_scope() as s:
        s.merge(Company(symbol="FIXCO", name="Fixture Co", in_portfolio=True))
        s.merge(PriceBar(symbol="FIXCO", date="2026-10-01", close=10, volume=1, source="synthetic-fixture"))
    with pytest.raises(SystemExit) as e:
        E.export(out=tmp_path / "s.json")
    assert "did not come from FINN's real ingestion" in str(e.value)


def test_export_structure_for_the_phone_app(tmp_path):
    import sys
    sys.path.insert(0, "scripts")
    import export_snapshot as E
    r = E.export(out=tmp_path / "s.json", allow_synthetic=True, fetch_missing=False)   # structure check only, offline
    snap = json.loads((tmp_path / "s.json").read_text())
    assert {"meta", "get", "docs", "anns", "bars", "companies"} <= set(snap)
    assert snap["meta"]["kind"] == "real" and "/api/digest?hours=24" in snap["get"] and "/api/alerts/rules" in snap["get"]
    assert r["companies"] >= 1
