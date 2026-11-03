# AI build history

FINN was built by Abhishek Chhawai working with **Claude** (claude.ai, Opus, with a code-execution sandbox) over two long sessions, 31 Oct to 3 Nov 2026. Claude wrote and ran the code, tests and browser checks. Abhishek set the direction, wrote the phase prompts, reviewed results and pushed back.

| File | What it is |
|---|---|
| `BUILD_TRANSCRIPT_SHORT.md` | **Start here.** The whole build in two pages |
| `BUILD_TRANSCRIPT.md` | **The prompts behind the customer experience:** each step's prompt, why it mattered to investors, what changed for them, and a short technical note |
| `claude-session-1-transcript.md` | Readable export of session 1 (Parts 1 to 3: data engine, Push, Pull; security review; live-layout fixes). 11 turns, 176 tool calls |
| Share link: session 2 | **[paste the claude.ai share link here]**: Parts 4 and 5, the phone demo, the real-data pivot, portfolio and ETFs, WhatsApp, Vercel |
| Share link: prompt drafting and reviews | **[optional: paste links to any other assistant chats used to draft the phase prompts or reviews]** |

> These chats ran on a claude.ai account whose saved profile belongs to someone else, so Claude sometimes addresses the user as "Chitransh" in its replies. Every instruction came from Abhishek Chhawai. The raw export is left out because it embeds that account's private saved data; the share link shows the full conversation.

## How the work was done

1. **The brief became phased prompts.** Five parts (data engine → Push → Pull → mobile UX → beginner experience and release), each with acceptance criteria. Each part began with an audit of what already existed, so finished work wasn't rebuilt.
2. **The rule throughout: the model extracts, code judges.** Fiscal-period arithmetic, variances, promise verdicts and alert thresholds are deterministic Python, and the LLM only extracts quotes and claims. This was decided in session 1 and held throughout.
3. **Tests over claims.** Every phase ended with tests actually being run, never just reported: 79 backend tests (SQLite and PostgreSQL 16), 8 frontend tests, and 16 scripted browser journeys that click through the app at phone sizes.
4. **The tests found real bugs, which were fixed:**
   - Ask showed a blank screen when no model key was set.
   - Two controls shared the accessible name "Ask".
   - Prompt-injection gaps in document excerpts.
   - 37 tap targets were under the WCAG 2.2 minimum.
   - Long tickers (HNGSNGBEES) overlapped their text. A permanent "no overlapping text" scan was added afterwards.
5. **Course corrections, driven by Abhishek's reviews:**
   - **From modules to one connected journey:** Research This → back to the filing.
   - **From an expert-only UI to plain English:** the FINN Explain glossary, a Plain/Detailed view and onboarding.
   - **From a fictional demo to real data.** Claude refused to put real company names on invented numbers. Real NSE prices were then downloaded from the open eod2_data archive (built from NSE's official bhavcopy) and cross-checked against an independent source: HNGSNGBEES closed at ₹494.96 and ₹496.38 on 12 and 15 Jun 2026 in both.
6. **Honest limits were kept visible.** Claude's sandbox couldn't reach BSE, Yahoo or Gemini, so live filings and AI research are built and tested on fixtures, and run live through `python -m finn.ingest` or the included GitHub Action. They were never claimed as verified live.
