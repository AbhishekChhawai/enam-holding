"""Live smoke test: runs FINN's own ingestion code against the real providers.

    cd backend && python scripts/smoke_test.py                 # uses GEMINI_API_KEY if set
    python scripts/smoke_test.py --portfolio RELIANCE DIXON --unseen KAYNES

Writes to a throwaway database (never your real finn.db). Prints PASS / FAIL / SKIP per check,
saves smoke_report.json, and exits 1 if anything failed. A mocked test is not a live test: this is
the script that turns NOT VERIFIED into PASS or FAIL.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="finn-smoke-")
os.environ["FINN_DATA_DIR"] = _tmp
os.environ["FINN_DB_URL"] = f"sqlite:///{_tmp}/smoke.db"
os.environ["FINN_LIVE_REFRESH"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finn import llm, registry, store  # noqa: E402
from finn.db import PriceBar, init_db, session_scope  # noqa: E402
from finn.pull import promises as P  # noqa: E402
from finn.pull.citations import verify_numbers  # noqa: E402
from finn.push import classify, results  # noqa: E402
from finn.push.refresh import _summarise  # noqa: E402
from finn.quality import expected_session, price_checks, weekdays_between  # noqa: E402
from finn.sources import bse_filings, prices, screener  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

REPORT: list[dict] = []
CTX: dict = {}


class _Skip(Exception):
    pass


def check(name: str, needs: str | None = None):
    def wrap(fn):
        def run(*a, **k):
            if needs and needs not in CTX:
                REPORT.append({"check": name, "status": "SKIP", "detail": f"needs {needs}"})
                return
            t = time.time()
            try:
                detail = fn(*a, **k)
                REPORT.append({"check": name, "status": "PASS", "detail": detail, "seconds": round(time.time() - t, 1)})
            except _Skip as e:
                REPORT.append({"check": name, "status": "SKIP", "detail": str(e)})
            except AssertionError as e:
                REPORT.append({"check": name, "status": "FAIL", "detail": str(e), "seconds": round(time.time() - t, 1)})
            except Exception as e:  # noqa: BLE001
                REPORT.append({"check": name, "status": "FAIL", "detail": f"{type(e).__name__}: {str(e)[:300]}",
                               "trace": traceback.format_exc(limit=3), "seconds": round(time.time() - t, 1)})
        return run
    return wrap


# ------------------------------------------------------------------ prices
@check("EOD prices (yfinance): completeness, alignment, idempotent store")
def t_prices(symbols: list[str]):
    data = prices.fetch_eod(symbols, period="3mo")
    exp = expected_session()
    lines = []
    for sym in symbols:
        bars = data.get(sym) or []
        assert len(bars) >= 40, f"{sym}: only {len(bars)} bars for 3 months"
        dates = [b["date"] for b in bars]
        assert len(dates) == len(set(dates)), f"{sym}: duplicate dates"
        assert all(date.fromisoformat(d).weekday() < 5 for d in dates), f"{sym}: weekend bars"
        behind = weekdays_between(date.fromisoformat(dates[-1]), exp)
        assert behind <= 3, f"{sym}: last bar {dates[-1]} is {behind} sessions behind {exp}"
        objs = [PriceBar(symbol=sym, **b) for b in bars]
        fails = [c for c in price_checks(objs) if c["status"] == "fail"]
        assert not fails, f"{sym}: {fails}"
        with session_scope() as s:
            for b in bars:
                s.merge(PriceBar(symbol=sym, **b))
        with session_scope() as s:
            for b in bars:
                s.merge(PriceBar(symbol=sym, **b))
            n = s.scalar(select(func.count()).select_from(PriceBar).where(PriceBar.symbol == sym))
        assert n == len(bars), f"{sym}: re-store changed row count {len(bars)} -> {n}"
        lines.append(f"{sym} {len(bars)} bars to {dates[-1]} via {bars[-1]['source']}, close {bars[-1]['close']:.2f}")
    CTX["prices"] = True
    return "; ".join(lines)


@check("Prices read back through the app API match what was stored", needs="prices")
def t_prices_api(symbols: list[str]):
    from fastapi.testclient import TestClient
    from finn.api import app
    out = []
    with TestClient(app) as c:
        for sym in symbols:
            r = c.get(f"/api/companies/{sym}/prices?period=3m").json()
            with session_scope() as s:
                last = s.scalars(select(PriceBar).where(PriceBar.symbol == sym).order_by(PriceBar.date.desc()).limit(1)).first()
            assert r["count"] >= 40 and r["bars"][-1]["date"] == last.date and abs(r["bars"][-1]["close"] - last.close) < 1e-6, f"{sym}: API/DB mismatch"
            out.append(f"{sym}: {r['count']} bars, freshness {r['freshness']}")
    return "; ".join(out)


# ------------------------------------------------------------------ filings
@check("BSE: code lookup matches portfolio.yaml")
def t_bse_lookup(expect: dict[str, str]):
    b = bse_filings.client()
    try:
        got = {s: bse_filings.lookup_code(b, s) for s in expect}
    finally:
        b.exit()
    bad = {s: (got[s], expect[s]) for s in expect if got[s] != expect[s]}
    assert not bad, f"mismatch (got, expected): {bad}"
    CTX["bse"] = True
    return ", ".join(f"{s}={c}" for s, c in got.items())


@check("BSE: announcements parse, classify, unique ids", needs="bse")
def t_bse_ann(expect: dict[str, str]):
    b = bse_filings.client()
    rows = []
    try:
        for sym, code in expect.items():
            for r in bse_filings.fetch(b, code, datetime.now() - timedelta(days=30), datetime.now(), max_pages=3):
                rows.append(bse_filings.normalize(r, sym))
    finally:
        b.exit()
    assert rows, "no announcements in 30 days for any symbol (BSE blocked or endpoint changed)"
    assert all(r["published_at"] for r in rows), "unparsed timestamps"
    assert len({r["id"] for r in rows}) == len(rows), "duplicate NEWSIDs"
    cats = {}
    for r in rows:
        c = classify.rule_classify(r["subject"], r["headline"], r["bse_category"], r["bse_subcategory"]) or "needs_model"
        cats[c] = cats.get(c, 0) + 1
    CTX["filings"] = rows
    with_pdf = [r for r in rows if r["attachment_url"]]
    return f"{len(rows)} filings, {len(with_pdf)} with PDFs; categories {cats}"


@check("BSE: download one filing PDF and extract pages", needs="filings")
def t_bse_pdf():
    for r in [r for r in CTX["filings"] if r["attachment_url"]][:5]:
        did = store.register_doc(r["symbol"], "filing", r["attachment_url"], title=r["headline"][:200])
        meta, pages = store.load_pages(did)
        if meta["status"] in ("ok", "scanned"):
            CTX["filing_doc"] = (r, did, pages)
            return f"{meta['status']}: {meta['pages']} pages, '{r['headline'][:60]}'"
    raise AssertionError("none of the first 5 attachments downloaded (blocked or moved)")


# ------------------------------------------------------------------ screener
@check("Screener: tables, latest quarter, QoQ/YoY card")
def t_screener(sym: str):
    c = screener.fetch_company(sym)
    q = c["tables"]["quarters"]
    assert len(q["headers"]) >= 8, f"only {len(q['headers'])} quarter columns"
    assert P.periods.quarter_of(q["headers"][-1]), f"unparseable latest quarter label {q['headers'][-1]!r}"
    card = results.card_from_screener(c)
    assert card and card["rows"][0]["current"], "no revenue in latest quarter"
    CTX["screener"] = c
    with session_scope() as s:
        from finn.db import kv_set
        kv_set(s, f"screener:{sym}", c)
    r0 = card["rows"][0]
    return f"{c['name']} ({c['basis']}), latest {card['periods'][0]}: revenue {r0['current']} cr, QoQ {r0['qoq_pct']}%, YoY {r0['yoy_pct']}%"


@check("Screener: annual reports and concall transcripts discovered", needs="screener")
def t_docs():
    d = CTX["screener"]["documents"]
    ars = [a for a in d["annual_reports"] if a.get("url")]
    calls = [x for x in d["concalls"] if x.get("transcript")]
    assert ars, "no annual report links"
    assert calls, "no concall transcript links"
    CTX["calls"], CTX["ars"] = calls, ars
    return f"{len(ars)} annual reports (latest FY{ars[0].get('year')}), {len(calls)} transcripts (latest {calls[0]['period']})"


@check("Transcript: download, page-level text", needs="calls")
def t_transcript(sym: str):
    c = CTX["calls"][0]
    did = store.register_doc(sym, "transcript", c["transcript"], title=f"Concall {c['period']}", period=c["period"])
    meta, pages = store.load_pages(did)
    assert meta["status"] == "ok", f"status {meta['status']}: {meta.get('error')}"
    assert len(pages) >= 3, f"only {len(pages)} pages"
    _, p2 = store.get_page(did, 2)
    assert p2 and len(p2) > 200, "page 2 has no text"
    CTX["transcript"] = (did, pages, c)
    return f"{c['period']}: {len(pages)} pages; page 2 starts '{p2[:70].strip()}...'"


@check("Annual report: download, page-level text", needs="ars")
def t_ar(sym: str):
    a = CTX["ars"][0]
    did = store.register_doc(sym, "annual_report", a["url"], title=a["title"])
    meta, pages = store.load_pages(did)
    assert meta["status"] in ("ok", "scanned"), f"status {meta['status']}: {meta.get('error')}"
    return f"{a['title']}: {meta['status']}, {len(pages)} pages"


# ------------------------------------------------------------------ unseen ticker
@check("Unseen ticker: resolve + ingest without code changes")
def t_unseen(sym: str):
    out = registry.resolve(sym, background=False)
    steps = (out.get("job") or {}).get("steps", {})
    assert out["symbol"] == sym.upper(), f"resolved to {out['symbol']}"
    assert steps.get("prices", {}).get("status") == "ok", f"prices: {steps.get('prices')}"
    return f"{out['name']} bse={out['bse_code']} via {out['identity_sources']}; prices {steps['prices']}, filings {steps.get('filings')}"


# ------------------------------------------------------------------ research this
@check("Research This: real filing -> context; opening research makes no model calls", needs="bse")
def t_research_this(sym: str):
    from fastapi.testclient import TestClient
    from finn.api import app
    from finn.push.refresh import refresh_announcements
    with TestClient(app) as c:
        refresh_announcements(days=30, symbols=[sym])
        from finn.db import Announcement
        with session_scope() as s:
            ann = s.scalars(select(Announcement).where(Announcement.symbol == sym, Announcement.category != "unclassified")
                            .order_by(Announcement.base_score.desc())).first()
        assert ann, f"no non-routine {sym} filing in 30 days to hand off"
        ctx = c.get(f"/api/announcements/{ann.id}/research-context").json()
        assert ctx["symbol"] == sym and ctx["event_id"] == ann.id and ctx["suggested_question"], f"bad context {ctx}"
        before = llm.usage_summary()["total_calls"]
        gated = {p: c.get(f"/api/research/{sym}/{p}").json().get("status") for p in ("promises", "narrative", "business", "bullbear")}
        after = llm.usage_summary()["total_calls"]
        assert after == before, f"opening research made {after - before} model calls"
        CTX["handoff"] = ctx
        return f"{ctx['category_label']}: '{ctx['headline'][:50]}', {len(ctx['document_ids'])} docs, q='{ctx['suggested_question'][:60]}...'; opening tabs -> {gated}, 0 model calls"


# ------------------------------------------------------------------ gemini
@check("Gemini: configured model ids exist")
def t_models():
    if not llm.available():
        raise _Skip("GEMINI_API_KEY not set")
    from google import genai
    names = [m.name.split("/")[-1] for m in genai.Client(api_key=os.environ["GEMINI_API_KEY"]).models.list()]
    missing = [m for m in (llm.MODEL_FAST, llm.MODEL_REASON) if m not in names]
    flash = sorted(n for n in names if "flash" in n)[-8:]
    assert not missing, f"not available to this key: {missing}. Set FINN_MODEL_FAST / FINN_MODEL_REASON to one of {flash}"
    CTX["gemini"] = True
    return f"fast={llm.MODEL_FAST}, reason={llm.MODEL_REASON}"


@check("Gemini: classify real headlines (structured output)", needs="gemini")
def t_classify():
    rows = CTX.get("filings") or []
    assert rows, "needs real filings from the BSE check"
    items = [(i, f"{r['subject']} | {r['headline']}") for i, r in enumerate(rows[:6])]
    got = classify.llm_classify(items)
    assert got and all(v in classify.CATEGORIES for v in got.values()), f"bad output {got}"
    return "; ".join(f"{rows[i]['headline'][:40]!r} -> {c}" for i, c in list(got.items())[:4])


@check("Gemini: summary grounded in the filing (no invented numbers)", needs="gemini")
def t_summary():
    src = CTX.get("filing_doc") or (CTX.get("transcript") and (None, CTX["transcript"][0], CTX["transcript"][1]))
    assert src, "needs a downloaded text filing or transcript"
    r, did, pages = src
    text_pages = [p for p in pages[:3] if len(p) > 100]
    assert text_pages, "document has no text layer (scanned); try another"
    summary = _summarise(pages, (r or {}).get("headline", "Earnings call transcript"))
    assert summary, "empty summary"
    missing = verify_numbers(summary, pages[:3])
    assert not missing, f"numbers not found in source: {missing} | {summary}"
    return summary


@check("Gemini: guidance extraction with verified quotes", needs="gemini")
def t_guidance():
    assert "transcript" in CTX, "needs the transcript check"
    did, pages, c = CTX["transcript"]
    q = P.periods.call_month_to_quarter(c["period"])
    items = P.extract(did, pages, {"period": c["period"], "fy": q[0] if q else None, "q": q[1] if q else None})
    ok = sum(1 for g in items if g["quote_verified"])
    assert items, "no guidance extracted (possible, but check the transcript)"
    assert ok >= max(1, len(items) // 2), f"only {ok}/{len(items)} quotes found verbatim in the transcript"
    return f"{len(items)} items, {ok} quotes verified; e.g. {items[0]['metric']}: {items[0]['statement'][:80]}"


@check("Gemini: document-grounded Q&A with valid citations", needs="gemini")
def t_ask(sym: str):
    from finn.pull import agent
    q = (CTX.get("handoff") or {}).get("suggested_question") or "What did management say about margins and growth in the latest call?"
    a = agent.ask(sym, q)
    assert a["status"] in ("ok", "not_found"), f"status {a['status']}"
    cited = [c for c in a["claims"] if c["citations"]]
    assert a["status"] == "not_found" or cited, "answer has no cited claims"
    bad = [c["text"] for c in a["claims"] if c["unsupported_numbers"]]
    return f"{a['summary'][:120]} | {len(cited)}/{len(a['claims'])} claims cited; numbers not on cited page: {bad or 'none'}"


@check("Gemini: unanswerable question is not answered with invented figures", needs="gemini")
def t_unanswerable(sym: str):
    from finn.pull import agent
    a = agent.ask(sym, "What was the company's exact revenue in fiscal year 1985, and who was its auditor that year?")
    verified_numeric = [c for c in a["claims"] if c["verified"] and any(ch.isdigit() for ch in c["text"])]
    assert a["status"] == "not_found" or not verified_numeric, f"possible fabrication: {a['summary']}"
    return f"status {a['status']}: {a['summary'][:120]}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--portfolio", nargs="*", default=["RELIANCE", "DIXON"])
    ap.add_argument("--unseen", default="KAYNES")
    a = ap.parse_args()
    init_db()
    import yaml
    from finn.config import PORTFOLIO_FILE
    codes = {c["symbol"]: str(c["bse"]) for c in yaml.safe_load(open(PORTFOLIO_FILE))["portfolio"]}
    expect = {s: codes[s] for s in a.portfolio if s in codes}
    research_sym = a.portfolio[-1]
    t_prices(a.portfolio)
    t_prices_api(a.portfolio)
    t_bse_lookup(expect)
    t_bse_ann(expect)
    t_bse_pdf()
    t_screener(research_sym)
    t_docs()
    t_transcript(research_sym)
    t_ar(research_sym)
    t_unseen(a.unseen)
    t_research_this(research_sym)
    t_models()
    t_classify()
    t_summary()
    t_guidance()
    t_ask(research_sym)
    t_unanswerable(research_sym)
    width = max(len(r["check"]) for r in REPORT)
    print("\nFINN live smoke test", datetime.now().strftime("%Y-%m-%d %H:%M"), f"(throwaway db: {_tmp})\n")
    label = {"PASS": "PASS (real provider)", "FAIL": "FAIL", "SKIP": "NOT VERIFIED"}
    for r in REPORT:
        print(f"{label[r['status']]:<20} {r['check']:<{width}}  {r.get('detail') or ''}")
    if llm.available():
        print("\nModel use:", json.dumps(llm.usage_summary()["models"]))
    Path("smoke_report.json").write_text(json.dumps(REPORT, indent=2, default=str))
    fails = sum(r["status"] == "FAIL" for r in REPORT)
    print(f"\n{sum(r['status'] == 'PASS' for r in REPORT)} pass, {fails} fail, "
          f"{sum(r['status'] == 'SKIP' for r in REPORT)} skip. Details in smoke_report.json")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
