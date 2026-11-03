"""PDF text extraction that preserves page numbers (needed for citations)."""
from __future__ import annotations

import re
from pathlib import Path

import pymupdf as fitz


def extract_pages(path: Path | str) -> list[str]:
    """Return one cleaned text string per page (index 0 = page 1)."""
    pages: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            text = page.get_text("text") or ""
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            pages.append(text.strip())
    return pages


def is_scanned(pages: list[str]) -> bool:
    """Exchange filings are often signed scans with no text layer."""
    if not pages:
        return True
    avg = sum(len(p) for p in pages) / len(pages)
    return avg < 150


def with_page_markers(pages: list[str], start: int = 1, max_chars: int | None = None) -> str:
    """Format pages as '[p.N]\n...' blocks so the model can cite page numbers."""
    out, total = [], 0
    for i, text in enumerate(pages, start=start):
        block = f"[p.{i}]\n{text}\n"
        if max_chars and total + len(block) > max_chars:
            break
        out.append(block)
        total += len(block)
    return "\n".join(out)
