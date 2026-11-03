from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from finn.api import app
from finn.db import Alert, AlertRule, Announcement, Company, PriceBar, init_db, session_scope, utcnow
from finn.push import digest, rules


def bars(sym, closes, vols, start="2026-09-01"):
    d = datetime.strptime(start, "%Y-%m-%d")
    out, i = [], 0
    while len(out) < len(closes):
        if d.weekday() < 5:
            out.append(PriceBar(symbol=sym, date=d.strftime("%Y-%m-%d"), open=closes[i], high=closes[i] + 1, low=closes[i] - 1,
                                close=closes[i], volume=vols[i]))
            i += 1
        d += timedelta(days=1)
    return out


@pytest.fixture()
def market(monkeypatch):
    init_db()
    closes = [100.0] * 25 + [107.0, 104.0]      # +7% then -2.8%
    vols = [1000.0] * 25 + [2500.0, 1100.0]     # 2.5x then 1.1x
    with session_scope() as s:
        s.merge(Company(symbol="RLCO", name="Rule Co", in_portfolio=False))
        for b in bars("RLCO", closes, vols):
            s.merge(b)
        last = max(b.date for b in bars("RLCO", closes, vols))
    monkeypatch.setattr(rules, "_completed_session", lambda: last)
    return last


def mkrule(**kw):
    with session_scope() as s:
        r = AlertRule(**rules.validate(kw))
        s.add(r)
        s.flush()
        return r.id


def count(rule_id):
    with session_scope() as s:
        return s.scalar(select(func.count()).select_from(Alert).where(Alert.rule_id == rule_id))


def test_validation():
    with pytest.raises(ValueError):
        rules.validate({"kind": "price_move"})            # missing threshold
    with pytest.raises(ValueError):
        rules.validate({"kind": "filing", "categories": ["nope"]})
    assert rules.validate({"kind": "volume", "threshold": 2})["window"] == 20


def test_price_rule_triggers_once_and_respects_direction(market):
    up = mkrule(kind="price_move", symbol="RLCO", threshold=5, direction="up")
    down = mkrule(kind="price_move", symbol="RLCO", threshold=5, direction="down")
    loose = mkrule(kind="price_move", symbol="RLCO", threshold=2.5, direction="either")
    rules.evaluate([up, down, loose], sessions=5)
    assert count(up) == 1 and count(down) == 0 and count(loose) == 2
    rules.evaluate([up, down, loose], sessions=5)           # re-run: idempotent
    assert count(up) == 1 and count(loose) == 2
    with session_scope() as s:
        a = s.scalar(select(Alert).where(Alert.rule_id == up))
        assert a.observed == 7.0 and a.threshold == 5 and a.severity == "medium" and "rose 7.0%" in a.message


def test_volume_rule_ratio_and_insufficient_history(market):
    v = mkrule(kind="volume", symbol="RLCO", threshold=2, window=20)
    rules.evaluate([v], sessions=5)
    with session_scope() as s:
        a = s.scalar(select(Alert).where(Alert.rule_id == v))
        assert a.observed == 2.5 and a.provenance["average"] == 1000
    assert count(v) == 1
    short = mkrule(kind="volume", symbol="RLCO", threshold=1.01, window=20)
    rules.evaluate([short], sessions=40)                     # early sessions lack 5 prior days: skipped, not guessed
    with session_scope() as s:
        dates = sorted(s.scalars(select(Alert.session_date).where(Alert.rule_id == short)))
    assert dates and dates[0] > "2026-09-05"


def test_disabled_rule_and_unfinished_session(market, monkeypatch):
    off = mkrule(kind="price_move", symbol="RLCO", threshold=1, enabled=False)
    rules.evaluate(sessions=5)
    assert count(off) == 0
    on = mkrule(kind="price_move", symbol="RLCO", threshold=1)
    monkeypatch.setattr(rules, "_completed_session", lambda: "2026-09-01")  # pretend later bars are unfinished
    rules.evaluate([on], sessions=5)
    assert count(on) == 0


def test_management_change_alert_fires_once_and_ignores_routine():
    init_db()
    with session_scope() as s:
        s.merge(Company(symbol="MGCO", name="Mgmt Co", in_portfolio=False))
        s.merge(Announcement(id="mg-cfo", symbol="MGCO", published_at=utcnow() - timedelta(hours=2), headline="Resignation of Chief Financial Officer",
                             subject="Change in KMP", category="management_change", base_score=86, reasons=[]))
        s.merge(Announcement(id="mg-esop", symbol="MGCO", published_at=utcnow() - timedelta(hours=1), headline="ESOP allotment",
                             subject="Allotment", category="unclassified", base_score=5, reasons=[]))
    r = mkrule(kind="filing", symbol="MGCO", categories=["management_change"], min_tier="worth_a_look")
    rules.evaluate([r]); rules.evaluate([r])
    with session_scope() as s:
        got = list(s.scalars(select(Alert).where(Alert.rule_id == r)))
    assert [a.announcement_id for a in got] == ["mg-cfo"] and got[0].severity == "high"


def test_clustering_groups_results_day_only():
    t0 = datetime(2026, 10, 30, 10, 0)
    def it(i, cat, title, score, sym="CLCO", h=0):
        return {"id": i, "symbol": sym, "category": cat, "title": title, "subject": "", "score": score, "tier": "needs_you" if score >= 70 else "routine",
                "published_at": (t0 + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ"), "category_label": cat, "attachment_url": None, "summary": None}
    items = [it("res", "results", "Unaudited financial results Q2", 80), it("ppt", "results", "Investor presentation Q2", 55, h=1),
             it("call", "earnings_call", "Schedule of earnings call", 25, h=2), it("div", "dividend", "Interim dividend declared", 35, h=1),
             it("order", "press_release", "Bags order worth Rs 500 crore", 58, h=3), it("other", "results", "Results Q2", 80, sym="ZZCO")]
    left = digest.cluster(items)
    res = next(x for x in left if x["id"] == "res")
    assert {r["id"] for r in res["related"]} == {"ppt", "call", "div"}
    assert {x["id"] for x in left} == {"res", "order", "other"}


def test_alert_api_and_prefs_sync(market):
    with TestClient(app) as c:
        rr = c.post("/api/alerts/rules", json={"kind": "price_move", "symbol": "RLCO", "threshold": 6, "direction": "up"}).json()
        assert rr["evaluation"]["rules_checked"] == 1 and rr["description"].startswith("When RLCO rises 6%")
        assert c.post("/api/alerts/rules", json={"kind": "price_move", "symbol": "NOSUCH", "threshold": 6}).status_code == 404
        assert c.post("/api/alerts/rules", json={"kind": "volume"}).status_code == 422
        lst = c.get("/api/alerts?symbol=RLCO").json()
        mine = [a for a in lst["items"] if a["rule_id"] == rr["id"]]
        assert len(mine) == 1 and not mine[0]["read"]
        assert c.patch(f"/api/alerts/{mine[0]['id']}", json={"read": True}).json()["read"]
        assert c.patch(f"/api/alerts/rules/{rr['id']}", json={"enabled": False}).json()["enabled"] is False
        assert c.delete(f"/api/alerts/rules/{rr['id']}").json()["deleted"] == rr["id"]
        c.put("/api/prefs", json={"volume_multiple": 3.5})
        vol_rule = next(r for r in c.get("/api/alerts/rules").json()["items"] if r["kind"] == "volume" and r["scope"] == "portfolio")
        assert vol_rule["threshold"] == 3.5 and c.get("/api/prefs").json()["volume_multiple"] == 3.5
        assert c.post("/api/alerts/read-all").json()["marked_read"] >= 0


def test_why_now_attaches_nearby_filings_without_cause():
    init_db()
    with session_scope() as s:
        s.merge(Company(symbol="WNCO", name="Why Now Co", in_portfolio=True))
        for b in bars("WNCO", [100.0] * 25 + [115.0], [1000.0] * 25 + [6000.0], start="2026-09-01"):
            s.merge(b)
        last = max(b.date for b in bars("WNCO", [100.0] * 26, [1.0] * 26, start="2026-09-01"))
        s.merge(Announcement(id="wn-res", symbol="WNCO", published_at=datetime.strptime(last, "%Y-%m-%d") - timedelta(hours=20),
                             headline="Unaudited results", subject="Outcome", category="results", base_score=80, reasons=[]))
    with session_scope() as s:
        from finn.prefs import get_prefs
        moves = [m for m in digest.build(s, 24 * 90, get_prefs(s))["moves"] if m["symbol"] == "WNCO"]
    assert moves and moves[0]["nearby"][0]["id"] == "wn-res" and "does not infer cause" in moves[0]["context_note"]


def test_results_day_alerts_once_not_per_companion_filing():
    init_db()
    t = utcnow() - timedelta(hours=5)
    with session_scope() as s:
        s.merge(Company(symbol="BDCO", name="Bundle Co", in_portfolio=False))
        s.merge(Announcement(id="bd-res", symbol="BDCO", published_at=t, headline="Unaudited financial results Q2", subject="Outcome", category="results", base_score=80, reasons=[]))
        s.merge(Announcement(id="bd-ppt", symbol="BDCO", published_at=t + timedelta(hours=1), headline="Investor presentation Q2 results", subject="Presentation", category="results", base_score=55, reasons=[]))
    r = mkrule(kind="filing", symbol="BDCO", categories=["results"], min_tier="worth_a_look")
    rules.evaluate([r])
    with session_scope() as s:
        assert list(s.scalars(select(Alert.announcement_id).where(Alert.rule_id == r))) == ["bd-res"]


def test_market_alert_carries_why_now_and_says_so_when_nothing_is_nearby(market):
    with session_scope() as s:
        last = max(s.scalars(select(PriceBar.date).where(PriceBar.symbol == "RLCO")))
        s.merge(Announcement(id="rl-res", symbol="RLCO", published_at=datetime.strptime(last, "%Y-%m-%d") - timedelta(days=4),
                             headline="Unaudited results", subject="Outcome", category="results", base_score=80, reasons=[]))
    r = mkrule(kind="price_move", symbol="RLCO", threshold=2.5)
    rules.evaluate([r], sessions=5)
    with session_scope() as s:
        by_date = {a.session_date: a.provenance for a in s.scalars(select(Alert).where(Alert.rule_id == r))}
    jump, drop = sorted(by_date)                       # +7% session, then the -2.8% session
    assert [n["id"] for n in by_date[jump]["nearby"]] == ["rl-res"] and "not as the cause" in by_date[jump]["context"]
    assert by_date[drop]["nearby"] == [] or by_date[drop]["nearby"][0]["id"] == "rl-res"
    assert all("context" in p for p in by_date.values())


def test_research_context_handoff_and_alert_api_extras(market):
    t = utcnow() - timedelta(hours=3)
    with session_scope() as s:
        s.merge(Announcement(id="rc-res", symbol="RLCO", published_at=t, headline="Unaudited financial results Q2", subject="Outcome",
                             category="results", base_score=80, reasons=[], attachment_url="https://www.bseindia.com/xml-data/corpfiling/AttachLive/a.pdf",
                             enrichment={"type": "results", "periods": ["Q2 FY27"], "rows": []}, enrichment_status="ok"))
        s.merge(Announcement(id="rc-ppt", symbol="RLCO", published_at=t + timedelta(hours=1), headline="Investor presentation Q2 results",
                             subject="Presentation", category="results", base_score=55, reasons=[], attachment_url="https://www.bseindia.com/xml-data/corpfiling/AttachLive/b.pdf"))
    with TestClient(app) as c:
        ctx = c.get("/api/announcements/rc-res/research-context").json()
        assert ctx["symbol"] == "RLCO" and ctx["event_id"] == "rc-res" and ctx["related_filing_ids"] == ["rc-ppt"]
        assert len(ctx["document_ids"]) == 2 and ctx["reporting_period"] == "Q2 FY27" and ctx["target_tab"] == "promises"
        assert "Q2 FY27" in ctx["suggested_question"]
        from_member = c.get("/api/announcements/rc-ppt/research-context").json()
        assert "rc-res" in from_member["related_filing_ids"]     # opening a companion still finds its bundle
        assert c.get("/api/announcements/nope/research-context").status_code == 404
        r = mkrule(kind="volume", symbol="RLCO", threshold=2)
        rules.evaluate([r], sessions=5)
        vol = c.get("/api/alerts?kind=volume&symbol=RLCO").json()["items"]
        assert vol and all(a["rule_kind"] == "volume" for a in vol)
        assert all(a["rule_kind"] == "price_move" for a in c.get("/api/alerts?kind=price").json()["items"])
        assert c.get("/api/alerts/unread-count").json()["unread_count"] >= 1
        assert c.patch(f"/api/alerts/{vol[0]['id']}", json={"read": False}).json()["read"] is False
        assert c.post("/api/alerts/mark-all-read").json()["marked_read"] >= 1
        assert c.get("/api/alerts?unread=true").json()["total"] == 0
        runs = c.get("/api/alerts/runs").json()["items"]
        assert runs and {"at", "rules_checked", "created", "failures"} <= set(runs[0])
