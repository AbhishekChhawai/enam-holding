from datetime import timedelta
from fastapi.testclient import TestClient

from finn.api import app
from finn.db import Announcement, Company, PriceBar, init_db, session_scope, utcnow


def seed():
    init_db()
    with session_scope() as s:
        s.merge(Company(symbol="DIXON", name="Dixon Technologies", sector="EMS", bse_code="540699", in_portfolio=True))
        for i in range(30):
            s.merge(PriceBar(symbol="DIXON", date=f"2026-10-{i+1:02d}", close=100 + (8 if i == 29 else 0), volume=1000 * (3 if i == 29 else 1)))
        s.merge(Announcement(id="a1", symbol="DIXON", published_at=utcnow() - timedelta(hours=3), headline="Unaudited financial results for Q2",
                             subject="Outcome of Board Meeting", category="results", base_score=80, reasons=["x"]))
        s.merge(Announcement(id="a2", symbol="DIXON", published_at=utcnow() - timedelta(hours=5), headline="Loss of share certificate",
                             subject="Reg 39(3)", category="unclassified", base_score=5, reasons=["x"]))


def test_digest_and_feedback():
    with TestClient(app) as c:
        seed()
        d = c.get("/api/digest?hours=24").json()
        assert d["counts"]["needs_you"] == 1 and d["counts"]["routine"] == 1
        assert d["moves"] and d["moves"][0]["flags"] == ["price", "volume"]
        assert d["triggered"][0]["id"] == "a1"
        r = c.post("/api/feedback", json={"announcement_id": "a1", "signal": "less"}).json()
        assert r["weight"] == -10
        d2 = c.get("/api/digest?hours=24").json()
        assert d2["tiers"]["needs_you"][0]["score"] == 70
        p = c.put("/api/prefs", json={"price_move_pct": 10}).json()
        assert p["price_move_pct"] == 10
        assert c.get("/api/digest?hours=24").json()["moves"][0]["flags"] == ["volume"]
        assert c.get("/api/research/DIXON/promises").json()["status"] == "llm_disabled"


def test_manual_refresh_and_cron(monkeypatch):
    import time
    import finn.api as api_mod
    calls = []
    monkeypatch.setattr(api_mod.push_refresh, "refresh_prices", lambda period="3mo": calls.append("prices") or 0)
    monkeypatch.setattr(api_mod.push_refresh, "refresh_announcements", lambda days=2, symbols=None: calls.append("filings") or 3)
    monkeypatch.setattr(api_mod.push_refresh, "enrich_pending", lambda limit=10, since_days=3: 0)
    with TestClient(app) as c:
        r = c.post("/api/refresh").json()
        assert r["status"] in ("running", "done") and r["trigger"] == "manual"
        for _ in range(50):
            if c.get("/api/refresh").json()["status"] != "running":
                break
            time.sleep(0.05)
        done = c.get("/api/refresh").json()
        assert done["status"] == "done" and done["new_filings"] == 3 and "filings" in calls
        again = c.post("/api/refresh").json()
        assert "try again" in again["note"]  # rate-limited
        assert c.get("/api/cron").status_code == 503                      # disabled until a secret is configured
        import finn.api as A
        A.CRON_SECRET = "s3cret"
        try:
            assert c.get("/api/cron").status_code == 403
            assert c.get("/api/cron", headers={"X-Cron-Secret": "wrong"}).status_code == 403
            assert c.get("/api/cron", headers={"X-Cron-Secret": "s3cret"}).json()["ok"]
            assert c.post("/api/announcements/a1/enrich").status_code == 403    # admin-only now
        finally:
            A.CRON_SECRET = ""


def test_model_budget_caps_visitors(monkeypatch):
    import finn.api as A
    monkeypatch.setattr(A.llm, "available", lambda: True)
    monkeypatch.setattr(A, "ASK_PER_IP_HOUR", 2)
    monkeypatch.setattr(A.agent, "ask", lambda sym, q, *a: {"status": "ok", "summary": "stub"})
    A._hits.clear()
    with TestClient(app) as c:
        h = {"X-Forwarded-For": "203.0.113.9"}
        codes = [c.post("/api/research/DIXON/ask", json={"question": "q"}, headers=h).status_code for _ in range(3)]
        assert codes == [200, 200, 429]
        assert c.post("/api/research/DIXON/ask", json={"question": "q"}, headers={"X-Forwarded-For": "198.51.100.4"}).status_code == 200


def test_ssrf_guard_refuses_internal_targets():
    import pytest
    from finn.sources.http import FetchError, get
    for url in ("http://127.0.0.1:8000/api/health", "http://169.254.169.254/latest/meta-data/", "file:///etc/passwd"):
        with pytest.raises(FetchError):
            get(url, retries=1)
