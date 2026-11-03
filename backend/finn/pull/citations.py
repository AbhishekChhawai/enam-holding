"""Post-hoc verification of model output against the pages it cites.

- A citation to a page the model was not shown is dropped.
- Every number in a claim must appear on a cited page (allowing rounding) or in the deterministic
  metrics; otherwise the claim is marked unverified in the UI.
- A 'quote' must actually occur on its page (fuzzy, whitespace/punctuation-insensitive).
"""
from __future__ import annotations

import re

def neutralise(text: str) -> str:
    """Document text can't open or close our excerpt tags."""
    return (text or "").replace("<excerpt", "‹excerpt").replace("</excerpt", "‹/excerpt")


def attr(value: str) -> str:
    """Safe inside a double-quoted attribute: no quotes or angle brackets from source metadata."""
    return (value or "").replace('"', "'").replace("<", "‹").replace(">", "›")


_NUM = re.compile(r"(?<![\w.])[-−]?\d[\d,]*(?:\.\d+)?")


def _norm_num(s: str) -> str | None:
    s = s.replace(",", "").replace("−", "-").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return f"{v:.4f}".rstrip("0").rstrip(".")


def numbers_in(text: str) -> list[str]:
    out = []
    for m in _NUM.findall(text or ""):
        n = _norm_num(m)
        if n is not None:
            out.append(n)
    return out


def _is_trivial(n: str) -> bool:
    try:
        v = float(n)
    except ValueError:
        return True
    if v.is_integer() and (abs(v) <= 12 or 1990 <= v <= 2100):
        return True  # small counts, quarter numbers, years
    return False


def _matches(claim_num: str, pool: set[float]) -> bool:
    v = float(claim_num)
    decimals = len(claim_num.split(".")[1]) if "." in claim_num else 0
    for p in pool:
        if round(p, decimals) == round(v, decimals) or abs(p - v) <= max(abs(v) * 0.005, 0.01):
            return True
    return False


def verify_numbers(claim: str, sources: list[str], extra: list[float] | None = None) -> list[str]:
    """Return numbers in `claim` that are not supported by any source text."""
    pool: set[float] = set(extra or [])
    for s in sources:
        for n in numbers_in(s):
            pool.add(float(n))
    missing = []
    for n in numbers_in(claim):
        if _is_trivial(n):
            continue
        if not _matches(n, pool):
            missing.append(n)
    return missing


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


def quote_on_page(quote: str, page_text: str, threshold: float = 0.8) -> bool:
    q = _words(quote)
    if not q:
        return False
    p = " ".join(_words(page_text))
    if " ".join(q) in p:
        return True
    n = 4 if len(q) >= 8 else 2
    grams = [" ".join(q[i:i + n]) for i in range(max(1, len(q) - n + 1))]
    hits = sum(1 for g in grams if g in p)
    return hits / len(grams) >= threshold


def check_citations(cites: list[dict], allowed: dict[tuple[str, int], str]) -> tuple[list[dict], list[str]]:
    """Keep citations that point at pages the model was given. Returns (kept, cited_texts)."""
    kept, texts = [], []
    for c in cites:
        key = (c.get("doc_id"), int(c.get("page") or 0))
        if key in allowed:
            kept.append({"doc_id": key[0], "page": key[1]})
            texts.append(allowed[key])
    return kept, texts
