"""Investor preferences: thresholds, which filing types trigger alerts, and learned weights."""
from __future__ import annotations

import copy

from sqlalchemy.orm import Session

from .config import DEFAULT_PREFS
from .db import kv_get, kv_set
from .push.classify import CATEGORIES


def get_prefs(s: Session) -> dict:
    stored = kv_get(s, "prefs", {}) or {}
    merged = copy.deepcopy(DEFAULT_PREFS)
    merged.update({k: v for k, v in stored.items() if k in DEFAULT_PREFS})
    return merged


def update_prefs(s: Session, patch: dict) -> dict:
    p = get_prefs(s)
    if "price_move_pct" in patch:
        p["price_move_pct"] = max(0.5, min(30.0, float(patch["price_move_pct"])))
    if "volume_multiple" in patch:
        p["volume_multiple"] = max(1.1, min(20.0, float(patch["volume_multiple"])))
    if "default_window_hours" in patch:
        p["default_window_hours"] = int(patch["default_window_hours"])
    if "alert_categories" in patch:
        p["alert_categories"] = [c for c in patch["alert_categories"] if c in CATEGORIES]
    if "muted_symbols" in patch:
        p["muted_symbols"] = [str(x).upper() for x in patch["muted_symbols"]]
    if "category_weights" in patch:
        p["category_weights"] = {k: int(v) for k, v in patch["category_weights"].items() if k in CATEGORIES}
    kv_set(s, "prefs", p)
    return p


def apply_feedback(s: Session, category: str, signal: str) -> dict:
    """'more'/'less' like this nudges the category's score by 10 points (bounded to +/-40)."""
    p = get_prefs(s)
    w = dict(p.get("category_weights") or {})
    step = 10 if signal == "more" else -10
    w[category] = max(-40, min(40, int(w.get(category, 0)) + step))
    p["category_weights"] = w
    kv_set(s, "prefs", p)
    return p
