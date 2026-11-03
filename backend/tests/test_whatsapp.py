from datetime import timedelta

from finn.db import Alert, Announcement, init_db, session_scope, utcnow
from finn.notify import whatsapp as W


def _env(monkeypatch):
    monkeypatch.setenv("FINN_WHATSAPP_PROVIDER", "callmebot")
    monkeypatch.setenv("FINN_WHATSAPP_TO", "+919876543210")
    monkeypatch.setenv("FINN_CALLMEBOT_APIKEY", "secret-key")


def test_status_masks_number_and_needs_all_settings(monkeypatch):
    monkeypatch.delenv("FINN_WHATSAPP_PROVIDER", raising=False)
    assert W.status()["configured"] is False
    _env(monkeypatch)
    st = W.status()
    assert st["configured"] and st["to"] == "+91 ••••• 3210" and "secret" not in str(st)


def test_compose_is_factual_and_flags_context_not_cause():
    msg = W.compose({"symbol": "DIXON", "kind": "market", "message": "DIXON fell 6.2% to ₹14,210.00, beyond your 5% rule.", "session_date": "2026-10-30",
                     "provenance": {"nearby": [{"category_label": "Results", "published_at": "2026-10-29T18:00:00"}], "url": None}})
    assert "*FINN: DIXON*" in msg and "context, not proof of cause" in msg and "not investment advice" in msg


def test_dispatch_sends_only_fresh_high_alerts_once(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setenv("FINN_WHATSAPP_DAILY_CAP", "1000")      # other tests leave their own fresh alerts in the shared DB
    sent = []
    monkeypatch.setattr(W, "send", lambda text: (sent.append(text) or (True, None)))
    init_db()
    now = utcnow()
    with session_scope() as s:
        s.merge(Announcement(id="wa-new", symbol="WAX", published_at=now - timedelta(hours=3), headline="Results", category="results", base_score=80))
        s.merge(Announcement(id="wa-old", symbol="WAX", published_at=now - timedelta(days=5), headline="Old results", category="results", base_score=80))
        for i, (ann, sev) in enumerate((("wa-new", "high"), ("wa-old", "high"), ("wa-new", "medium"))):
            s.add(Alert(rule_id=900 + i, dedupe_key=f"wa-test-{i}", symbol="WAX", kind="filing", announcement_id=ann, severity=sev,
                        title="WAX: Results", message="Unaudited results", provenance={"url": "https://example.com/r.pdf"}, created_at=now))
    W.dispatch(now=now)
    ours = [m for m in sent if "*FINN: WAX*" in m]
    W.dispatch(now=now)
    assert len(ours) == 1 and len([m for m in sent if "*FINN: WAX*" in m]) == 1   # fresh + high only, and never twice
    assert "https://example.com/r.pdf" in ours[0] and "Old results" not in ours[0]
