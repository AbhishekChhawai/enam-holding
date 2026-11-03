# Covering note: draft

Edit this into your own words before sending. Keep only what is true of your final build.

---

**To:** assessment@enam.com
**Subject:** ENAM - IIT screening - 2027

Hi team,

My submission for the FINN build challenge:

- **Prototype (open on a phone):** <deployed URL with real data>
- **Phone demo (fictional data, no setup):** <claude.ai artifact link, shared>
- **Repository:** <GitHub URL>
- **AI build history:** <share links / exports>

**What I built**

FINN is a mobile-first app whose point of view is that an investor's scarce resource is attention. It runs from one command bar: a ticker opens research, `7d` changes the window, `vol 3x` sets an alert threshold, and a question gets answered from the company's own filings.

- **Push:**
  - A windowed digest of every BSE filing across an 18-company portfolio, tiered into *needs you*, *worth a look* and *routine* (collapsed). Each item says why it was ranked where it was.
  - An "attention strip" shows every filing as a tick, with only those that need you lit.
  - Results filings get a Revenue, EBITDA, PBT and PAT card (QoQ and YoY) read from the filing and cross-checked against screener.in.
  - Management changes show the incoming person's background from the filing's mandatory profile.
  - EOD price and volume moves are flagged against thresholds the investor sets.
- **Pull:** for any NSE symbol, the centrepiece is promised vs delivered.
  - FINN reads the last five concall transcripts and extracts management's guidance with verbatim quotes and page numbers.
  - Each promise is judged against reported numbers. Every verdict opens to the quote, the page, and the formula behind the reported figure.
  - Each verdict shows the variance and links to both sources: the transcript page and the results filing.
  - A companion **narrative vs numbers** view checks how management described results against what was reported. The model only extracts quotes; code decides, and divergences are framed as questions, not accusations.
  - Around it: deterministic financial metrics with traceable inputs and watch items, a business snapshot from the annual report, bull vs bear, and cited Q&A with follow-up context.

- **Usable without a finance background:** a plain-English mode (the default) turns results and promises into sentences built in code from the same verified numbers, and FINN Explain defines 44 terms in place with no model calls. Each filing reads as what happened, why it matters, the proof and what next.

**Key decisions and trade-offs**

1. **The model reads; code judges.** The LLM is limited to extraction. EBITDA, growth, fiscal-period mapping and verdicts are deterministic and unit-tested, and citations and numbers are verified after generation. This trades some flexibility for answers I can defend.
2. **Cost:**
   - Rules classify most filings at zero cost; a cheap model handles leftovers in one batched call.
   - Flash-Lite handles extraction and Flash handles reasoning.
   - Every response is cached, with a visible usage ledger.
   - The whole demo was built on the free tier.
3. **Reliability over liveness:** the brief asks for EOD data, so there's no streaming.
   - Ingestion runs from my machine into a free hosted Postgres, so the demo works even if exchanges block the cloud server, and alert rules survive restarts.
   - On top of that, filings refresh three ways: when stale on a read, every 15 minutes via a free cron ping, or on demand from a Refresh button that reports what's new.
4. **BM25 over embeddings:** it's free, deterministic, and suited to keyword-heavy financial questions.
5. **BSE over NSE for filings:** NSE blocks cloud IPs; BSE has the same filings for these companies.

**What I left out, deliberately**

- NSE filings and intraday data.
- Macro data.
- Broker or news sources, which the brief rules out for Pull.
- Multi-user accounts.
- Voice.
- Embeddings and a vector database.
- Investor-presentation parsing.

**Where I'd take it next**

- Turn the promise tracker into a running credibility score per management team, with alerts when a new call walks back earlier guidance.
- Segment-level guidance checks using investor presentations.
- Push notifications (web push) for triggered alerts.
- Per-user portfolios.
- A scheduled refresh job in India.

Thanks,
Abhishek Chhawai

---

## Submission checklist

- [ ] `./scripts/phone_app.sh` run on your laptop; the coverage report lists 18 companies with prices, real filings, and research for the demo companies.
- [ ] `python scripts/smoke_test.py` passes on your laptop. Keep `smoke_report.json`; only claim "verified against live sources" for rows marked PASS.
- [ ] `FINN_DB_URL` set to a free Neon Postgres, then `python -m finn.ingest` run with `GEMINI_API_KEY` set. Check the log for each research-demo company's promise headline.
- [ ] Deployed on Render or Hugging Face with `GEMINI_API_KEY` set; `/api/health` returns `{"ok": true, "llm": true}`.
- [ ] cron-job.org hitting `/api/cron` every 15 minutes with the header `X-Cron-Secret`. Check that a request without the header gets 403.
- [ ] Opened on a real phone: Today, a filing sheet, Portfolio, Research → Promises → tap a quote, Ask.
- [ ] Tried a symbol outside the demo set (the brief says they may).
- [ ] AI build history exported: share links for the Claude conversations and any Cursor or Claude Code sessions.
- [ ] Email sent to assessment@enam.com with the exact subject line.
