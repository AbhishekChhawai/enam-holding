/** Deterministic command parsing: the command bar costs nothing until the investor asks a real question. */
export type ResearchTab = "promises" | "numbers" | "timeline" | "business" | "ask";
export type Intent =
  | { kind: "window"; hours: number }
  | { kind: "research"; symbol: string; tab?: ResearchTab }
  | { kind: "ask"; symbol: string; question: string }
  | { kind: "settings" }
  | { kind: "threshold"; price?: number; volume?: number }
  | { kind: "tab"; tab: "today" | "portfolio" | "research" | "alerts" }
  | { kind: "search"; query: string }
  | { kind: "none" };

const QUESTION = /^(what|how|why|did|does|do|is|are|was|were|will|when|where|which|who|explain|compare|summari[sz]e|list|show|tell|has|have|can)\b|\?$/i;

function windowOf(t: string): number | null {
  const s = t.toLowerCase().trim();
  if (/^(today|24 ?h(ours?)?|1 ?d(ay)?|last day)$/.test(s)) return 24;
  if (/^(this|last|past) week$|^week$/.test(s)) return 168;
  if (/^(this|last|past) month$|^month$/.test(s)) return 720;
  const m = s.match(/^(?:last |past )?(\d{1,3})\s*(h|hr|hrs|hours?|d|days?|w|wk|weeks?)$/);
  if (!m) return null;
  const n = parseInt(m[1], 10);
  const u = m[2][0];
  return u === "h" ? n : u === "d" ? n * 24 : n * 168;
}

function tabFor(rest: string): ResearchTab | undefined {
  if (/promis|guid|deliver|track record|credib/i.test(rest)) return "promises";
  if (/timeline|history|events|chronolog|filings/i.test(rest)) return "timeline";
  if (/number|financ|balance|cash|debt|margin|ratio|result/i.test(rest)) return "numbers";
  if (/business|segment|bull|bear|what (do|does) they do/i.test(rest)) return "business";
  return undefined;
}

export function parseIntent(input: string, ctx: { known: string[]; current?: string | null }): Intent {
  const raw = input.trim();
  if (!raw) return { kind: "none" };
  const w = windowOf(raw);
  if (w) return { kind: "window", hours: w };

  const vol = raw.match(/vol(?:ume)?\s*(?:>|≥|above|over)?\s*(\d+(?:\.\d+)?)\s*x/i);
  const px = raw.match(/(?:price|move|moves?)\s*(?:>|≥|±|above|over)?\s*(\d+(?:\.\d+)?)\s*%/i);
  if (vol || px) return { kind: "threshold", volume: vol ? parseFloat(vol[1]) : undefined, price: px ? parseFloat(px[1]) : undefined };

  if (/^(alerts?|notifications?|inbox)$/i.test(raw)) return { kind: "tab", tab: "alerts" };
  if (/^(settings|rules?|thresholds?|preferences|prefs|cost|usage)$/i.test(raw)) return { kind: "settings" };
  if (/^(portfolio|holdings|watchlist)$/i.test(raw)) return { kind: "tab", tab: "portfolio" };
  if (/^(today|digest|feed|home)$/i.test(raw)) return { kind: "tab", tab: "today" };
  if (/^(research)$/i.test(raw)) return { kind: "tab", tab: "research" };

  const [first, ...restParts] = raw.split(/\s+/);
  const rest = restParts.join(" ");
  const cand = first.replace(/[^A-Za-z0-9&-]/g, "").toUpperCase();
  const known = new Set(ctx.known);
  const looksLikeTicker = known.has(cand) || (/^[A-Z0-9&-]{2,15}$/.test(first) && first === first.toUpperCase());

  if (cand && looksLikeTicker) {
    if (!rest) return { kind: "research", symbol: cand };
    const tab = tabFor(rest);
    if (tab && rest.split(/\s+/).length <= 3) return { kind: "research", symbol: cand, tab };
    return { kind: "ask", symbol: cand, question: rest };
  }
  if (ctx.current && (QUESTION.test(raw) || raw.split(/\s+/).length >= 4)) {
    return { kind: "ask", symbol: ctx.current, question: raw };
  }
  if (!rest && /^[A-Za-z0-9&-]{2,15}$/.test(first)) return { kind: "research", symbol: cand };
  return { kind: "search", query: raw };
}

export function describeIntent(i: Intent, names: Record<string, string>): string {
  switch (i.kind) {
    case "window": return `Show filings from the last ${i.hours >= 48 ? `${Math.round(i.hours / 24)} days` : `${i.hours} hours`}`;
    case "research": return `Open ${names[i.symbol] ?? i.symbol}${i.tab ? `, ${i.tab}` : ""}`;
    case "ask": return `Ask about ${names[i.symbol] ?? i.symbol}, answered from its own filings`;
    case "settings": return "Edit alert rules";
    case "threshold": return [i.price != null ? `Flag moves beyond ±${i.price}%` : "", i.volume != null ? `flag volume above ${i.volume}× average` : ""].filter(Boolean).join(", ");
    case "tab": return `Go to ${i.tab}`;
    case "search": return `Search companies for “${i.query}”`;
    default: return "";
  }
}
