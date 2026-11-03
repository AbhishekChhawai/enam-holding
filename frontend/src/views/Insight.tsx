import { Fragment, useEffect, useMemo, useState } from "react";
import { api, useApi } from "../api";
import { ago, istDay, istTime, pct, signClass } from "../format";
import { Loading, Notice } from "../components/ui";

/* ------------------------------------------------------------------ types */
interface TEvent {
  id: string; timestamp: string; date_precision: "exact" | "day" | "month" | "period_end"; type: string; category: string | null;
  title: string; detail: string | null; metrics: Record<string, any>; source: string | null; url: string | null;
  provenance: "direct" | "derived" | "normalized"; doc_id: string | null; related: string[];
}
interface Timeline { symbol: string; count: number; counts_by_type: Record<string, number>; events: TEvent[]; note: string }
interface Source { key: string; label: string; provider: string; status: string; confidence: string; note?: string | null; [k: string]: any }
interface Quality {
  symbol: string; identity: { bse_code: string | null; isin: string | null; sources: string[]; validated_at: string | null };
  sources: Source[]; checks: { name: string; status: "pass" | "warn" | "fail"; detail: string }[];
  conflicts: { what: string; note: string; resolution: string }[]; legend: Record<string, string>;
}
interface Job { status: "queued" | "running" | "done" | "failed"; steps?: Record<string, { status: string; records?: number; new_records?: number; error?: string }> }

/* ------------------------------------------------------------------ unseen ticker ingestion */
export function useIngest(symbol: string, onDone: () => void) {
  const [job, setJob] = useState<Job | null>(null);
  useEffect(() => {
    let alive = true, timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async (n: number) => {
      try {
        const c = await api<{ job: Job | null; in_portfolio: boolean }>(`/api/companies/${symbol}`);
        if (!alive) return;
        setJob(c.job);
        if (c.job && (c.job.status === "queued" || c.job.status === "running") && n < 60) timer = setTimeout(() => poll(n + 1), 3000);
        else if (n > 0 && c.job?.status === "done") onDone();
      } catch {
        if (alive && n < 3) timer = setTimeout(() => poll(n + 1), 2000);  // company may not be registered yet
      }
    };
    timer = setTimeout(() => poll(0), 1200);
    return () => { alive = false; if (timer) clearTimeout(timer); };
  }, [symbol]); // eslint-disable-line react-hooks/exhaustive-deps
  return job;
}

export function IngestBanner({ symbol, job }: { symbol: string; job: Job | null }) {
  if (!job) return null;
  if (job.status === "queued" || job.status === "running") {
    return <div className="mt-3"><Loading text={`New to FINN: fetching a year of prices and recent BSE filings for ${symbol}`} /></div>;
  }
  const steps = Object.entries(job.steps ?? {}).filter(([, v]) => v.status !== "ok");
  if (!steps.length) return null;
  return (
    <div className="mt-3"><Notice>
      {steps.map(([k, v]) => <span key={k} className="block">{k === "prices" ? "Prices" : "Filings"}: {v.status === "unavailable" ? v.error : v.status === "empty" ? "no data returned" : v.error ?? v.status}</span>)}
    </Notice></div>
  );
}

/* ------------------------------------------------------------------ timeline */
const FILTERS: { key: string; label: string }[] = [
  { key: "", label: "All" }, { key: "results", label: "Results" }, { key: "filings", label: "Filings" },
  { key: "market", label: "Market" }, { key: "documents", label: "Calls" },
];
const TYPE_LABEL: Record<string, string> = {
  results: "Results filing", financials: "Quarter closed", filing: "Filing", management: "Management", corporate_action: "Corporate action",
  market: "Market move", concall: "Earnings call",
};
const PROV: Record<string, string> = { direct: "Direct from source", derived: "Derived from EOD prices", normalized: "Standardised figures" };

function when(e: TEvent) {
  if (e.date_precision === "month") return new Intl.DateTimeFormat("en-IN", { month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(e.timestamp));
  if (e.date_precision === "day" || e.date_precision === "period_end") return istDay(e.timestamp.slice(0, 10));
  return istTime(e.timestamp);
}

export function TimelineTab({ symbol, refreshKey }: { symbol: string; refreshKey: number }) {
  const [filter, setFilter] = useState("");
  const qs = new URLSearchParams({ ...(filter ? { types: filter } : {}), _: String(refreshKey) });
  const { data, error, loading } = useApi<Timeline>(`/api/companies/${symbol}/timeline?${qs}`);
  const byId = useMemo(() => new Map((data?.events ?? []).map((e) => [e.id, e])), [data]);
  return (
    <div className="mt-4">
      <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 scrollbar-none">
        {FILTERS.map((f) => (
          <button key={f.key} onClick={() => setFilter(f.key)} aria-pressed={filter === f.key}
            className={`min-h-[34px] shrink-0 rounded-full border px-3 py-1 text-[13px] ${filter === f.key ? "border-ink bg-ink text-paper" : "border-line text-muted"}`}>
            {f.label}{data && !filter && f.key === "" ? ` ${data.count}` : ""}
          </button>
        ))}
      </div>
      {loading && !data && <Loading text="Assembling the timeline" />}
      {error && <div className="mt-3"><Notice tone="warn">{error.includes("not registered") ? "This company is still being registered. Try again in a moment." : error}</Notice></div>}
      {data && data.events.length === 0 && <div className="mt-3"><Notice>No events in this view yet.</Notice></div>}
      <ol className="relative mt-4 border-l border-line pl-4">
        {data?.events.map((e) => (
          <li key={e.id} className="relative pb-4">
            <span className={`absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-paper ${e.type === "results" ? "bg-marigold" : e.type === "market" ? "bg-muted" : "bg-ink"}`} aria-hidden="true" />
            <div className="flex items-baseline gap-2 text-[12px] text-muted">
              <span>{TYPE_LABEL[e.type] ?? e.type}{e.category && e.type === "filing" ? `, ${e.category}` : ""}</span>
              <span className="ml-auto num">{when(e)}</span>
            </div>
            <p className="mt-0.5 text-[15px] leading-snug">{e.title}</p>
            {e.detail && <p className="mt-0.5 text-[13px] text-muted">{e.detail}</p>}
            <Metrics e={e} />
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted">
              <span>{PROV[e.provenance]}{e.source ? `, ${e.source}` : ""}</span>
              {e.url && <a href={e.url} target="_blank" rel="noreferrer" className="inline-flex min-h-[28px] items-center underline decoration-line underline-offset-2">Original</a>}
            </div>
            {e.related.length > 0 && (
              <p className="mt-1 text-[12px] text-muted">
                Same window: {e.related.map((r) => byId.get(r)?.title ?? r).slice(0, 3).join("; ")}
              </p>
            )}
          </li>
        ))}
      </ol>
      {data && <p className="text-[12px] text-muted">{data.note}</p>}
    </div>
  );
}

function Metrics({ e }: { e: TEvent }) {
  if (e.type === "market") {
    return (
      <p className="mt-0.5 text-[13px] num">
        <span className={signClass(e.metrics.pct)}>{pct(e.metrics.pct)}</span>
        {e.metrics.volume_multiple != null && <span className="text-muted">, {Number(e.metrics.volume_multiple).toFixed(1)}× volume</span>}
      </p>
    );
  }
  const entries = Object.entries(e.metrics).filter(([, v]) => v && typeof v === "object" && v.value != null);
  if (!entries.length) return null;
  return (
    <p className="mt-0.5 text-[13px] num">
      {entries.map(([k, v], i) => (
        <span key={k}>{i > 0 && <span className="text-muted">, </span>}{k} ₹{Math.round(v.value).toLocaleString("en-IN")} cr
          {v.yoy_pct != null && <span className={signClass(v.yoy_pct)}> ({pct(v.yoy_pct)} YoY)</span>}</span>
      ))}
    </p>
  );
}

/* ------------------------------------------------------------------ data quality */
const STATUS_TONE: Record<string, string> = {
  fresh: "text-up", ok: "text-up", pass: "text-up", possibly_stale: "text-ink", partial: "text-ink", warn: "text-ink",
  stale: "text-down", missing: "text-down", fail: "text-down", not_mapped: "text-down", never_synced: "text-down",
};
const STATUS_TEXT: Record<string, string> = {
  fresh: "Fresh", ok: "OK", possibly_stale: "One session behind", stale: "Stale", missing: "Missing", partial: "Partial",
  not_mapped: "Not linked", never_synced: "Not synced yet", pass: "Pass", warn: "Check", fail: "Fail",
};

export function freshnessLine(q: Quality | null) {
  if (!q) return null;
  const px = q.sources.find((s) => s.key === "prices");
  const fl = q.sources.find((s) => s.key === "filings");
  const parts = [px && `Prices ${STATUS_TEXT[px.status]?.toLowerCase() ?? px.status}${px.last_record ? ` (${istDay(px.last_record)})` : ""}`,
                 fl && (fl.last_sync ? `filings synced ${ago(fl.last_sync)}` : `filings ${STATUS_TEXT[fl.status]?.toLowerCase() ?? fl.status}`)];
  const warn = q.conflicts.length > 0 || q.checks.some((c) => c.status === "fail");
  return { text: parts.filter(Boolean).join(", "), warn };
}

export function useQuality(symbol: string, refreshKey: number) {
  return useApi<Quality>(`/api/companies/${symbol}/data-quality?_=${refreshKey}`);
}

export function QualityView({ q }: { q: Quality }) {
  return (
    <div className="space-y-5 text-[14px]">
      <section>
        <h3 className="display text-[17px] font-semibold">Sources</h3>
        <ul className="mt-1">
          {q.sources.map((s) => (
            <li key={s.key} className="border-t border-line py-2 first:border-t-0">
              <div className="flex items-baseline justify-between gap-3">
                <span className="font-medium">{s.label}</span>
                <span className={`text-[13px] ${STATUS_TONE[s.status] ?? "text-muted"}`}>{STATUS_TEXT[s.status] ?? s.status}</span>
              </div>
              <div className="text-[12px] text-muted">
                {s.provider}. Confidence: {s.confidence}.
                {s.last_record && ` Last session ${istDay(s.last_record)}, expected ${istDay(s.expected_session)}.`}
                {s.records != null && ` ${s.records} records.`}
                {s.records_90d != null && ` ${s.records_90d} ${s.records_90d === 1 ? "filing" : "filings"} in 90 days.`}
                {s.latest_quarter && ` Latest quarter ${s.latest_quarter} (${s.basis}).`}
                {s.counts && Object.keys(s.counts).length > 0 && ` ${Object.entries(s.counts).map(([k, v]) => `${v} ${k}`).join(", ")}.`}
                {(s.retrieved_at || s.last_sync) && ` Updated ${ago(s.retrieved_at ?? s.last_sync)}.`}
                {s.note && ` ${s.note}`}
              </div>
            </li>
          ))}
        </ul>
      </section>
      {q.conflicts.length > 0 && (
        <section>
          <h3 className="display text-[17px] font-semibold text-down">Conflicting values</h3>
          {q.conflicts.map((c, i) => (
            <div key={i} className="mt-1 rounded-lg bg-down-wash px-3 py-2 text-[13px]">
              <p className="font-medium">{c.what}</p><p>{c.note}</p><p className="text-muted">{c.resolution}</p>
            </div>
          ))}
        </section>
      )}
      <section>
        <h3 className="display text-[17px] font-semibold">Checks</h3>
        <ul className="mt-1">
          {q.checks.map((c, i) => (
            <li key={i} className="flex gap-3 border-t border-line py-1.5 first:border-t-0">
              <span className={`w-12 shrink-0 text-[13px] ${STATUS_TONE[c.status]}`}>{STATUS_TEXT[c.status]}</span>
              <span className="min-w-0"><span>{c.name}</span><span className="block text-[12px] text-muted">{c.detail}</span></span>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className="display text-[17px] font-semibold">What the labels mean</h3>
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-[13px]">
          {Object.entries(q.legend).map(([k, v]) => (<Fragment key={k}><dt className="font-medium">{k}</dt><dd className="text-muted">{v}</dd></Fragment>))}
        </dl>
      </section>
    </div>
  );
}
