import { useState } from "react";
import { api, useApi } from "../api";
import { ago, istDay, istTime } from "../format";
import type { DigestItem, Usage } from "../types";
import { Loading, Notice, Segmented, useUI } from "../components/ui";
import { Term } from "../components/Explain";
import { alertMessage, waLink } from "../whatsapp";

export interface AlertItem {
  id: number; rule_id: number; symbol: string; kind: "market" | "filing"; session_date: string | null; announcement_id: string | null;
  observed: number | null; threshold: number | null; severity: "high" | "medium"; title: string; message: string;
  provenance: Record<string, any> | null; created_at: string; read: boolean; rule_kind?: string | null;
}
export interface AlertsResp { total: number; unread_count: number; evaluated_at: string | null; items: AlertItem[] }
interface Rule {
  id: number; name: string; symbol: string | null; scope: string; kind: "price_move" | "volume" | "filing"; direction: string | null;
  threshold: number | null; window: number | null; categories: string[] | null; min_tier: string | null; enabled: boolean;
  description: string; last_evaluated_at: string | null;
}

const KIND_TAB: Record<string, string> = { price_move: "Price move", volume: "Volume spike", filing: "Filing", market: "Market move" };
const FILTERS = [
  { key: "all", label: "All", q: "" }, { key: "unread", label: "Unread", q: "&unread=true" }, { key: "read", label: "Read", q: "&unread=false" },
  { key: "price", label: "Price", q: "&kind=price" }, { key: "volume", label: "Volume", q: "&kind=volume" }, { key: "filing", label: "Filings", q: "&kind=filing" },
];

function observedText(a: AlertItem) {
  if (a.observed == null) return null;
  if (a.provenance?.formula?.startsWith("volume")) return `${a.observed.toFixed(1)}× vs your ${a.threshold}×`;
  return `${a.observed > 0 ? "+" : "−"}${Math.abs(a.observed).toFixed(1)}% vs your ${a.threshold}%`;
}

export default function AlertsView({ onChanged, openRules, refreshKey }: { onChanged: () => void; openRules: () => void; refreshKey: number }) {
  const ui = useUI();
  const [filter, setFilter] = useState("all");
  const [checking, setChecking] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const q = FILTERS.find((f) => f.key === filter)!.q;
  const { data, error, loading, reload, setData } = useApi<AlertsResp>(`/api/alerts?limit=100${q}&_=${refreshKey}`);

  const open = async (a: AlertItem) => {
    if (!a.read) {
      api(`/api/alerts/${a.id}`, { method: "PATCH", body: JSON.stringify({ read: true }) }).then(onChanged).catch(() => {});
      if (data) setData({ ...data, unread_count: Math.max(0, data.unread_count - 1), items: data.items.map((x) => (x.id === a.id ? { ...x, read: true } : x)) });
    }
    if (a.announcement_id) {
      try { ui.openItem(await api<DigestItem>(`/api/announcements/${a.announcement_id}`)); } catch { /* filing gone */ }
    } else ui.openResearch(a.symbol, "timeline");
  };
  const checkNow = async () => {
    setChecking(true);
    try {
      const r = await api<{ created: number; completed_session: string }>("/api/alerts/evaluate", { method: "POST" });
      setNote(r.created ? `${r.created} new ${r.created === 1 ? "alert" : "alerts"}.` : `No rule crossed. Sessions checked up to ${istDay(r.completed_session)}.`);
      reload(); onChanged();
    } finally { setChecking(false); }
  };
  const readAll = async () => { await api("/api/alerts/mark-all-read", { method: "POST" }); reload(); onChanged(); };
  const markUnread = async (a: AlertItem) => {
    await api(`/api/alerts/${a.id}`, { method: "PATCH", body: JSON.stringify({ read: false }) });
    if (data) setData({ ...data, unread_count: data.unread_count + 1, items: data.items.map((x) => (x.id === a.id ? { ...x, read: false } : x)) });
    onChanged();
  };

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 scrollbar-none">
          {FILTERS.map((f) => (
            <button key={f.key} onClick={() => setFilter(f.key)} aria-pressed={filter === f.key}
              className={`min-h-[34px] shrink-0 rounded-full border px-3 py-1 text-[13px] ${filter === f.key ? "border-ink bg-ink text-paper" : "border-line text-muted"}`}>{f.label}</button>
          ))}
        </div>
      </div>
      <h1 className="display mt-5 text-[26px] font-semibold leading-[1.1]">
        {data ? (data.unread_count ? `${data.unread_count} unread ${data.unread_count === 1 ? "alert" : "alerts"}` : "No unread alerts") : "Alerts"}
      </h1>
      <p className="mt-1 text-[14px] text-muted">
        Rules checked {ago(data?.evaluated_at)}, against completed end-of-day sessions and newly ingested filings.{" "}
        <button onClick={checkNow} disabled={checking} className="text-ink underline decoration-line underline-offset-2 disabled:text-muted disabled:no-underline">{checking ? "Checking…" : "Check now"}</button>
        <button onClick={openRules} className="ml-3 text-ink underline decoration-line underline-offset-2">Edit rules</button>
      </p>
      {note && <p className="mt-1 text-[13px] text-muted">{note}</p>}
      {error && <div className="mt-4"><Notice tone="warn">{error}</Notice></div>}
      {!data && loading && <Loading text="Loading alerts" />}
      {data && data.items.length === 0 && <div className="mt-4"><Notice>Nothing here yet. Alerts appear when a rule matches a completed session or a new filing.</Notice></div>}
      {data && data.items.length > 0 && (
        <>
          <ul className="mt-4 space-y-3">
            {data.items.map((a, i) => (
              <li key={a.id} className={`rise overflow-hidden rounded-2xl bg-surface px-4 pt-2.5 ${a.read ? "" : "ring-1 ring-marigold/30"}`} style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}>
                <div className="flex items-center justify-between gap-2">
                  <span className="rounded-full bg-marigold-wash px-2.5 py-0.5 text-[11.5px] font-semibold text-marigold">{KIND_TAB[a.rule_kind ?? a.kind] ?? "Alert"}</span>
                  <span className="chip num text-[11.5px]">{a.session_date ? istDay(a.session_date) : istTime(a.created_at)}</span>
                </div>
                <button onClick={() => open(a)} className="flex w-full gap-3 py-3 text-left">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${a.read ? "bg-transparent" : a.severity === "high" ? "bg-marigold" : "bg-muted"}`} aria-label={a.read ? "Read" : `Unread, ${a.severity}`} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline gap-2">
                      <span className={`truncate text-[15px] ${a.read ? "" : "font-semibold"}`}>{a.title}</span>

                    </span>
                    <span className="mt-0.5 block text-[14px] leading-snug text-muted">{a.message}</span>
                    {observedText(a) && <span className="mt-1.5 inline-flex rounded-full border border-line px-2.5 py-0.5 text-[12.5px] font-semibold num">{observedText(a)}</span>}
                  </span>
                </button>
                <div className="-mt-1 flex flex-wrap items-baseline gap-x-3 gap-y-1 pb-3 pl-5 text-[12px] text-muted">
                  {a.kind === "market" && a.provenance?.context && (
                    <span className="w-full">
                      <span className="font-medium text-ink">Why now? </span>
                      {(a.provenance.nearby ?? []).map((n: any, i: number) => (
                        <span key={n.id}>{i > 0 && "; "}{n.attachment_url ? <a href={n.attachment_url} target="_blank" rel="noreferrer" className="inline-flex min-h-[28px] items-center underline decoration-line underline-offset-2">{n.category_label}, {istDay(n.published_at)}</a> : `${n.category_label}, ${istDay(n.published_at)}`}</span>
                      ))}{(a.provenance.nearby ?? []).length ? ". " : ""}{a.provenance.context}
                    </span>
                  )}
                  {a.kind === "filing" && a.provenance?.url && <a href={a.provenance.url} target="_blank" rel="noreferrer" className="inline-flex min-h-[28px] items-center underline decoration-line underline-offset-2">Original filing</a>}
                  <a href={waLink(alertMessage(a))} target="_blank" rel="noreferrer" className="inline-flex min-h-[28px] items-center gap-1 font-semibold text-[#128C4B]" aria-label={`Share ${a.symbol} alert on WhatsApp`}><svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.7 11.8 11.8 0 0 0 4.5 4c1.7.7 2.3.8 3.2.6a2.7 2.7 0 0 0 1.8-1.3 2.2 2.2 0 0 0 .2-1.3c-.1-.1-.3-.2-.5-.3z"/></svg>WhatsApp</a>
                  {a.kind === "market" && <span>Source: {a.provenance?.source ?? "EOD prices"}, {a.provenance?.formula}</span>}
                  {a.read && <button onClick={() => markUnread(a)} className="min-h-[32px] underline decoration-line underline-offset-2">Mark unread</button>}
                </div>
              </li>
            ))}
          </ul>
          {data.unread_count > 0 && <button onClick={readAll} className="mt-3 min-h-[32px] text-[13px] text-muted underline decoration-line underline-offset-2">Mark all read</button>}
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ rules */
const KIND_OPTS = [{ value: "price_move", label: "Price move" }, { value: "volume", label: "Volume" }, { value: "filing", label: "Filings" }] as const;
const TIER_OPTS = [{ value: "routine", label: "Any" }, { value: "worth_a_look", label: "Non-routine" }, { value: "needs_you", label: "Top priority" }];

/** WhatsApp alerts: status of automatic sending, plus a preview of the exact message format. */
export function WhatsAppPanel({ sample }: { sample: string | null }) {
  const st = useApi<{ configured: boolean; provider: string | null; to: string | null; daily_cap: number; demo?: boolean }>("/api/notify/status");
  const preview = sample ?? "*FINN: TCS, Results*\nUnaudited results for Q2 FY27\nRevenue ₹… cr (YoY …, QoQ …)\nFiling: https://www.bseindia.com/…\nInformational only, not investment advice.";
  return (
    <section className="mb-5 rounded-2xl border border-line p-3">
      <h3 className="display flex items-center gap-2 text-[16px] font-bold"><span aria-hidden="true" className="grid h-7 w-7 place-items-center rounded-full bg-[#25D366] text-[#062b16]"><svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2z"/></svg></span>WhatsApp alerts
        <span className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold ${st.data?.configured ? "bg-up-wash text-up" : "border border-line text-muted"}`}>{st.data?.configured ? "On" : "Not set up"}</span></h3>
      {st.data?.configured ? (
        <p className="mt-1.5 text-[13px]">On. Important alerts go to <b className="num">{st.data.to}</b> via {st.data.provider}, at most {st.data.daily_cap} a day, each once.</p>
      ) : (
        <p className="mt-1.5 text-[13px] text-muted">
          {st.data?.demo ? "Automatic messages need the full app with your WhatsApp settings; this page is a snapshot. " : "Automatic messages aren’t set up yet. "}
          Every alert and important filing already has a <b>Share on WhatsApp</b> button. To get messages automatically, set <code>FINN_WHATSAPP_PROVIDER</code> and your number (see the README); the daily GitHub run then sends them.
        </p>
      )}
      <p className="mt-2 text-[12px] font-medium text-muted">What a message looks like</p>
      <div className="mt-1 max-w-[290px] whitespace-pre-line rounded-2xl rounded-tl-sm bg-[#DCF8C6] px-3 py-2 text-[13px] leading-snug text-[#111b21] shadow-sm">{preview.replace(/\*/g, "")}</div>
      <p className="mt-2 text-[11.5px] text-muted">Only high-priority events are sent: big end-of-day moves from the latest session and important filings from the last day. Your number stays on the server, never in the app.</p>
    </section>
  );
}

export function RulesView({ symbols, onSaved }: { symbols: { symbol: string; name: string }[]; onSaved: (msg: string) => void }) {
  const { data, error, reload } = useApi<{ items: Rule[] }>("/api/alerts/rules");
  const cats = useApi<{ key: string; label: string }[]>("/api/meta/categories");
  const [kind, setKind] = useState<Rule["kind"]>("price_move");
  const [scope, setScope] = useState("");
  const [direction, setDirection] = useState("either");
  const [threshold, setThreshold] = useState("5");
  const [windowN, setWindowN] = useState("20");
  const [picked, setPicked] = useState<string[]>(["results", "management_change"]);
  const [tier, setTier] = useState("worth_a_look");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);

  const startEdit = (r: Rule) => {
    setEditing(r.id); setKind(r.kind); setScope(r.symbol ?? ""); setErr(null);
    if (r.direction) setDirection(r.direction);
    if (r.threshold != null) setThreshold(String(r.threshold));
    if (r.window) setWindowN(String(r.window));
    if (r.categories) setPicked(r.categories);
    if (r.min_tier) setTier(r.min_tier);
  };

  const save = async () => {
    setErr(null); setBusy(true);
    const body: Record<string, unknown> = { kind, symbol: scope || null };
    if (kind === "price_move") Object.assign(body, { direction, threshold: parseFloat(threshold) });
    if (kind === "volume") Object.assign(body, { threshold: parseFloat(threshold), window: parseInt(windowN, 10) });
    if (kind === "filing") Object.assign(body, { categories: picked, min_tier: tier });
    try {
      const r = await api<Rule & { evaluation: { created: number } | null }>(editing ? `/api/alerts/rules/${editing}` : "/api/alerts/rules",
        { method: editing ? "PATCH" : "POST", body: JSON.stringify(body) });
      reload(); setEditing(null);
      const n = r.evaluation?.created ?? 0;
      onSaved(`Rule ${editing ? "updated" : "saved"}. ${n ? `${n} recent ${n === 1 ? "match" : "matches"} added to Alerts.` : "No new recent matches."}`);
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };
  const toggle = async (r: Rule) => { await api(`/api/alerts/rules/${r.id}`, { method: "PATCH", body: JSON.stringify({ enabled: !r.enabled }) }); reload(); onSaved(r.enabled ? "Rule paused" : "Rule on"); };
  const remove = async (r: Rule) => { await api(`/api/alerts/rules/${r.id}`, { method: "DELETE" }); reload(); onSaved("Rule removed"); };

  return (
    <div className="space-y-6">
      <section>
        <h3 className="display text-[17px] font-semibold">Your rules</h3>
        {error && <Notice tone="warn">{error}</Notice>}
        <ul className="mt-1">
          {data?.items.map((r) => (
            <li key={r.id} className="flex items-start gap-3 border-t border-line py-2.5 first:border-t-0">
              <span className={`min-w-0 flex-1 text-[14px] leading-snug ${r.enabled ? "" : "text-muted line-through"}`}>{r.description}</span>
              <button onClick={() => startEdit(r)} className="min-h-[32px] shrink-0 px-1 text-[12px] text-muted underline decoration-line underline-offset-2" aria-label={`Edit: ${r.description}`}>Edit</button>
              <button onClick={() => toggle(r)} aria-pressed={r.enabled} className={`min-h-[32px] shrink-0 rounded-full border px-3 text-[12px] ${r.enabled ? "border-ink" : "border-line text-muted"}`}>{r.enabled ? "On" : "Off"}</button>
              <button onClick={() => remove(r)} className="min-h-[32px] shrink-0 px-1 text-[12px] text-muted underline decoration-line underline-offset-2" aria-label={`Remove: ${r.description}`}>Remove</button>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h3 className="display text-[17px] font-semibold">{editing ? "Edit rule" : "Add a rule"}</h3>
        <div className="mt-2 space-y-3 text-[14px]">
          <Segmented label="Rule type" value={kind} onChange={(v) => { setKind(v); setThreshold(v === "volume" ? "2" : "5"); }} options={[...KIND_OPTS]} />
          <p className="text-[13px] text-muted">
            {kind === "price_move" && <>How much a share’s closing price changed from the day before. A big one-day move often follows news. FINN uses <Term k="eod">end-of-day</Term> prices, so it checks after each trading day closes.</>}
            {kind === "volume" && <>How many shares changed hands compared with a normal day. A sudden spike in <Term k="volume">trading volume</Term> can mean news or a large investor moving; it doesn’t say whether that’s good or bad.</>}
            {kind === "filing" && <>Get alerted when a company publishes a particular kind of official <Term k="filing">filing</Term>, such as results or a change of CEO.</>}
          </p>
          <label className="block">
            <span className="text-muted">For</span>
            <select value={scope} onChange={(e) => setScope(e.target.value)} className="mt-1 block w-full rounded-xl border border-line bg-surface px-3 py-2">
              <option value="">Any holding in my portfolio</option>
              {symbols.map((s) => <option key={s.symbol} value={s.symbol}>{s.symbol}, {s.name}</option>)}
            </select>
          </label>
          {kind === "price_move" && (
            <div className="flex flex-wrap items-end gap-3">
              <Segmented label="Direction" value={direction} onChange={setDirection} options={[{ value: "either", label: "Either way" }, { value: "up", label: "Up" }, { value: "down", label: "Down" }]} />
              <label className="block w-24"><span className="text-muted">By at least</span>
                <span className="mt-1 flex items-center rounded-xl border border-line bg-surface px-3 py-1.5"><input inputMode="decimal" value={threshold} onChange={(e) => setThreshold(e.target.value)} className="w-full bg-transparent num" aria-label="Percent" /><span className="text-muted">%</span></span>
              </label>
            </div>
          )}
          {kind === "volume" && (
            <div className="flex flex-wrap items-end gap-3">
              <label className="block w-28"><span className="text-muted">Volume above</span>
                <span className="mt-1 flex items-center rounded-xl border border-line bg-surface px-3 py-1.5"><input inputMode="decimal" value={threshold} onChange={(e) => setThreshold(e.target.value)} className="w-full bg-transparent num" aria-label="Multiple" /><span className="text-muted">×</span></span>
              </label>
              <label className="block w-36"><span className="text-muted">Average of last</span>
                <span className="mt-1 flex items-center gap-1 rounded-xl border border-line bg-surface px-3 py-1.5"><input inputMode="numeric" value={windowN} onChange={(e) => setWindowN(e.target.value)} className="w-full bg-transparent num" aria-label="Sessions" /><span className="text-muted">sessions</span></span>
              </label>
            </div>
          )}
          {kind === "filing" && (
            <>
              <div className="flex flex-wrap gap-1.5">
                {(cats.data ?? []).filter((c) => c.key !== "unclassified").map((c) => {
                  const on = picked.includes(c.key);
                  return <button key={c.key} onClick={() => setPicked((p) => on ? p.filter((x) => x !== c.key) : [...p, c.key])} aria-pressed={on}
                    className={`min-h-[34px] rounded-full border px-3 py-1 text-[13px] ${on ? "border-ink bg-ink text-paper" : "border-line text-muted"}`}>{c.label}</button>;
                })}
              </div>
              <div><span className="mr-2 text-muted">Only if ranked</span><Segmented label="Minimum priority" value={tier} onChange={setTier} options={TIER_OPTS} /></div>
            </>
          )}
          {err && <Notice tone="warn">{err}</Notice>}
          <div className="flex items-center gap-3">
            <button onClick={save} disabled={busy} className="rounded-full bg-ink px-4 py-2 text-paper disabled:opacity-50">{busy ? "Saving…" : editing ? "Update rule" : "Save rule"}</button>
            {editing && <button onClick={() => setEditing(null)} className="text-muted underline decoration-line underline-offset-2">Cancel edit</button>}
          </div>
          <p className="text-[12px] text-muted">Saving checks the rule against the last 10 completed sessions and 7 days of filings. After that, rules run whenever new data arrives: on refresh, on the 15-minute schedule, or when you tap Check now.</p>
        </div>
      </section>
      <UsageView />
    </div>
  );
}

function UsageView() {
  const usage = useApi<Usage>("/api/meta/usage");
  if (!usage.data) return null;
  const u = usage.data;
  return (
    <section className="border-t border-line pt-4 text-[13px] text-muted">
      <h3 className="display text-[17px] font-semibold text-ink">Model use</h3>
      {!u.llm_enabled && <p>No model key on this server: AI features are off, everything else works.</p>}
      <p>Bulk extraction runs on {u.routing.fast}; reasoning on {u.routing.reason}. Alerts, scores and calculations use no model.</p>
      <p className="num">{u.total_calls} paid calls so far, {u.total_cache_hits} answered free from cache.</p>
    </section>
  );
}
