import pytest
from finn import registry
from finn.db import Company, PriceBar, session_scope
from sqlalchemy import func, select


def test_normalize_rules():
    assert registry.normalize("reliance.ns") == {"kind": "symbol", "value": "RELIANCE", "exchange": "NSE"}
    assert registry.normalize("NSE:TCS")["value"] == "TCS"
    assert registry.normalize("RELIANCE.BO")["exchange"] == "BSE"
    assert registry.normalize("500325") == {"kind": "bse_code", "value": "500325", "exchange": "BSE"}
    assert registry.normalize("M&M")["value"] == "M&M"
    with pytest.raises(registry.ResolveError):
        registry.normalize("DROP TABLE;")


BARS = [{"date": f"2026-10-{d:02d}", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1000, "source": "yfinance:NSE"} for d in range(1, 29)]


def test_unseen_ticker_resolves_and_ingests_idempotently(monkeypatch):
    monkeypatch.setattr(registry, "_bse_lookup", lambda t: ({"symbol": "NEWCO", "company_name": "New Co Ltd", "isin": "INE000X01010", "bse_code": "543999"}, None))
    monkeypatch.setattr(registry.px, "fetch_eod", lambda syms, period="1y": {s: BARS for s in syms})
    import finn.push.refresh as refresh
    calls = []
    monkeypatch.setattr(refresh, "refresh_announcements", lambda days=2, symbols=None: calls.append(symbols) or 0)
    out = registry.resolve("newco.ns", background=False)
    assert out["created"] and out["symbol"] == "NEWCO" and out["bse_code"] == "543999" and not out["in_portfolio"]
    assert out["job"]["status"] == "done" and out["job"]["steps"]["prices"]["records"] == len(BARS)
    assert calls == [["NEWCO"]]
    registry.ingest("NEWCO")  # re-run: upserts, no duplicates
    with session_scope() as s:
        assert s.scalar(select(func.count()).select_from(PriceBar).where(PriceBar.symbol == "NEWCO")) == len(BARS)
        assert s.get(Company, "NEWCO").identity_sources == ["bse_lookup"]
    again = registry.resolve("NEWCO", background=False)
    assert not again["created"] and not again["ingestion_started"]  # cooldown respected


def test_ambiguous_bse_match_is_not_guessed(monkeypatch):
    monkeypatch.setattr(registry, "_bse_lookup", lambda t: ({"symbol": "OTHERCO", "company_name": "Other Co", "isin": "X", "bse_code": "500001"}, None))
    monkeypatch.setattr(registry.px, "fetch_eod", lambda syms, period="1y": {})
    with pytest.raises(registry.ResolveError) as e:
        registry.resolve("OTHER", background=False)
    assert "Did you mean OTHERCO" in str(e.value)
    # if Yahoo confirms the NSE symbol, accept it but do NOT attach the mismatched BSE code
    monkeypatch.setattr(registry.px, "fetch_eod", lambda syms, period="1y": {s: BARS for s in syms})
    monkeypatch.setattr(registry.screener, "search", lambda q: [])
    out = registry.resolve("OTHER", background=False)
    assert out["bse_code"] is None and out["job"]["steps"]["filings"]["status"] == "unavailable"
    assert any("different symbol" in w for w in out["warnings"])
