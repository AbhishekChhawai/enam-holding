"""Corporate announcements from BSE.

We build on the maintained `bse` package (BennyThadikaran/BseIndiaApi) rather than
hand-rolling requests: BSE changes headers/endpoints periodically and that library
tracks the changes. NSE was deliberately left out: its API needs browser cookies and
usually rejects cloud IPs, while every NSE-listed large/mid-cap also files on BSE.
"""
from __future__ import annotations

import logging
import re
import tempfile
from datetime import datetime, timedelta

from bse import BSE

log = logging.getLogger("finn.bse")

ATTACH_LIVE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/"
ATTACH_HIS = "https://www.bseindia.com/xml-data/corpfiling/AttachHis/"
IST_OFFSET = timedelta(hours=5, minutes=30)


def client() -> BSE:
    return BSE(download_folder=tempfile.gettempdir())


def fetch(bse: BSE, scripcode: str, start: datetime, end: datetime, max_pages: int = 10) -> list[dict]:
    rows: list[dict] = []
    for page in range(1, max_pages + 1):
        data = bse.announcements(page_no=page, from_date=start, to_date=end, scripcode=str(scripcode))
        table = data.get("Table") or []
        rows.extend(table)
        total = (data.get("Table1") or [{}])[0].get("ROWCNT") or 0
        if not table or len(rows) >= int(total):
            break
    return rows


def lookup_code(bse: BSE, symbol: str) -> str | None:
    try:
        res = bse.lookup(symbol)
        return res.get("bse_code") if res else None
    except Exception as e:  # noqa: BLE001
        log.warning("BSE lookup failed for %s: %s", symbol, e)
        return None


def _parse_ist(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.split(".")[0]
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d %b %Y %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt) - IST_OFFSET  # naive UTC
        except ValueError:
            continue
    return None


def _clean_subject(newssub: str) -> str:
    # "PAN ELECTRONICS INDIA LTD. - 517397 - Compliances-Reg. 39 (3) - ..." -> subject part only
    parts = [p.strip() for p in re.split(r"\s-\s", newssub or "")]
    if len(parts) >= 3 and parts[1].isdigit():
        return " - ".join(parts[2:])
    return (newssub or "").strip()


def normalize(row: dict, symbol: str) -> dict:
    attach = (row.get("ATTACHMENTNAME") or "").strip()
    published = _parse_ist(row.get("DissemDT")) or _parse_ist(row.get("NEWS_DT")) or _parse_ist(row.get("DT_TM"))
    return {
        "id": str(row.get("NEWSID")),
        "symbol": symbol,
        "published_at": published,
        "headline": (row.get("HEADLINE") or "").strip(),
        "subject": _clean_subject(row.get("NEWSSUB") or ""),
        "bse_category": (row.get("CATEGORYNAME") or None),
        "bse_subcategory": (row.get("SUBCATNAME") or None),
        "attachment_url": (ATTACH_LIVE + attach) if attach else None,
        "source_url": row.get("NSURL") or None,
        "critical": bool(row.get("CRITICALNEWS")),
    }


def attachment_candidates(url: str | None) -> list[str]:
    """Older filings move from AttachLive to AttachHis. screener links transcripts through BSE's viewer
    (stockinfo/AnnPdfOpen.aspx?Pname=<id>.pdf); the same id is also served directly from either folder."""
    if not url:
        return []
    m = re.search(r"bseindia\.com/stockinfo/AnnPdfOpen\.aspx\?Pname=([\w.-]+\.pdf)", url, re.I)
    if m:
        name = m.group(1)
        return [url, ATTACH_LIVE + name, ATTACH_HIS + name]
    return [url, url.replace(ATTACH_LIVE, ATTACH_HIS)] if url.startswith(ATTACH_LIVE) else [url]
