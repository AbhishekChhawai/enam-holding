import { useState } from "react";
import type { Digest } from "../types";
import { ago, istDay, windowLabel } from "../format";
import { AttentionStrip, FeedItem, MoveRow } from "../components/Feed";
import { Icon, Notice, SectionHead, Segmented, useCountUp, useUI } from "../components/ui";

const WINDOWS = [
  { value: 24, label: "24h" }, { value: 72, label: "3d" }, { value: 168, label: "7d" }, { value: 720, label: "30d" },
];

type Mode = "quick" | "standard" | "deep";
const MODES: { value: Mode; label: string }[] = [{ value: "quick", label: "Quick" }, { value: "standard", label: "Standard" }, { value: "deep", label: "Deep" }];

export default function Today({ digest, error, loading, hours, setHours, onRefresh, refreshing, unread = 0, plain, setPlain }: {
  digest: Digest | null; error: string | null; loading: boolean; hours: number; setHours: (h: number) => void;
  onRefresh: () => void; refreshing: boolean; unread?: number; plain: boolean; setPlain: (v: boolean) => void;
}) {
  const ui = useUI();
  const [showRoutine, setShowRoutine] = useState(false);
  const [mode, setModeState] = useState<Mode>(() => {
    try { return (localStorage.getItem("finn.mode") as Mode) || "standard"; } catch { return "standard"; }
  });
  const setMode = (m: Mode) => { setModeState(m); try { localStorage.setItem("finn.mode", m); } catch { /* private mode */ } };
  const quick = mode === "quick", deep = mode === "deep";
  const needs = digest ? (quick ? digest.tiers.needs_you.slice(0, 5) : digest.tiers.needs_you) : [];
  const moves = digest ? (quick ? digest.moves.slice(0, 3) : digest.moves) : [];
  const windows = WINDOWS.some((w) => w.value === hours) ? WINDOWS : [...WINDOWS, { value: hours, label: `${Math.round(hours / 24)}d` }];
  const n = useCountUp(digest?.counts.needs_you ?? 0);

  return (
    <div>
      {/* ---------- hero: the one number that matters, with actions under it */}
      <section className="navy rise relative overflow-hidden rounded-[28px] px-5 pb-5 pt-4">
        <div className="flex items-center justify-between text-[13px] text-muted">
          <span>Today’s brief</span>
          <span className="num">last {windowLabel(hours)}</span>
        </div>
        {error && <div className="mt-3"><Notice tone="warn">Couldn’t load the digest: {error}.</Notice></div>}
        {!digest && loading && <div className="mt-3 h-[124px] animate-pulse rounded-2xl bg-wash" aria-label="Loading today’s filings" />}
        {digest && (
          <>
            {digest.counts.total === 0 ? <h1 className="display mt-1.5 text-[26px] font-extrabold leading-tight">No filings in the last {windowLabel(hours)}</h1> : (
              <h1 className="display mt-1.5 flex items-baseline gap-2 font-extrabold">
                <span className="shrink-0 text-[46px] leading-none num">{n}</span>
                <span className="min-w-0 text-[22px] leading-tight">of {digest.counts.total} {digest.counts.total === 1 ? "filing" : "filings"} {digest.counts.needs_you === 1 ? "needs" : "need"} you</span>
              </h1>
            )}
            <div className="mt-3 flex flex-wrap gap-1.5">
              {digest.counts.moves > 0 && <span className="chip"><Icon.trend />{digest.counts.moves} unusual {digest.counts.moves === 1 ? "move" : "moves"}</span>}
              {digest.counts.routine > 0 && <span className="chip num">{digest.counts.routine} routine set aside</span>}
              {unread > 0 && <button onClick={() => { window.location.hash = "#alerts"; }} className="chip num font-semibold">{unread} unread {unread === 1 ? "alert" : "alerts"}</button>}
            </div>
            <AttentionStrip digest={digest} />
            <p className="mt-1 text-[12px] text-muted">
              Across {digest.counts.companies} companies{digest.counts.grouped ? `, ${digest.counts.grouped} grouped into results bundles` : ""}. {digest.as_of.announcements ? `Filings checked ${ago(digest.as_of.announcements)}.` : "No exchange filings loaded yet."}
            </p>
          </>
        )}
        <div className="mt-4 grid grid-cols-3 gap-2.5">
          <button onClick={onRefresh} disabled={refreshing} className="glass-btn flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-2xl text-[12.5px] font-semibold disabled:opacity-70">
            <span className={refreshing ? "animate-spin" : ""}><Icon.refresh /></span>{refreshing ? "Checking…" : "Refresh"}
          </button>
          <button onClick={ui.openSettings} className="glass-btn flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-2xl text-[12.5px] font-semibold">
            <Icon.sliders />Alert rules
          </button>
          <button onClick={() => { window.location.hash = "#research"; }} className="glass-btn flex min-h-[64px] flex-col items-center justify-center gap-1 rounded-2xl text-[12.5px] font-semibold">
            <Icon.search />Research
          </button>
        </div>
      </section>

      {/* ---------- controls */}
      <div className="rise mt-4 flex flex-wrap items-center justify-between gap-2" style={{ animationDelay: "80ms" }}>
        <Segmented label="Digest window" value={hours} options={windows} onChange={setHours} />
        <Segmented size="sm" label="How FINN explains things" value={plain ? "plain" : "detailed"} onChange={(v) => setPlain(v === "plain")}
          options={[{ value: "plain", label: "Plain" }, { value: "detailed", label: "Detailed" }]} />
      </div>
      {digest && (
        <div className="rise mt-2.5 flex items-center gap-2" style={{ animationDelay: "120ms" }}>
          <span className="text-[13px] text-muted">Depth</span>
          <Segmented label="Briefing depth" value={mode} onChange={setMode} options={MODES} />
        </div>
      )}

      {digest && (
        <>
          {digest.counts.total === 0 && digest.counts.moves === 0 && (
            <div className="mt-4"><Notice>Quiet window. Try 7d or 30d above{!digest.as_of.announcements ? ", or run ingestion to load filings" : ""}.</Notice></div>
          )}

          {needs.length > 0 && (
            <section className="navy rise mt-5 rounded-[26px] px-4 pb-1 pt-4" style={{ animationDelay: "160ms" }}>
              <div className="mb-1 flex items-baseline justify-between">
                <h2 className="display text-[18px] font-bold">Needs you <span className="ml-1 font-sans text-[13px] font-medium text-muted num">{quick && digest.counts.needs_you > needs.length ? `top ${needs.length} of ${digest.counts.needs_you}` : digest.counts.needs_you}</span></h2>
                <span className="text-[12px] text-muted">ranked by importance</span>
              </div>
              {needs.map((it, k) => <FeedItem key={it.id} item={it} compact={quick} expand={deep} top={k === 0} />)}
            </section>
          )}

          {moves.length > 0 && (
            <section className="rise" style={{ animationDelay: "220ms" }}>
              <SectionHead title="Unusual moves" note={`end of day, since ${istDay(digest.as_of.moves_from_session)}`} />
              <div className="rounded-2xl bg-surface px-4">
                {moves.map((m) => <MoveRow key={m.symbol + m.date} m={m} compact={quick} />)}
              </div>
            </section>
          )}

          {quick && (digest.counts.worth_a_look + digest.counts.routine > 0) && (
            <p className="mt-4 text-[14px] text-muted">
              {digest.counts.worth_a_look} worth a look and {digest.counts.routine} routine not shown in Quick.{" "}
              <button onClick={() => setMode("standard")} className="text-ink underline decoration-line underline-offset-2">Show more</button>
            </p>
          )}

          {!quick && digest.tiers.worth_a_look.length > 0 && (
            <section className="rise" style={{ animationDelay: "260ms" }}>
              <SectionHead title="Worth a look" note={digest.counts.worth_a_look} />
              <div className="rounded-2xl bg-surface px-4">
                {digest.tiers.worth_a_look.map((it) => <FeedItem key={it.id} item={it} expand={deep} />)}
              </div>
            </section>
          )}

          {!quick && digest.tiers.routine.length > 0 && (
            <section className="rise" style={{ animationDelay: "300ms" }}>
              <SectionHead title="Routine" note={digest.counts.routine}
                right={<button onClick={() => setShowRoutine((v) => !v)} className="min-h-[32px] px-1 text-[13px] text-muted underline decoration-line underline-offset-2">{showRoutine ? "Hide" : "Show"}</button>} />
              {showRoutine || deep ? (
                <div className="rounded-2xl bg-surface px-4">
                  {digest.tiers.routine.map((it) => <FeedItem key={it.id} item={it} dense />)}
                </div>
              ) : (
                <p className="text-[14px] text-muted">{summariseRoutine(digest)}</p>
              )}
            </section>
          )}
        </>
      )}
    </div>
  );
}

function summariseRoutine(d: Digest) {
  const counts = new Map<string, number>();
  d.tiers.routine.forEach((it) => counts.set(it.category_label, (counts.get(it.category_label) ?? 0) + 1));
  const parts = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4).map(([k, v]) => `${v} ${k.toLowerCase()}`);
  return parts.length ? `Collapsed: ${parts.join(", ")}.` : "";
}
