import yaml

from finn import portfolio_analysis as PA
from finn.config import PORTFOLIO_FILE
from finn.db import Company, PriceBar, init_db, session_scope


def test_portfolio_file_has_15_to_20_real_holdings_across_asset_classes():
    cfg = yaml.safe_load(open(PORTFOLIO_FILE))
    p = cfg["portfolio"]
    assert 15 <= len(p) <= 20
    assert abs(sum(h["weight"] for h in p) - 100) < 1e-9
    classes = {h["asset_class"] for h in p}
    assert classes == {"Equity", "Debt", "Gold", "International"}
    assert {h["symbol"] for h in p if h["asset_class"] == "International"} == {"MON100", "HNGSNGBEES"}
    assert all(h.get("underlying") for h in p if h["asset_class"] == "International")
    assert cfg["mock"]["benchmark"]["symbol"] == "^NSEI"


def _seed():
    init_db()
    with session_scope() as s:
        for c in list(s.scalars(__import__("sqlalchemy").select(Company))):
            c.in_portfolio = False                       # isolate from other tests' companies
        s.merge(Company(symbol="PAEQ", name="Equity Co", sector="Banking", in_portfolio=True, kind="stock", asset_class="Equity", weight=60))
        s.merge(Company(symbol="PAUS", name="US ETF", sector="US technology", in_portfolio=True, kind="etf", asset_class="International", weight=40,
                        meta={"underlying": "^PAIDX", "underlying_name": "Test-100"}))
        rows = {"PAEQ": [("2025-12-31", 90), ("2026-01-02", 100), ("2026-01-05", 110), ("2026-01-06", 120)],
                "PAUS": [("2026-01-02", 50), ("2026-01-06", 45)],                     # no 5 Jan bar: carried forward
                "^PAIDX": [("2026-01-02", 1000), ("2026-01-05", 1010), ("2026-01-06", 990)],
                "^PANIFTY": [("2026-01-02", 200), ("2026-01-06", 210)]}
        for sym, bars in rows.items():
            for d, c in bars:
                s.merge(PriceBar(symbol=sym, date=d, close=c, volume=1, source="yfinance:NSE"))


def test_analysis_maths_from_real_closes():
    _seed()
    with session_scope() as s:
        a = PA.analyse(s, {"amount": 100000, "start": "2026-01-01", "benchmark": {"symbol": "^PANIFTY", "name": "Test Nifty"}})
    h = {r["symbol"]: r for r in a["holdings"]}
    assert h["PAEQ"]["bought_on"] == "2026-01-02" and h["PAEQ"]["avg_cost"] == 100       # first close on/after start, not 31 Dec
    assert h["PAEQ"]["quantity"] == 600 and h["PAEQ"]["current"] == 72000 and h["PAEQ"]["returns_pct"] == 20.0
    assert h["PAUS"]["current"] == 36000 and h["PAUS"]["returns_pct"] == -10.0
    assert a["invested"] == 100000 and a["current"] == 108000 and a["returns_pct"] == 8.0
    assert [g["key"] for g in a["by_asset"]] == ["Equity", "International"] and a["by_asset"][0]["name"] == "Stocks"
    assert a["benchmark"]["returns_pct"] == 5.0 and a["benchmark"]["difference_pp"] == 3.0
    # 5 Jan: equity 600*110 + US ETF carried forward at 50 -> 66000 + 40000
    assert {x["date"]: x["value"] for x in a["history"]}["2026-01-05"] == 106000
    assert h["PAUS"]["underlying"]["day_pct"] == round((990 / 1010 - 1) * 100, 2) and h["PAUS"]["underlying"]["since_start_pct"] == -1.0
    assert abs(sum(r["allocation_pct"] for r in a["holdings"]) - 100) < 0.05


def test_horizon_returns_use_sessions_and_previous_year_close():
    ds = [f"2025-12-{d:02d}" for d in (29, 30, 31)] + [f"2026-01-{d:02d}" for d in range(1, 9)]
    vs = [100, 101, 102] + [103 + i for i in range(8)]
    h = PA.horizon_returns(ds, vs)
    assert h["1W"]["pct"] == round((110 / 105 - 1) * 100, 2) and h["1W"]["from"] == ds[-6]
    assert h["YTD"]["from"] == "2025-12-31" and h["YTD"]["pct"] == round((110 / 102 - 1) * 100, 2)   # from last close of 2025
    assert h["1M"] is None and h["1Y"] is None                                                       # not enough history: never guessed


def test_analysis_carries_horizons():
    _seed()
    with session_scope() as s:
        a = PA.analyse(s, {"amount": 100000, "start": "2026-01-01", "benchmark": {"symbol": "^PANIFTY", "name": "Test Nifty"}})
    assert a["horizons"]["order"] == ["1W", "1M", "3M", "6M", "YTD", "1Y"]
    assert set(a["horizons"]["by_asset"]) == {"Equity", "International"}
    assert "horizons" in a["holdings"][0] and "horizons" in a["benchmark"]
