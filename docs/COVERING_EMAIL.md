**To:** assessment@enam.com
**Subject:** ENAM - IIT screening - 2027

Dear ENAM team,

Please find my submission for the AI Engineer Build Challenge: **FINN, a mobile-first financial investment agent.**

- **Prototype (open on a phone):** [Vercel URL]. A Claude-hosted copy where Ask FINN also answers live: https://claude.ai/artifact/2upZAZbR7uh7sa5XSozDQk
- **GitHub repository:** [GitHub URL]
- **AI build history:** `ai-build-history/` in the repo (readable transcript, raw export and share links)

**What I built.** FINN watches a mock portfolio of 19 real NSE-listed holdings. Fourteen are stocks across sectors; the rest are gold, debt, and US and Hong Kong ETFs for global exposure.
- **Push:** a daily brief that ranks exchange filings so the few material ones come first and routine paperwork collapses. Results filings become a four-line card (revenue, EBITDA, PBT, PAT, with QoQ and YoY). Price and volume alerts run on end-of-day data with a "why now" line, and important ones can go to WhatsApp.
- **Pull:** research on primary sources (annual reports and concall transcripts), with page-level citations. The flagship is a promise tracker that compares what management guided against what was later reported, plus a "narrative vs numbers" check.
- **Portfolio:** a view showing returns from one week to one year against NIFTY 50.
- **For non-experts:** a plain-English mode and a tap-to-explain glossary.

**Key decisions.**
- **The model extracts; code judges.** Periods, variances, verdicts and thresholds are deterministic, so the AI can't invent a result.
- **Rules first.** Most filings are classified by rules without an LLM; only leftovers go to Gemini, in one batched call.
- **Cost control.** Every response is cached, and nothing expensive runs just because a screen opens.
- **BM25 retrieval over pages** instead of embeddings: free, deterministic and citable.
- **End-of-day data only,** and BSE for filings, because NSE blocks cloud servers.
- **No server needed to try it.** The phone version is a single static page.

**Trade-offs and honesty about data.**
- **Real prices:** the hosted prototype uses real NSE end-of-day prices up to 23 Oct 2026, downloaded from NSE's official bhavcopy via the open eod2_data archive and spot-checked against an independent source.
- **Filings and research not yet run live:** the filings and AI-research pipeline is built and tested (79 backend tests, 16 browser journeys), but my build environment couldn't reach BSE or Gemini, so the hosted snapshot doesn't include filings yet. `python -m finn.ingest` or the included GitHub Action adds them.
- **The mock cost basis** is derived, not invented: ₹10 lakh bought at real closing prices on 1 Jan 2026.

**Deliberately left out.** Live intraday prices, trading, accounts and logins, news as research evidence, price predictions and a native app. The brief favoured a small working product, and each of these would have added risk without serving the core question: what changed, why it matters, and where's the proof.

**Next.**
- Run the daily pipeline live and verify filings and research end to end.
- Widen the research set beyond the four demo companies.
- Production WhatsApp templates.
- Peer comparisons, and tracking guidance across more quarters.

[Optional: I'm sorry this reaches you after the 1 November deadline. I wanted the prototype to run on real market data before sending it.]

Best regards,
Abhishek Chhawai
BS, Economics
