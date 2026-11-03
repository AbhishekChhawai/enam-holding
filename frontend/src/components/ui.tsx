import { createContext, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { Cite, DigestItem, Verdict } from "../types";
import type { ResearchTab } from "../intent";

export interface UI {
  openCitation: (c: Cite & { quote?: string; label?: string }) => void;
  openResearch: (symbol: string, tab?: ResearchTab) => void;
  openItem: (item: DigestItem) => void;
  openSettings: () => void;
  researchThis: (announcementId: string) => void;
  openTerm: (key: string) => void;
  openHelp: () => void;
  plain: boolean;
}
export const UIContext = createContext<UI | null>(null);
export const useUI = () => {
  const ui = useContext(UIContext);
  if (!ui) throw new Error("UIContext missing");
  return ui;
};

export function Sheet({ open, onClose, title, children }: {
  open: boolean; onClose: () => void; title?: ReactNode; children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", onKey); document.body.style.overflow = ""; prev?.focus(); };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center" role="dialog" aria-modal="true">
      <button aria-label="Close" className="fade absolute inset-0 bg-[#06102a]/45 backdrop-blur-[2px]" onClick={onClose} />
      <div ref={ref} tabIndex={-1}
        className="sheet relative w-full max-w-lg max-h-[88vh] overflow-y-auto rounded-t-[28px] bg-paper safe-bottom outline-none shadow-[0_-20px_50px_-20px_rgba(0,0,0,.45)]">
        <div aria-hidden="true" className="mx-auto mt-2 h-1 w-10 rounded-full bg-line" />
        <div className="sticky top-0 z-10 flex items-start gap-3 border-b border-line bg-paper px-4 pt-2 pb-3">
          <div className="min-w-0 flex-1">{title}</div>
          <button onClick={onClose} className="-mr-2 -mt-1 h-10 w-10 shrink-0 rounded-full text-muted hover:text-ink" aria-label="Close">✕</button>
        </div>
        <div className="px-4 py-4">{children}</div>
      </div>
    </div>
  );
}

/** Segmented control with a thumb that springs to the selected option (iOS-style). */
export function Segmented<T extends string | number>({ value, options, onChange, label, size = "md" }: {
  value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string; size?: "sm" | "md";
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState<{ x: number; w: number } | null>(null);
  useLayoutEffect(() => {
    const el = wrap.current?.querySelector<HTMLElement>(`[data-v="${String(value)}"]`);
    if (el) setThumb({ x: el.offsetLeft, w: el.offsetWidth });
  }, [value, options.length]);
  return (
    <div ref={wrap} role="radiogroup" aria-label={label} className="relative inline-flex rounded-full border border-line bg-wash p-[3px]">
      {thumb && <span aria-hidden="true" className="absolute top-[3px] bottom-[3px] rounded-full bg-surface shadow-[0_2px_8px_-2px_rgba(14,28,54,.25)]"
        style={{ left: thumb.x, width: thumb.w, transition: "left .38s cubic-bezier(.3,1.35,.45,1), width .38s cubic-bezier(.3,1.35,.45,1)" }} />}
      {options.map((o) => (
        <button key={String(o.value)} data-v={String(o.value)} role="radio" aria-checked={o.value === value} onClick={() => onChange(o.value)}
          className={`relative z-[1] min-h-[32px] rounded-full ${size === "sm" ? "px-2.5 text-[12px]" : "px-3.5 text-[13px]"} font-medium num ${o.value === value ? "text-ink" : "text-muted"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** Two-letter monogram, like a bank app's merchant badge. */
export function Avatar({ symbol, size = 38 }: { symbol: string; size?: number }) {
  const t = symbol.replace(/[^A-Z0-9]/gi, "");
  return <span aria-hidden="true" className="avatar" style={{ width: size, height: size, fontSize: size * 0.34 }}>{(t[0] ?? "") + (t[1] ?? "")}</span>;
}

/** Counts up to a number when it first appears (skipped under reduced motion). */
export function useCountUp(target: number, ms = 700) {
  const [v, setV] = useState(target);
  useEffect(() => {
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) { setV(target); return; }
    let raf = 0; const t0 = performance.now();
    const step = (t: number) => { const k = Math.min(1, (t - t0) / ms); setV(Math.round(target * (1 - Math.pow(1 - k, 3)))); if (k < 1) raf = requestAnimationFrame(step); };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

const P = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
export const Icon = {
  home: () => <svg width="22" height="22" viewBox="0 0 24 24" {...P}><path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4.5v-6h-5v6H5a1 1 0 0 1-1-1z" /></svg>,
  bell: () => <svg width="20" height="20" viewBox="0 0 24 24" {...P}><path d="M6 17V11a6 6 0 1 1 12 0v6l1.5 2h-15z" /><path d="M10 21h4" /></svg>,
  pie: () => <svg width="22" height="22" viewBox="0 0 24 24" {...P}><path d="M12 3v9h9a9 9 0 1 1-9-9z" /><path d="M15 3.5A9 9 0 0 1 20.5 9H15z" /></svg>,
  search: () => <svg width="22" height="22" viewBox="0 0 24 24" {...P}><circle cx="11" cy="11" r="6.5" /><path d="m20 20-4.2-4.2" /></svg>,
  menu: () => <svg width="20" height="20" viewBox="0 0 24 24" {...P}><path d="M5 7h14M5 12h14M5 17h9" /></svg>,
  sun: () => <svg width="20" height="20" viewBox="0 0 24 24" {...P}><circle cx="12" cy="12" r="4" /><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4" /></svg>,
  moon: () => <svg width="20" height="20" viewBox="0 0 24 24" {...P}><path d="M20 14.5A8 8 0 1 1 9.5 4 6.5 6.5 0 0 0 20 14.5z" /></svg>,
  refresh: () => <svg width="20" height="20" viewBox="0 0 24 24" {...P}><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></svg>,
  sliders: () => <svg width="20" height="20" viewBox="0 0 24 24" {...P}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></svg>,
  spark: () => <svg width="20" height="20" viewBox="0 0 24 24" {...P}><path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /></svg>,
  trend: () => <svg width="14" height="14" viewBox="0 0 24 24" {...P}><path d="m4 16 5-5 4 4 7-7" /><path d="M15 8h5v5" /></svg>,
};

export function Spark({ values, width = 72, height = 24, tone }: { values: number[]; width?: number; height?: number; tone?: "up" | "down" }) {
  if (!values || values.length < 2) return <span className="inline-block" style={{ width, height }} />;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => [(i / (values.length - 1)) * (width - 4) + 2, height - 2 - ((v - min) / span) * (height - 4)]);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  const color = tone === "up" ? "var(--up)" : tone === "down" ? "var(--down)" : "var(--muted)";
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <path d={d} fill="none" stroke="var(--muted)" strokeWidth="1.25" strokeLinejoin="round" opacity="0.7" />
      <circle cx={last[0]} cy={last[1]} r="2.2" fill={color} />
    </svg>
  );
}

const VERDICT: Record<Verdict, { label: string; cls: string; glyph: string }> = {
  delivered: { label: "Delivered", cls: "bg-up-wash text-up", glyph: "✓" },
  partly: { label: "Partly", cls: "bg-marigold-wash text-ink", glyph: "◐" },
  missed: { label: "Missed", cls: "bg-down-wash text-down", glyph: "✕" },
  in_progress: { label: "In progress", cls: "border border-line text-muted", glyph: "…" },
  too_early: { label: "Too early", cls: "border border-line text-muted", glyph: "○" },
  unverifiable: { label: "Can’t verify", cls: "border border-dashed border-line text-muted", glyph: "?" },
};
export const verdictMeta = (v: Verdict) => VERDICT[v] ?? VERDICT.unverifiable;
export function VerdictChip({ v }: { v: Verdict }) {
  const m = verdictMeta(v);
  return (
    <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[12px] font-medium ${m.cls}`}>
      <span aria-hidden="true">{m.glyph}</span>{m.label}
    </span>
  );
}

export function CiteChip({ c, label, quote }: { c: Cite; label?: string; quote?: string }) {
  const ui = useUI();
  return (
    <button onClick={() => ui.openCitation({ ...c, quote, label })}
      className="inline-flex min-h-[32px] items-center gap-1 rounded-md border border-line px-2 py-1 text-[12px] text-muted hover:border-ink hover:text-ink num">
      {label ? `${label}, ` : ""}p.{c.page}
    </button>
  );
}

export function Loading({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3 py-8 text-muted" role="status">
      <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-marigold opacity-60" /><span className="relative inline-flex h-2 w-2 rounded-full bg-marigold" /></span>
      <span className="text-[14px]">{text}</span>
    </div>
  );
}

export function Notice({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "warn" }) {
  return (
    <div className={`rounded-xl px-3 py-2.5 text-[14px] ${tone === "warn" ? "bg-marigold-wash" : "bg-wash text-muted"}`}>{children}</div>
  );
}

export function SectionHead({ title, note, right }: { title: string; note?: ReactNode; right?: ReactNode }) {
  return (
    <div className="mt-6 mb-2 flex items-baseline justify-between gap-3">
      <h2 className="display text-[19px] font-semibold">{title}{note != null && <span className="ml-2 font-sans text-[13px] font-normal text-muted num">{note}</span>}</h2>
      {right}
    </div>
  );
}
