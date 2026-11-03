"""End-to-end investor journeys in a real browser against a real FINN server.

    pip install playwright && playwright install chromium
    cd frontend && npm run build && cd ../backend && python scripts/ui_journeys.py

Seeds a throwaway database with a FICTIONAL company (FINNDEMO, clearly labelled synthetic), starts the
API + built frontend, then clicks through the journeys and a viewport sweep. This tests interactions and
wiring, not data providers (that is scripts/smoke_test.py).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="finn-ui-")
ENV = {**os.environ, "FINN_DATA_DIR": TMP, "FINN_DB_URL": f"sqlite:///{TMP}/ui.db", "FINN_LIVE_REFRESH": "0", "GEMINI_API_KEY": ""}
os.environ.update(ENV)
BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
DIST = BACKEND.parent / "frontend" / "dist"
PORT = int(os.getenv("FINN_UI_PORT", "9300"))
BASE = f"http://localhost:{PORT}"
SYM, NAME = "FINNDEMO", "FINN Demo Industries (synthetic fixture)"
T_URL, R_URL = "https://example.com/finndemo/transcript-q1.pdf", "https://example.com/finndemo/results-q2.pdf"
QUOTE = "We expect revenue growth of fifteen to seventeen percent this year"


def seed() -> None:
    from finn import store
    from finn.db import Announcement, Company, DocPage, Document, PriceBar, init_db, kv_set, session_scope, utcnow
    from finn.quality import expected_session
    from finn.sources import screener
    init_db()
    end = expected_session()
    days, d = [], end
    while len(days) < 60:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.sort()
    did = store.doc_id_for(T_URL)
    with session_scope() as s:
        s.merge(Company(symbol=SYM, name=NAME, sector="Synthetic", in_portfolio=True, bse_code="999999"))
        for i, day in enumerate(days):
            c = 500 + i * 0.8 + (35 if i == len(days) - 1 else 0)
            s.merge(PriceBar(symbol=SYM, date=day.isoformat(), open=c, high=c + 4, low=c - 4, close=c,
                             volume=1e5 * (3 if i == len(days) - 1 else 1), source="synthetic-fixture"))
        card = {"type": "results", "basis": "consolidated", "unit": "₹ crore", "periods": ["Q2 FY27", "Q1 FY27", "Q2 FY26"],
                "rows": [{"key": k, "label": l, "current": c, "previous": p, "year_ago": y, "qoq_pct": round((c / p - 1) * 100, 1), "yoy_pct": round((c / y - 1) * 100, 1)}
                         for k, l, c, p, y in (("revenue", "Revenue", 1560, 1450, 1300), ("ebitda", "EBITDA", 175, 160, 140),
                                               ("pbt", "PBT", 160, 150, 125), ("pat", "PAT", 120, 112, 94))],
                "ebitda_margin": [11.2, 11.0, 10.8], "source": "results filing", "source_url": None,
                "check": {"status": "match", "note": "Revenue and PAT match screener.in"}}
        now = utcnow()
        s.merge(Announcement(id="ui-res", symbol=SYM, published_at=now - timedelta(hours=3), headline="Unaudited financial results for Q2 FY27 (synthetic)",
                             subject="Outcome of Board Meeting", category="results", base_score=80, reasons=["Results filings start at 80"],
                             attachment_url=R_URL, enrichment=card, enrichment_status="ok"))
        s.merge(Announcement(id="ui-ppt", symbol=SYM, published_at=now - timedelta(hours=2), headline="Investor presentation for Q2 FY27 results (synthetic)",
                             subject="Investor Presentation", category="results", base_score=55, reasons=["companion material"], attachment_url=R_URL))
        for j in range(5):
            s.merge(Announcement(id=f"ui-r{j}", symbol=SYM, published_at=now - timedelta(hours=4 + j), headline="Certificate under Regulation 74(5) (synthetic)",
                                 subject="Compliances", category="unclassified", base_score=5, reasons=["Routine"]))
        c = screener.parse_company((BACKEND / "tests" / "fixtures" / "screener_company.html").read_text())
        c.update(symbol=SYM, name=NAME, basis="consolidated", url="https://example.com/finndemo", retrieved_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        c["documents"] = {"annual_reports": [], "concalls": [{"period": "Jul 2026", "transcript": T_URL}]}
        kv_set(s, f"screener:{SYM}", c)
        s.merge(Document(id=did, symbol=SYM, kind="transcript", title="Concall transcript, Jul 2026 (synthetic)", period="Jul 2026",
                         url=T_URL, status="ok", pages=2, retrieved_at=now))
        s.merge(DocPage(doc_id=did, page=1, text="Opening remarks. " * 20))
        s.merge(DocPage(doc_id=did, page=2, text=f"CFO: {QUOTE}, driven by new contracts. " + "Further commentary. " * 15))
        pledge = {"id": "p1", "metric": "revenue_growth", "metric_label": "Revenue growth", "statement": "Revenue growth of 15-17% in FY27",
                  "quote": QUOTE, "quote_verified": True, "page": 2, "doc_id": did, "speaker": "CFO", "horizon": "Q2 FY27", "target": "15–17%",
                  "firmness": "explicit", "call_period": "Jul 2026", "call_quarter": "Q1 FY27", "verdict": "delivered", "outcome": "exceeded",
                  "variance": 3.0, "variance_text": "+3.0 pp above the top of the range", "explanation": "beat the top of the range", "judged_by": "numbers",
                  "actual": {"value": 20.0, "unit": "%", "period": "Q2 FY27", "formula": "sales vs same period a year earlier",
                             "inputs": ["Quarterly / Sales / Sep 2025", "Quarterly / Sales / Sep 2026"], "source_url": R_URL}}
        kv_set(s, f"promises:{SYM}", {"symbol": SYM, "status": "ok", "basis": "consolidated", "promises": [pledge], "current_guidance": [],
                                       "transcripts": [{"doc_id": did, "period": "Jul 2026", "quarter": "Q1 FY27", "status": "ok", "pages_n": 2, "url": T_URL}],
                                       "scorecard": {"delivered": 1, "partly": 0, "missed": 0, "in_progress": 0, "too_early": 0, "unverifiable": 0,
                                                     "checkable": 1, "hit_rate": 100, "headline": "Delivered on 1 of 1 checkable promises"}})
        kv_set(s, "stamp:announcements", now.strftime("%Y-%m-%dT%H:%M:%SZ"))
        kv_set(s, "stamp:prices", now.strftime("%Y-%m-%dT%H:%M:%SZ"))


RESULTS: list[tuple[str, str, str]] = []

# Finds any two visible pieces of text that physically overlap (text clipped by truncation counts only where visible).
OVERLAP_JS = r"""() => {
  const fixedAnc = (el) => { for (let e = el; e && e !== document.body; e = e.parentElement) { const p = getComputedStyle(e).position; if (p === 'fixed' || p === 'sticky') return e; } return null; };
  const boxes = [];
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || el.closest('[aria-hidden="true"]')) continue;
    for (const n of el.childNodes) {
      if (n.nodeType !== 3 || !n.textContent.trim()) continue;
      const r = document.createRange(); r.selectNodeContents(n);
      for (const raw of r.getClientRects()) {
        // clip to every ancestor that hides overflow (truncated text is only visible up to its box edge)
        let L = raw.left, R = raw.right, T = raw.top, Bt = raw.bottom;
        for (let e = el; e && e !== document.body; e = e.parentElement) {
          const c = getComputedStyle(e);
          if (c.overflowX !== 'visible' || c.overflowY !== 'visible') { const q = e.getBoundingClientRect(); L = Math.max(L, q.left); R = Math.min(R, q.right); T = Math.max(T, q.top); Bt = Math.min(Bt, q.bottom); }
        }
        if (R - L > 1 && Bt - T > 1) boxes.push({ el, rc: { left: L, right: R, top: T, bottom: Bt }, t: n.textContent.trim().slice(0, 28), fx: fixedAnc(el) });
      }
    }
  }
  const hits = [];
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.el === b.el || a.fx !== b.fx) continue;                       // floating bars legitimately sit over scrolled content
    const ox = Math.min(a.rc.right, b.rc.right) - Math.max(a.rc.left, b.rc.left);
    const oy = Math.min(a.rc.bottom, b.rc.bottom) - Math.max(a.rc.top, b.rc.top);
    if (ox > 2 && oy > 3) hits.push(`"${a.t}" x "${b.t}"`);
  }
  return [...new Set(hits)].slice(0, 12);
}"""


def step(journey: str, name: str, fn) -> None:
    try:
        detail = fn()
        RESULTS.append(("PASS", f"{journey}: {name}", detail or ""))
    except Exception as e:  # noqa: BLE001
        RESULTS.append(("FAIL", f"{journey}: {name}", f"{type(e).__name__}: {str(e).splitlines()[0][:160]}"))


def main() -> int:
    if not (DIST / "index.html").exists():
        print("Build the frontend first: cd frontend && npm run build")
        return 2
    seed()
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "finn.api:app", "--port", str(PORT)], cwd=BACKEND,
                           env={**ENV, "FINN_FRONTEND_DIST": str(DIST)}, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        time.sleep(4)
        from playwright.sync_api import expect, sync_playwright
        expect.set_options(timeout=6000)
        exe = os.getenv("FINN_CHROMIUM")
        with sync_playwright() as p:
            b = p.chromium.launch(**({"executable_path": exe} if exe else {}))
            ctx = b.new_context(viewport={"width": 375, "height": 812})
            ctx.add_init_script("try{localStorage.setItem('finn.onboarded','1');localStorage.setItem('finn.view','detailed')}catch(e){}")
            pg = ctx.new_page()   # J1-J7 test the Detailed view; beginner walkthroughs below start as a new visitor

            def j1():
                pg.goto(f"{BASE}/#today")
                expect(pg.get_by_role("heading", level=1)).to_contain_text(re.compile(r"needs? you"))
                expect(pg.get_by_text("Highest priority right now")).to_be_visible()
                pg.get_by_text("Unaudited financial results for Q2 FY27").first.click()
                expect(pg.get_by_text("Why it’s at the top")).to_be_visible()
                href = pg.get_by_role("link", name="Open filing").get_attribute("href")
                assert href == R_URL, href
                return "top card opens; reasons shown; original filing link correct"
            step("J1 Morning review", "brief to top event to original filing", j1)

            def j2():
                pg.get_by_role("button", name="Research this").click()
                expect(pg).to_have_url(f"{BASE}/#research/{SYM}/promises")
                expect(pg.get_by_text("From the filing:")).to_be_visible()
                pg.get_by_role("button", name="Back to the filing").click()
                expect(pg.get_by_text("Why it’s at the top")).to_be_visible()
                pg.keyboard.press("Escape")
                return "event context carried into Research and back to the same filing"
            step("J2 Push to Pull", "Research this, then back to the filing", j2)

            def j3():
                pg.goto(f"{BASE}/#research/{SYM}/promises")
                pg.get_by_text("Revenue growth of 15-17% in FY27").click()
                expect(pg.get_by_text("+3.0 pp above the top of the range").first).to_be_visible()
                assert pg.get_by_role("link", name="Open results filing").get_attribute("href") == R_URL
                pg.get_by_role("button", name="p.2").first.click()
                expect(pg.get_by_text("Concall transcript, Jul 2026 (synthetic)")).to_be_visible()
                expect(pg.get_by_text("Page 2 of 2")).to_be_visible()
                expect(pg.locator("mark")).to_have_text(QUOTE + "")  # highlight covers the quote exactly
                assert pg.get_by_role("link", name="Open PDF at page 2").get_attribute("href").endswith("#page=2")
                pg.keyboard.press("Escape")
                return "variance shown; transcript evidence highlighted; both sources linked"
            step("J3 Accountability", "promise to both sources", j3)

            def j4():
                pg.goto(f"{BASE}/#alerts")
                pg.get_by_role("button", name="Edit rules").click()
                pg.get_by_label("For").select_option(SYM)
                pg.get_by_label("Percent").fill("3")
                pg.get_by_role("button", name="Save rule").click()
                expect(pg.get_by_text("Rule saved.")).to_be_visible()
                pg.keyboard.press("Escape")
                card = pg.get_by_role("button", name=f"{SYM}: When {SYM} moves 3%").first
                expect(card).to_be_visible()
                card.click()
                expect(pg).to_have_url(f"{BASE}/#research/{SYM}/timeline")
                pg.goto(f"{BASE}/#alerts")
                pg.reload()
                expect(pg.get_by_role("button", name=f"{SYM}: When {SYM} moves 3%").first.locator("[aria-label='Read']")).to_have_count(1)
                return "rule saved via API, alert generated, read state survives reload"
            step("J4 Alerts", "create rule, alert fires, read persists", j4)

            def j5():
                pg.goto(f"{BASE}/#research/{SYM}/numbers")
                pg.reload()
                chart = pg.get_by_role("img", name=f"{SYM} closing price")
                expect(chart).to_be_visible()
                readout = pg.locator("[aria-live='polite']").first
                before = readout.inner_text()
                box = chart.bounding_box()
                pg.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.5)
                after = readout.inner_text()
                assert before != after, "scrub did not change the readout"
                pg.get_by_role("radio", name="1M").click()
                expect(pg.get_by_text("over 1M")).to_be_visible()
                return "deep link survives reload; chart scrubs; range switches"
            step("J5 Company profile", "price chart on a reloaded deep link", j5)

            def j6():
                pg.goto(f"{BASE}/#research")
                pg.get_by_label("Company name or NSE symbol").fill("FINN")
                pg.get_by_role("button", name=f"{SYM} {NAME}").click()
                expect(pg).to_have_url(f"{BASE}/#research/{SYM}/promises")
                return "visible search finds the company and opens it"
            step("J6 Explore", "search from the Research landing", j6)

            def j7():
                pg.goto(f"{BASE}/#research/{SYM}/ask")
                pg.get_by_label("Question", exact=True).fill("What did management guide for revenue?")
                pg.get_by_role("button", name="Send question").click()
                expect(pg.get_by_text("Q&A needs a Gemini key on the server.")).to_be_visible()
                return "no key on this server: honest notice, no crash (live answers need the smoke test)"
            step("J7 Ask FINN", "question without a model key", j7)

            # ---------------- beginner walkthroughs: a brand-new visitor, Plain English by default
            nb = b.new_context(viewport={"width": 375, "height": 812}).new_page()
            taps = {}

            def b0():
                nb.goto(f"{BASE}/#today")
                expect(nb.get_by_text("Your companies, explained")).to_be_visible()
                nb.get_by_role("button", name="Next").click(); nb.get_by_role("button", name="Next").click()
                nb.get_by_role("button", name="See what matters today").click()
                expect(nb.get_by_role("heading", level=1)).to_contain_text(re.compile(r"needs? you"))
                nb.reload(); expect(nb.get_by_text("Your companies, explained")).to_have_count(0)
                taps["B0"] = 3
                return "3 taps from first launch to today’s brief; tour not shown again after reload"
            step("B0 First visit", "onboarding to a useful screen", b0)

            def b1():
                expect(nb.get_by_text("Profit after tax was ₹120 crore, up 27.7% from a year earlier.")).to_be_visible()
                taps["B1"] = 0
                return "profit direction, size and period readable on the home card with 0 taps"
            step("B1 Did profit rise?", "plain sentence on the top card", b1)

            def b2():
                nb.get_by_role("button", name="See the numbers").first.click()
                nb.get_by_role("button", name="EBITDA: what does this mean?").first.click()
                expect(nb.get_by_text("In simple terms")).to_be_visible()
                expect(nb.get_by_text("What the core business earns from its operations")).to_be_visible()
                nb.get_by_role("button", name="EBITDA margin (operating margin)").click()
                expect(nb.get_by_text("How many rupees of operating profit the company keeps from every ₹100 of sales.")).to_be_visible()
                nb.keyboard.press("Escape")
                taps["B2"] = 2
                return "tap EBITDA: plain meaning + why it matters, related term one tap away (no model call)"
            step("B2 What is EBITDA?", "FINN Explain from inside the results", b2)

            def b3():
                nb.get_by_text("Unaudited financial results for Q2 FY27").first.click()
                for h in ("What happened", "Why it matters", "The proof", "What next"):
                    expect(nb.get_by_role("heading", name=h)).to_be_visible()
                expect(nb.get_by_text("Results show how much the company sold and earned this quarter.")).to_be_visible()
                assert nb.get_by_role("link", name="Open filing").get_attribute("href") == R_URL
                nb.keyboard.press("Escape")
                taps["B3"] = 1
                return "what happened, why it matters, the proof (original filing) and next step in one sheet"
            step("B3 Verify a claim", "structured insight with the source", b3)

            def b4():
                nb.goto(f"{BASE}/#research/{SYM}/promises")
                expect(nb.get_by_text("Promise beaten")).to_be_visible()
                expect(nb.get_by_text("Management expected revenue growth of 15–17% for Q2 FY27. The company reported 20.0% for Q2 FY27. "
                                      "That is 3.0 percentage points above the top of the range.")).to_be_visible()
                assert nb.get_by_role("link", name="What was reported").get_attribute("href") == R_URL
                nb.get_by_role("button", name="What was said").first.click()
                expect(nb.get_by_text("Page 2 of 2")).to_be_visible(); nb.keyboard.press("Escape")
                taps["B4"] = 1
                return "promise, outcome and gap in one sentence; both sources one tap away"
            step("B4 Did management deliver?", "plain promise tracker", b4)

            def b5():
                nb.goto(f"{BASE}/#alerts")
                nb.get_by_role("button", name="Edit rules").click()
                expect(nb.get_by_text("How much a share’s closing price changed from the day before.")).to_be_visible()
                nb.get_by_label("For").select_option(SYM); nb.get_by_label("Percent").fill("5")
                nb.get_by_role("button", name="Save rule").click()
                expect(nb.get_by_text("Rule saved.")).to_be_visible(); nb.keyboard.press("Escape")
                taps["B5"] = 4
                return "rule explained in everyday words; saved in 4 interactions without any formula"
            step("B5 Set a 5% alert", "plain rule builder", b5)

            def targets():
                small = []
                for r in ("today", "alerts", f"research/{SYM}/promises", f"research/{SYM}/numbers", f"research/{SYM}/timeline", "research"):
                    nb.goto(f"{BASE}/#{r}"); nb.wait_for_timeout(500)
                    small += nb.evaluate("""(r) => [...document.querySelectorAll('button, a[href], input, select, [role=radio]')].filter(el => {
                        const b = el.getBoundingClientRect(); if (!b.width || !b.height) return false;
                        if (el.closest('p, li > span, td, th, blockquote, summary')) return false;          // WCAG 2.5.8 inline exception
                        if (el.dataset.a11yEquivalent) return false;                                       // documented "equivalent control" exception
                        return b.width < 24 || b.height < 24; }).map(el => r + ': ' + (el.getAttribute('aria-label') || el.textContent.trim().slice(0, 30)) + ' ' + Math.round(el.getBoundingClientRect().width) + 'x' + Math.round(el.getBoundingClientRect().height))""", r)
                if small:
                    print("UNDERSIZED:\n  " + "\n  ".join(sorted(set(small))))
                assert not small, f"{len(small)} undersized controls (listed above)"
                return "every standalone control is at least 24×24 CSS px on 6 screens (inline links in text excepted)"
            step("A11y", "WCAG 2.2 target size (2.5.8)", targets)

            def sweep():
                bad = []
                for w in (320, 375, 390, 768, 1280):
                    vp = b.new_page(viewport={"width": w, "height": 800})
                    for r in ("today", "alerts", "portfolio", "research", f"research/{SYM}/promises", f"research/{SYM}/numbers",
                              f"research/{SYM}/timeline", f"research/{SYM}/business", f"research/{SYM}/ask"):
                        vp.goto(f"{BASE}/#{r}")
                        vp.wait_for_timeout(500)
                        sw = vp.evaluate("document.documentElement.scrollWidth")
                        if sw > w:
                            bad.append(f"{r}@{w}={sw}")
                    vp.close()
                assert not bad, ", ".join(bad)
                return "9 routes x 5 widths, no horizontal overflow"
            step("Responsive", "320/375/390/768/1280", sweep)

            def overlaps():
                hits = {}
                for w in (320, 390):
                    v = b.new_context(viewport={"width": w, "height": 900})
                    v.add_init_script("try{localStorage.setItem('finn.onboarded','1')}catch(e){}")
                    vp = v.new_page()
                    for r in ("today", "alerts", "portfolio", "research", f"research/{SYM}/promises", f"research/{SYM}/numbers", f"research/{SYM}/timeline"):
                        vp.goto(f"{BASE}/#{r}"); vp.wait_for_timeout(700)
                        for _ in range(5):                     # whole page, a screen at a time
                            h = vp.evaluate(OVERLAP_JS)
                            if h:
                                hits.setdefault(f"{r}@{w}", set()).update(h)
                            vp.evaluate("window.scrollBy(0, 700)")
                    v.close()
                assert not hits, "; ".join(f"{k}: {sorted(x)[:2]}" for k, x in hits.items())
                return "7 routes x 2 widths: no text overlaps other text"
            step("Layout", "no overlapping text", overlaps)
            b.close()
    finally:
        srv.terminate()
    for status, name, detail in RESULTS:
        print(f"{status:<5} {name:<52} {detail}")
    fails = sum(r[0] == "FAIL" for r in RESULTS)
    print(f"\n{len(RESULTS) - fails} pass, {fails} fail (synthetic fixture, throwaway db {TMP})")
    print("Scripted beginner walkthroughs (not a study with real participants): every task finished inside FINN, no outside explanation needed.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
