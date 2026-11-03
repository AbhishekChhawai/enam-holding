/** Plain-English sentences built in code from the same data the Detailed view shows. No model call,
 *  so Plain and Detailed can never disagree about a fact. */
import type { Pledge, ResultsCard } from "./types";
import { crore } from "./format";

const dir = (v: number | null | undefined) =>
  v == null ? null : Math.abs(v) < 0.5 ? "about the same as" : v > 0 ? `up ${Math.abs(v).toFixed(1)}% from` : `down ${Math.abs(v).toFixed(1)}% from`;

export function resultsSentences(card: ResultsCard): string[] {
  const period = card.periods[0] || "the latest quarter";
  const row = (k: string) => card.rows.find((r) => r.key === k);
  const out: string[] = [];
  const rev = row("revenue"), pat = row("pat");
  const pick = (r: typeof rev) => (r?.yoy_pct != null ? { v: r.yoy_pct, vs: "a year earlier" } : r?.qoq_pct != null ? { v: r.qoq_pct, vs: "the previous quarter" } : null);
  if (rev?.current != null) {
    const p = pick(rev);
    out.push(`Sales were ₹${crore(rev.current)} crore in ${period}${p ? `, ${dir(p.v)} ${p.vs}` : ""}.`);
  }
  if (pat?.current != null) {
    const p = pick(pat);
    out.push(pat.current < 0
      ? `The company made a loss of ₹${crore(Math.abs(pat.current))} crore after tax.`
      : `Profit after tax was ₹${crore(pat.current)} crore${p ? `, ${dir(p.v)} ${p.vs}` : ""}.`);
  }
  const m = card.ebitda_margin;
  if (!card.is_lender && m?.[0] != null && m?.[2] != null) {
    out.push(`From every ₹100 of sales it kept ₹${m[0].toFixed(1)} as operating profit, compared with ₹${m[2].toFixed(1)} a year earlier.`);
  }
  return out;
}

const METRIC_NOUN: Record<string, string> = {
  revenue_growth: "revenue growth", revenue: "revenue", ebitda_margin: "an operating (EBITDA) margin", ebitda_growth: "operating profit growth",
  pat_growth: "profit growth", pat_margin: "a net profit margin",
};

export function pledgeSentence(g: Pledge): string {
  const noun = METRIC_NOUN[g.metric] ?? g.metric_label.toLowerCase();
  const when = g.horizon && g.horizon !== "unspecified" ? ` for ${g.horizon}` : "";
  const promised = g.target ? `Management expected ${noun} of ${g.target}${when}.` : `Management said: ${g.statement}.`;
  const a = g.actual;
  const actual = a ? `${a.unit === "₹ cr" ? `₹${crore(a.value)} crore` : `${a.value.toFixed(1)}%`}` : "";
  switch (g.verdict) {
    case "delivered":
    case "partly":
    case "missed": {
      const how = g.variance_text ? ` That is ${g.variance_text.replace(/^([+-]?)([\d.]+) pp/, (_m, s, n) => `${n} percentage points${s === "-" ? "" : ""}`)}.` : "";
      return `${promised} The company reported ${actual} for ${a?.period}.${how}`;
    }
    case "in_progress": return `${promised} So far (${a?.period}) the company has reported ${actual}; the full period isn’t over yet.`;
    case "too_early": return `${promised} That period hasn’t been reported yet, so FINN can’t judge it. Pending is not a miss.`;
    default: return `${promised} This can’t be checked against reported numbers${g.metric === "capex" || g.metric === "other" ? " (it’s about plans, plants or launches, not a figure in the accounts)" : ""}.`;
  }
}

export const VERDICT_PLAIN: Record<string, string> = {
  delivered: "Promise kept", partly: "Nearly kept", missed: "Promise missed", in_progress: "Still in progress",
  too_early: "Too early to judge", unverifiable: "Can’t be checked",
};
