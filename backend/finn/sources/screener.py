"""screener.in: standardised multi-year financials + links to annual reports and concall transcripts.

Screener is used for (a) document discovery and (b) standardised numbers that our
deterministic code computes on. Narrative evidence always comes from the primary PDFs.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from .http import FetchError, get

log = logging.getLogger("finn.screener")
BASE = "https://www.screener.in"
SECTIONS = {
    "quarters": "quarters",
    "profit_loss": "profit-loss",
    "balance_sheet": "balance-sheet",
    "cash_flow": "cash-flow",
    "ratios": "ratios",
}


# ---------------------------------------------------------------------- fetch
def fetch_company(symbol: str) -> dict:
    """Fetch and parse a company page. Prefers consolidated figures, falls back to standalone."""
    symbol = symbol.upper().strip()
    errors = []
    for basis, path in (("consolidated", f"/company/{symbol}/consolidated/"), ("standalone", f"/company/{symbol}/")):
        url = BASE + path
        try:
            html = get(url).text
        except FetchError as e:
            errors.append(str(e))
            continue
        parsed = parse_company(html)
        q = parsed["tables"].get("quarters")
        if q and any(v is not None for row in q["rows"].values() for v in row):
            parsed.update({"symbol": symbol, "basis": basis, "url": url,
                           "retrieved_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")})
            return parsed
    raise FetchError(f"No screener.in data for {symbol}: {'; '.join(errors) or 'empty tables'}")


def search(query: str) -> list[dict]:
    """Company search via screener's public autocomplete endpoint."""
    try:
        r = get(f"{BASE}/api/company/search/", params={"q": query, "v": 3, "fts": 1}, timeout=5, retries=1)
        items = r.json()
    except Exception as e:  # noqa: BLE001
        log.warning("screener search failed: %s", e)
        return []
    out = []
    for it in items[:8]:
        url = it.get("url") or ""
        m = re.match(r"/company/([^/]+)/", url)
        if m and it.get("name"):
            out.append({"symbol": m.group(1).upper(), "name": it["name"]})
    return out


# ---------------------------------------------------------------------- parse
def _txt(node: Tag | None) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.get_text(" ", strip=True)).strip()


def parse_number(raw: str) -> float | None:
    t = (raw or "").replace("\xa0", " ").strip()
    if t in {"", "-", "--", "N/A", "NA"}:
        return None
    neg = t.startswith("(") and t.endswith(")")
    t = re.sub(r"[,%₹\s()+]", "", t)
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def normalize_label(label: str) -> str:
    label = re.sub(r"\s+", " ", label.replace("\xa0", " ")).strip()
    label = re.sub(r"\s*\+\s*$", "", label)
    return label.lower()


def parse_table(section: Tag) -> dict | None:
    table = section.find("table")
    if table is None:
        return None
    headers: list[str] = []
    thead = table.find("thead")
    if thead:
        headers = [_txt(th) for th in thead.find_all("th")[1:]]
    rows: dict[str, list[float | None]] = {}
    labels: dict[str, str] = {}
    pdf_links: list[str | None] = []
    body = table.find("tbody") or table
    for tr in body.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue
        raw_label = _txt(cells[0])
        if not raw_label:
            continue
        key = normalize_label(raw_label)
        if key == "raw pdf":
            for c in cells[1:]:
                a = c.find("a", href=True)
                href = a["href"] if a else None
                pdf_links.append((BASE + href) if href and href.startswith("/") else href)
            continue
        rows[key] = [parse_number(_txt(c)) for c in cells[1:]]
        labels[key] = re.sub(r"\s*\+\s*$", "", raw_label)
    return {"headers": headers, "rows": rows, "labels": labels, "pdf_links": pdf_links}


def parse_documents(soup: BeautifulSoup) -> dict:
    sec = soup.find("section", id="documents")
    out = {"annual_reports": [], "concalls": []}
    if sec is None:
        return out
    for block in sec.find_all("div", class_=re.compile(r"\bdocuments\b")):
        h = block.find(["h3", "h2", "h4"])
        heading = _txt(h).lower()
        if "annual" in heading:
            for a in block.find_all("a", href=True):
                title = _txt(a)
                m = (re.search(r"(?:Financial Year|Annual Report|FY)\s*'?(\d{4}|\d{2})\b", title, re.I)
                     or re.search(r"\b((?:19|20)\d{2})\b", title))
                year = int(m.group(1)) if m else None
                if year and year < 100:
                    year += 2000
                out["annual_reports"].append({
                    "title": re.sub(r"\s*from\s+\w+\s*$", "", title, flags=re.I).strip() or "Annual report",
                    "year": year, "url": a["href"],
                })
        elif "concall" in heading:
            for li in block.find_all("li"):
                period = ""
                d = li.find("div")
                if d:
                    period = _txt(d)
                if not re.match(r"[A-Za-z]{3}\s+\d{4}", period or ""):
                    m = re.search(r"([A-Z][a-z]{2})\s+(\d{4})", _txt(li))
                    period = f"{m.group(1)} {m.group(2)}" if m else ""
                links = {}
                for a in li.find_all("a", href=True):
                    t = (_txt(a) + " " + (a.get("title") or "")).lower()
                    if "transcript" in t:
                        links["transcript"] = a["href"]
                    elif "ppt" in t or "presentation" in t:
                        links["ppt"] = a["href"]
                    elif "rec" in t or "audio" in t or "video" in t:
                        links["recording"] = a["href"]
                    elif "note" in t:
                        links["notes"] = a["href"]
                if period and links:
                    out["concalls"].append({"period": period, **links})
    return out


def parse_top_ratios(soup: BeautifulSoup) -> dict:
    ul = soup.find(id="top-ratios")
    out = {}
    if ul is None:
        return out
    for li in ul.find_all("li"):
        name = _txt(li.find(class_="name"))
        val = _txt(li.find(class_="number")) or _txt(li.find(class_="value"))
        if name:
            out[name] = val
    return out


def parse_company(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    tables = {}
    for key, sid in SECTIONS.items():
        sec = soup.find("section", id=sid)
        if sec is not None:
            t = parse_table(sec)
            if t:
                tables[key] = t
    name = _txt(soup.find("h1"))
    return {
        "name": name,
        "tables": tables,
        "documents": parse_documents(soup),
        "top_ratios": parse_top_ratios(soup),
    }


# ---------------------------------------------------------------------- helpers
def row(table: dict | None, *aliases: str) -> tuple[str | None, list[float | None]]:
    """Find the first row whose normalised label starts with one of the aliases."""
    if not table:
        return None, []
    for alias in aliases:
        for key, vals in table["rows"].items():
            if key == alias or key.startswith(alias):
                return key, vals
    return None, []
