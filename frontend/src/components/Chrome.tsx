import { useEffect, useMemo, useRef, useState } from "react";
import { api, useApi } from "../api";
import { describeIntent, parseIntent, type Intent } from "../intent";
import { Loading, Notice } from "./ui";

/* ------------------------------------------------------------------ command bar */
export function CommandBar({ known, names, current, onIntent }: {
  known: string[]; names: Record<string, string>; current: string | null; onIntent: (i: Intent) => void;
}) {
  const [text, setText] = useState("");
  const [focus, setFocus] = useState(false);
  const [matches, setMatches] = useState<{ symbol: string; name: string }[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const intent = useMemo(() => parseIntent(text, { known, current }), [text, known, current]);

  useEffect(() => {
    const q = text.trim();
    if (q.length < 2 || q.includes(" ")) { setMatches([]); return; }
    const t = setTimeout(async () => {
      try { setMatches((await api<{ symbol: string; name: string }[]>(`/api/search?q=${encodeURIComponent(q)}`)).slice(0, 5)); }
      catch { setMatches([]); }
    }, 220);
    return () => clearTimeout(t);
  }, [text]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && document.activeElement?.tagName !== "INPUT" && document.activeElement?.tagName !== "TEXTAREA")) {
        e.preventDefault(); inputRef.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const run = (i: Intent) => { if (i.kind === "none") return; onIntent(i); setText(""); inputRef.current?.blur(); };
  const hints = current
    ? [`${current} promises`, "Did margins match guidance?", "7d", "vol 3x"]
    : ["DIXON promises", "7d", "vol 3x", "price 4%"];

  return (
    <div className="relative">
      {focus && (
        <div className="absolute bottom-full left-0 right-0 mb-2 rounded-2xl border border-line bg-surface p-2 shadow-[0_8px_30px_rgba(0,0,0,0.12)]">
          {text && intent.kind !== "none" && (
            <button onMouseDown={(e) => { e.preventDefault(); run(intent); }} className="flex w-full items-center gap-2 rounded-xl bg-wash px-3 py-2 text-left text-[14px]">
              <span className="text-muted">Enter</span><span>{describeIntent(intent, names)}</span>
            </button>
          )}
          {matches.map((m) => (
            <button key={m.symbol} onMouseDown={(e) => { e.preventDefault(); run({ kind: "research", symbol: m.symbol }); }}
              className="flex w-full items-baseline gap-2 rounded-xl px-3 py-2 text-left hover:bg-wash">
              <span className="display-tight text-[15px] font-semibold tracking-wide">{m.symbol}</span>
              <span className="truncate text-[13px] text-muted">{m.name}</span>
            </button>
          ))}
          {!text && (
            <div className="flex flex-wrap gap-1.5 p-1">
              {hints.map((h) => (
                <button key={h} onMouseDown={(e) => { e.preventDefault(); setText(h); }} className="rounded-full border border-line px-2.5 py-1 text-[13px] text-muted">{h}</button>
              ))}
              <p className="w-full px-1 pt-1 text-[12px] text-muted">A symbol opens research. A window or threshold changes your digest. A question is answered from the company’s own filings.</p>
            </div>
          )}
        </div>
      )}
      <form onSubmit={(e) => { e.preventDefault(); run(intent); }}>
        <input ref={inputRef} value={text} onChange={(e) => setText(e.target.value)}
          onFocus={() => setFocus(true)} onBlur={() => setFocus(false)}
          placeholder={current ? `Ask about ${current}, or a symbol` : "Symbol, 7d, or a question"}
          aria-label="Command" enterKeyHint="go" autoCapitalize="characters" autoCorrect="off" spellCheck={false}
          className="w-full rounded-full border border-line bg-surface px-4 py-2.5 text-[15px] placeholder:text-muted" />
      </form>
    </div>
  );
}

/* ------------------------------------------------------------------ citation viewer */
export function CitationView({ docId, page, quote }: { docId: string; page: number; quote?: string }) {
  const { data, error, loading } = useApi<{ doc: { title: string; url: string; kind: string; period: string; symbol: string; status: string; pages: number }; page: number; text: string; open_url: string }>(`/api/docs/${docId}/page/${page}`);
  const parts = useMemo(() => highlight(data?.text ?? "", quote), [data, quote]);
  if (loading && !data) return <Loading text="Opening the page" />;
  if (error) return <Notice tone="warn">{error}</Notice>;
  if (!data) return null;
  const KIND: Record<string, string> = { transcript: "Earnings-call transcript", annual_report: "Annual report", filing: "Exchange filing", presentation: "Investor presentation" };
  const host = (() => { try { return new URL(data.doc.url).hostname.replace(/^www\./, ""); } catch { return ""; } })();
  return (
    <div>
      <div className="mb-3 rounded-xl bg-wash px-3 py-2.5 text-[13px]">
        <p className="font-medium text-ink">{data.doc.title || KIND[data.doc.kind] || "Document"}</p>
        <p className="text-muted num">
          {KIND[data.doc.kind] ?? data.doc.kind}{data.doc.period ? `, ${data.doc.period}` : ""}{data.doc.symbol ? `, ${data.doc.symbol}` : ""}.
          {" "}Page {page}{data.doc.pages ? ` of ${data.doc.pages}` : ""}{host ? `, from ${host}` : ""}.
          {data.doc.status === "scanned" && " Scanned document: text may be incomplete."}
        </p>
      </div>
      <a href={data.open_url} target="_blank" rel="noreferrer" className="inline-block rounded-full bg-ink px-3.5 py-1.5 text-[14px] text-paper">Open PDF at page {page}</a>
      <div className="mt-4 whitespace-pre-wrap text-[13px] leading-relaxed text-muted">
        {parts.map((p, i) => p.hit ? <mark key={i} className="rounded bg-marigold-wash px-0.5 text-ink">{p.text}</mark> : <span key={i}>{p.text}</span>)}
      </div>
    </div>
  );
}

function highlight(text: string, quote?: string) {
  if (!quote || !text) return [{ text, hit: false }];
  const words = quote.toLowerCase().match(/[a-z0-9]+/g) ?? [];
  if (words.length < 3) return [{ text, hit: false }];
  // find the window in text that starts with the first 3 quote words, tolerant of whitespace/punctuation
  const head = words.slice(0, 3).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("[^a-z0-9]+");
  const m = new RegExp(head, "i").exec(text);
  if (!m) return [{ text, hit: false }];
  // end at the quote's last three words, so the highlight covers the quote and nothing more
  const tail = words.slice(-3).map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("[^a-z0-9]+");
  const t = new RegExp(tail, "i").exec(text.slice(m.index));
  const end = t && t.index + t[0].length <= quote.length * 1.6 ? m.index + t.index + t[0].length : Math.min(text.length, m.index + quote.length);
  return [{ text: text.slice(0, m.index), hit: false }, { text: text.slice(m.index, end), hit: true }, { text: text.slice(end), hit: false }];
}
