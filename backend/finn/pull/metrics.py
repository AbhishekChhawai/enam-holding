"""Deterministic research numbers. No model touches these: every value carries the formula and
the exact table cells it came from, so the investor can audit it in one tap."""
from __future__ import annotations

from ..sources import screener


def _last(vals: list, headers: list[str], skip_ttm: bool = True) -> tuple[int | None, float | None]:
    for i in range(len(vals) - 1, -1, -1):
        if skip_ttm and i < len(headers) and headers[i].upper().startswith("TTM"):
            continue
        if vals[i] is not None:
            return i, vals[i]
    return None, None


def _last_fy(vals: list, headers: list[str]) -> tuple[int | None, float | None]:
    """Last March (fiscal year-end) column with a value; skips half-year columns like 'Sep 2026'."""
    for i in range(len(vals) - 1, -1, -1):
        if i < len(headers) and headers[i].startswith("Mar") and vals[i] is not None:
            return i, vals[i]
    return None, None


def _cagr(a: float | None, b: float | None, years: int) -> float | None:
    if a is None or b is None or a <= 0 or b <= 0 or years <= 0:
        return None
    return round(((b / a) ** (1 / years) - 1) * 100, 1)


def _m(label: str, value, unit: str, formula: str, inputs: list[str], note: str | None = None) -> dict:
    return {"label": label, "value": value, "unit": unit, "formula": formula, "inputs": inputs, "note": note}


def _series(table: dict | None, aliases: tuple[str, ...], n: int = 8, skip_ttm: bool = True) -> dict | None:
    if not table:
        return None
    key, vals = screener.row(table, *aliases)
    if not key:
        return None
    pairs = [(h, v) for h, v in zip(table["headers"], vals) if not (skip_ttm and h.upper().startswith("TTM"))]
    pairs = pairs[-n:]
    return {"label": table["labels"].get(key, key), "periods": [p[0] for p in pairs], "values": [p[1] for p in pairs]}


def compute(company: dict) -> dict:
    t = company["tables"]
    pl, bs, cf, ratios, q = t.get("profit_loss"), t.get("balance_sheet"), t.get("cash_flow"), t.get("ratios"), t.get("quarters")
    out: dict = {"basis": company.get("basis"), "source": "screener.in", "source_url": company.get("url"),
                 "retrieved_at": company.get("retrieved_at"), "stale": bool(company.get("stale")),
                 "top_ratios": company.get("top_ratios", {}), "snapshot": [], "trajectory": [], "balance": [],
                 "cash": [], "series": {}}
    is_lender = False
    if pl:
        h = pl["headers"]
        sales_k, sales = screener.row(pl, "sales", "revenue")
        op_k, op = screener.row(pl, "operating profit", "financing profit")
        is_lender = bool(op_k and op_k.startswith("financing"))
        _, np_ = screener.row(pl, "net profit")
        i, s_last = _last(sales, h)
        if i is not None:
            fy = h[i]
            out["latest_fy"] = fy
            out["snapshot"].append(_m("Revenue", s_last, "₹ cr", "Sales for the year", [f"P&L / Sales / {fy}"]))
            if op and op[i] is not None and s_last:
                lbl = "Pre-provision margin" if is_lender else "EBITDA margin"
                out["snapshot"].append(_m(lbl, round(op[i] / s_last * 100, 1), "%",
                                          "Operating profit / Sales", [f"P&L / {pl['labels'].get(op_k, op_k)} / {fy}", f"P&L / Sales / {fy}"]))
            if np_ and np_[i] is not None:
                out["snapshot"].append(_m("PAT", np_[i], "₹ cr", "Net profit for the year", [f"P&L / Net Profit / {fy}"]))
                if s_last:
                    out["snapshot"].append(_m("PAT margin", round(np_[i] / s_last * 100, 1), "%", "Net profit / Sales",
                                              [f"P&L / Net Profit / {fy}", f"P&L / Sales / {fy}"]))
            for yrs in (3, 5):
                j = i - yrs
                if j >= 0:
                    out["trajectory"].append(_m(f"Revenue CAGR {yrs}y", _cagr(sales[j], sales[i], yrs), "%",
                                                f"(Sales {h[i]} / Sales {h[j]})^(1/{yrs}) - 1", [f"P&L / Sales / {h[j]}", f"P&L / Sales / {h[i]}"]))
                    if np_:
                        cg = _cagr(np_[j], np_[i], yrs)
                        out["trajectory"].append(_m(f"PAT CAGR {yrs}y", cg, "%",
                                                    f"(PAT {h[i]} / PAT {h[j]})^(1/{yrs}) - 1", [f"P&L / Net Profit / {h[j]}", f"P&L / Net Profit / {h[i]}"],
                                                    note="Not meaningful: a loss year in the window" if cg is None else None))
            margins = []
            for k in range(max(0, i - 5), i + 1):
                if op and sales[k] and op[k] is not None:
                    margins.append({"period": h[k], "value": round(op[k] / sales[k] * 100, 1)})
            out["series"]["margin"] = margins
            if len(margins) >= 3:
                delta = round(margins[-1]["value"] - margins[0]["value"], 1)
                out["trajectory"].append(_m("Margin change", delta, "pp", f"Margin {margins[-1]['period']} - margin {margins[0]['period']}",
                                            [f"P&L / OPM / {margins[0]['period']}", f"P&L / OPM / {margins[-1]['period']}"]))
        out["series"]["revenue"] = _series(pl, ("sales", "revenue"))
        out["series"]["pat"] = _series(pl, ("net profit",))

    if bs:
        h = bs["headers"]
        _, borrow = screener.row(bs, "borrowings", "borrowing")
        _, eqcap = screener.row(bs, "equity capital")
        _, reserves = screener.row(bs, "reserves")
        i, b_last = _last(borrow, h, skip_ttm=False)
        if i is not None:
            eq = (eqcap[i] or 0) + (reserves[i] or 0) if eqcap and reserves else None
            out["balance"].append(_m("Borrowings", b_last, "₹ cr", "Borrowings at year end", [f"Balance sheet / Borrowings / {h[i]}"]))
            if eq:
                out["balance"].append(_m("Net worth", round(eq, 1), "₹ cr", "Equity capital + Reserves",
                                         [f"Balance sheet / Equity Capital / {h[i]}", f"Balance sheet / Reserves / {h[i]}"]))
                out["balance"].append(_m("Debt / Equity", round(b_last / eq, 2), "x", "Borrowings / (Equity capital + Reserves)",
                                         [f"Balance sheet / Borrowings / {h[i]}", "Net worth"],
                                         note="Lenders borrow by design; read with capital adequacy, not alone" if is_lender else None))
            j, bj = _last_fy(borrow, h)
            if j is not None and j >= 3 and borrow[j - 3] is not None:
                out["balance"].append(_m("Borrowings change 3y", round(bj - borrow[j - 3], 1), "₹ cr",
                                         f"Borrowings {h[j]} - Borrowings {h[j-3]}", [f"Balance sheet / Borrowings / {h[j-3]}", f"Balance sheet / Borrowings / {h[j]}"]))
        out["series"]["borrowings"] = _series(bs, ("borrowings", "borrowing"), skip_ttm=False)
    if ratios:
        h = ratios["headers"]
        for aliases, label in ((("cash conversion cycle",), "Cash conversion cycle"), (("working capital days",), "Working capital days"),
                               (("debtor days",), "Debtor days"), (("inventory days",), "Inventory days"), (("roce",), "ROCE"), (("roe",), "ROE")):
            k, vals = screener.row(ratios, *aliases)
            i, v = _last(vals, h, skip_ttm=False)
            if i is not None:
                unit = "%" if label in ("ROCE", "ROE") else "days"
                tgt = out["snapshot"] if unit == "%" else out["balance"]
                prev = vals[i - 3] if i >= 3 else None
                note = f"{prev:g} three years earlier" if prev is not None else None
                tgt.append(_m(label, v, unit, f"Ratios / {ratios['labels'].get(k, k)}", [f"Ratios / {ratios['labels'].get(k, k)} / {h[i]}"], note=note))
    if cf and pl:
        h = cf["headers"]
        _, cfo = screener.row(cf, "cash from operating activity", "cash from operating")
        _, cfi = screener.row(cf, "cash from investing activity", "cash from investing")
        _, np_ = screener.row(pl, "net profit")
        pl_idx = {hh: j for j, hh in enumerate(pl["headers"])}
        conv = []
        for j, hh in enumerate(h):
            if cfo and cfo[j] is not None and hh in pl_idx and np_[pl_idx[hh]]:
                conv.append({"period": hh, "cfo": cfo[j], "pat": np_[pl_idx[hh]], "ratio": round(cfo[j] / np_[pl_idx[hh]], 2)})
        conv = conv[-6:]
        out["series"]["cash_conversion"] = conv
        if conv:
            last5 = conv[-5:]
            tot_cfo, tot_pat = sum(c["cfo"] for c in last5), sum(c["pat"] for c in last5)
            if tot_pat:
                out["cash"].append(_m(f"CFO / PAT ({len(last5)}y cumulative)", round(tot_cfo / tot_pat, 2), "x",
                                      "Sum of cash from operations / sum of net profit",
                                      [f"Cash flow / CFO / {c['period']}" for c in last5],
                                      note="Below ~0.8x for years means profits are not turning into cash"))
            out["cash"].append(_m(f"CFO / PAT ({conv[-1]['period']})", conv[-1]["ratio"], "x", "Cash from operations / net profit",
                                  [f"Cash flow / CFO / {conv[-1]['period']}", f"P&L / Net Profit / {conv[-1]['period']}"]))
        fcf_k, fcf = screener.row(cf, "free cash flow")
        if fcf_k:
            i, v = _last(fcf, h, skip_ttm=False)
            if i is not None:
                neg = sum(1 for x in fcf[max(0, i - 2):i + 1] if x is not None and x < 0)
                out["cash"].append(_m("Free cash flow", v, "₹ cr", "screener.in's Free Cash Flow row (cash from operations less capex)",
                                      [f"Cash flow / Free Cash Flow / {h[i]}"],
                                      note=f"Negative in {neg} of the last 3 years" if neg else None))
        elif cfo and cfi:
            i, _ = _last(cfo, h, skip_ttm=False)
            if i is not None and cfi[i] is not None:
                out["cash"].append(_m("CFO + CFI", round(cfo[i] + cfi[i], 1), "₹ cr", "Cash from operations + cash from investing",
                                      [f"Cash flow / CFO / {h[i]}", f"Cash flow / CFI / {h[i]}"],
                                      note="A conservative free-cash proxy: investing includes treasury moves, not only capex"))
    if q:
        out["series"]["quarterly_revenue"] = _series(q, ("sales", "revenue"), n=12, skip_ttm=False)
        out["series"]["quarterly_margin"] = _series(q, ("opm", "financing margin"), n=12, skip_ttm=False)
    out["is_lender"] = is_lender
    out["watch"], out["watch_checks"] = watch_items(out, t, is_lender)
    return out


def watch_items(m: dict, t: dict, is_lender: bool) -> tuple[list[dict], list[str]]:
    """Fixed, explainable red-flag checks. An item appears only when the inputs exist and cross the line."""
    items, checks = [], []
    ratios, bs, pl = t.get("ratios"), t.get("balance_sheet"), t.get("profit_loss")

    def ratio_rise(aliases, label, limit, unit="days"):
        k, vals = screener.row(ratios, *aliases)
        if not k:
            return
        checks.append(f"{label} up {limit}+ {unit} in 3 years")
        h = ratios["headers"]
        i, v = _last(vals, h, skip_ttm=False)
        if i is not None and i >= 3 and vals[i - 3] is not None and v - vals[i - 3] >= limit:
            items.append({"label": f"{label} rising", "detail": f"{vals[i - 3]:g} → {v:g} {unit} ({h[i - 3]} to {h[i]})",
                          "inputs": [f"Ratios / {ratios['labels'].get(k, k)} / {h[i - 3]}", f"Ratios / {ratios['labels'].get(k, k)} / {h[i]}"]})

    if not is_lender:
        ratio_rise(("debtor days",), "Receivable days", 15)
        ratio_rise(("inventory days",), "Inventory days", 20)
        ratio_rise(("cash conversion cycle",), "Cash conversion cycle", 20)
        if bs:
            _, borrow = screener.row(bs, "borrowings", "borrowing")
            _, eqc = screener.row(bs, "equity capital")
            _, res = screener.row(bs, "reserves")
            h = bs["headers"]
            i, b = _last_fy(borrow, h)
            if i is not None and i >= 3 and borrow[i - 3]:
                checks.append("Borrowings up 50%+ in 3 years and above 25% of net worth")
                nw = (eqc[i] or 0) + (res[i] or 0) if eqc and res else None
                if b / borrow[i - 3] >= 1.5 and nw and b / nw >= 0.25:
                    items.append({"label": "Leverage rising", "detail": f"Borrowings ₹{borrow[i - 3]:,.0f} cr → ₹{b:,.0f} cr ({h[i - 3]} to {h[i]}), now {b / nw:.2f}× net worth",
                                  "inputs": [f"Balance sheet / Borrowings / {h[i - 3]}", f"Balance sheet / Borrowings / {h[i]}", "Net worth"]})
        if pl:
            _, interest = screener.row(pl, "interest")
            _, pbt = screener.row(pl, "profit before tax")
            h = pl["headers"]
            i, it = _last(interest, h)
            if i is not None and it and pbt and pbt[i] is not None:
                checks.append("Interest cover below 3×")
                cover = (pbt[i] + it) / it
                if cover < 3:
                    items.append({"label": "Thin interest cover", "detail": f"(PBT + interest) / interest = {cover:.1f}× in {h[i]}",
                                  "inputs": [f"P&L / Profit before tax / {h[i]}", f"P&L / Interest / {h[i]}"]})
    conv = [x for x in m["cash"] if x["label"].startswith("CFO / PAT (") and "cumulative" in x["label"]]
    if conv:
        checks.append("Cumulative CFO / PAT below 0.7×")
        if conv[0]["value"] is not None and conv[0]["value"] < 0.7:
            items.append({"label": "Profits not turning into cash", "detail": f"{conv[0]['label']} = {conv[0]['value']:.2f}×", "inputs": conv[0]["inputs"]})
    margins = m["series"].get("margin") or []
    if len(margins) >= 3:
        checks.append("Margin down 3+ pp over the period shown")
        d = margins[-1]["value"] - margins[0]["value"]
        if d <= -3:
            items.append({"label": "Margin compression", "detail": f"{margins[0]['value']}% → {margins[-1]['value']}% ({margins[0]['period']} to {margins[-1]['period']})",
                          "inputs": [f"P&L / OPM / {margins[0]['period']}", f"P&L / OPM / {margins[-1]['period']}"]})
    return items, checks
