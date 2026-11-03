import React, { useMemo, useState } from "react";
import { useApi } from "../api";
import type { Prefs, PriceSnap } from "../types";
import { istDay, pct, price, signClass } from "../format";
import { Avatar, Loading, Notice, SectionHead, Segmented, Spark, useCountUp, useUI } from "../components/ui";
import { Term } from "../components/Explain";

type Row = { symbol: string; name: string; sector: string; price: PriceSnap | null };
type Sort = "value" | "move" | "name";
interface Group { key: string; name: string; count: number; invested: number; current: number; returns: number; returns_pct: number | null; allocation_pct: number }
interface Holding {
  symbol: string; name: string; kind: string; asset_class: string; sector: string; weight: number; invested: number; current: number;
  returns: number; returns_pct: number | null; day_pct: number | null; allocation_pct: number; avg_cost: number; last_close: number; bought_on: string;
  meta: { tracks?: string; note?: string; underlying_name?: string };
  horizons?: Hz;
  underlying?: { name: string; day_pct: number | null; since_start_pct: number | null; last_date: string };
}
interface Analysis {
  status: string; as_of: string; invested: number; current: number; returns: number; returns_pct: number | null;
  mock: { amount: number; start: string; bought_on: string; method: string };
  benchmark: { name: string; returns_pct: number | null; difference_pp: number | null; from: string; to: string; horizons?: Hz } | null;
  by_asset: Group[]; by_sector: Group[]; holdings: Holding[]; history: { date: string; value: number }[]; missing: string[];
  horizons?: { order: string[]; note: string; portfolio: Hz; by_asset: Record<string, Hz> };
}
type Hz = Record<string, { pct: number | null; from: string } | null>;

const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const rupees = (v: number) => `₹${inr0.format(Math.round(v))}`;
const signed = (v: number) => `${v >= 0 ? "+" : "−"}\u2060₹${inr0.format(Math.abs(Math.round(v)))}`;
const ASSET_COLOR: Record<string, string> = { Equity: "#4F7CF7", Debt: "#7FB3E8", Gold: "#E9B949", International: "#3DC48C" };
const SECTOR_COLORS = ["#4F7CF7", "#3DC48C", "#E9B949", "#7FB3E8", "#B08CF5", "#F28B82", "#5CC8D6", "#9AA9C9", "#F2A766", "#86D08A", "#D88FD6", "#6E8CC9", "#C5B358", "#8FC0FF", "#E07A9A", "#A0C4B8", "#C9A0DC", "#7BA05B"];
const TAG: Record<string, string> = { Debt: "Debt", Gold: "Gold", International: "Global" };

export default function Portfolio({ rows, prefs, error }: { rows: Row[] | null; prefs: Prefs | null; error: string | null }) {
  const ui = useUI();
  const an = useApi<Analysis>("/api/portfolio/analysis");
  const [sort, setSort] = useState<Sort>("value");
  const byHolding = useMemo(() => new Map((an.data?.holdings ?? []).map((h) => [h.symbol, h])), [an.data]);
  const sorted = useMemo(() => {
    const r = [...(rows ?? [])];
    if (sort === "value") r.sort((a, b) => (byHolding.get(b.symbol)?.current ?? 0) - (byHolding.get(a.symbol)?.current ?? 0));
    if (sort === "move") r.sort((a, b) => Math.abs(b.price?.pct ?? 0) - Math.abs(a.price?.pct ?? 0));
    if (sort === "name") r.sort((a, b) => a.symbol.localeCompare(b.symbol));
    return r;
  }, [rows, sort, byHolding]);
  const a = an.data?.status === "ok" ? an.data : null;

  return (
    <div>
      {a ? <Hero a={a} /> : an.loading ? <div className="h-[300px] animate-pulse rounded-[28px] bg-surface" aria-label="Loading portfolio analysis" /> : null}
      {an.data && an.data.status !== "ok" && <Notice>Portfolio analysis needs price history. Run ingestion to load real EOD prices.</Notice>}
      {a?.horizons && <Horizons a={a} />}
      {a && (
        <>
          <Allocation title="Asset allocation" groups={a.by_asset} colors={(g) => ASSET_COLOR[g.key] ?? "#9AA9C9"} half
            caption={<>Spread across stocks, <Term k="debt">debt</Term>, gold and international funds, so one market doesn’t drive everything.</>} />
          <Allocation title="Sector allocation" groups={a.by_sector} colors={(_, i) => SECTOR_COLORS[i % SECTOR_COLORS.length]} />
        </>
      )}

      <div className="mt-6 flex items-center justify-between gap-3">
        <h2 className="display text-[20px] font-bold">{rows ? `${rows.length} holdings` : "Holdings"}</h2>
        <Segmented size="sm" label="Sort" value={sort} onChange={setSort} options={[{ value: "value", label: "Value" }, { value: "move", label: "Move" }, { value: "name", label: "A–Z" }]} />
      </div>
      <p className="mt-1 text-[13px] text-muted">
        End-of-day closes{rows?.find((r) => r.price)?.price?.date ? ` for ${istDay(rows.find((r) => r.price)!.price!.date)}` : ""}. Flags at ±{prefs?.price_move_pct ?? 5}% or {prefs?.volume_multiple ?? 2}× volume.
      </p>
      {error && <div className="mt-3"><Notice tone="warn">{error}</Notice></div>}
      {!rows && !error && <Loading text="Loading prices" />}
      <ul className="rise mt-3 rounded-2xl bg-surface px-4" style={{ animationDelay: "120ms" }}>
        {sorted.map((r) => {
          const p = r.price, h = byHolding.get(r.symbol);
          const flagged = p?.flags?.some((f) => f === "price" || f === "volume");
          return (
            <li key={r.symbol} className="border-t border-line first:border-t-0">
              <button onClick={() => ui.openResearch(r.symbol, h?.kind === "etf" ? "numbers" : "promises")} className="flex w-full items-center gap-3 py-2.5 text-left">
                <Avatar symbol={r.symbol} size={36} />
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="display-tight min-w-0 truncate text-[15px] font-bold">{r.symbol}</span>
                    {flagged && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-marigold" aria-label="Crossed your threshold" />}
                  </div>
                  <div className="mt-0.5 flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-[12px] text-muted num">
                    {h?.kind === "etf" && <span className="rounded-full border border-line px-1.5 text-[10.5px] font-semibold">ETF</span>}
                    {h && TAG[h.asset_class] && <span className="rounded-full bg-marigold-wash px-1.5 text-[10.5px] font-semibold text-marigold">{TAG[h.asset_class]}</span>}
                    <span>{h ? `${rupees(h.current)} (${h.allocation_pct.toFixed(1)}%)` : r.name}</span>
                  </div>
                </div>
                <Spark width={48} values={p?.spark ?? []} tone={(p?.pct ?? 0) >= 0 ? "up" : "down"} />
                <div className="w-[84px] shrink-0 text-right num">
                  <div className="text-[14px] font-semibold">{price(p?.close)}</div>
                  <div className={`text-[12.5px] ${signClass(p?.pct)}`}>{pct(p?.pct)} day</div>
                  {h?.returns_pct != null && <div className={`text-[11px] ${signClass(h.returns_pct)}`}>{pct(h.returns_pct)} total</div>}
                </div>
              </button>
            </li>
          );
        })}
      </ul>
      {a && <p className="mt-3 text-[12px] text-muted">{a.mock.method} Bought on {istDay(a.mock.bought_on)}; values as of {istDay(a.as_of)}. Not live prices.</p>}
    </div>
  );
}

function Hero({ a }: { a: Analysis }) {
  const [range, setRange] = useState<"1m" | "3m" | "all">("all");
  const cur = useCountUp(Math.round(a.current), 900);
  const hist = useMemo(() => {
    const n = range === "1m" ? 22 : range === "3m" ? 66 : a.history.length;
    return a.history.slice(-n);
  }, [a.history, range]);
  const W = 340, H = 120;
  const vals = hist.map((x) => x.value), lo = Math.min(a.invested, ...vals), hi = Math.max(a.invested, ...vals), span = hi - lo || 1;
  const x = (i: number) => (i / Math.max(1, hist.length - 1)) * W, y = (v: number) => 6 + (1 - (v - lo) / span) * (H - 12);
  const line = hist.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const up = a.returns >= 0;
  const b = a.benchmark;
  return (
    <section className="navy rise rounded-[28px] px-5 pb-4 pt-4">
      <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
        <div>
          <div className="text-[13px] text-muted">Current value</div>
          <div className="display text-[28px] font-extrabold leading-tight num min-[360px]:text-[34px]">₹{inr0.format(cur)}</div>
        </div>
        <div className="text-right">
          <div className="text-[13px] text-muted">Invested</div>
          <div className="display text-[18px] font-bold num">{rupees(a.invested)}</div>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        <span className={`chip font-semibold num ${signClass(a.returns)}`}>{signed(a.returns)} ({pct(a.returns_pct, 2)})</span>
        {b?.difference_pp != null && (
          <span className="chip num">{b.difference_pp >= 0 ? "Ahead of" : "Behind"} {b.name} by {Math.abs(b.difference_pp).toFixed(2)} pts</span>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-3 w-full" role="img" aria-label={`Portfolio value from ${rupees(vals[0] ?? 0)} to ${rupees(vals[vals.length - 1] ?? 0)}; invested ${rupees(a.invested)}`}>
        <line x1="0" x2={W} y1={y(a.invested)} y2={y(a.invested)} stroke="rgba(255,255,255,.45)" strokeDasharray="4 4" strokeWidth="1" />
        <path key={range} d={line} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth="2" strokeLinejoin="round" pathLength={1} className="draw" style={{ ["--len" as string]: 1 }} />
      </svg>
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-[11.5px] text-muted">Solid: value. Dashed: invested.</span>
        <Segmented size="sm" label="History range" value={range} onChange={setRange} options={[{ value: "1m", label: "1M" }, { value: "3m", label: "3M" }, { value: "all", label: "Since start" }]} />
      </div>
      {b && <p className="mt-2 text-[12px] text-muted">{b.name}: {pct(b.returns_pct, 2)} over the same period ({istDay(b.from)} to {istDay(b.to)}). Portfolio: {pct(a.returns_pct, 2)}.</p>}
    </section>
  );
}

function Allocation({ title, groups, colors, half, caption }: { title: string; groups: Group[]; colors: (g: Group, i: number) => string; half?: boolean; caption?: React.ReactNode }) {
  const R = 70, C = (half ? Math.PI : 2 * Math.PI) * R;
  let at = 0;
  const segs = groups.map((g, i) => { const len = (g.allocation_pct / 100) * C; const s = { g, len, off: at, color: colors(g, i) }; at += len; return s; });
  return (
    <section className="rise mt-5 rounded-2xl bg-surface px-4 pb-2 pt-4" style={{ animationDelay: "100ms" }}>
      <SectionHead title={title} />
      {caption && <p className="-mt-1 text-[12.5px] text-muted">{caption}</p>}
      <div className={`relative mx-auto mt-2 ${half ? "h-[110px] w-[220px]" : "h-[180px] w-[180px]"}`}>
        <svg viewBox={half ? "0 0 180 95" : "0 0 180 180"} className={`h-full w-full ${half ? "" : "-rotate-90"}`} role="img"
          aria-label={`${title}: ${groups.map((g) => `${g.name} ${g.allocation_pct.toFixed(1)}%`).join(", ")}`}>
          {half ? (
            <g transform="translate(90,90) scale(-1,1) rotate(180)">
              {segs.map((s, i) => <circle key={s.g.key} r={R} fill="none" stroke={s.color} strokeWidth="22" strokeDasharray={`${Math.max(0, s.len - 2)} ${2 * Math.PI * R}`} strokeDashoffset={-s.off}
                className="fade" style={{ animationDelay: `${i * 120}ms` }} />)}
            </g>
          ) : (
            segs.map((s, i) => <circle key={s.g.key} cx="90" cy="90" r={R} fill="none" stroke={s.color} strokeWidth="22" strokeDasharray={`${Math.max(0, s.len - 2)} ${C}`} strokeDashoffset={-s.off}
              className="fade" style={{ animationDelay: `${i * 70}ms` }} />)
          )}
        </svg>
        <div className={`absolute inset-x-0 text-center text-[12px] font-semibold text-muted ${half ? "bottom-0" : "top-1/2 -translate-y-1/2"}`}>{groups.length} {half ? (groups.length === 1 ? "asset class" : "asset classes") : (groups.length === 1 ? "sector" : "sectors")}</div>
      </div>
      <table className="mt-3 w-full text-[13px] num">
        <thead><tr className="text-left text-[12px] text-muted"><th className="pb-1.5 font-normal">{half ? "Asset" : "Sector"}</th><th className="pb-1.5 text-right font-normal">Current (share)</th><th className="pb-1.5 text-right font-normal">Returns</th></tr></thead>
        <tbody>
          {segs.map((s) => (
            <tr key={s.g.key} className="border-t border-line">
              <td className="py-2"><span className="mr-2 inline-block h-3 w-1 rounded-full align-middle" style={{ background: s.color }} />{s.g.name}<span className="block pl-3 text-[11.5px] text-muted">{s.g.count} {s.g.count === 1 ? "holding" : "holdings"}</span></td>
              <td className="whitespace-nowrap py-2 pl-2 text-right">{rupees(s.g.current)}<span className="block text-[11.5px] text-muted">{s.g.allocation_pct.toFixed(1)}%</span></td>
              <td className={`whitespace-nowrap py-2 pl-2 text-right ${signClass(s.g.returns)}`}>{signed(s.g.returns)}<span className="block text-[11.5px]">({pct(s.g.returns_pct)})</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

const HZ_LABEL: Record<string, string> = { "1W": "the last week", "1M": "the last month", "3M": "the last 3 months", "6M": "the last 6 months", YTD: "this year so far", "1Y": "the last year" };

/** Same maths at every horizon: what moved, against the benchmark, by asset class, and the biggest movers. */
function Horizons({ a }: { a: Analysis }) {
  const hz = a.horizons!;
  const [k, setK] = useState(hz.order.find((x) => hz.portfolio[x]) ?? "1M");
  const port = hz.portfolio[k], bench = a.benchmark?.horizons?.[k];
  const movers = a.holdings.map((h) => ({ h, v: h.horizons?.[k]?.pct ?? null })).filter((x) => x.v != null).sort((x, y) => (y.v as number) - (x.v as number));
  const top = movers.slice(0, 3), bottom = movers.slice(-3).reverse().filter((x) => !top.includes(x));
  return (
    <section className="rise mt-5 rounded-2xl bg-surface px-4 pb-3 pt-4" style={{ animationDelay: "60ms" }}>
      <SectionHead title="Returns by horizon" />
      <div className="-mt-1 overflow-x-auto scrollbar-none"><Segmented size="sm" label="Horizon" value={k} onChange={setK} options={hz.order.map((x) => ({ value: x, label: x }))} /></div>
      <p className="mt-3 text-[15px] leading-snug num">
        {port?.pct != null ? <>Over {HZ_LABEL[k]}, the portfolio is <b className={signClass(port.pct)}>{pct(port.pct, 2)}</b></> : <>The mock portfolio didn’t exist for all of {HZ_LABEL[k]}</>}
        {bench?.pct != null && <>; {a.benchmark!.name} is <b className={signClass(bench.pct)}>{pct(bench.pct, 2)}</b></>}.
      </p>
      <div className="mt-2 grid grid-cols-2 gap-2">
        {Object.entries(hz.by_asset).map(([cls, h]) => (
          <div key={cls} className="rounded-xl bg-wash px-3 py-2">
            <div className="text-[12px] text-muted">{cls === "Equity" ? "Stocks" : cls}</div>
            <div className={`text-[16px] font-bold num ${signClass(h[k]?.pct)}`}>{h[k]?.pct != null ? pct(h[k]!.pct, 1) : "–"}</div>
          </div>
        ))}
      </div>
      {movers.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-3 text-[13px] num">
          <div><div className="mb-1 text-[12px] font-medium text-muted">Best</div>{top.map(({ h, v }) => <div key={h.symbol} className="flex justify-between"><span className="truncate">{h.symbol}</span><span className={signClass(v)}>{pct(v)}</span></div>)}</div>
          <div><div className="mb-1 text-[12px] font-medium text-muted">Worst</div>{bottom.map(({ h, v }) => <div key={h.symbol} className="flex justify-between"><span className="truncate">{h.symbol}</span><span className={signClass(v)}>{pct(v)}</span></div>)}</div>
        </div>
      )}
      <p className="mt-2 text-[11.5px] text-muted">Measured in trading sessions from end-of-day closes. {hz.note}</p>
    </section>
  );
}
