# FINN: build transcript (short version)

**Abhishek Chhawai** working with **Claude** (claude.ai, with a code sandbox), 31 Oct to 3 Nov 2026.
The full transcript and raw export are in this folder.

---

## Session 1: building the engine

**1. Brief to plan.** *Abhishek* shared both ENAM PDFs and a master prompt.
*Claude* checked the current Gemini models first: the 2.5 models had been retired, so it used 3.x. It chose FastAPI, React and Postgres, and BSE over NSE, because NSE blocks cloud servers.

**2. Part 1: data engine.** End-of-day prices, BSE filings, Screener financials, PDF page extraction, a company timeline, and support for any NSE ticker.

**3. Part 2: Push.** A rules-first filing classifier (over 90% of filings need no AI), a ranked daily brief, a results card (revenue, EBITDA, PBT, PAT with QoQ and YoY), saved alert rules with no duplicate alerts, and "why now" context on price moves.

**4. Part 3: Pull.** Cited research on annual reports and transcripts, and a **promise tracker**: management guidance against reported results, with the verdict computed by code rather than the AI.

**5. Security review.** *Claude* found two prompt-injection gaps in how document text reached the model, fixed them, and added 12 attack tests.

**6. Live check.** A real Screener page had changed layout in four ways. Each was fixed and locked in with a test.
→ **70 tests pass on SQLite and PostgreSQL.**

---

## Session 2: turning it into a product

**7. Part 4: mobile UX.** *Abhishek* said: audit first, don't rebuild.
*Claude* found the real gaps (no price chart, no way back from research to the filing, no visible search) and fixed only those. New click-through browser tests caught a bug: Ask showed a **blank screen** when no AI key was set.

**8. Part 5: beginners.** *Abhishek* said: make it usable without finance knowledge.
*Claude* added a tap-to-explain glossary (44 terms, no AI calls), a Plain/Detailed switch, a 3-step welcome tour, and fixed 37 buttons that were too small to tap.

**9. "Make it work on a phone."** *Claude* couldn't log into hosting accounts, so it built a single-file phone app and published it as a link. It ran on a clearly labelled **fictional** demo.

**10. Redesign.** *Abhishek* shared a fintech app design.
*Claude* restyled FINN in blue glass with tap animations and light/dark themes. All tests still passed.

**11. Course correction.** *Abhishek* (with a reviewer's critique) said fictional data isn't enough for ENAM.
*Claude* **refused to put real company names on made-up numbers** and built a real-data export instead. Its safety check caught Claude's own sample database being mislabelled as real, and the check was tightened.

**12. Real portfolio.** 19 real holdings: 14 stocks, plus gold, debt, US and Hong Kong ETFs. Added a Groww-style analysis against NIFTY 50.

**13. Horizons and WhatsApp.** Returns from 1W to 1Y, and WhatsApp alerts (a share button plus automatic sending, each alert once).

**14. "Real data is online, use it."** *Claude* found an open archive of NSE's official daily price files on GitHub, downloaded all 19 holdings and NIFTY 50, and **cross-checked** the data against an independent source (HNGSNGBEES: ₹494.96 and ₹496.38, an exact match).
→ ₹10 lakh on 1 Jan 2026 became **₹9,30,853** (−6.9%), while **NIFTY 50 fell 13.6%**.

**15. Alignment.** *Abhishek* spotted long tickers overlapping text.
*Claude* fixed the layout and added a permanent scan that fails if any text overlaps.

**16. Release.** Vercel config, the GitHub repo, the covering email and this history.
→ **Final: 79 backend tests, 8 frontend tests and 16 browser journeys pass.**

---

## How we worked

- **Phased prompts with acceptance criteria**, and each phase began by auditing what already existed.
- **The AI extracts, code judges:** numbers and verdicts are never left to the model.
- **Tests, not claims:** browser tests found real bugs that screenshots would have missed.
- **Honest limits:** live BSE filings and Gemini research couldn't run from Claude's sandbox, so they were never claimed as verified live.
