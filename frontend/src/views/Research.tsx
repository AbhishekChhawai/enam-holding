import { useEffect, useMemo, useState, type ReactNode } from "react";
import { DEMO, api, useApi } from "../api";
import type { Answer, BullBear, Business, Gate, Metric, NarrativeReport, Overview, Pledge, PromiseReport, Series, Verdict } from "../types";
import type { ResearchTab } from "../intent";
import type { Handoff } from "../App";
import { ago, metricValue, pct, price, signClass } from "../format";
import { ResultsTable } from "../components/Feed";
import PriceChart from "../components/PriceChart";
import { LabelTerm, Term } from "../components/Explain";
import { GLOSSARY, keyForLabel } from "../glossary";
import { VERDICT_PLAIN, pledgeSentence } from "../plain";
import { Avatar, CiteChip, Loading, Notice, SectionHead, Sheet, VerdictChip, useUI, verdictMeta } from "../components/ui";
import { IngestBanner, QualityView, TimelineTab, freshnessLine, useIngest, useQuality } from "./Insight";

const TABS: { key: ResearchTab; label: string }[] = [
  { key: "promises", label: "Promises" }, { key: "numbers", label: "Numbers" }, { key: "timeline", label: "Timeline" },
  { key: "business", label: "Business" }, { key: "ask", label: "Ask" },
];

/** Opening a screen never spends model calls: uncached analyses wait for an explicit tap. */
function RunGate({ data, label, onRun, children }: { data: Gate | null; label: string; onRun: () => void; children: ReactNode }) {
  if (data?.status === "not_run") {
    return (
      <div className="mt-4 rounded-2xl border border-line bg-surface px-4 py-4">
        <p className="text-[14px] text-muted">{data.note}</p>
        {!(data as Gate & { demo_locked?: boolean }).demo_locked && <button onClick={onRun} className="mt-3 min-h-[40px] rounded-full bg-ink px-4 text-[14px] text-paper">{label}</button>}
      </div>
    );
  }
  return (
    <>
      {data?.stale && data.cached_at && (
        <p className="mt-3 text-[12px] text-muted">From {ago(data.cached_at)}. <button onClick={onRun} className="underline decoration-line underline-offset-2">Refresh</button></p>
      )}
      {children}
    </>
  );
}

interface CompanyInfo { kind?: string; asset_class?: string; name?: string; sector?: string; meta?: { tracks?: string; note?: string; underlying_name?: string } }

/** Funds don't publish results or hold earnings calls, so an ETF page shows what it tracks and how it moved. */
function EtfView({ symbol, info }: { symbol: string; info: CompanyInfo }) {
  const an = useApi<{ holdings?: { symbol: string; current: number; returns_pct: number | null; horizons?: Record<string, { pct: number | null } | null>;
    underlying?: { name: string; day_pct: number | null; since_start_pct: number | null; last_date: string } }[] }>("/api/portfolio/analysis");
  const h = an.data?.holdings?.find((x) => x.symbol === symbol);
  const stock = info.kind !== "etf";
  const label = stock ? (info.sector || "Stock") : info.asset_class === "International" ? "International ETF" : info.asset_class === "Debt" ? "Debt ETF" : info.asset_class === "Gold" ? "Gold ETF" : "ETF";
  return (
    <div>
      <section className="navy rise rounded-[28px] px-5 pb-4 pt-4">
        <div className="flex items-start gap-3">
          <Avatar symbol={symbol} size={44} />
          <div className="min-w-0"><div className="text-[12.5px] text-muted">{symbol}, {label}</div><h1 className="display text-[19px] font-bold leading-tight">{info.name ?? symbol}</h1></div>
        </div>
        {info.meta?.tracks && <p className="mt-3 text-[14px]">Tracks: <b>{info.meta.tracks}</b></p>}
        {h?.underlying && (
          <div className="mt-2 flex flex-wrap gap-1.5 num">
            <span className={`chip ${signClass(h.underlying.day_pct)}`}>{h.underlying.name} {pct(h.underlying.day_pct)} on {h.underlying.last_date}</span>
            <span className={`chip ${signClass(h.underlying.since_start_pct)}`}>{h.underlying.name} {pct(h.underlying.since_start_pct)} since bought</span>
            <span className={`chip ${signClass(h.returns_pct)}`}>This ETF {pct(h.returns_pct)} since bought</span>
          </div>
        )}
        {h?.horizons && (
          <div className="mt-3 grid grid-cols-3 gap-1.5 num">
            {["1W", "1M", "3M", "6M", "YTD", "1Y"].map((k) => (
              <div key={k} className="rounded-xl bg-wash px-2.5 py-1.5">
                <div className="text-[11px] text-muted">{k}</div>
                <div className={`text-[15px] font-bold ${signClass(h.horizons?.[k]?.pct)}`}>{h.horizons?.[k]?.pct != null ? pct(h.horizons[k]!.pct) : "–"}</div>
              </div>
            ))}
          </div>
        )}
        {info.meta?.note && <p className="mt-2 text-[12px] text-muted">{info.meta.note}</p>}
      </section>
      <SectionHead title="Price" note="end of day, in ₹" />
      <PriceChart symbol={symbol} />
      <p className="mt-4 text-[13px] text-muted">
        {stock ? "Results, filings and AI research for this company aren’t in this snapshot; FINN’s daily run adds them. Price, volume and alerts here are real end-of-day data."
          : <>Funds don’t publish quarterly results or hold earnings calls, so FINN tracks this ETF’s price and volume (alerts work as for stocks)
          {h?.underlying ? ` and compares it with the ${h.underlying.name}, the index it follows. The gap between the two reflects currency moves, fees and timing` : ""}.</>}
      </p>
    </div>
  );
}

export default function Research({ symbol, tab, setTab, pendingQuestion, clearPending, suggestions, portfolio, handoff, clearHandoff, askHandoff, backToEvent }: {
  symbol: string | null; tab: ResearchTab; setTab: (t: ResearchTab) => void;
  pendingQuestion: string | null; clearPending: () => void; suggestions: Co[]; portfolio: Co[];
  handoff: Handoff | null; clearHandoff: () => void; askHandoff: (q: string) => void; backToEvent: (id: string) => void;
}) {
  if (!symbol) return <Landing suggestions={suggestions} portfolio={portfolio} />;
  return (
    <>
      {handoff && (
        <div className="mb-4 rounded-2xl border border-marigold bg-marigold-wash px-4 py-3 text-[14px]">
          <div className="flex items-start gap-2">
            <p className="min-w-0 flex-1"><span className="text-muted">From the filing: </span>{handoff.category_label}{handoff.reporting_period ? `, ${handoff.reporting_period}` : ""}. {handoff.headline}</p>
            <button onClick={clearHandoff} aria-label="Dismiss" className="text-muted">✕</button>
          </div>
          <p className="mt-1.5 font-medium">{handoff.suggested_question}</p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <button onClick={() => askHandoff(handoff.suggested_question)} className="rounded-full bg-ink px-3.5 py-1.5 text-paper">Ask this</button>
            <button onClick={() => backToEvent(handoff.event_id)} className="rounded-full border border-ink px-3.5 py-1.5">Back to the filing</button>
            <span className="text-[12px] text-muted">{1 + handoff.related_filing_ids.length} filings, {handoff.document_ids.length} documents in context</span>
          </div>
        </div>
      )}
      <CompanyOrEtf key={symbol} symbol={symbol} tab={tab} setTab={setTab} pendingQuestion={pendingQuestion} clearPending={clearPending} />
    </>
  );
}

const RECENT_KEY = "finn.recent";
type Co = { symbol: string; name: string };
function readRecent(): Co[] {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]"); } catch { return []; }
}
function rememberRecent(symbol: string, name: string) {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify([{ symbol, name }, ...readRecent().filter((r) => r.symbol !== symbol)].slice(0, 6))); } catch { /* private mode */ }
}

function Landing({ suggestions, portfolio }: { suggestions: Co[]; portfolio: Co[] }) {
  const ui = useUI();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<(Co & { in_portfolio?: boolean })[] | null>(null);
  const recent = readRecent();
  useEffect(() => {
    const t = q.trim();
    if (t.length < 2) { setHits(null); return; }
    const id = setTimeout(() => { api<(Co & { in_portfolio?: boolean })[]>(`/api/search?q=${encodeURIComponent(t)}`).then(setHits).catch(() => setHits([])); }, 250);
    return () => clearTimeout(id);
  }, [q]);
  const go = (sym: string) => ui.openResearch(sym.trim().toUpperCase().replace(/\.(NS|BO)$/, ""), "promises");
  return (
    <div>
      <h1 className="display mt-2 text-[26px] font-semibold leading-[1.1]">Research any NSE company</h1>
      <p className="mt-1 max-w-[34em] text-[14px] text-muted">
        FINN reads the company’s own annual report and concall transcripts, checks what management promised
        against what it reported, and cites the page for every claim.
      </p>
      <form className="mt-4" onSubmit={(e) => { e.preventDefault(); if (hits?.[0]) go(hits[0].symbol); else if (q.trim()) go(q); }}>
        <label className="sr-only" htmlFor="co-search">Company name or NSE symbol</label>
        <input id="co-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Company name or NSE symbol" autoComplete="off"
          className="w-full rounded-xl border border-line bg-surface px-4 py-2.5 text-[15px] placeholder:text-muted" />
      </form>
      {hits && (
        <ul className="mt-2 rounded-2xl bg-surface px-4" aria-label="Search results">
          {hits.length === 0 && <li className="py-2.5 text-[14px] text-muted">No match. Try the exact NSE symbol and press Enter.</li>}
          {hits.slice(0, 6).map((h) => (
            <li key={h.symbol} className="border-t border-line first:border-t-0">
              <button onClick={() => go(h.symbol)} className="flex w-full items-baseline gap-2 py-2.5 text-left">
                <span className="display-tight text-[15px] font-semibold tracking-wide">{h.symbol}</span>
                <span className="min-w-0 flex-1 truncate text-[13px] text-muted">{h.name}</span>
                {h.in_portfolio && <span className="shrink-0 text-[12px] text-muted">in portfolio</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {recent.length > 0 && (<><SectionHead title="Recent" /><div className="flex flex-wrap gap-2">{recent.map((s) => <OpenChip key={s.symbol} symbol={s.symbol} name={s.name} />)}</div></>)}
      <SectionHead title="Precomputed for the demo" />
      <div className="flex flex-wrap gap-2">
        {suggestions.map((s) => <OpenChip key={s.symbol} symbol={s.symbol} name={s.name} />)}
      </div>
      {portfolio.length > 0 && (<><SectionHead title="Your portfolio" /><div className="flex flex-wrap gap-2">{portfolio.map((s) => <OpenChip key={s.symbol} symbol={s.symbol} name={s.name} />)}</div></>)}
    </div>
  );
}

function OpenChip({ symbol, name }: { symbol: string; name: string }) {
  const ui = useUI();
  return (
    <button onClick={() => ui.openResearch(symbol, "promises")} className="rounded-full border border-line bg-surface px-3 py-1.5 text-left">
      <span className="display-tight text-[15px] font-semibold tracking-wide">{symbol}</span>
      <span className="ml-1.5 text-[13px] text-muted">{name}</span>
    </button>
  );
}

function CompanyOrEtf(props: { symbol: string; tab: ResearchTab; setTab: (t: ResearchTab) => void; pendingQuestion: string | null; clearPending: () => void }) {
  const info = useApi<CompanyInfo>(`/api/companies/${props.symbol}`);
  // a snapshot without research for this company still shows its real prices and horizon returns
  const [ovOk, setOvOk] = useState<boolean | null>(DEMO ? null : true);
  useEffect(() => { if (DEMO) api(`/api/research/${props.symbol}/overview`).then(() => setOvOk(true)).catch(() => setOvOk(false)); }, [props.symbol]);
  if ((info.loading && !info.data && !info.error) || ovOk === null) return <Loading text="Opening" />;
  if (info.data && (info.data.kind === "etf" || ovOk === false)) return <EtfView symbol={props.symbol} info={info.data} />;
  return <Company {...props} />;
}

function Company({ symbol, tab, setTab, pendingQuestion, clearPending }: {
  symbol: string; tab: ResearchTab; setTab: (t: ResearchTab) => void; pendingQuestion: string | null; clearPending: () => void;
}) {
  const ov = useApi<Overview>(`/api/research/${symbol}/overview`);
  const [runPr, setRunPr] = useState(false);
  const pr = useApi<PromiseReport>(`/api/research/${symbol}/promises${runPr ? "?run=true" : ""}`);
  const [rk, setRk] = useState(0);  // bumps after a first-time ingestion completes
  const job = useIngest(symbol, () => { ov.reload(); setRk((k) => k + 1); });
  const q = useQuality(symbol, rk);
  const fresh = freshnessLine(q.data);
  useEffect(() => { if (ov.data) rememberRecent(symbol, ov.data.name); }, [ov.data, symbol]);
  const [showQ, setShowQ] = useState(false);
  const docLabel = useMemo(() => {
    const m: Record<string, string> = {};
    ov.data?.documents.concalls.forEach((c) => { if (c.doc_id) m[c.doc_id] = `${c.period} call`; });
    ov.data?.documents.annual_reports.forEach((a) => { m[a.doc_id] = `AR ${a.year ?? ""}`.trim(); });
    pr.data?.transcripts.forEach((t) => { m[t.doc_id] = `${t.period} call`; });
    return (id: string) => m[id] ?? "Source";
  }, [ov.data, pr.data]);

  const p = ov.data?.price;
  return (
    <div>
      <section className="navy rise rounded-[28px] px-5 pb-4 pt-4">
        <div className="flex items-start gap-3">
          <Avatar symbol={symbol} size={44} />
          <div className="min-w-0 flex-1">
            <div className="text-[12.5px] text-muted">{symbol}{ov.data?.in_portfolio ? ", in your portfolio" : ""}</div>
            <h1 className="display text-[19px] font-bold leading-tight sm:text-[22px]">{ov.data?.name ?? (ov.error ? symbol : "Loading…")}</h1>
          </div>
        </div>
        {p && (
          <div className="mt-3 flex flex-wrap items-end gap-x-3 gap-y-1.5 num">
            <span className="display text-[34px] font-extrabold leading-none">{price(p.close)}</span>
            <span className={`chip font-semibold ${signClass(p.pct)}`}>{pct(p.pct)} day</span>
            {p.pct_1y != null && <span className={`chip ${signClass(p.pct_1y)}`}>{pct(p.pct_1y)} 1y</span>}
          </div>
        )}
        <p className="mt-1.5 text-[11.5px] text-muted">Last close, end-of-day data. Not live.</p>
      </section>
      {fresh && (
        <button onClick={() => setShowQ(true)} className={`mt-1 min-h-[32px] text-left text-[12px] underline decoration-line underline-offset-2 ${fresh.warn ? "text-down" : "text-muted"}`}>
          {fresh.warn ? "Data check needs attention. " : ""}{fresh.text}
        </button>
      )}
      <IngestBanner symbol={symbol} job={job} />
      <Sheet open={showQ && !!q.data} onClose={() => setShowQ(false)} title={<div className="display text-[18px] font-semibold">Data behind {symbol}</div>}>
        {q.data && <QualityView q={q.data} />}
      </Sheet>
      {ov.error && <div className="mt-3"><Notice tone="warn">{ov.error.includes("No screener") ? `No public financials found for ${symbol}. Check the NSE symbol.` : ov.error}</Notice></div>}

      <nav className="sticky top-0 z-20 -mx-4 mt-3 bg-paper/85 px-4 py-2 backdrop-blur-md" aria-label="Research sections">
        <div className="flex gap-4 overflow-x-auto border-b border-line scrollbar-none">
          {TABS.map((t) => (
            <button key={t.key} onClick={() => setTab(t.key)} aria-current={tab === t.key}
              className={`-mb-px shrink-0 border-b-2 pb-2 text-[15px] ${tab === t.key ? "border-marigold text-ink font-medium" : "border-transparent text-muted"}`}>
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      {tab === "promises" && (
        <RunGate data={pr.data} label="Run promise check" onRun={() => setRunPr(true)}>
          <PromisesTab state={pr} docLabel={docLabel} />
          <NarrativeSection symbol={symbol} docLabel={docLabel} />
        </RunGate>
      )}
      {tab === "numbers" && (ov.data ? <NumbersTab ov={ov.data} /> : !ov.error && <Loading text="Reading reported financials" />)}
      {tab === "timeline" && <TimelineTab symbol={symbol} refreshKey={rk} />}
      {tab === "business" && <BusinessTab symbol={symbol} ov={ov.data} docLabel={docLabel} />}
      {tab === "ask" && <AskTab symbol={symbol} docLabel={docLabel} pending={pendingQuestion} clearPending={clearPending} />}
    </div>
  );
}

/* ------------------------------------------------------------------ promises */
function PromisesTab({ state, docLabel }: { state: ReturnType<typeof useApi<PromiseReport>>; docLabel: (id: string) => string }) {
  const { data, error, loading } = state;
  if (loading && !data) return <Loading text="Reading the last five concall transcripts and checking each promise against reported numbers. First run takes about a minute." />;
  if (error) return <div className="mt-4"><Notice tone="warn">{error}</Notice></div>;
  if (!data || data.status === "not_run") return null;
  if (data.status === "llm_disabled") return <div className="mt-4"><Notice>Promise tracking needs a Gemini key on the server. Numbers and filings still work.</Notice></div>;
  const sc = data.scorecard;
  const okTranscripts = data.transcripts.filter((t) => t.status === "ok").length;
  return (
    <div className="mt-4">
      {sc?.headline ? (
        <>
          <p className="display text-[21px] font-semibold leading-snug">{sc.headline}.</p>
          <VerdictBar sc={sc} />
        </>
      ) : (
        <Notice>No checkable numeric promises found in the transcripts read{data.promises.length ? "; see the commitments below" : ""}.</Notice>
      )}
      <p className="mt-2 text-[13px] text-muted">
        FINN reads what management promised on past <Term k="concall">earnings calls</Term> (their <Term k="guidance">guidance</Term>) and checks it against the results the company later reported.
        From {okTranscripts} of {data.transcripts.length} transcripts ({data.transcripts.map((t) => t.quarter).join(", ")}).
        Verdicts on numbers are computed from reported {data.basis ?? ""} results, not by the model.
      </p>
      {data.promises.length > 0 && (
        <>
          <SectionHead title="Promised vs delivered" note={data.promises.length} />
          <div className="rounded-2xl bg-surface px-4">
            {sortPledges(data.promises).map((g) => <PledgeRow key={g.id} g={g} docLabel={docLabel} />)}
          </div>
        </>
      )}
      {data.current_guidance.length > 0 && (
        <>
          <SectionHead title="Current guidance" note={data.current_guidance[0].call_period + " call"} />
          <div className="rounded-2xl bg-surface px-4">
            {data.current_guidance.map((g) => <PledgeRow key={g.id} g={g} docLabel={docLabel} />)}
          </div>
        </>
      )}
      {data.transcripts.some((t) => t.status !== "ok") && (
        <p className="mt-3 text-[12px] text-muted">
          Unreadable: {data.transcripts.filter((t) => t.status !== "ok").map((t) => `${t.period} (${t.status})`).join(", ")}.
        </p>
      )}
    </div>
  );
}

const ORDER: Verdict[] = ["missed", "partly", "delivered", "in_progress", "too_early", "unverifiable"];
const sortPledges = (xs: Pledge[]) => [...xs].sort((a, b) => ORDER.indexOf(a.verdict) - ORDER.indexOf(b.verdict));

function VerdictBar({ sc }: { sc: NonNullable<PromiseReport["scorecard"]> }) {
  const parts = (["delivered", "partly", "missed", "in_progress", "too_early", "unverifiable"] as Verdict[]).filter((k) => sc[k] > 0);
  const total = parts.reduce((s, k) => s + sc[k], 0) || 1;
  const color: Record<Verdict, string> = {
    delivered: "var(--up)", partly: "var(--marigold)", missed: "var(--down)",
    in_progress: "var(--muted)", too_early: "var(--line)", unverifiable: "var(--wash)",
  };
  return (
    <div className="mt-3">
      <div className="flex h-2.5 overflow-hidden rounded-full">
        {parts.map((k) => <div key={k} style={{ width: `${(sc[k] / total) * 100}%`, background: color[k] }} />)}
      </div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[12px] text-muted num">
        {parts.map((k) => <span key={k}>{verdictMeta(k).label} {sc[k]}</span>)}
      </div>
    </div>
  );
}

function PledgeRow({ g, docLabel }: { g: Pledge; docLabel: (id: string) => string }) {
  const ui = useUI();
  const [open, setOpen] = useState(false);
  if (ui.plain) {
    const tone = g.outcome === "exceeded" || g.verdict === "delivered" ? "bg-up-wash text-up" : g.verdict === "missed" ? "bg-down-wash text-down" : g.verdict === "partly" ? "bg-marigold-wash text-ink" : "border border-line text-muted";
    return (
      <div className="border-t border-line py-3 first:border-t-0">
        <span className={`inline-flex rounded-full px-2 py-0.5 text-[12px] font-medium ${tone}`}>{g.outcome === "exceeded" ? "Promise beaten" : VERDICT_PLAIN[g.verdict]}</span>
        <p className="mt-1.5 text-[15px] leading-snug num">{pledgeSentence(g)}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[13px]">
          <span className="text-muted">Check it:</span>
          <CiteChip c={{ doc_id: g.doc_id, page: g.page }} label={`What was said, ${docLabel(g.doc_id)}`} quote={g.quote} />
          {g.actual?.source_url && <a href={g.actual.source_url} target="_blank" rel="noreferrer" className="inline-flex min-h-[32px] items-center rounded-md border border-line px-2 text-[12px] text-muted">What was reported</a>}
        </div>
      </div>
    );
  }
  return (
    <div className="border-t border-line py-3 first:border-t-0">
      <button onClick={() => setOpen((v) => !v)} className="block w-full text-left" aria-expanded={open}>
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <div className="text-[13px] text-muted">
              {g.metric_label}{g.target ? `, target ${g.target}` : ""}{g.horizon && g.horizon !== "unspecified" ? `, ${g.horizon}` : ""}
            </div>
            <p className="mt-0.5 text-[15px] leading-snug">{g.statement}</p>
          </div>
          {g.outcome === "exceeded"
            ? <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-up-wash px-2 py-0.5 text-[12px] font-medium text-up"><span aria-hidden="true">▲</span>Exceeded</span>
            : <VerdictChip v={g.verdict} />}
        </div>
        {g.actual && (
          <p className="mt-1 text-[14px] num">
            Reported <span className="font-semibold">{metricValue(g.actual.value, g.actual.unit === "₹ cr" ? "₹ cr" : "%")}</span>
            <span className="text-muted"> for {g.actual.period}{g.variance_text ? `, ${g.variance_text}` : ""}</span>
          </p>
        )}
      </button>
      {open && (
        <div className="mt-2 space-y-2 text-[14px]">
          <blockquote className="border-l-2 border-marigold pl-3 italic leading-snug">“{g.quote}”</blockquote>
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
            <CiteChip c={{ doc_id: g.doc_id, page: g.page }} label={docLabel(g.doc_id)} quote={g.quote} />
            {g.speaker && <span>{g.speaker}</span>}
            {!g.quote_verified && <span className="text-down">Quote not found verbatim on that page</span>}
          </div>
          {g.explanation && <p className="text-muted">{g.explanation}.</p>}
          {g.actual && (
            <p className="text-[12px] text-muted">
              How: {g.actual.formula}. Inputs: {g.actual.inputs.join("; ")}.{" "}
              {g.actual.source_url && <a href={g.actual.source_url} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2">Open results filing</a>}
            </p>
          )}
          {g.evidence?.map((e, i) => (
            <div key={i} className="rounded-lg bg-wash px-3 py-2">
              <p className="italic leading-snug">“{e.quote}”</p>
              <div className="mt-1"><CiteChip c={{ doc_id: e.doc_id, page: e.page }} label={docLabel(e.doc_id)} quote={e.quote} /></div>
            </div>
          ))}
          <p className="text-[12px] text-muted">Said on the {g.call_period} call ({g.call_quarter}). Judged by {g.judged_by === "numbers" ? "reported numbers" : g.judged_by === "transcript" ? "later transcripts" : "no source yet"}.</p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ narrative */
const NV: Record<NarrativeClaim["verdict"], { label: string; cls: string }> = {
  supported: { label: "Backed by numbers", cls: "bg-up-wash text-up" },
  partly: { label: "Partly backed", cls: "bg-marigold-wash text-ink" },
  divergent: { label: "Numbers diverge", cls: "bg-down-wash text-down" },
  not_measurable: { label: "Not measurable", cls: "border border-line text-muted" },
  insufficient: { label: "No data to check", cls: "border border-dashed border-line text-muted" },
};
type NarrativeClaim = NonNullable<NarrativeReport["claims"]>[number];

function NarrativeSection({ symbol, docLabel }: { symbol: string; docLabel: (id: string) => string }) {
  const [run, setRun] = useState(false);
  const { data, error, loading } = useApi<NarrativeReport>(`/api/research/${symbol}/narrative${run ? "?run=true" : ""}`);
  return (
    <section>
      <SectionHead title="Narrative vs numbers" />
      <p className="-mt-1 mb-2 text-[13px] text-muted">How management described the results, checked against what was reported. A divergence is a question to ask, not a verdict on honesty.</p>
      {loading && !data && <Loading text="Reading the last two earnings calls" />}
      {error && <Notice tone="warn">{error}</Notice>}
      <RunGate data={data} label="Check management’s claims" onRun={() => setRun(true)}>
        {data?.status === "llm_disabled" && <Notice>Needs a Gemini key on the server.</Notice>}
        {data?.status === "ok" && (
          <>
            {data.headline && <p className="mb-2 text-[15px] font-medium">{data.headline}.</p>}
            {!data.claims?.length && <Notice>No verifiable descriptive claims found in the calls read.</Notice>}
            <div className="space-y-3">
              {data.claims?.map((c) => (
                <div key={c.id} className="rounded-2xl bg-surface px-4 py-3">
                  <div className="flex items-start gap-2">
                    <p className="min-w-0 flex-1 text-[13px] text-muted">{c.call_quarter} call{c.speaker ? `, ${c.speaker}` : ""}</p>
                    <span className={`shrink-0 rounded-full px-2 py-0.5 text-[12px] font-medium ${NV[c.verdict].cls}`}>{NV[c.verdict].label}</span>
                  </div>
                  <p className="mt-1.5 text-[12px] font-medium text-muted">What management said</p>
                  <blockquote className="border-l-2 border-marigold pl-3 text-[14px] italic leading-snug">“{c.quote}”</blockquote>
                  <div className="mt-1"><CiteChip c={{ doc_id: c.doc_id, page: c.page }} label={docLabel(c.doc_id)} quote={c.quote} /></div>
                  {c.numbers && (
                    <>
                      <p className="mt-2 text-[12px] font-medium text-muted">What the numbers show</p>
                      <p className="text-[14px] num">{c.numbers.text}</p>
                      <p className="text-[12px] text-muted">
                        {c.numbers.formula}.{" "}
                        {c.numbers.source_url && <a href={c.numbers.source_url} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2">Open results filing</a>}
                      </p>
                    </>
                  )}
                  <p className="mt-2 text-[13px] leading-snug">{c.interpretation}</p>
                </div>
              ))}
            </div>
          </>
        )}
      </RunGate>
    </section>
  );
}

/* ------------------------------------------------------------------ numbers */
function NumbersTab({ ov }: { ov: Overview }) {
  const m = ov.metrics;
  return (
    <div className="mt-4">
      {m.stale && <Notice tone="warn">Showing the last saved copy; the live source didn’t respond.</Notice>}
      <SectionHead title="Price" note="end of day" />
      <PriceChart symbol={ov.symbol} />
      {m.watch && (
        <section>
          <SectionHead title="Watch items" note={m.watch.length ? m.watch.length : undefined} />
          {m.watch.length ? (
            <ul className="space-y-2 rounded-2xl bg-marigold-wash px-4 py-3">
              {m.watch.map((w) => (
                <li key={w.label} className="text-[14px] leading-snug"><span className="font-medium">{w.label}.</span> <span className="num">{w.detail}</span>
                  <span className="block text-[12px] text-muted">From: {w.inputs.join("; ")}</span></li>
              ))}
            </ul>
          ) : (
            <p className="text-[13px] text-muted">None flagged. Checked: {(m.watch_checks ?? []).join("; ").toLowerCase() || "no inputs available"}.</p>
          )}
        </section>
      )}
      {ov.results && (
        <>
          <SectionHead title="Latest quarter" note={ov.results.periods[0]} />
          <ResultsTable card={ov.results} />
        </>
      )}
      <QuarterChart rev={m.series.quarterly_revenue} margin={m.series.quarterly_margin} lender={m.is_lender} />
      <MetricGroup title="Snapshot" note={m.latest_fy} items={m.snapshot} />
      <MetricGroup title="Trajectory" items={m.trajectory} />
      <MetricGroup title="Balance sheet" items={m.balance} />
      <MetricGroup title="Cash quality" items={m.cash} />
      {m.series.cash_conversion && m.series.cash_conversion.length > 0 && (
        <div className="mt-2 grid grid-cols-6 gap-1 text-center text-[11px] text-muted num">
          {m.series.cash_conversion.map((c) => (
            <div key={c.period}>
              <div className="mx-auto mb-1 w-full rounded-sm" style={{ height: 36 * Math.min(1.5, Math.max(0.05, c.ratio)) / 1.5, background: c.ratio >= 0.8 ? "var(--up)" : "var(--down)", opacity: 0.75 }} />
              {c.ratio.toFixed(2)}×<br />{c.period.replace("Mar ", "FY")}
            </div>
          ))}
        </div>
      )}
      <p className="mt-6 text-[12px] text-muted">
        {m.basis} figures from {m.source}, read {m.retrieved_at?.slice(0, 10)}. Every value is computed in code; tap a row for the formula and cells.
      </p>
    </div>
  );
}

function MetricGroup({ title, items, note }: { title: string; items: Metric[]; note?: string }) {
  const ui = useUI();
  const [open, setOpen] = useState<string | null>(null);
  if (!items?.length) return null;
  return (
    <section>
      <SectionHead title={title} note={note} />
      <div className="rounded-2xl bg-surface px-4">
        {items.map((x) => (
          <div key={x.label} className="border-t border-line first:border-t-0">
            <div className="flex w-full items-baseline justify-between gap-3 py-2.5">
              <span className="min-w-0 text-[14px]">
                <LabelTerm label={x.label} />
                {ui.plain && keyForLabel(x.label) && <span className="block text-[12px] text-muted">{GLOSSARY[keyForLabel(x.label)!].simple}</span>}
              </span>
              <button onClick={() => setOpen(open === x.label ? null : x.label)} aria-expanded={open === x.label} aria-label={`${x.label}: show how it was calculated`}
                className="min-h-[32px] shrink-0 text-[15px] font-medium num">{metricValue(x.value, x.unit)}</button>
            </div>
            {(open === x.label || x.note) && (
              <div className="-mt-1 pb-2.5 text-[12px] text-muted">
                {x.note && <p>{x.note}</p>}
                {open === x.label && <p>{x.formula}. From: {x.inputs.join("; ")}</p>}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function QuarterChart({ rev, margin, lender }: { rev?: Series | null; margin?: Series | null; lender: boolean }) {
  if (!rev || rev.values.filter((v) => v != null).length < 3) return null;
  const W = 340, H = 120, pad = 18;
  const vals = rev.values.map((v) => v ?? 0);
  const max = Math.max(...vals) || 1;
  const bw = (W - pad) / vals.length;
  const mv = margin?.values ?? [];
  const mmax = Math.max(...mv.map((v) => v ?? 0), 1), mmin = Math.min(...mv.filter((v) => v != null).map((v) => v as number), 0);
  const my = (v: number) => 8 + (1 - (v - mmin) / (mmax - mmin || 1)) * (H - 40);
  const line = mv.map((v, i) => (v == null ? "" : `${i === 0 || mv[i - 1] == null ? "M" : "L"}${(i + 0.5) * bw},${my(v).toFixed(1)}`)).join(" ");
  return (
    <section>
      <SectionHead title="Quarterly revenue" note={margin && !lender ? "bars, with margin line" : undefined} />
      <div className="rounded-2xl bg-surface px-3 py-3">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Quarterly revenue bars with operating margin line">
          {vals.map((v, i) => {
            const h = (v / max) * (H - 30);
            return <rect key={i} x={i * bw + 2} y={H - 18 - h} width={bw - 4} height={h} rx="2" fill={i === vals.length - 1 ? "var(--ink)" : "var(--muted)"} opacity={i === vals.length - 1 ? 0.9 : 0.35} />;
          })}
          {margin && !lender && <path d={line} fill="none" stroke="var(--marigold)" strokeWidth="2" />}
          {rev.periods.map((p, i) => (i % 3 === vals.length % 3 || i === vals.length - 1) && (
            <text key={p} x={i * bw + bw / 2} y={H - 4} textAnchor="middle" fontSize="9" fill="var(--muted)">{p.replace(/ 20(\d\d)/, " ’$1")}</text>
          ))}
        </svg>
        {margin && !lender && mv.length > 0 && (
          <p className="mt-1 text-[12px] text-muted num">Margin {mv[mv.length - 1] ?? "–"}% latest, {mv[Math.max(0, mv.length - 5)] ?? "–"}% a year earlier</p>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ business */
function BusinessTab({ symbol, ov, docLabel }: { symbol: string; ov: Overview | null; docLabel: (id: string) => string }) {
  const [runBiz, setRunBiz] = useState(false);
  const [runBb, setRunBb] = useState(false);
  const biz = useApi<Business>(`/api/research/${symbol}/business${runBiz ? "?run=true" : ""}`);
  const bb = useApi<BullBear>(`/api/research/${symbol}/bullbear${runBb ? "?run=true" : ""}`);
  return (
    <div className="mt-4">
      {biz.loading && !biz.data && <Loading text="Reading the latest annual report" />}
      {biz.error && <Notice tone="warn">{biz.error}</Notice>}
      {biz.data?.status === "not_run" && <RunGate data={biz.data} label="Read the annual report" onRun={() => setRunBiz(true)}>{null}</RunGate>}
      {biz.data?.stale && <RunGate data={biz.data} label="" onRun={() => setRunBiz(true)}>{null}</RunGate>}
      {biz.data?.status === "llm_disabled" && <Notice>Business summaries need a Gemini key on the server.</Notice>}
      {biz.data?.status === "no_documents" && <Notice>No readable annual report found for this company.</Notice>}
      {biz.data?.status === "ok" && (
        <>
          <p className="display text-[21px] font-semibold leading-snug">{biz.data.one_liner}</p>
          {biz.data.segments && biz.data.segments.length > 0 && (
            <>
              <SectionHead title="Segments" />
              <div className="rounded-2xl bg-surface px-4">
                {biz.data.segments.map((s) => (
                  <div key={s.name} className="flex items-start gap-3 border-t border-line py-2.5 first:border-t-0">
                    <div className="min-w-0 flex-1">
                      <div className="text-[15px] font-medium">{s.name}</div>
                      <div className="text-[13px] text-muted">{s.description}</div>
                    </div>
                    <div className="shrink-0 text-right">
                      {s.revenue_share_pct != null && <div className="text-[15px] num">{s.revenue_share_pct}%</div>}
                      {s.citations[0] && <CiteChip c={s.citations[0]} label={docLabel(s.citations[0].doc_id)} />}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
          {biz.data.facts && <ClaimList title="Worth knowing" claims={biz.data.facts} docLabel={docLabel} />}
        </>
      )}

      <SectionHead title="Bull vs bear" />
      {bb.loading && !bb.data && <Loading text="Weighing the evidence" />}
      {bb.error && <Notice tone="warn">{bb.error}</Notice>}
      {(bb.data?.status === "not_run" || bb.data?.stale) && <RunGate data={bb.data} label="Build the bull and bear case" onRun={() => setRunBb(true)}>{null}</RunGate>}
      {bb.data?.status === "ok" && (
        <div className="grid gap-3 sm:grid-cols-2">
          {(["bull", "bear"] as const).map((side) => (
            <div key={side} className="rounded-2xl bg-surface px-4 py-3">
              <h3 className={`display text-[17px] font-semibold ${side === "bull" ? "text-up" : "text-down"}`}>{side === "bull" ? "Bull case" : "Bear case"}</h3>
              <ul className="mt-1 space-y-2.5">
                {(bb.data?.[side] ?? []).map((p, i) => (
                  <li key={i} className="text-[14px] leading-snug">
                    {p.point}
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {p.citations.map((c, j) => <CiteChip key={j} c={c} label={docLabel(c.doc_id)} />)}
                      {p.metric_refs.map((r) => <span key={r} className="rounded-md bg-wash px-1.5 py-0.5 text-[12px] text-muted">{r}</span>)}
                      {!p.verified && <span className="text-[12px] text-down">unverified</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      {ov && (
        <>
          <SectionHead title="Primary sources" />
          <ul className="rounded-2xl bg-surface px-4 text-[14px]">
            {ov.documents.annual_reports.slice(0, 3).map((a) => (
              <li key={a.url} className="border-t border-line py-2 first:border-t-0">
                <a href={a.url} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2">{a.title}</a>
              </li>
            ))}
            {ov.documents.concalls.slice(0, 6).map((c) => (
              <li key={c.period} className="flex gap-3 border-t border-line py-2">
                <span className="w-20 shrink-0 text-muted num">{c.period}</span>
                {c.transcript && <a href={c.transcript} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2">Transcript</a>}
                {c.ppt && <a href={c.ppt} target="_blank" rel="noreferrer" className="underline decoration-line underline-offset-2">Presentation</a>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function ClaimList({ title, claims, docLabel }: { title: string; claims: Answer["claims"]; docLabel: (id: string) => string }) {
  if (!claims.length) return null;
  return (
    <>
      <SectionHead title={title} />
      <ul className="space-y-2.5 rounded-2xl bg-surface px-4 py-3">
        {claims.map((c, i) => (
          <li key={i} className="text-[14px] leading-snug">
            {c.text}
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {c.citations.map((ci, j) => <CiteChip key={j} c={ci} label={docLabel(ci.doc_id)} />)}
              {!c.verified && (
                <span className="text-[12px] text-down">
                  {c.unsupported_numbers.length ? `${c.unsupported_numbers.join(", ")} not found in the cited page` : "no valid citation"}
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

/* ------------------------------------------------------------------ ask */
const STARTERS = [
  "What did management guide for margins this year?",
  "What are the biggest risks management called out?",
  "How much capex is planned, and for what?",
];

function AskTab({ symbol, docLabel, pending, clearPending }: { symbol: string; docLabel: (id: string) => string; pending: string | null; clearPending: () => void }) {
  const [q, setQ] = useState("");
  const [thread, setThread] = useState<(Answer | { status: "loading"; question: string } | { status: "error"; question: string; error: string })[]>([]);
  const busy = thread.some((t) => t.status === "loading");

  const ask = async (question: string) => {
    if (!question.trim() || busy) return;
    setQ("");
    setThread((t) => [{ status: "loading", question }, ...t]);
    try {
      const history = thread.filter((t): t is Answer => "summary" in t && t.status !== "llm_disabled").slice(0, 2).reverse()
        .map((t) => ({ question: t.question, summary: t.summary }));
      const a = await api<Answer>(`/api/research/${symbol}/ask`, { method: "POST", body: JSON.stringify({ question, history }) });
      setThread((t) => t.map((x) => (x.status === "loading" ? a : x)));
    } catch (e) {
      setThread((t) => t.map((x) => (x.status === "loading" ? { status: "error" as const, question, error: e instanceof Error ? e.message : String(e) } : x)));
    }
  };
  useEffect(() => { if (pending) { ask(pending); clearPending(); } }, [pending]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="mt-4">
      <form onSubmit={(e) => { e.preventDefault(); ask(q); }} className="flex gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Ask about ${symbol}’s filings`}
          className="min-w-0 flex-1 rounded-full border border-line bg-surface px-4 py-2 text-[15px] placeholder:text-muted" aria-label="Question" />
        <button disabled={busy || !q.trim()} aria-label="Send question" className="rounded-full bg-ink px-4 text-[14px] text-paper disabled:opacity-40">Ask</button>
      </form>
      <p className="mt-2 text-[12px] text-muted">Answers come only from the last four concall transcripts and the latest annual report. Numbers not found on the cited page are flagged. Follow-ups remember your last two questions.</p>
      {thread.length === 0 && (
        <div className="mt-4 flex flex-col items-start gap-2">
          {STARTERS.map((s) => <button key={s} onClick={() => ask(s)} className="rounded-full border border-line bg-surface px-3 py-1.5 text-left text-[14px]">{s}</button>)}
        </div>
      )}
      <div className="mt-4 space-y-4">
        {thread.map((t, i) => (
          <div key={i} className="rounded-2xl bg-surface px-4 py-3">
            <p className="text-[13px] text-muted">{t.question}</p>
            {t.status === "loading" && <Loading text="Searching the transcripts and annual report" />}
            {"error" in t && <Notice tone="warn">{t.error}</Notice>}
            {t.status === "llm_disabled" && <div className="mt-2"><Notice>{DEMO ? "Live Q&A runs through Claude: open this page as a Claude artifact and choose Allow when asked. Precomputed research and every source still work here." : "Q&A needs a Gemini key on the server. Numbers, filings and cached research still work."}</Notice></div>}
            {t.status === "no_documents" && <div className="mt-2"><Notice>No transcript or annual report could be read for this company, so FINN won’t answer from memory.</Notice></div>}
            {"summary" in t && (
              <>
                <p className="mt-1 text-[16px] leading-snug">{t.summary}</p>
                {t.status === "not_found" && <p className="mt-1 text-[13px] text-muted">The documents searched don’t answer this directly.</p>}
                <ul className="mt-2 space-y-2">
                  {t.claims.map((c, j) => (
                    <li key={j} className="text-[14px] leading-snug">
                      {c.text}
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        {c.citations.map((ci, k) => <CiteChip key={k} c={ci} label={docLabel(ci.doc_id)} />)}
                        {!c.verified && <span className="text-[12px] text-down">{c.unsupported_numbers.length ? `${c.unsupported_numbers.join(", ")} not on cited page` : "no valid citation"}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
                {t.follow_ups?.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {t.follow_ups.map((f) => <button key={f} onClick={() => ask(f)} className="rounded-full border border-line px-2.5 py-1 text-left text-[13px]">{f}</button>)}
                  </div>
                )}
                {t.searched?.length > 0 && <p className="mt-2 text-[12px] text-muted">Searched {t.searched.filter((s) => s.status === "ok").length} documents, {t.searched.reduce((s, d) => s + d.pages, 0)} pages.</p>}
              </>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
