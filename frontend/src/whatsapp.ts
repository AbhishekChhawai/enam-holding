/** WhatsApp messages built from FINN's own fields (no model call). Share links open WhatsApp with the text filled in. */
import type { DigestItem } from "./types";

const DISCLAIMER = "Informational only, not investment advice.";
export const waLink = (text: string) => `https://wa.me/?text=${encodeURIComponent(text)}`;

export function itemMessage(it: DigestItem): string {
  const lines = [`*FINN: ${it.symbol}, ${it.category_label}*`, it.title];
  const e = it.enrichment;
  if (e?.type === "results") {
    const row = (k: string) => e.rows.find((r) => r.key === k);
    const rev = row("revenue"), pat = row("pat");
    const f = (v: number | null | undefined) => (v == null ? "n/a" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`);
    if (rev) lines.push(`Revenue ₹${rev.current?.toLocaleString("en-IN")} cr (YoY ${f(rev.yoy_pct)}, QoQ ${f(rev.qoq_pct)})`);
    if (pat) lines.push(`Net profit ₹${pat.current?.toLocaleString("en-IN")} cr (YoY ${f(pat.yoy_pct)}, QoQ ${f(pat.qoq_pct)})`);
    if (e.periods?.[0]) lines.push(`Period: ${e.periods[0]}, ${e.basis}`);
  } else if (it.summary) lines.push(it.summary);
  if (it.attachment_url) lines.push(`Filing: ${it.attachment_url}`);
  lines.push(DISCLAIMER);
  return lines.join("\n");
}

export function alertMessage(a: { symbol: string; message: string; kind: string; session_date?: string | null;
  provenance?: { url?: string | null; nearby?: { category_label: string; published_at: string }[] } | null }): string {
  const lines = [`*FINN: ${a.symbol}*`, a.message];
  const nb = a.provenance?.nearby ?? [];
  if (a.kind === "market") {
    lines.push(nb.length ? `Why now: ${nb[0].category_label} filed ${nb[0].published_at.slice(0, 10)} (context, not proof of cause).` : "Why now: no company filing around this session.");
    if (a.session_date) lines.push(`End-of-day data for ${a.session_date}.`);
  }
  if (a.provenance?.url) lines.push(`Source: ${a.provenance.url}`);
  lines.push(DISCLAIMER);
  return lines.join("\n");
}
