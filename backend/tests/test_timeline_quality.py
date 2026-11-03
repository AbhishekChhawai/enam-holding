from datetime import date, datetime, timedelta
from fastapi.testclient import TestClient

from conftest import FIXTURES
from finn import quality, timeline
from finn.api import app
from finn.db import Announcement, Company, PriceBar, init_db, kv_set, session_scope
from finn.sources import screener


def seed(sym="TLCO", mismatch=False, bad_ohlc=False):
    init_db()
    with session_scope() as s:
        s.merge(Company(symbol=sym, name="Timeline Co", bse_code="599999", in_portfolio=True))
        d0 = date(2026, 8, 3)
        days = [d0 + timedelta(days=i) for i in range(60) if (d0 + timedelta(days=i)).weekday() < 5]
        for i, d in enumerate(days):
            jump = d == date(2026, 9, 2)
            close = 100 * (1.08 if jump else 1.0) + i * 0.01
            s.merge(PriceBar(symbol=sym, date=d.isoformat(), open=close, high=close + 1, low=(close + 5 if bad_ohlc and i == 3 else close - 1),
                             close=close, volume=1000 * (3 if jump else 1)))
        enr = {"type": "results", "rows": [{"key": "revenue", "label": "Revenue", "current": 1560, "yoy_pct": 20.0},
                                           {"key": "ebitda", "label": "EBITDA", "current": 175, "yoy_pct": 25.0},
                                           {"key": "pbt", "label": "PBT", "current": 160, "yoy_pct": 28.0},
                                           {"key": "pat", "label": "PAT", "current": 120, "yoy_pct": 27.7}],
               "check": {"status": "mismatch" if mismatch else "match", "note": "screener.in shows revenue 1500 / PAT 118" if mismatch else "Revenue and PAT match screener.in"}}
        s.merge(Announcement(id=f"{sym}-res", symbol=sym, published_at=datetime(2026, 9, 1, 11, 0), headline="Unaudited financial results Q1 FY27",
                             subject="Outcome of Board Meeting", category="results", base_score=80, reasons=[], enrichment=enr, enrichment_status="ok",
                             attachment_url="https://www.bseindia.com/xml-data/corpfiling/AttachLive/x.pdf"))
        s.merge(Announcement(id=f"{sym}-esop", symbol=sym, published_at=datetime(2026, 9, 5, 11, 0), headline="ESOP allotment",
                             subject="Allotment", category="unclassified", base_score=5, reasons=[]))
        c = screener.parse_company((FIXTURES / "screener_company.html").read_text())
        c.update(symbol=sym, basis="consolidated", retrieved_at="2026-10-31T00:00:00Z")
        kv_set(s, f"screener:{sym}", c)
        kv_set(s, f"stamp:announcements:{sym}", "2026-10-31T00:00:00Z")


def test_timeline_merges_types_and_links_same_window():
    seed()
    t = timeline.build("TLCO", start=date(2026, 1, 1), end=date(2026, 12, 31))
    types = set(t["counts_by_type"])
    assert {"results", "market", "financials", "concall"} <= types
    assert not any(e["category"] == "Paperwork" for e in t["events"])  # routine paperwork excluded
    res = next(e for e in t["events"] if e["type"] == "results")
    assert "mkt:2026-09-02" in res["related"] and res["metrics"]["Revenue"]["value"] == 1560
    mkt = next(e for e in t["events"] if e["id"] == "mkt:2026-09-02")
    assert mkt["provenance"] == "derived" and res["provenance"] == "direct"
    only_market = timeline.build("TLCO", start=date(2026, 1, 1), end=date(2026, 12, 31), types={"market"})
    assert set(only_market["counts_by_type"]) == {"market"}


def test_freshness_respects_weekends():
    sunday_noon_utc = datetime(2026, 11, 1, 6, 30)
    assert quality.expected_session(sunday_noon_utc) == date(2026, 10, 30)
    assert quality.price_freshness("2026-10-30", sunday_noon_utc)[0] == "fresh"
    assert quality.price_freshness("2026-10-29", sunday_noon_utc)[0] == "possibly_stale"
    assert quality.price_freshness("2026-10-20", sunday_noon_utc)[0] == "stale"
    assert quality.price_freshness(None, sunday_noon_utc)[0] == "missing"


def test_quality_flags_verified_conflicting_and_bad_data():
    seed("QOK")
    q = quality.company_quality("QOK")
    assert any(c["status"] == "pass" and "verified" in c["detail"] for c in q["checks"])
    assert q["conflicts"] == []
    seed("QBAD", mismatch=True, bad_ohlc=True)  # simulated conflict + broken bar, test-only
    q2 = quality.company_quality("QBAD")
    assert q2["conflicts"] and "unresolved" in q2["conflicts"][0]["resolution"]
    assert next(c for c in q2["checks"] if c["name"] == "OHLC consistency")["status"] == "fail"
    assert set(q2["legend"]) >= {"verified", "direct", "derived", "conflicting"}


def test_part1_endpoints():
    seed("APICO")
    with TestClient(app) as c:
        assert c.get("/health").json()["ok"]
        assert any(x["symbol"] == "APICO" for x in c.get("/api/companies").json()["items"])
        p = c.get("/api/companies/APICO/prices?period=1m&end=2026-09-30").json()
        assert p["count"] > 15 and p["adjusted"] and p["bars"] == sorted(p["bars"], key=lambda b: b["date"])
        assert c.get("/api/companies/APICO/prices?period=7y").status_code == 422
        assert c.get("/api/companies/APICO/prices?start=2026-10-01&end=2026-09-01").status_code == 422
        a = c.get("/api/companies/APICO/announcements?category=results").json()
        assert a["total"] == 1 and a["items"][0]["exchange"] == "BSE"
        assert [c.get(f"/api/companies/APICO/announcements?limit=1&offset={o}").json()["items"][0]["category"] for o in (0, 1)] == ["unclassified", "results"]
        assert c.get("/api/companies/APICO/timeline?start=2026-01-01&end=2026-12-31").json()["count"] > 3
        assert c.get("/api/companies/APICO/data-quality").json()["sources"][0]["key"] == "prices"
        assert c.get("/api/companies/NOPE/prices").status_code == 404
        assert c.get("/api/system/source-health").json()["companies"] >= 1
