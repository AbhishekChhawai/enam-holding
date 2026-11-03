"""Package REAL ingested FINN data into the single-file phone app (no server needed).

    cd backend
    export GEMINI_API_KEY=...            # so ingestion can run promises / narrative / research
    python -m finn.ingest                # real prices, BSE filings, Screener docs, AI research
    python scripts/export_snapshot.py    # -> frontend/src/demo/snapshot.json (real data)
    cd ../frontend && npm run build:demo # -> frontend/dist-demo/index.html  (open on any phone)

Every response in the snapshot is produced by FINN's own API over your database. The script refuses to
export if it finds fictional test fixtures, and prints a coverage report so you know exactly what's inside.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
OUT = BACKEND.parent / "frontend" / "src" / "demo" / "snapshot.json"
MAX_BYTES = 14 * 1024 * 1024        # artifact/static pages stay well under 16 MB
AR_PAGES = 160                      # annual reports are long; Ask needs the business/MD&A/risk pages, not all 400


def export(out: Path = OUT, kind: str = "real", allow_synthetic: bool = False, fetch_missing: bool = True, note: str | None = None) -> dict:
    from fastapi.testclient import TestClient
    from sqlalchemy import func, select

    from finn.api import app
    from finn.db import Announcement, Document, PriceBar, kv_get, session_scope
    from finn.push.digest import cluster, item_dict

    from finn.db import Company, init_db
    init_db()
    with session_scope() as s:
        bars_total = s.scalar(select(func.count()).select_from(PriceBar)) or 0
        # positive proof of real ingestion: the yfinance ingester tags rows "yfinance:NSE" / "yfinance:BSE"
        real = (PriceBar.source.like("yfinance:%")) | (PriceBar.source.like("nse-bhavcopy:%"))
        real_bars = s.scalar(select(func.count()).select_from(PriceBar).where(real)) or 0
        fixture = (s.scalar(select(func.count()).select_from(PriceBar).where(~real)) or 0) \
            + (s.scalar(select(func.count()).select_from(Announcement).where(Announcement.headline.ilike("%synthetic%"))) or 0) \
            + (s.scalar(select(func.count()).select_from(Company).where(Company.sector == "Synthetic")) or 0)
        stamp = kv_get(s, "stamp:announcements") or kv_get(s, "stamp:prices") or s.scalar(select(func.max(PriceBar.date)))
    if kind == "real" and not allow_synthetic:
        if bars_total == 0:
            raise SystemExit("No price data found. Run `python -m finn.ingest` first (on a machine with internet access).")
        if fixture or real_bars == 0:
            raise SystemExit(f"Refusing: this database contains data that did not come from FINN's real ingestion "
                             f"({fixture} fixture/untagged rows, {real_bars} real price rows). Ingest into a fresh FINN_DB_URL and export that.")

    snap: dict = {"meta": {"kind": kind, "snapshot_at": stamp, "research": [], "note": note}, "get": {}, "docs": {}}
    report = {"companies": 0, "with_prices": 0, "filings": 0, "documents": 0, "research": [], "missing": []}
    with TestClient(app) as c:
        def get(path: str, required: bool = False):
            r = c.get(path)
            if r.status_code == 200:
                snap["get"][path] = r.json()
                return r.json()
            if required:
                report["missing"].append(f"{path} -> {r.status_code}")
            return None

        c.post("/api/alerts/evaluate")
        for h in (24, 72, 168, 720):
            get(f"/api/digest?hours={h}", required=True)
        for p in ("/api/portfolio", "/api/portfolio/analysis", "/api/alerts?limit=200", "/api/alerts/rules", "/api/meta/categories", "/api/meta/usage", "/api/prefs"):
            get(p, required=True)
        companies = c.get("/api/companies").json()["items"]
        report["companies"] = len(companies)
        for co in companies:
            sym = co["symbol"]
            get(f"/api/companies/{sym}")
            get(f"/api/companies/{sym}/data-quality")
            if get(f"/api/companies/{sym}/prices?period=1y"):
                report["with_prices"] += 1
                for per in ("1m", "3m", "6m"):
                    get(f"/api/companies/{sym}/prices?period={per}")
            for t in ("", "results", "filings", "market", "documents"):
                get(f"/api/companies/{sym}/timeline" + (f"?types={t}" if t else ""))
            with session_scope() as s:
                have = kv_get(s, f"screener:{sym}") is not None
            # Screener financials: saved by ingestion for researched companies; fetched now for the rest (needs internet)
            if (have or fetch_missing) and get(f"/api/research/{sym}/overview"):
                got = {p: (get(f"/api/research/{sym}/{p}") or {}).get("status") for p in ("promises", "narrative", "business", "bullbear")}
                if got.get("promises") == "ok":
                    snap["meta"]["research"].append(sym)
                    report["research"].append(f"{sym} ({', '.join(k for k, v in got.items() if v == 'ok')})")
        with session_scope() as s:
            docs = [(d.id, d.pages, d.kind) for d in s.scalars(select(Document).where(Document.status.in_(("ok", "scanned"))))]
            anns = list(s.scalars(select(Announcement)))
            items = [item_dict(a, {}, {"category_weights": {}, "alert_categories": []}) for a in anns]
            standing = {it["id"] for it in cluster(items)}
            snap["bars"] = {co["symbol"]: [{"date": b.date, "close": b.close, "volume": b.volume, "source": b.source}
                                           for b in s.scalars(select(PriceBar).where(PriceBar.symbol == co["symbol"]).order_by(PriceBar.date))]
                            for co in companies}
        report["filings"] = len(items)
        for did, n, dkind in docs:
            for pg in range(1, min(n, AR_PAGES if dkind == "annual_report" else n) + 1):
                r = c.get(f"/api/docs/{did}/page/{pg}")
                if r.status_code != 200:
                    continue
                j = r.json()
                snap["get"][f"/api/docs/{did}/page/{pg}"] = j
                snap["docs"].setdefault(j["doc"]["symbol"], []).append({"doc_id": did, "page": pg, "title": j["doc"]["title"], "text": j["text"]})
            report["documents"] += 1
        for it in items:
            get(f"/api/announcements/{it['id']}")
            get(f"/api/announcements/{it['id']}/research-context")
        snap["anns"] = [{**{k: it[k] for k in ("id", "symbol", "category", "category_label", "score", "tier", "title", "published_at", "attachment_url", "summary")},
                         "standing": it["id"] in standing} for it in items]
        snap["companies"] = companies
    blob = json.dumps(snap, ensure_ascii=False, separators=(",", ":"))
    if len(blob.encode()) > MAX_BYTES:
        raise SystemExit(f"Snapshot is {len(blob) // 1048576} MB; lower AR_PAGES or research fewer companies.")
    out.parent.mkdir(exist_ok=True)
    out.write_text(blob)
    report["size_kb"] = len(blob.encode()) // 1024
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-synthetic", action="store_true", help="testing only")
    ap.add_argument("--note-file", help="text shown in the app's data banner (e.g. data/eod2_note.txt)")
    ap.add_argument("--offline", action="store_true", help="don't fetch missing Screener data")
    a = ap.parse_args()
    r = export(allow_synthetic=a.allow_synthetic, fetch_missing=not a.offline, note=Path(a.note_file).read_text() if a.note_file else None)
    print(f"Wrote {OUT} ({r['size_kb']} KB)")
    print(f"  companies: {r['companies']} ({r['with_prices']} with EOD prices)   filings: {r['filings']}   documents: {r['documents']}")
    print(f"  AI research included for: {', '.join(r['research']) or 'none (set GEMINI_API_KEY and re-run python -m finn.ingest --step research)'}")
    if r["missing"]:
        print("  missing:", "; ".join(r["missing"][:8]))
    print("Next: cd ../frontend && npm run build:demo   ->  frontend/dist-demo/index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
