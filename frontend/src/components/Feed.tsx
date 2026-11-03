import React, { useEffect, useState } from "react";
import type { Digest, DigestItem, MgmtCard, Move, ResultsCard } from "../types";
import { crore, istDay, istTime, pct, signClass } from "../format";
import { Avatar, CiteChip, useUI } from "./ui";
import { LabelTerm, Term } from "./Explain";
import { resultsSentences } from "../plain";
import { WHY_CATEGORY } from "../glossary";
import { itemMessage, waLink } from "../whatsapp";

/** Every filing in the window is one tick. On load they arrive level, then settle into tiers:
 *  the investor literally watches the noise being set aside. */
export function AttentionStrip({ digest }: { digest: Digest }) {
  const ui = useUI();
  const [settled, setSettled] = useState(false);
  useEffect(() => {
    setSettled(false);
    const t = setTimeout(() => setSettled(true), 120);
    return () => clearTimeout(t);
  }, [digest.since, digest.counts.total]);
  const byId = new Map<string, DigestItem>();
  (["needs_you", "worth_a_look", "routine"] as const).forEach((k) => digest.tiers[k].forEach((it) => byId.set(it.id, it)));
  const ticks = digest.ticks;
  if (!ticks.length) return null;
  const h = { needs_you: 30, worth_a_look: 16, routine: 7 } as const;
  return (
    <div className="mt-3" aria-label={`${ticks.length} filings, ${digest.counts.needs_you} need attention`}>
      <div className="flex h-[36px] items-end gap-[2px]">
        {ticks.map((t) => {
          const item = byId.get(t.id);
          const lit = t.tier === "needs_you";
          return (
            // Tap area is the full strip height; each filing also has a full-size card below
            // (WCAG 2.2 2.5.8 "equivalent" exception for the narrow width).
            <button key={t.id} onClick={() => item && ui.openItem(item)} aria-label={`${t.symbol}: ${item?.title ?? "filing"}`}
              data-a11y-equivalent="feed card" className="flex h-full min-w-[3px] flex-1 items-end" style={{ maxWidth: 14 }}>
              <span className="tick block w-full rounded-[2px]" style={{
                height: settled ? h[t.tier] : 22,
                background: settled ? (lit ? "var(--marigold)" : t.tier === "worth_a_look" ? "var(--muted)" : "var(--line)") : "var(--muted)",
                opacity: settled && t.tier === "worth_a_look" ? 0.55 : 1,
              }} />
            </button>
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between text-[12px] text-muted num">
        <span>{istTime(ticks[0].published_at)}</span>
        <span>{istTime(ticks[ticks.length - 1].published_at)}</span>
      </div>
    </div>
  );
}

export function ResultsTable({ card, compact }: { card: ResultsCard; compact?: boolean }) {
  const ui = useUI();
  const rows = compact ? card.rows : card.rows;
  return (
    <div className="mt-2 rounded-xl border border-line">
      <table className="w-full text-[13px] num">
        <thead>
          <tr className="text-muted">
            <th className="py-1.5 pl-3 text-left font-normal">₹ crore, {card.periods[0] || "latest"}</th>
            <th className="py-1.5 text-right font-normal">Value</th>
            <th className="py-1.5 text-right font-normal"><Term k="qoq">QoQ</Term></th>
            <th className="py-1.5 pr-3 text-right font-normal"><Term k="yoy">YoY</Term></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-line">
              <td className="py-1.5 pl-3"><LabelTerm label={r.label} /></td>
              <td className="py-1.5 text-right">{crore(r.current)}</td>
              <td className={`py-1.5 text-right ${signClass(r.qoq_pct)}`}>{pct(r.qoq_pct)}</td>
              <td className={`py-1.5 pr-3 text-right font-medium ${signClass(r.yoy_pct)}`}>{pct(r.yoy_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-line px-3 py-1.5 text-[12px] text-muted">
        {card.ebitda_margin?.[0] != null && !card.is_lender && (
          <span>Margin {card.ebitda_margin[0]?.toFixed(1)}% vs {card.ebitda_margin[2]?.toFixed(1) ?? "–"}% a year ago</span>
        )}
        <span><Term k={card.basis === "standalone" ? "standalone" : "consolidated"}>{card.basis}</Term>, from {card.source}</span>
        {card.check && (
          <span className={card.check.status === "match" ? "text-up" : card.check.status === "mismatch" ? "text-down" : ""}>
            {card.check.status === "match" ? "✓ " : ""}{card.check.note}
          </span>
        )}
        {card.doc_id && card.source_page ? <CiteChip c={{ doc_id: card.doc_id, page: card.source_page }} label="Filing" /> : null}
        {!card.doc_id && card.source_url && (
          <a className="inline-flex min-h-[28px] items-center underline decoration-line underline-offset-2" href={card.source_url} target="_blank" rel="noreferrer">Source</a>
        )}
        {card.doc_id && !card.source_page && (
          <button className="underline decoration-line underline-offset-2" onClick={() => ui.openCitation({ doc_id: card.doc_id!, page: 1, label: "Filing" })}>Filing</button>
        )}
      </div>
    </div>
  );
}

export function MgmtBlock({ card }: { card: MgmtCard }) {
  return (
    <div className="mt-2 space-y-2">
      {card.people.map((p, i) => (
        <div key={i} className="rounded-xl border border-line px-3 py-2.5">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="display text-[16px] font-semibold">{p.name}</span>
            <span className="text-[13px] text-muted">{p.change} as {p.role}{p.effective_date ? `, effective ${p.effective_date}` : ""}</span>
          </div>
          {p.profile && <p className="mt-1 text-[14px] leading-snug">{p.profile}</p>}
          {p.previous_roles?.length > 0 && <p className="mt-1 text-[13px] text-muted">Previously: {p.previous_roles.join("; ")}</p>}
          {p.reason && <p className="mt-1 text-[13px] text-muted">Reason given: {p.reason}</p>}
          <div className="mt-1.5 flex gap-3 text-[13px]">
            <a className="underline decoration-line underline-offset-2" href={p.linkedin_search} target="_blank" rel="noreferrer">Find on LinkedIn</a>
            {card.doc_id && p.page ? <CiteChip c={{ doc_id: card.doc_id, page: p.page }} label="Filing" /> : null}
          </div>
        </div>
      ))}
    </div>
  );
}

function Related({ items, open: initial }: { items: NonNullable<DigestItem["related"]>; open?: boolean }) {
  const [open, setOpen] = useState(!!initial);
  if (!items.length) return null;
  return (
    <div className="mt-2">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="min-h-[32px] text-[13px] text-muted underline decoration-line underline-offset-2">
        {open ? "Hide" : `+${items.length}`} related {items.length === 1 ? "filing" : "filings"} from the same results
      </button>
      {open && (
        <ul className="mt-1.5 space-y-1 border-l border-line pl-3 text-[13px]">
          {items.map((r) => (
            <li key={r.id} className="flex items-baseline gap-2">
              <span className="text-muted">{r.category_label}</span>
              {r.attachment_url ? <a href={r.attachment_url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate underline decoration-line underline-offset-2">{r.title}</a>
                : <span className="min-w-0 flex-1 truncate">{r.title}</span>}
              <span className="shrink-0 text-muted num">{istTime(r.published_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Results in two plain sentences, with the full table one tap away (same numbers either way). */
export function PlainResults({ card, open: initial }: { card: ResultsCard; open?: boolean }) {
  const [open, setOpen] = useState(!!initial);
  return (
    <div className="mt-2">
      <div className="rounded-xl bg-wash px-3 py-2 text-[14px] leading-snug num">
        {resultsSentences(card).map((s, i) => <p key={i} className={i ? "mt-1" : ""}>{s}</p>)}
      </div>
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} className="mt-1 min-h-[32px] text-[13px] text-muted underline decoration-line underline-offset-2">
        {open ? "Hide the numbers" : "See the numbers"}
      </button>
      {open && <ResultsTable card={card} />}
    </div>
  );
}

export function FeedItem({ item, dense, compact, expand, top }: { item: DigestItem; dense?: boolean; compact?: boolean; expand?: boolean; top?: boolean }) {
  const ui = useUI();
  const e = item.enrichment;
  return (
    <article className="border-t border-line py-3 first:border-t-0">
      <button onClick={() => ui.openItem(item)} className="block w-full text-left">
        {top && <div className="mb-1 text-[12px] font-medium text-ink"><span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-marigold align-middle" aria-hidden="true" />Highest priority right now</div>}
        <div className="flex min-w-0 items-center gap-2 text-[13px]">
          {!dense && <Avatar symbol={item.symbol} size={30} />}
          <span className="display-tight min-w-[3.5rem] max-w-[45%] truncate text-[15px] font-bold">{item.symbol}</span>
          <span className="min-w-0 truncate text-muted">{item.category_label}</span>
          {item.alert && item.tier === "needs_you" && <span className="h-1.5 w-1.5 rounded-full bg-marigold" aria-label="Matches your alert types" />}
          <span className="ml-auto shrink-0 whitespace-nowrap text-muted num">{istTime(item.published_at)}</span>
        </div>
        <p className={`mt-0.5 ${dense ? "text-[14px] text-muted line-clamp-1" : "text-[15px] leading-snug line-clamp-3"}`}>
          {item.summary || item.title}
        </p>
      </button>
      {!dense && !compact && e?.type === "results" && (ui.plain ? <PlainResults card={e} /> : <ResultsTable card={e} compact />)}
      {!dense && !compact && e?.type === "management_change" && <MgmtBlock card={e} />}
      {!dense && !compact && item.related && <Related key={String(expand)} items={item.related} open={expand} />}
    </article>
  );
}

export function MoveRow({ m, compact }: { m: Move; compact?: boolean }) {
  const ui = useUI();
  return (
    <div className="border-t border-line py-2.5 first:border-t-0">
      <button onClick={() => ui.openResearch(m.symbol, "timeline")} className="flex w-full items-start gap-3 text-left">
        <Avatar symbol={m.symbol} size={34} />
        <span className="min-w-0 flex-1">
          <span className="flex items-baseline justify-between gap-2">
            <span className="display-tight min-w-0 truncate text-[15px] font-bold">{m.symbol}</span>
            <span className="shrink-0 text-[12px] text-muted num">{istDay(m.date)}</span>
          </span>
          <span className="mt-0.5 block text-[14px] leading-snug">{m.text}</span>
        </span>
      </button>
      {!compact && (m as Move & { index_context?: { name: string; pct: number; date: string } }).index_context && (() => {
        const ic = (m as Move & { index_context: { name: string; pct: number; date: string } }).index_context;
        return <p className="mt-1 pl-[2.9rem] text-[13px] text-muted num">The {ic.name} it tracks moved <span className={signClass(ic.pct)}>{pct(ic.pct)}</span> in its session of {istDay(ic.date)}.</p>;
      })()}
      {!compact && m.nearby && m.nearby.length > 0 && (
        <div className="mt-1 pl-[2.9rem] text-[13px]">
          <span className="text-muted">Around this session: </span>
          {m.nearby.map((n, i) => (
            <span key={n.id}>{i > 0 && "; "}{n.attachment_url ? <a href={n.attachment_url} target="_blank" rel="noreferrer" className="inline-flex min-h-[28px] items-center underline decoration-line underline-offset-2">{n.category_label}, {istDay(n.published_at)}</a> : `${n.category_label}, ${istDay(n.published_at)}`}</span>
          ))}
          <span className="block text-[12px] text-muted">Context only; FINN doesn’t infer cause.</span>
        </div>
      )}
    </div>
  );
}


function ResearchButton({ item }: { item: DigestItem }) {
  const ui = useUI();
  return (
    <button onClick={() => ui.researchThis(item.id)} className="rounded-full border border-ink px-3.5 py-1.5 text-[14px]">
      Research this
    </button>
  );
}

export function ItemDetail({ item, onFeedback }: { item: DigestItem; onFeedback: (s: "more" | "less") => void }) {
  const ui = useUI();
  if (ui.plain) return <PlainDetail item={item} onFeedback={onFeedback} />;
  return <DetailedDetail item={item} onFeedback={onFeedback} />;
}

/** What happened → why it matters → the proof → what next. Every sentence comes from data or a fixed template. */
function PlainDetail({ item, onFeedback }: { item: DigestItem; onFeedback: (s: "more" | "less") => void }) {
  const e = item.enrichment;
  const H = ({ children }: { children: React.ReactNode }) => <h3 className="mt-4 text-[12px] font-semibold text-muted first:mt-0">{children}</h3>;
  return (
    <div className="text-[15px] leading-snug">
      <H>What happened</H>
      {e?.type === "results" ? (
        <div className="mt-1 num">{resultsSentences(e).map((s, i) => <p key={i} className={i ? "mt-1" : ""}>{s}</p>)}</div>
      ) : e?.type === "management_change" ? (
        <p className="mt-1">{e.people.map((p) => `${p.name} ${p.change} as ${p.role}${p.effective_date ? ` (from ${p.effective_date})` : ""}.`).join(" ")}</p>
      ) : <p className="mt-1">{item.summary || item.title}</p>}
      <H>Why it matters</H>
      <p className="mt-1">{WHY_CATEGORY[item.category] ?? "This is an official company disclosure; open it to see the details."}</p>
      <H>The proof</H>
      {e?.type === "results" && <ResultsTable card={e} />}
      {e?.type === "management_change" && <MgmtBlock card={e} />}
      <div className="mt-2 flex flex-wrap gap-2">
        {item.attachment_url && <a href={item.attachment_url} target="_blank" rel="noreferrer" className="inline-flex min-h-[40px] items-center rounded-full bg-ink px-4 text-[14px] text-paper">Open filing</a>}
        <a href={waLink(itemMessage(item))} target="_blank" rel="noreferrer" className="inline-flex min-h-[40px] items-center gap-1.5 rounded-full bg-[#25D366] px-4 text-[14px] font-semibold text-[#062b16]"><svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.7 11.8 11.8 0 0 0 4.5 4c1.7.7 2.3.8 3.2.6a2.7 2.7 0 0 0 1.8-1.3 2.2 2.2 0 0 0 .2-1.3c-.1-.1-.3-.2-.5-.3z"/></svg>Share on WhatsApp</a>
        {item.exchange_url && <a href={item.exchange_url} target="_blank" rel="noreferrer" className="inline-flex min-h-[40px] items-center rounded-full border border-line px-4 text-[14px]">BSE page</a>}
      </div>
      <H>What next</H>
      <div className="mt-1.5 flex flex-wrap gap-2"><ResearchButton item={item} /></div>
      <details className="mt-5 border-t border-line pt-3 text-[13px] text-muted">
        <summary className="min-h-[32px] cursor-pointer">How FINN ranked this ({item.tier === "needs_you" ? "needs you" : item.tier === "worth_a_look" ? "worth a look" : "routine"}, score {item.score} of 100)</summary>
        <ul className="mt-1 space-y-0.5">{item.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        <Feedback item={item} onFeedback={onFeedback} />
      </details>
    </div>
  );
}

function Feedback({ item, onFeedback }: { item: DigestItem; onFeedback: (s: "more" | "less") => void }) {
  const [sent, setSent] = useState<string | null>(null);
  return (
    <div className="mt-3">
      <p className="text-[13px] text-muted">Tune what reaches you. This changes how all {item.category_label.toLowerCase()} filings rank.</p>
      <div className="mt-2 flex gap-2">
        {(["more", "less"] as const).map((s) => (
          <button key={s} disabled={!!sent} onClick={() => { onFeedback(s); setSent(s); }}
            className={`min-h-[40px] rounded-full border px-3 text-[14px] ${sent === s ? "border-ink" : "border-line"} disabled:opacity-60`}>
            {s === "more" ? "More like this" : "Less like this"}
          </button>
        ))}
      </div>
      {sent && <p className="mt-2 text-[13px] text-muted">Saved. {sent === "more" ? "Raised" : "Lowered"} by 10 points.</p>}
    </div>
  );
}

function DetailedDetail({ item, onFeedback }: { item: DigestItem; onFeedback: (s: "more" | "less") => void }) {
  const [sent, setSent] = useState<string | null>(null);
  const e = item.enrichment;
  return (
    <div>
      <p className="text-[16px] leading-snug">{item.title}</p>
      {item.summary && item.summary !== item.title && <p className="mt-2 text-[14px] text-muted">{item.summary}</p>}
      {e?.type === "results" && <ResultsTable card={e} />}
      {e?.type === "management_change" && <MgmtBlock card={e} />}
      {e?.type === "results" && e.ebitda_note && <p className="mt-1.5 text-[12px] text-muted">{e.ebitda_note}</p>}

      <h3 className="display mt-5 text-[16px] font-semibold">Why it’s {item.tier === "needs_you" ? "at the top" : item.tier === "worth_a_look" ? "worth a look" : "set aside"}</h3>
      <ul className="mt-1 space-y-0.5 text-[14px] text-muted">
        {item.reasons.map((r, i) => <li key={i}>{r}</li>)}
        <li>Score {item.score} of 100. Classified by {item.classified_by === "rule" ? "a rule (no model call)" : item.classified_by === "llm" ? "the low-cost model" : "default"}.</li>
      </ul>

      {item.related && item.related.length > 0 && <Related items={item.related} open />}

      <div className="mt-5 flex flex-wrap gap-2">
        <ResearchButton item={item} />
        {item.attachment_url && <a href={item.attachment_url} target="_blank" rel="noreferrer" className="inline-flex min-h-[40px] items-center rounded-full bg-ink px-4 text-[14px] text-paper">Open filing</a>}
        <a href={waLink(itemMessage(item))} target="_blank" rel="noreferrer" className="inline-flex min-h-[40px] items-center gap-1.5 rounded-full bg-[#25D366] px-4 text-[14px] font-semibold text-[#062b16]"><svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8-.2-.1-.4-.1-.6.1l-.8 1c-.1.2-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.2-.4.2-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.7 11.8 11.8 0 0 0 4.5 4c1.7.7 2.3.8 3.2.6a2.7 2.7 0 0 0 1.8-1.3 2.2 2.2 0 0 0 .2-1.3c-.1-.1-.3-.2-.5-.3z"/></svg>Share on WhatsApp</a>
        {item.exchange_url && <a href={item.exchange_url} target="_blank" rel="noreferrer" className="rounded-full border border-line px-3.5 py-1.5 text-[14px]">BSE page</a>}
      </div>

      <div className="mt-6 border-t border-line pt-3">
        <p className="text-[13px] text-muted">Tune what reaches you. This changes how all {item.category_label.toLowerCase()} filings rank.</p>
        <div className="mt-2 flex gap-2">
          {(["more", "less"] as const).map((s) => (
            <button key={s} disabled={!!sent} onClick={() => { onFeedback(s); setSent(s); }}
              className={`min-h-[40px] rounded-full border px-3 text-[14px] ${sent === s ? "border-ink" : "border-line"} disabled:opacity-60`}>
              {s === "more" ? "More like this" : "Less like this"}
            </button>
          ))}
        </div>
        {sent && <p className="mt-2 text-[13px] text-muted">Saved. {sent === "more" ? "Raised" : "Lowered"} by 10 points.</p>}
      </div>
    </div>
  );
}
