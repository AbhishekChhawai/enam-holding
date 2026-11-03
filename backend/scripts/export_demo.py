"""Export the phone demo's data by running the REAL backend against fictional companies.

    cd backend && python scripts/export_demo.py      # writes frontend/src/demo/snapshot.json
    cd ../frontend && npm run build:demo              # single-file demo page

Every response is produced by FINN's own endpoints; promise verdicts and narrative checks are computed
by finn.pull.promises / finn.pull.narrative, not written by hand. All companies and figures are FICTIONAL.
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ui_journeys as U  # noqa: E402  (sets the throwaway DB env and seeds FINNDEMO)

from fastapi.testclient import TestClient  # noqa: E402

U.seed()
from finn import store  # noqa: E402
from finn.api import app  # noqa: E402
from finn.db import Announcement, Company, DocPage, Document, PriceBar, kv_get, kv_set, session_scope, utcnow  # noqa: E402
from finn.pull import narrative as N  # noqa: E402
from finn.pull import promises as P  # noqa: E402
from finn.push.digest import cluster, item_dict  # noqa: E402
from finn.quality import expected_session  # noqa: E402

SYM = U.SYM
AR_URL = "https://example.com/finndemo/annual-report-fy26.pdf"
T_DID, AR_DID = store.doc_id_for(U.T_URL), store.doc_id_for(AR_URL)
now = utcnow()

TRANSCRIPT = {
    1: "FINN Demo Industries Q1 FY27 earnings call (synthetic transcript for the FINN demo). Moderator: Good evening and welcome. " * 3,
    2: f"CFO: {U.QUOTE}, driven by new contracts in power cables. Our order book gives us good visibility for the second quarter. "
       "Analyst: What is the margin outlook? ",
    3: "CFO: We are targeting an operating margin of thirteen to fourteen percent in the second quarter as copper costs ease. "
       "MD: We will commission the new Pune plant by March 2027, which adds about thirty percent capacity. "
       "MD: For the full year FY27 we should comfortably grow revenue above twenty percent. ",
    4: "MD: Revenue growth was strong across power cables and building wires this quarter. "
       "CFO: Profit was broadly flat this quarter as we absorbed higher input costs. "
       "MD: The demand environment remains very healthy going into the festive season. ",
}
ANNUAL = {
    1: "FINN Demo Industries Limited, Annual Report FY2026 (synthetic, for the FINN demo). Business overview: the company makes power cables, "
       "building wires and offers installation services to utilities, builders and industrial customers across India.",
    2: "Segment performance FY2026: Power cables contributed 58% of revenue, building wires 30% and installation services 12%. "
       "Power cables grew fastest on state utility orders. Exports were 9% of revenue.",
    3: "Risks: copper and aluminium prices drive most of our raw-material cost, and sharp moves can compress margins. "
       "Our five largest customers account for 41% of revenue. Receivable days rose as utility payments slowed.",
    4: "Capital expenditure: the Board approved Rs 400 crore for a new plant in Pune, to be commissioned in FY27, funded from internal accruals "
       "and a term loan. Outlook: management expects demand from power transmission projects to remain strong.",
}


def scaled(company: dict, f: float, name: str, sym: str) -> dict:
    c = copy.deepcopy(company)
    c.update(name=name, symbol=sym, url=f"https://example.com/{sym.lower()}")
    for t in c["tables"].values():
        for k, vals in t["rows"].items():
            if "%" in k or "days" in k or "cycle" in k:
                continue
            t["rows"][k] = [round(v * f, 1) if isinstance(v, (int, float)) else v for v in vals]
    c["documents"] = {"annual_reports": [], "concalls": []}
    return c


def extend() -> None:
    import random
    random.seed(11)
    days, d = [], expected_session()
    while len(days) < 260:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    days.sort()
    with session_scope() as s:
        # a full year of fictional prices for FINNDEMO, plus two more fictional companies
        holdings = (  # all fictional; weights mirror the real portfolio's mix (65 / 7 / 13 / 15)
            (SYM, U.NAME, 420, 0.0011, 0.065, 3.0, "stock", "Equity", 30, "Cables & wires (synthetic)", None),
            ("ORBITAL", "Orbital Cables (synthetic)", 1240, 0.0006, -0.058, 2.6, "stock", "Equity", 20, "Power equipment (synthetic)", None),
            ("NOVAPHARMA", "Nova Pharma (synthetic)", 860, -0.0004, 0.004, 1.0, "stock", "Equity", 15, "Pharma (synthetic)", None),
            ("DEMOGOLD", "Demo Gold ETF (synthetic)", 90, 0.0012, 0.0, 1.0, "etf", "Gold", 7, "Gold (synthetic)", {"tracks": "Gold price (synthetic)"}),
            ("DEMOBOND", "Demo Gilt ETF (synthetic)", 60, 0.0002, 0.0, 1.0, "etf", "Debt", 13, "Government bonds (synthetic)", {"tracks": "Government bonds (synthetic)"}),
            ("DEMOGLOBAL", "Demo Global 100 ETF (synthetic)", 210, 0.0009, 0.021, 1.4, "etf", "International", 15, "Global technology (synthetic)",
             {"tracks": "Demo Global 100 index (synthetic)", "underlying": "^DEMOIDX", "underlying_name": "Demo Global 100"}),
        )
        for sym, name, base, drift, last, vol, kind, asset, weight, sector, meta in holdings:
            s.merge(Company(symbol=sym, name=name, sector=sector, in_portfolio=True, bse_code="999999" if sym == SYM else None,
                            kind=kind, asset_class=asset, weight=weight, meta=meta))
            p = base
            for i, day in enumerate(days):
                p *= 1 + drift + random.gauss(0, 0.012) + (last if i == len(days) - 1 else 0)
                s.merge(PriceBar(symbol=sym, date=day.isoformat(), close=round(p, 2), open=round(p, 2), high=round(p * 1.01, 2), low=round(p * 0.99, 2),
                                 volume=round(1e5 * (vol if i == len(days) - 1 else 0.8 + random.random() * 0.4)), source="synthetic-fixture"))
        p = 18000
        for i, day in enumerate(days):    # the fictional index behind the fictional global ETF
            p *= 1 + 0.0009 + random.gauss(0, 0.011) + (0.018 if i == len(days) - 1 else 0)
            s.merge(PriceBar(symbol="^DEMOIDX", date=day.isoformat(), close=round(p, 2), volume=0, source="synthetic-fixture"))
        s.merge(Announcement(id="pv-mgmt", symbol="NOVAPHARMA", published_at=now - timedelta(hours=5), headline="Appointment of Chief Financial Officer (synthetic)",
            subject="Change in Directors/ Key Managerial Personnel", category="management_change", base_score=80,
            reasons=["Management filings start at 62", "involves a top role (CEO/CFO/MD/Chair)"], attachment_url="https://example.com/novapharma/cfo.pdf", enrichment_status="ok",
            enrichment={"type": "management_change", "is_top_role": True, "people": [{"name": "A. Sharma (fictional)", "role": "Chief Financial Officer", "change": "appointed",
                "effective_date": "1 Dec 2026", "reason": None, "profile": "Chartered accountant with 20 years in finance; previously finance head at a listed manufacturer. (Synthetic profile.)",
                "previous_roles": ["Finance head, listed manufacturer"], "page": 2, "linkedin_search": "https://www.linkedin.com/search/results/people/?keywords=example"}]}))
        s.merge(Announcement(id="pv-order", symbol="ORBITAL", published_at=now - timedelta(hours=9), headline="Order win worth Rs 640 crore from a state utility (synthetic)",
            subject="Press Release", category="press_release", base_score=58, reasons=["Business update filings start at 40", "an order win with a stated value"],
            attachment_url="https://example.com/orbital/order.pdf"))
        s.merge(Announcement(id="pv-rating", symbol="ORBITAL", published_at=now - timedelta(days=2), headline="Credit rating reaffirmed at AA / Stable (synthetic)",
            subject="Credit Rating", category="credit_rating", base_score=30, reasons=["Credit rating filings start at 50", "simple reaffirmation"],
            attachment_url="https://example.com/orbital/rating.pdf"))
        s.merge(Announcement(id="pv-call", symbol=SYM, published_at=now - timedelta(days=5), headline="Transcript of the Q1 FY27 earnings call (synthetic)",
            subject="Analysts/Institutional Investor Meet/Con. Call Updates", category="earnings_call", base_score=25, reasons=["Earnings call filings start at 25"],
            attachment_url=U.T_URL))
        # documents: transcript pages with every quote used below, and an annual report
        s.merge(Document(id=T_DID, symbol=SYM, kind="transcript", title="Concall transcript, Jul 2026 (synthetic)", period="Jul 2026", url=U.T_URL, status="ok", pages=4, retrieved_at=now))
        s.merge(Document(id=AR_DID, symbol=SYM, kind="annual_report", title="Annual Report FY2026 (synthetic)", period="FY2026", url=AR_URL, status="ok", pages=4, retrieved_at=now))
        for did, pages in ((T_DID, TRANSCRIPT), (AR_DID, ANNUAL)):
            for n, txt in pages.items():
                s.merge(DocPage(doc_id=did, page=n, text=txt))
        base = kv_get(s, f"screener:{SYM}")
        base["documents"] = {"annual_reports": [{"title": "Annual Report FY2026 (synthetic)", "year": 2026, "url": AR_URL}],
                             "concalls": [{"period": "Jul 2026", "transcript": U.T_URL}]}
        kv_set(s, f"screener:{SYM}", base)
        kv_set(s, "screener:ORBITAL", scaled(base, 1.8, "Orbital Cables (synthetic)", "ORBITAL"))
        kv_set(s, "screener:NOVAPHARMA", scaled(base, 0.6, "Nova Pharma (synthetic)", "NOVAPHARMA"))

        # research results computed by FINN's own deterministic judges
        T = P.Tables(base)
        call = {"fy": 2027, "q": 1, "period": "Jul 2026", "quarter": "Q1 FY27"}
        specs = [
            ("revenue_growth", "Revenue growth of 15-17% in Q2 FY27", U.QUOTE, 2, "Q2 FY27", 15, 17, "CFO"),
            ("ebitda_margin", "Operating margin of 13-14% in Q2 FY27", "We are targeting an operating margin of thirteen to fourteen percent in the second quarter", 3, "Q2 FY27", 13, 14, "CFO"),
            ("revenue_growth", "Revenue growth above 20% for FY27", "For the full year FY27 we should comfortably grow revenue above twenty percent", 3, "FY27", 20, None, "MD"),
            ("capex", "Commission the new Pune plant by March 2027", "We will commission the new Pune plant by March 2027", 3, "FY27", None, None, "MD"),
        ]
        pledges = []
        for j, (metric, statement, quote, page, horizon, lo, hi, speaker) in enumerate(specs):
            g = {"id": f"g{j}", "metric": metric, "metric_label": P.METRIC_LABEL[metric], "statement": statement, "quote": quote, "quote_verified": True,
                 "page": page, "doc_id": T_DID, "speaker": speaker, "horizon": horizon, "target_low": lo, "target_high": hi, "unit": "%" if lo is not None else "",
                 "firmness": "explicit" if lo is not None else "soft", "call_period": "Jul 2026", "call_quarter": "Q1 FY27"}
            g["target"] = P._target_text(g)
            g.update(P.judge(g, call, T))
            g["outcome"] = P.outcome(g)
            pledges.append(g)
        judged = [g for g in pledges if g["verdict"] in ("delivered", "partly", "missed")]
        tally = {k: sum(1 for g in pledges if g["verdict"] == k) for k in ("delivered", "partly", "missed", "in_progress", "too_early", "unverifiable")}
        head = f"Delivered on {tally['delivered']} of {len(judged)} checkable promises" + (f", partly on {tally['partly']}" if tally["partly"] else "") \
            + (". Missed: " + ", ".join(sorted({g['metric_label'] for g in pledges if g['verdict'] == 'missed'})) if tally["missed"] else "")
        kv_set(s, f"promises:{SYM}", {"symbol": SYM, "status": "ok", "basis": "consolidated",
            "promises": [g for g in pledges if g["verdict"] not in ("too_early",)], "current_guidance": [g for g in pledges if g["verdict"] == "too_early"],
            "transcripts": [{"doc_id": T_DID, "period": "Jul 2026", "quarter": "Q1 FY27", "status": "ok", "pages_n": 4, "url": U.T_URL}],
            "scorecard": {**tally, "checkable": len(judged), "hit_rate": None, "headline": head}})
        ncall = {"fy": 2027, "q": 2, "period": "Oct 2026", "quarter": "Q2 FY27"}
        claims = []
        for j, (metric, direction, statement, quote, page, speaker) in enumerate([
                ("revenue", "strong", "Revenue growth was strong", "Revenue growth was strong across power cables and building wires this quarter", 4, "MD"),
                ("profit", "flat", "Profit was broadly flat", "Profit was broadly flat this quarter as we absorbed higher input costs", 4, "CFO"),
                ("demand", "strong", "Demand remains very healthy", "The demand environment remains very healthy going into the festive season", 4, "MD")]):
            c = {"id": f"n{j}", "statement": statement, "quote": quote, "page": page, "doc_id": T_DID, "speaker": speaker, "metric": metric, "direction": direction,
                 "period": "reported_quarter", "call_period": "Oct 2026", "call_quarter": "Q2 FY27", "metric_label": N.LABEL[metric]}
            c.update(N.judge(c, ncall, T))
            c["interpretation"] = N.explain(c, c["verdict"])
            claims.append(c)
        order = {"divergent": 0, "partly": 1, "supported": 2, "insufficient": 3, "not_measurable": 4}
        claims.sort(key=lambda x: order[x["verdict"]])
        nt = {k: sum(1 for x in claims if x["verdict"] == k) for k in order}
        meas = nt["supported"] + nt["partly"] + nt["divergent"]
        kv_set(s, f"narrative:{SYM}", {"symbol": SYM, "status": "ok", "basis": "consolidated", "tally": nt, "claims": claims, "transcripts": [],
            "headline": f"{nt['supported']} of {meas} measurable claims are backed by the reported numbers"
                        + (f"; {nt['divergent']} {'points' if nt['divergent'] == 1 else 'point'} the other way" if nt["divergent"] else "")})
        cite = lambda p: [{"doc_id": AR_DID, "page": p}]  # noqa: E731
        kv_set(s, f"business:{SYM}", {"status": "ok", "one_liner": "Makes power cables and building wires and installs them for utilities, builders and factories across India.",
            "segments": [{"name": "Power cables", "description": "Cables for utilities and transmission projects", "revenue_share_pct": 58, "citations": cite(2)},
                         {"name": "Building wires", "description": "Wires for homes and commercial buildings", "revenue_share_pct": 30, "citations": cite(2)},
                         {"name": "Installation services", "description": "Laying and commissioning for customers", "revenue_share_pct": 12, "citations": cite(2)}],
            "facts": [{"text": "Exports were 9% of revenue in FY2026.", "citations": cite(2), "verified": True, "unsupported_numbers": []},
                      {"text": "The five largest customers account for 41% of revenue.", "citations": cite(3), "verified": True, "unsupported_numbers": []},
                      {"text": "The Board approved Rs 400 crore for a new plant in Pune, to be commissioned in FY27.", "citations": cite(4), "verified": True, "unsupported_numbers": []}],
            "sources": [{"id": AR_DID, "title": "Annual Report FY2026 (synthetic)"}]})
        kv_set(s, f"bullbear:{SYM}", {"status": "ok",
            "bull": [{"point": "Sales grew 20% year on year in Q2 FY27, and management expects demand from transmission projects to stay strong.", "citations": cite(4), "metric_refs": ["Revenue CAGR 3y"], "verified": True},
                     {"point": "The new Pune plant adds capacity, funded mainly from internal accruals.", "citations": cite(4), "metric_refs": [], "verified": True}],
            "bear": [{"point": "Copper and aluminium prices drive most raw-material cost and can compress margins quickly.", "citations": cite(3), "metric_refs": [], "verified": True},
                     {"point": "The five largest customers are 41% of revenue, and receivable days rose as utility payments slowed.", "citations": cite(3), "metric_refs": [], "verified": True}]})


def main() -> None:
    extend()
    from export_snapshot import OUT, export          # same exporter as the real-data snapshot
    r = export(kind="fictional", allow_synthetic=True, fetch_missing=False)
    print(f"wrote {OUT} ({r['size_kb']} KB): {r['companies']} fictional companies, research for {r['research']}")


if __name__ == "__main__":
    main()
