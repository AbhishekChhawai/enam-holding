"""Shared access layer used by both Push and Pull, so ingestion logic exists in one place.

- Screener snapshots are cached in KV with a TTL and served stale if a refresh fails.
- Documents (filings, transcripts, annual reports) are registered once, downloaded once,
  and stored page-by-page so any citation can be opened at the exact page.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select

from .db import Document, DocPage, kv_get_row, kv_set, session_scope, utcnow
from .sources import screener
from .sources.bse_filings import attachment_candidates
from .sources.http import FetchError, download
from .sources.pdf import extract_pages, is_scanned

log = logging.getLogger("finn.store")


# ------------------------------------------------------------------ screener
def get_screener(symbol: str, max_age_hours: float = 12) -> dict:
    symbol = symbol.upper()
    key = f"screener:{symbol}"
    with session_scope() as s:
        row = kv_get_row(s, key)
        cached = row.value if row else None
        fresh = row is not None and row.updated_at > utcnow() - timedelta(hours=max_age_hours)
    if cached and fresh:
        return cached
    try:
        data = screener.fetch_company(symbol)
    except FetchError:
        if cached:
            cached["stale"] = True
            return cached
        raise
    with session_scope() as s:
        kv_set(s, key, data)
    return data


# ------------------------------------------------------------------ documents
def doc_id_for(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def register_doc(symbol: str, kind: str, url: str, title: str = "", period: str = "") -> str:
    did = doc_id_for(url)
    with session_scope() as s:
        doc = s.get(Document, did)
        if doc is None:
            s.add(Document(id=did, symbol=symbol.upper(), kind=kind, url=url, title=title, period=period))
        else:
            doc.title = title or doc.title
            doc.period = period or doc.period
    return did


def load_pages(doc_id: str, *, retry_failed_after_min: int = 60) -> tuple[dict, list[str]]:
    """Ensure a document is downloaded and split into pages. Returns (doc_meta, pages)."""
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        if doc is None:
            raise KeyError(doc_id)
        meta = _meta(doc)
        if doc.status in ("ok", "scanned"):
            pages = [p.text for p in s.scalars(select(DocPage).where(DocPage.doc_id == doc_id).order_by(DocPage.page))]
            return meta, pages
        if doc.status == "failed" and doc.retrieved_at and doc.retrieved_at > utcnow() - timedelta(minutes=retry_failed_after_min):
            return meta, []
        url, kind = doc.url, doc.kind

    path, err = None, None
    candidates = attachment_candidates(url)  # BSE viewer links and moved filings fall back to direct paths
    for cand in candidates:
        try:
            path = download(cand)
            break
        except FetchError as e:
            err = str(e)
    pages: list[str] = []
    status = "failed"
    if path is not None:
        try:
            pages = extract_pages(path)
            status = "scanned" if is_scanned(pages) else "ok"
        except Exception as e:  # noqa: BLE001
            err = f"PDF parse failed: {e}"
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        doc.status, doc.pages, doc.error, doc.retrieved_at = status, len(pages), (None if path else err), utcnow()
        s.execute(delete(DocPage).where(DocPage.doc_id == doc_id))
        for i, text in enumerate(pages, start=1):
            s.add(DocPage(doc_id=doc_id, page=i, text=text))
        meta = _meta(doc)
    if status == "failed":
        log.warning("Document %s failed: %s", url, err)
    return meta, pages


def file_path_for(doc_id: str):
    from .sources.http import cached_path
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        urls = attachment_candidates(doc.url)
    for u in urls:
        p = cached_path(u)
        if p.exists():
            return p
    return None


def get_page(doc_id: str, page: int) -> tuple[dict, str | None]:
    with session_scope() as s:
        doc = s.get(Document, doc_id)
        if doc is None:
            raise KeyError(doc_id)
        row = s.get(DocPage, (doc_id, page))
        return _meta(doc), (row.text if row else None)


def _meta(doc: Document) -> dict:
    return {"id": doc.id, "symbol": doc.symbol, "kind": doc.kind, "title": doc.title, "period": doc.period,
            "url": doc.url, "status": doc.status, "pages": doc.pages, "error": doc.error}


def list_docs(symbol: str, kind: str | None = None) -> list[dict]:
    with session_scope() as s:
        q = select(Document).where(Document.symbol == symbol.upper())
        if kind:
            q = q.where(Document.kind == kind)
        return [_meta(d) for d in s.scalars(q)]


def stamp_age_minutes(key: str) -> float | None:
    with session_scope() as s:
        row = kv_get_row(s, key)
        if not row:
            return None
        return (utcnow() - row.updated_at).total_seconds() / 60


def stamp(key: str, value: str | None = None) -> None:
    with session_scope() as s:
        kv_set(s, key, value or datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"))
