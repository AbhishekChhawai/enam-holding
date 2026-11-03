import { useMemo, useState, type ReactNode } from "react";
import { GLOSSARY, keyForLabel } from "../glossary";
import { Segmented, useUI } from "./ui";

/** A financial term the reader can tap to understand. Inline, so it reads as part of the sentence. */
export function Term({ k, children, className = "" }: { k: string; children?: ReactNode; className?: string }) {
  const ui = useUI();
  const e = GLOSSARY[k];
  if (!e) return <>{children}</>;
  return (
    <button type="button" onClick={(ev) => { ev.stopPropagation(); ui.openTerm(k); }} aria-label={`${typeof children === "string" ? children : e.term}: what does this mean?`}
      className={`cursor-help py-1 underline decoration-dotted decoration-muted underline-offset-[3px] hover:decoration-ink ${className}`}>
      {children ?? e.term}
    </button>
  );
}

/** Wrap a metric label with its glossary entry when one exists. */
export function LabelTerm({ label }: { label: string }) {
  const k = keyForLabel(label);
  return k ? <Term k={k}>{label}</Term> : <>{label}</>;
}

export function ExplainView({ k, onOpen }: { k: string; onOpen: (k: string) => void }) {
  const e = GLOSSARY[k];
  if (!e) return <p className="text-muted">No explanation for this term yet.</p>;
  return (
    <div className="space-y-3 text-[15px] leading-snug">
      <div><p className="text-[12px] font-medium text-muted">In simple terms</p><p className="mt-0.5 text-[17px] font-medium">{e.simple}</p></div>
      <div><p className="text-[12px] font-medium text-muted">What it is</p><p className="mt-0.5">{e.what}</p></div>
      <div><p className="text-[12px] font-medium text-muted">Why it matters</p><p className="mt-0.5">{e.why}</p></div>
      {e.related && e.related.length > 0 && (
        <div>
          <p className="text-[12px] font-medium text-muted">Related</p>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {e.related.map((r) => GLOSSARY[r] && (
              <button key={r} onClick={() => onOpen(r)} className="min-h-[36px] rounded-full border border-line px-3 text-[14px]">{GLOSSARY[r].term}</button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export function HelpView({ plain, setPlain, onOpen, onTour, theme, setTheme }: { plain: boolean; setPlain: (v: boolean) => void; onOpen: (k: string) => void; onTour: () => void;
  theme: "auto" | "light" | "dark"; setTheme: (t: "auto" | "light" | "dark") => void }) {
  const [q, setQ] = useState("");
  const terms = useMemo(() => Object.entries(GLOSSARY).filter(([, e]) => !q || (e.term + e.simple).toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => a[1].term.localeCompare(b[1].term)), [q]);
  return (
    <div className="space-y-5 text-[14px]">
      <section>
        <h3 className="display text-[17px] font-semibold">How FINN talks to you</h3>
        <div className="mt-2 grid grid-cols-2 gap-2">
          {[{ v: true, t: "Plain English", d: "Short sentences, terms explained" }, { v: false, t: "Detailed", d: "Tables, ratios and formulas" }].map((o) => (
            <button key={o.t} onClick={() => setPlain(o.v)} aria-pressed={plain === o.v}
              className={`min-h-[64px] rounded-xl border px-3 py-2 text-left ${plain === o.v ? "border-ink bg-wash" : "border-line"}`}>
              <span className="block font-medium">{o.t}</span><span className="block text-[12px] text-muted">{o.d}</span>
            </button>
          ))}
        </div>
        <p className="mt-2 text-[12px] text-muted">Both show the same facts from the same sources; only the wording and depth change.</p>
      </section>
      <section>
        <h3 className="display text-[17px] font-semibold">Appearance</h3>
        <div className="mt-2"><Segmented label="Theme" value={theme} onChange={setTheme} options={[{ value: "auto", label: "Auto" }, { value: "light", label: "Light" }, { value: "dark", label: "Dark" }]} /></div>
        <p className="mt-1.5 text-[12px] text-muted">Auto follows your phone’s setting. Your choice is remembered on this device.</p>
      </section>
      <section>
        <h3 className="display text-[17px] font-semibold">Good to know</h3>
        <ul className="mt-1 space-y-1.5 text-muted">
          <li>Prices are <Term k="eod">end-of-day</Term> closes, not live quotes.</li>
          <li>Every number links back to the company’s own <Term k="filing">filing</Term>, <Term k="annual_report">annual report</Term> or <Term k="concall">earnings-call transcript</Term>.</li>
          <li>FINN explains and checks; it doesn’t give buy or sell advice.</li>
        </ul>
        <button onClick={onTour} className="mt-3 min-h-[40px] rounded-full border border-ink px-4">Replay the 3-step tour</button>
      </section>
      <section>
        <h3 className="display text-[17px] font-semibold">Glossary</h3>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search a term, e.g. EBITDA" aria-label="Search glossary"
          className="mt-2 w-full rounded-xl border border-line bg-surface px-3 py-2.5" />
        <ul className="mt-2">
          {terms.map(([k, e]) => (
            <li key={k} className="border-t border-line first:border-t-0">
              <button onClick={() => onOpen(k)} className="block min-h-[48px] w-full py-2 text-left">
                <span className="font-medium">{e.term}</span><span className="block text-[13px] text-muted">{e.simple}</span>
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

export function Onboarding({ portfolio, onDone, go, plain, setPlain }: {
  portfolio: { symbol: string; name: string }[]; onDone: () => void; plain: boolean; setPlain: (v: boolean) => void;
  go: (where: "today" | "portfolio" | "research" | "alerts" | { symbol: string }) => void;
}) {
  const [step, setStep] = useState(0);
  const finish = (where?: Parameters<typeof go>[0]) => { onDone(); if (where) go(where); };
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-1.5" aria-label={`Step ${step + 1} of 3`}>
        {[0, 1, 2].map((i) => <span key={i} className={`h-1.5 flex-1 rounded-full ${i <= step ? "bg-marigold" : "bg-line"}`} />)}
      </div>
      {step === 0 && (
        <>
          <h2 className="display text-[24px] font-semibold leading-tight">Your companies, explained</h2>
          <p className="text-[15px] leading-snug">FINN watches your companies, tells you which few updates actually matter, and helps you understand them using each company’s own reports, with a link to the source for every number.</p>
          <p className="text-[14px] text-muted">No finance background needed: tap any dotted term, like <Term k="ebitda">EBITDA</Term>, to see what it means.</p>
          <label className="flex min-h-[44px] items-center gap-3 rounded-xl border border-line px-3">
            <input type="checkbox" checked={plain} onChange={(e) => setPlain(e.target.checked)} className="h-5 w-5 accent-[var(--marigold)]" />
            <span className="text-[14px]">Explain things in plain English <span className="text-muted">(recommended; change any time in Help)</span></span>
          </label>
        </>
      )}
      {step === 1 && (
        <>
          <h2 className="display text-[24px] font-semibold leading-tight">Start with the demo portfolio</h2>
          <p className="text-[15px] leading-snug">FINN is following {portfolio.length || "a set of"} listed companies across sectors. Tap one to explore it, or search for any NSE company later.</p>
          <div className="flex flex-wrap gap-2">
            {portfolio.slice(0, 8).map((c) => (
              <button key={c.symbol} onClick={() => finish({ symbol: c.symbol })} className="min-h-[40px] rounded-full border border-line px-3 text-left text-[14px]">
                <span className="font-semibold">{c.symbol}</span> <span className="text-muted">{c.name}</span>
              </button>
            ))}
          </div>
          <button onClick={() => finish("portfolio")} className="min-h-[44px] rounded-full border border-ink px-4 text-[14px]">See the whole portfolio</button>
        </>
      )}
      {step === 2 && (
        <>
          <h2 className="display text-[24px] font-semibold leading-tight">What would you like to do?</h2>
          <div className="grid gap-2">
            {[
              { t: "See what matters today", d: "The few updates worth your time", w: "today" as const },
              { t: "Research a company", d: "Business, numbers, and whether management kept its word", w: "research" as const },
              { t: "Set a price or volume alert", d: "e.g. tell me if a stock moves 5% in a day", w: "alerts" as const },
            ].map((o) => (
              <button key={o.t} onClick={() => finish(o.w)} className="min-h-[60px] rounded-xl border border-line px-4 py-2 text-left">
                <span className="block text-[15px] font-medium">{o.t}</span><span className="block text-[13px] text-muted">{o.d}</span>
              </button>
            ))}
          </div>
        </>
      )}
      <div className="flex items-center justify-between pt-1">
        <button onClick={() => finish()} className="min-h-[44px] px-2 text-[14px] text-muted underline decoration-line underline-offset-2">Skip</button>
        {step < 2 && <button onClick={() => setStep(step + 1)} className="min-h-[44px] rounded-full bg-ink px-5 text-[15px] text-paper">Next</button>}
      </div>
    </div>
  );
}
