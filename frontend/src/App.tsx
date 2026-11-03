import { useCallback, useEffect, useMemo, useState } from "react";
import { DEMO as IS_DEMO, api, useApi } from "./api";
import type { Intent, ResearchTab } from "./intent";
import type { Cite, Digest, DigestItem, Prefs, PriceSnap } from "./types";
import { Icon, Sheet, UIContext, type UI } from "./components/ui";
import { CitationView, CommandBar } from "./components/Chrome";
import AlertsView, { RulesView, WhatsAppPanel, type AlertsResp } from "./views/Alerts";
import { itemMessage } from "./whatsapp";
import { ExplainView, HelpView, Onboarding } from "./components/Explain";
import { GLOSSARY } from "./glossary";
import { ItemDetail } from "./components/Feed";
import Today from "./views/Today";
import Portfolio from "./views/Portfolio";
import Research from "./views/Research";

type Tab = "today" | "portfolio" | "research" | "alerts";
export interface Handoff {
  symbol: string; company: string; event_id: string; category: string; category_label: string; headline: string;
  summary: string | null; published_at: string; related_filing_ids: string[]; document_ids: string[];
  reporting_period: string | null; suggested_question: string; target_tab: ResearchTab | "ask";
}
type Route = { tab: Tab; symbol: string | null; rtab: ResearchTab };

// The phone demo is hosted where only simple #names pass through, so it uses hyphens and plain hash assignment.
const SEP = IS_DEMO ? "-" : "/";
function readHash(): Route {
  const [tab, symbol, rtab] = window.location.hash.replace(/^#\/?/, "").split(SEP);
  if (tab === "research") return { tab: "research", symbol: symbol ? symbol.toUpperCase() : null, rtab: (rtab as ResearchTab) || "promises" };
  if (tab === "portfolio") return { tab: "portfolio", symbol: null, rtab: "promises" };
  if (tab === "alerts") return { tab: "alerts", symbol: null, rtab: "promises" };
  return { tab: "today", symbol: null, rtab: "promises" };
}
const writeHash = (r: Route) => {
  const h = r.tab === "research" ? `#research${r.symbol ? `${SEP}${r.symbol}${SEP}${r.rtab}` : ""}` : `#${r.tab}`;
  if (window.location.hash === h) return;
  if (IS_DEMO) window.location.hash = h; else window.history.pushState(null, "", h);
};

const DEMO = [
  { symbol: "DIXON", name: "Dixon Technologies" }, { symbol: "PERSISTENT", name: "Persistent Systems" },
  { symbol: "KAYNES", name: "Kaynes Technology" }, { symbol: "POLYCAB", name: "Polycab India" },
];

function DemoBanner() {
  const [open, setOpen] = useState(false);
  const [meta, setMeta] = useState<{ kind: string; snapshot_at: string | null; research: string[]; note?: string | null } | null>(null);
  useEffect(() => { import("./demo/mock").then((m) => setMeta(m.DEMO_META)); }, []);
  if (!meta) return null;
  const real = meta.kind === "real";
  const when = meta.snapshot_at ? new Intl.DateTimeFormat("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric" }).format(new Date(meta.snapshot_at)) : "";
  return (
    <div className="mt-3 rounded-xl border border-marigold bg-marigold-wash px-3 py-2 text-[13px] leading-snug">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="min-h-[28px] w-full text-left">
        <span className="font-semibold">{real ? `Real NSE data, end-of-day prices up to ${when}.` : "Demo with fictional companies and numbers."}</span>{" "}
        <span className="underline decoration-line underline-offset-2">{open ? "Less" : real ? "What’s in it" : "About this demo"}</span>
      </button>
      {open && (
        <div className="mt-1 space-y-1 text-muted">
          {real ? (<>
            <p>{meta.note || `Every price, filing, report and transcript here was ingested by FINN from public sources on ${when} and links to its original.`} Prices are end-of-day closes, not live.</p>
            {meta.research.length > 0 && <p>AI research (promises, narrative vs numbers, business, bull vs bear) is precomputed for {meta.research.join(", ")}. <b>Ask</b> answers live using Claude, only from each company’s own documents.</p>}
            <p>Alert rules and read states are saved on this phone. Refresh is disabled because this page is a snapshot; the full app refreshes from BSE.</p>
          </>) : (<>
            <p>This is the real FINN interface. Its data was produced by FINN’s real backend for three made-up companies (FINNDEMO, ORBITAL, NOVAPHARMA) and three made-up funds (gold, debt and global), so nothing here is real market data. The real portfolio has 19 real holdings, including gold, debt and international ETFs.</p>
            <p>Your alert rules and read states are saved on this phone. <b>Ask</b> answers live using Claude (you’ll be asked to allow it), only from the demo documents.</p>
            <p>The full app ingests real NSE/BSE prices, filings, annual reports and earnings calls; see the GitHub repo.</p>
          </>)}
          <button onClick={async () => { const m = await import("./demo/mock"); m.resetDemo(); window.location.reload(); }} className="min-h-[36px] rounded-full border border-ink px-3 text-ink">Reset saved alerts</button>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [route, setRoute] = useState<Route>(readHash);
  const [hours, setHours] = useState(24);
  const [item, setItem] = useState<DigestItem | null>(null);
  const [cite, setCite] = useState<(Cite & { quote?: string; label?: string }) | null>(null);
  const [settings, setSettings] = useState(false);
  const [pendingQ, setPendingQ] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const store = (k: string, v?: string) => { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch { /* private mode */ } return null; };
  const [plain, setPlainState] = useState(() => store("finn.view") !== "detailed");
  const setPlain = (v: boolean) => { setPlainState(v); store("finn.view", v ? "plain" : "detailed"); };
  const [onboard, setOnboard] = useState(() => store("finn.onboarded") !== "1");
  const [term, setTerm] = useState<string | null>(null);
  // Theme: Auto follows the phone; an explicit choice is remembered on this device.
  const [theme, setThemeState] = useState<"auto" | "light" | "dark">(() => (store("finn.theme") as "light" | "dark") || "auto");
  const setTheme = (t: "auto" | "light" | "dark") => { setThemeState(t); store("finn.theme", t); };
  useEffect(() => { if (theme === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.dataset.theme = theme; }, [theme]);
  const isDark = theme === "dark" || (theme === "auto" && (document.documentElement.dataset.theme === "dark" || (!document.documentElement.dataset.theme && window.matchMedia?.("(prefers-color-scheme: dark)").matches)));
  const [help, setHelp] = useState(false);

  const digest = useApi<Digest>(`/api/digest?hours=${hours}`);
  const port = useApi<{ companies: { symbol: string; name: string; sector: string; price: PriceSnap | null }[]; prefs: Prefs }>("/api/portfolio");
  const prefs = port.data?.prefs ?? null;
  const alertsMeta = useApi<AlertsResp>("/api/alerts?limit=1");
  const [alertsKey, setAlertsKey] = useState(0);
  const alertsChanged = () => { alertsMeta.reload(); setAlertsKey((k) => k + 1); };

  useEffect(() => {
    const f = () => setRoute(readHash());
    window.addEventListener("popstate", f); window.addEventListener("hashchange", f);
    return () => { window.removeEventListener("popstate", f); window.removeEventListener("hashchange", f); };
  }, []);
  const go = useCallback((r: Partial<Route>) => setRoute((cur) => { const n = { ...cur, ...r }; writeHash(n); window.scrollTo({ top: 0 }); return n; }), []);
  // Any navigation closes the filing sheet so it never floats over the next screen.
  useEffect(() => { setItem(null); }, [route.tab, route.symbol]);
  useEffect(() => { if (toast) { const t = setTimeout(() => setToast(null), 2400); return () => clearTimeout(t); } }, [toast]);

  const names = useMemo(() => Object.fromEntries((port.data?.companies ?? []).map((c) => [c.symbol, c.name])), [port.data]);
  const known = useMemo(() => [...Object.keys(names), ...DEMO.map((d) => d.symbol)], [names]);

  // Refresh: check BSE now, then tell the investor what changed ("the moment something crosses a threshold").
  const [refreshing, setRefreshing] = useState(false);
  const refresh = async () => {
    if (refreshing) return;
    const before = new Set((digest.data?.tiers.needs_you ?? []).map((i) => i.id));
    setRefreshing(true);
    try {
      type RS = { status: string; note?: string; error?: string | null; new_filings: number | null; new_alerts?: number | null };
      let st = await api<RS>("/api/refresh", { method: "POST" });
      for (let i = 0; i < 45 && st.status === "running"; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        st = await api<RS>("/api/refresh");
      }
      const d = await api<Digest>(`/api/digest?hours=${hours}`);
      digest.setData(d);
      port.reload();
      const fresh = d.tiers.needs_you.filter((i) => !before.has(i.id));
      alertsChanged();
      if (st.status === "failed") setToast("Couldn’t reach BSE. Showing saved filings.");
      else if (st.new_alerts) setToast(`${st.new_alerts} new ${st.new_alerts === 1 ? "alert" : "alerts"}${fresh.length ? `, ${fresh.length} ${fresh.length === 1 ? "filing needs" : "filings need"} you` : ""}`);
      else if (fresh.length) setToast(`${fresh.length} new ${fresh.length === 1 ? "filing needs" : "filings need"} you`);
      else if (st.note) setToast(st.note);
      else setToast(st.new_filings ? `${st.new_filings} new filings, none urgent` : "Up to date. Nothing new.");
    } catch {
      setToast("Refresh failed. Showing saved data.");
    } finally {
      setRefreshing(false);
    }
  };

  const savePrefs = async (p: Partial<Prefs>) => {
    await api<Prefs>("/api/prefs", { method: "PUT", body: JSON.stringify(p) });
    port.reload(); digest.reload(); alertsChanged();
  };

  const onIntent = (i: Intent) => {
    switch (i.kind) {
      case "window": setHours(i.hours); go({ tab: "today" }); break;
      case "research": go({ tab: "research", symbol: i.symbol, rtab: i.tab ?? "promises" }); break;
      case "ask": setPendingQ(i.question); go({ tab: "research", symbol: i.symbol, rtab: "ask" }); break;
      case "settings": setSettings(true); break;
      case "threshold":
        savePrefs({ ...(i.price != null ? { price_move_pct: i.price } : {}), ...(i.volume != null ? { volume_multiple: i.volume } : {}) })
          .then(() => setToast("Thresholds updated"));
        break;
      case "tab": go({ tab: i.tab }); break;
      case "search": go({ tab: "research", symbol: null }); setToast(`No exact symbol for “${i.query}”. Try the NSE symbol.`); break;
    }
  };

  const ui: UI = useMemo(() => ({
    openCitation: (c) => setCite(c),
    openResearch: (symbol, tab) => go({ tab: "research", symbol, rtab: tab ?? "promises" }),
    openItem: (it) => setItem(it),
    openSettings: () => setSettings(true),
    openTerm: (k: string) => setTerm(k),
    openHelp: () => setHelp(true),
    plain,
    researchThis: async (id: string) => {
      try {
        const ctx = await api<Handoff>(`/api/announcements/${id}/research-context`);
        setHandoff(ctx);
        go({ tab: "research", symbol: ctx.symbol, rtab: (ctx.target_tab as ResearchTab) || "promises" });
      } catch { setToast("Couldn’t prepare research context for this filing."); }
    },
  }), [go, plain]);

  const feedback = async (signal: "more" | "less") => {
    if (!item) return;
    await api("/api/feedback", { method: "POST", body: JSON.stringify({ announcement_id: item.id, signal }) });
    digest.reload();
  };

  return (
    <UIContext.Provider value={ui}>
      <div className="mx-auto min-h-full max-w-xl px-4 pb-48 safe-top">
        {IS_DEMO && <DemoBanner />}
        <header className="flex items-center justify-between pt-4 pb-3">
          <button onClick={() => go({ tab: "today" })} className="flex items-center gap-2.5" aria-label="FINN home">
            <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="10" fill="url(#fg)" /><defs><linearGradient id="fg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#3D7BEA" /><stop offset="1" stopColor="#12245A" /></linearGradient></defs><rect x="7" y="15" width="3.4" height="8" rx="1.4" fill="#fff" opacity=".55" /><rect x="12.6" y="9" width="3.4" height="14" rx="1.4" fill="#fff" /><rect x="18.2" y="12.5" width="3.4" height="10.5" rx="1.4" fill="#fff" opacity=".75" /><rect x="23.8" y="17" width="3.4" height="6" rx="1.4" fill="#fff" opacity=".45" /></svg>
            <span className="display text-[22px] font-extrabold">FINN</span>
          </button>
          <div className="flex items-center gap-2">
            <button onClick={() => setTheme(isDark ? "light" : "dark")} aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
              className="grid h-10 w-10 place-items-center rounded-full border border-line bg-surface text-ink">
              <span key={isDark ? "d" : "l"} className="spin-in">{isDark ? <Icon.sun /> : <Icon.moon />}</span>
            </button>
            <button onClick={() => go({ tab: "alerts" })} aria-label={`Alerts${(alertsMeta.data?.unread_count ?? 0) ? `, ${alertsMeta.data?.unread_count} unread` : ""}`}
              className="relative grid h-10 w-10 place-items-center rounded-full border border-line bg-surface text-ink">
              <Icon.bell />
              {(alertsMeta.data?.unread_count ?? 0) > 0 && <span key={alertsMeta.data?.unread_count} className="pop absolute -right-0.5 -top-0.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-marigold px-1 text-[10px] font-bold text-on-marigold num">{alertsMeta.data?.unread_count}</span>}
            </button>
            <button onClick={() => setHelp(true)} aria-label="Help and glossary" className="grid h-10 w-10 place-items-center rounded-full border border-line bg-surface text-ink"><Icon.menu /></button>
          </div>
        </header>

        <main>
          {route.tab === "today" && <Today plain={plain} setPlain={setPlain} digest={digest.data} error={digest.error} loading={digest.loading} hours={hours} setHours={setHours} onRefresh={refresh} refreshing={refreshing} unread={alertsMeta.data?.unread_count ?? 0} />}
          {route.tab === "portfolio" && <Portfolio rows={port.data?.companies ?? null} prefs={prefs} error={port.error} />}
          {route.tab === "alerts" && <AlertsView onChanged={alertsMeta.reload} openRules={() => setSettings(true)} refreshKey={alertsKey} />}
          {route.tab === "research" && (
            <Research symbol={route.symbol} tab={route.rtab} setTab={(t) => go({ rtab: t })}
              handoff={handoff && handoff.symbol === route.symbol ? handoff : null} clearHandoff={() => setHandoff(null)}
              askHandoff={(q) => { setPendingQ(q); go({ rtab: "ask" }); }}
              portfolio={(port.data?.companies ?? []).map((c) => ({ symbol: c.symbol, name: c.name }))}
              backToEvent={async (id) => { try { setItem(await api<DigestItem>(`/api/announcements/${id}`)); } catch { setToast("That filing is no longer available."); } }}
              pendingQuestion={pendingQ} clearPending={() => setPendingQ(null)} suggestions={DEMO} />
          )}
        </main>
      </div>

      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-40 bg-gradient-to-t from-[var(--paper-2)] via-[var(--paper-2)]/85 to-transparent pt-8 safe-bottom">
        <div className="pointer-events-auto mx-auto max-w-xl px-3 pb-2">
          <div className="mb-2"><CommandBar known={known} names={names} current={route.tab === "research" ? route.symbol : null} onIntent={onIntent} /></div>
          <nav aria-label="Main" className="relative grid grid-cols-4 rounded-[26px] border border-line bg-surface p-1.5">
            <span aria-hidden="true" className="absolute top-1.5 bottom-1.5 rounded-[20px] bg-marigold-wash"
              style={{ width: "calc((100% - 12px) / 4)", left: `calc(6px + ${["today", "alerts", "portfolio", "research"].indexOf(route.tab)} * (100% - 12px) / 4)`, transition: "left .42s cubic-bezier(.3,1.3,.45,1)" }} />
            {([["today", "Today", Icon.home], ["alerts", "Alerts", Icon.bell], ["portfolio", "Portfolio", Icon.pie], ["research", "Research", Icon.search]] as [Tab, string, () => JSX.Element][]).map(([t, label, Ico]) => (
              <button key={t} onClick={() => go({ tab: t })} aria-current={route.tab === t}
                className={`relative z-[1] flex min-h-[52px] flex-col items-center justify-center gap-0.5 rounded-[20px] text-[11.5px] font-semibold ${route.tab === t ? "text-marigold" : "text-muted"}`}>
                <span className={route.tab === t ? "pop" : ""} key={route.tab === t ? "on" : "off"}><Ico /></span>
                {label}
                {t === "alerts" && (alertsMeta.data?.unread_count ?? 0) > 0 && (
                  <span className="absolute right-[22%] top-1.5 rounded-full bg-marigold px-1.5 text-[10px] font-bold text-on-marigold num" aria-label={`${alertsMeta.data?.unread_count} unread`}>{alertsMeta.data?.unread_count}</span>
                )}
              </button>
            ))}
          </nav>
        </div>
      </div>

      {toast && <div className="fixed inset-x-0 bottom-36 z-50 mx-auto w-fit rounded-full bg-ink px-4 py-2 text-[14px] text-paper" role="status">{toast}</div>}

      <Sheet open={!!item} onClose={() => setItem(null)} title={item && (
        <div>
          <div className="display-tight text-[15px] font-semibold tracking-wide">{item.symbol} <span className="font-sans text-[13px] font-normal text-muted">{item.category_label}</span></div>
          <div className="text-[13px] text-muted">{item.company}</div>
        </div>
      )}>
        {item && <ItemDetail item={item} onFeedback={feedback} />}
      </Sheet>

      <Sheet open={!!cite} onClose={() => setCite(null)} title={cite && <div className="display text-[16px] font-semibold">{cite.label ?? "Source"}, page {cite.page}</div>}>
        {cite && <CitationView docId={cite.doc_id} page={cite.page} quote={cite.quote} />}
      </Sheet>

      <Sheet open={!!term} onClose={() => setTerm(null)} title={term && <div className="display text-[19px] font-semibold">{GLOSSARY[term]?.term}</div>}>
        {term && <ExplainView k={term} onOpen={setTerm} />}
      </Sheet>

      <Sheet open={help} onClose={() => setHelp(false)} title={<div className="display text-[19px] font-semibold">Help and glossary</div>}>
        <HelpView theme={theme} setTheme={setTheme} plain={plain} setPlain={setPlain} onOpen={(k) => setTerm(k)} onTour={() => { setHelp(false); setOnboard(true); }} />
      </Sheet>

      <Sheet open={onboard} onClose={() => { setOnboard(false); store("finn.onboarded", "1"); }} title={<div className="display text-[16px] font-semibold text-muted">Welcome to FINN</div>}>
        <Onboarding portfolio={(port.data?.companies ?? []).map((c) => ({ symbol: c.symbol, name: c.name }))} plain={plain} setPlain={setPlain}
          onDone={() => { setOnboard(false); store("finn.onboarded", "1"); }}
          go={(w) => (typeof w === "object" ? go({ tab: "research", symbol: w.symbol, rtab: "numbers" }) : go({ tab: w }))} />
      </Sheet>

      <Sheet open={settings} onClose={() => setSettings(false)} title={<div className="display text-[18px] font-semibold">Alert rules</div>}>
        <WhatsAppPanel sample={(() => { const top = digest.data?.tiers.needs_you[0]; return top ? itemMessage(top) : null; })()} />
          <RulesView symbols={(port.data?.companies ?? []).map((c) => ({ symbol: c.symbol, name: c.name }))}
          onSaved={(msg) => { setToast(msg); alertsChanged(); port.reload(); digest.reload(); }} />
      </Sheet>
    </UIContext.Provider>
  );
}
