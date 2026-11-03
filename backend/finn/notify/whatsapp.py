"""WhatsApp alerts: FINN messages you when something important happens.

Choose a provider with FINN_WHATSAPP_PROVIDER:
  callmebot - free, for personal alerts. Send "I allow callmebot to send me messages" to CallMeBot's WhatsApp number
              once, and it replies with your API key (FINN_CALLMEBOT_APIKEY).
  twilio    - Twilio WhatsApp (sandbox or approved sender): TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM.
The recipient (FINN_WHATSAPP_TO, e.g. +9198xxxxxxxx) lives only in the environment: never in the database or the browser.

Only fresh, high-priority events are sent (today's completed session, filings from the last 26 hours), at most
FINN_WHATSAPP_DAILY_CAP per day, each alert once. Re-running on a fresh database (e.g. a daily GitHub Action)
therefore never resends old news.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta

import requests
from sqlalchemy import select

from ..db import Alert, Announcement, session_scope, utcnow

log = logging.getLogger(__name__)


def _env(k: str) -> str:
    return (os.getenv(k) or "").strip()


def mask(number: str) -> str | None:
    d = "".join(c for c in number if c.isdigit())
    return f"+{d[:2]} ••••• {d[-4:]}" if len(d) >= 8 else None


def status() -> dict:
    prov, to = _env("FINN_WHATSAPP_PROVIDER").lower(), _env("FINN_WHATSAPP_TO")
    ok = bool(to) and ((prov == "callmebot" and _env("FINN_CALLMEBOT_APIKEY")) or
                       (prov == "twilio" and all(_env(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM"))))
    return {"configured": bool(ok), "provider": prov or None, "to": mask(to) if ok else None,
            "daily_cap": int(_env("FINN_WHATSAPP_DAILY_CAP") or 10), "sends": "high-priority alerts from the latest session and the last day's filings"}


def compose(a: dict) -> str:
    """Plain, factual message built from the alert's own fields (no model call)."""
    p = a.get("provenance") or {}
    lines = [f"*FINN: {a['symbol']}*", a["message"]]
    if a.get("kind") == "market":
        nb = p.get("nearby") or []
        lines.append(f"Why now: {nb[0]['category_label']} filed {nb[0]['published_at'][:10]} (context, not proof of cause)." if nb
                     else "Why now: no company filing around this session.")
        if a.get("session_date"):
            lines.append(f"End-of-day data for {a['session_date']}.")
    if p.get("url"):
        lines.append(f"Source: {p['url']}")
    lines.append("Informational only, not investment advice.")
    return "\n".join(lines)


def send(text: str) -> tuple[bool, str | None]:
    st = status()
    if not st["configured"]:
        return False, "WhatsApp isn't set up (see finn/notify/whatsapp.py)."
    to = _env("FINN_WHATSAPP_TO")
    try:
        if st["provider"] == "callmebot":
            r = requests.get("https://api.callmebot.com/whatsapp.php", timeout=20,
                             params={"phone": to.lstrip("+"), "text": text, "apikey": _env("FINN_CALLMEBOT_APIKEY")})
        else:
            sid = _env("TWILIO_ACCOUNT_SID")
            r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json", timeout=20,
                              auth=(sid, _env("TWILIO_AUTH_TOKEN")),
                              data={"From": f"whatsapp:{_env('TWILIO_WHATSAPP_FROM')}", "To": f"whatsapp:{to}", "Body": text})
        if r.status_code >= 300:
            return False, f"{st['provider']} returned HTTP {r.status_code}"
        return True, None
    except requests.RequestException as e:
        return False, type(e).__name__        # never echo URLs: they can carry the API key


def dispatch(now=None) -> dict:
    """Send fresh high-severity alerts that haven't been sent yet. Safe to call after every evaluation."""
    if not status()["configured"]:
        return {"sent": 0, "skipped": "not configured"}
    now = now or utcnow()
    from ..push import rules
    sent, failed, today = 0, 0, now.date().isoformat()
    cap = status()["daily_cap"]
    with session_scope() as s:
        already = sum(1 for a in s.scalars(select(Alert).where(Alert.created_at >= now - timedelta(days=1)))
                      if (a.provenance or {}).get("whatsapp_sent_on") == today)
        latest = max((a.session_date for a in s.scalars(select(Alert).where(Alert.kind == "market")) if a.session_date), default=None)
        for a in s.scalars(select(Alert).where(Alert.severity == "high").order_by(Alert.created_at)):
            prov = dict(a.provenance or {})
            if prov.get("whatsapp_sent_on") or already + sent >= cap:
                continue
            if a.kind == "market":
                fresh = a.session_date is not None and a.session_date == latest
            else:
                ann = s.get(Announcement, a.announcement_id) if a.announcement_id else None
                fresh = bool(ann and ann.published_at and ann.published_at >= now - timedelta(hours=26))
            if not fresh:
                continue
            ok, err = send(compose(rules.alert_dict(a)))
            if ok:
                prov["whatsapp_sent_on"] = today
                a.provenance = prov
                sent += 1
            else:
                failed += 1
                log.warning("WhatsApp send failed for alert %s: %s", a.id, err)
    return {"sent": sent, "failed": failed}
