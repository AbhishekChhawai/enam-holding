import { useMemo, useState, type PointerEvent } from "react";
import { useApi } from "../api";
import { istDay, pct, price, signClass } from "../format";
import { Segmented } from "./ui";

interface Bar { date: string; close: number; volume: number | null; pct: number | null; volume_multiple: number | null }
interface Prices { symbol: string; count: number; bars: Bar[]; adjustment: string; provider: string | null; to: string | null; freshness: string }

const RANGES = [{ value: "1m", label: "1M" }, { value: "3m", label: "3M" }, { value: "6m", label: "6M" }, { value: "1y", label: "1Y" }];
const W = 340, H = 150, VOL_H = 30, PAD_R = 2;
const vol = new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 });

/** End-of-day price with touch scrubbing. Range and axis labels are explicit so the scale never misleads. */
export default function PriceChart({ symbol }: { symbol: string }) {
  const [range, setRange] = useState("3m");
  const [hover, setHover] = useState<number | null>(null);
  const { data, error, loading } = useApi<Prices>(`/api/companies/${symbol}/prices?period=${range}`);
  const bars = data?.bars ?? [];

  const g = useMemo(() => {
    if (bars.length < 2) return null;
    const closes = bars.map((b) => b.close);
    const lo = Math.min(...closes), hi = Math.max(...closes), span = hi - lo || 1;
    const vmax = Math.max(...bars.map((b) => b.volume ?? 0)) || 1;
    const x = (i: number) => (i / (bars.length - 1)) * (W - PAD_R);
    const y = (c: number) => 6 + (1 - (c - lo) / span) * (H - VOL_H - 16);
    const line = bars.map((b, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(b.close).toFixed(1)}`).join(" ");
    const area = `${line} L${x(bars.length - 1).toFixed(1)},${H - VOL_H - 4} L0,${H - VOL_H - 4} Z`;
    return { lo, hi, x, y, line, area, vmax };
  }, [bars]);

  if (error) return <p className="mt-2 text-[13px] text-muted">{error.includes("not registered") ? "Prices appear once FINN finishes registering this company." : `Prices unavailable: ${error}`}</p>;
  if (loading && !data) return <div className="mt-2 h-[190px] animate-pulse rounded-2xl bg-surface" aria-label="Loading prices" />;
  if (!g) return <p className="mt-2 text-[13px] text-muted">Not enough price history yet.</p>;

  const i = hover ?? bars.length - 1;
  const b = bars[i];
  const first = bars[0].close, change = (bars[bars.length - 1].close / first - 1) * 100;
  const up = change >= 0;
  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const idx = Math.round(((e.clientX - r.left) / r.width) * (bars.length - 1));
    setHover(Math.max(0, Math.min(bars.length - 1, idx)));
  };

  return (
    <div className="rounded-2xl bg-surface px-3 pb-3 pt-2.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="num" aria-live="polite">
          <div className="text-[18px] font-semibold">{price(b.close)}</div>
          <div className="text-[12px] text-muted">
            {istDay(b.date)}{b.pct != null && <span className={`ml-1.5 ${signClass(b.pct)}`}>{pct(b.pct)} day</span>}
            {b.volume != null && <span className="ml-1.5">vol {vol.format(b.volume)}{b.volume_multiple != null ? ` (${b.volume_multiple.toFixed(1)}× avg)` : ""}</span>}
          </div>
        </div>
        <Segmented size="sm" label="Price range" value={range} onChange={(v) => { setRange(v); setHover(null); }} options={RANGES} />
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full select-none" style={{ touchAction: "pan-y" }} role="img"
        aria-label={`${symbol} closing price over ${range.toUpperCase()}: from ${price(first)} to ${price(bars[bars.length - 1].close)} (${pct(change)})`}
        onPointerMove={onMove} onPointerDown={onMove} onPointerLeave={() => setHover(null)}>
        <path key={`a${range}`} d={g.area} fill={up ? "var(--up)" : "var(--down)"} fillOpacity="0.12" className="fade" />
        <path key={`l${range}`} d={g.line} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"
          pathLength={1} className="draw" style={{ ["--len" as string]: 1 }} />
        {bars.map((bb, k) => {
          const h = ((bb.volume ?? 0) / g.vmax) * (VOL_H - 4);
          const bw = Math.max(1, (W - PAD_R) / bars.length - 1);
          return <rect key={bb.date} x={g.x(k) - bw / 2} y={H - h} width={bw} height={h} fill="var(--muted)" opacity={k === i ? 0.9 : 0.3} />;
        })}
        {hover != null && (
          <>
            <line x1={g.x(i)} x2={g.x(i)} y1={0} y2={H} stroke="var(--ink)" strokeWidth="0.75" opacity="0.5" />
            <circle cx={g.x(i)} cy={g.y(b.close)} r="3" fill="var(--ink)" />
          </>
        )}
        <text x={W - 4} y={12} textAnchor="end" fontSize="9" fill="var(--muted)">{price(g.hi)}</text>
        <text x={W - 4} y={H - VOL_H - 8} textAnchor="end" fontSize="9" fill="var(--muted)">{price(g.lo)}</text>
      </svg>
      <div className="mt-1 flex justify-between text-[11px] text-muted num">
        <span>{istDay(bars[0].date)}</span>
        <span className={signClass(change)}>{pct(change)} over {range.toUpperCase()}</span>
        <span>{istDay(bars[bars.length - 1].date)}</span>
      </div>
      <p className="mt-1.5 text-[11px] text-muted">
        {data?.provider?.startsWith("nse-bhavcopy") ? "End-of-day closes from NSE’s official bhavcopy (via the open eod2_data archive), adjusted for splits and bonuses."
          : `End-of-day closes (${data?.provider ?? "provider"}), ${data?.adjustment?.split(";")[0].toLowerCase()}.`} Not live. Drag across the chart to read any session.
      </p>
    </div>
  );
}
