"""Page-level BM25 retrieval. Chosen over embeddings on purpose: zero cost, no index service,
deterministic, and financial questions are keyword-heavy ("capex", "margin guidance", "order book")."""
from __future__ import annotations

import re
from rank_bm25 import BM25Okapi

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
_STOP = set("the a an and or of to in on for with by is are was were be been at as it this that from we our you they".split())

SYNONYMS = {
    "revenue": ["sales", "topline", "turnover"], "margin": ["ebitda", "profitability", "opm"],
    "guidance": ["guide", "expect", "target", "outlook", "aspire", "aim"], "capex": ["capital", "expenditure", "plant", "capacity"],
    "debt": ["borrowings", "leverage", "loan"], "growth": ["grow", "increase", "cagr"],
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in _STOP]


def expand(query: str) -> list[str]:
    toks = tokenize(query)
    extra = [s for t in toks for s in SYNONYMS.get(t, [])]
    return toks + extra


_cache: dict[tuple, tuple[BM25Okapi, list]] = {}


def build(corpus: list[tuple[str, int, str]]) -> tuple[BM25Okapi, list]:
    """corpus = [(doc_id, page, text)]. Cached per exact corpus identity."""
    key = tuple((d, p, len(t)) for d, p, t in corpus)
    if key in _cache:
        return _cache[key]
    tokens = [tokenize(t) or ["_empty_"] for _, _, t in corpus]
    idx = BM25Okapi(tokens)
    if len(_cache) > 32:
        _cache.clear()
    _cache[key] = (idx, corpus)
    return idx, corpus


def search(corpus: list[tuple[str, int, str]], query: str, k: int = 8, min_chars: int = 200) -> list[dict]:
    if not corpus:
        return []
    idx, docs = build(corpus)
    q = expand(query)
    scores = idx.get_scores(q)
    if not any(s > 0 for s in scores):
        # BM25's IDF collapses to zero on tiny corpora (e.g. one short transcript); fall back to term overlap
        qs = set(q)
        scores = [float(len(qs & set(tokenize(t)))) for _, _, t in docs]
    ranked = sorted(range(len(docs)), key=lambda i: scores[i], reverse=True)
    out = []
    for i in ranked:
        d, p, t = docs[i]
        if len(t) < min_chars or scores[i] <= 0:
            continue
        out.append({"doc_id": d, "page": p, "text": t, "score": float(scores[i])})
        if len(out) >= k:
            break
    return out
