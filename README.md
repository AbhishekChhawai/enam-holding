# FINN — Financial Investment Agent

> **ENAM AI Engineer Build Challenge submission by Abhishek Chhawai (BS, Economics).**
> Prototype: [Vercel URL] · Claude-hosted copy with live Ask: https://claude.ai/artifact/2upZAZbR7uh7sa5XSozDQk
> Covering note: `docs/COVERING_EMAIL.md` · AI build history: `ai-build-history/`


A mobile-first investment intelligence app for a portfolio of Indian listed companies.

- **Push:** what changed across the portfolio, ranked so that only what matters is in front of you.
- **Pull:** on-demand research on any NSE company, grounded only in its own annual reports and concall transcripts, with a page citation for every claim.

The centrepiece is a **promise tracker**. FINN reads the last five earnings calls, extracts what management guided, and checks each promise against the numbers the company later reported. The model extracts; code judges.

## What it does

**Today (Push)**
- A digest for a window you pick (24h, 3d, 7d, 30d) of every BSE filing across the portfolio, in three tiers: *Needs you*, *Worth a look*, and *Routine*, which is collapsed.
- The attention strip shows every filing as a tick, with only the ones that need you lit. Tap any tick to open it.
- **Results filings** get a first-cut card: Revenue, EBITDA, PBT and PAT, QoQ and YoY.
  - Numbers are read from the filing itself, and EBITDA and growth are computed in code.
  - Each card is cross-checked against screener.in and shows a ✓ when the two agree.
- **Management changes** show who is joining or leaving, with a short bio taken from the filing (SEBI requires a brief profile in it) and a LinkedIn search link.
- **Unusual EOD moves** flag a price move beyond ±X% or volume above N× its 20-day average. You set both thresholds.
- Every item explains *why* it ranked where it did. "More / less like this" re-weights that filing type for you.
- **Results-day bundles:** the presentation, press release and call schedule fold under the results card, so one results day is one card and one alert.
- **Depth control:** Quick, Standard or Deep. The same facts at different density.
- **Why-now:** a price move lists the company's filings from around that session, explicitly as context, not cause.
- **"Research this"** on any filing opens the right Research tab.

**Built for beginners too**
- **FINN Explain:** tap any dotted term (EBITDA, PAT, YoY, free cash flow…) for a plain-English definition, why it matters, and related terms. There are 44 prewritten entries and opening one never calls a model.
- **Plain English / Detailed:** a header switch, Plain by default. Results and promises read as sentences ("Profit after tax was ₹120 crore, up 27.7% from a year earlier"). The sentences are built in code from the same data as the Detailed tables, so the two views can't disagree.
- **Every filing** opens as What happened → Why it matters → The proof → What next.
- **A 3-step first-run tour** (skippable) and a Help sheet with a searchable glossary.

**Alerts**
- Rules for price moves (up, down or either way, beyond X%), volume (above N× a configurable average), or filing types (with a minimum priority), set per company or portfolio-wide.
- Each rule is checked against recent history the moment you save it, then again whenever new data arrives.
- Alerts are deduplicated per rule × company × session or filing, with an unread inbox and badge.
- Market rules only use completed end-of-day sessions, and the screen says when rules were last checked.

**Research (Pull)**, for any NSE symbol with a screener.in page. Opening an unseen symbol registers it and fetches a year of prices and its recent BSE filings in the background:
- **Promises:** promised vs delivered over the last four quarters, plus current guidance.
  - Each verdict shows the variance ("+1.2 pp above the top of the range"), an **Exceeded** label where it applies, the verbatim quote and page, and the reported number with its formula and input cells.
  - A link opens the results filing, so both sides of every comparison can be checked.
- **Narrative vs numbers:** how management *described* results ("a strong quarter", "margins improved"), checked against what was reported. Divergences are framed as questions to ask, and unmeasurable claims are labelled as such rather than judged.
- **Timeline:** filings, flagged market sessions, reported quarters and earnings calls in one chronology. Events in the same window as a results filing are linked, explicitly not as cause.
- **Data sheet:** tap the freshness line under the company name for per-source status, checks and any conflicting values.
- **Numbers:** the latest quarter, a quarterly revenue and margin chart, and snapshot, trajectory, balance sheet and cash quality. Every value is computed in code and traceable to its cells.
- **Business:** a segment and business snapshot from the latest annual report, and a bull vs bear case with citations.
- **Ask:** questions answered from the transcripts and annual report. Citations are validated, and numbers that don't appear on the cited page are flagged. Follow-ups remember the last two questions.
- **Watch items:** fixed checks for rising receivable or inventory days, rising leverage, thin interest cover, weak cash conversion and margin compression. An item is flagged only when its inputs exist.
- Opening a screen never triggers a model call. Uncached analyses wait for a tap, and the demo companies are precomputed.

**One command bar** runs the app. It parses deterministically, so it makes no model call:
- `DIXON` opens research.
- `KAYNES promises` opens a specific tab.
- `7d` changes the digest window.
- `vol 3x` or `price 4%` sets alert thresholds.
- A question is answered from the company's own filings.

## Host on Vercel

FINN's phone app is a single static page, so it needs no server or database.

- **Fastest (CLI):** unzip `finn-vercel.zip`, run `cd finn-vercel`, then `npx vercel --prod` and log in when asked.
- **From GitHub (redeploys on every push):** vercel.com/new → import this repo → Deploy. `vercel.json` already sets the install command (`cd frontend && npm ci`), the build command (`npm run build:demo`) and the output folder (`frontend/dist-demo`).

Everything works on Vercel except live **Ask FINN**, which needs Claude; the app says so where Ask appears.

## Real NSE prices in two commands (no API key)

```bash
cd backend
python scripts/import_eod2.py                                        # real NSE end-of-day prices for all 19 holdings + NIFTY 50
python scripts/export_snapshot.py --offline --note-file data/eod2_note.txt
cd ../frontend && npm run build:demo                                 # phone app with real prices, horizons and alerts
```

Prices come from NSE's official daily bhavcopy files via the open [eod2_data](https://github.com/BennyThadikaran/eod2_data) archive (adjusted for splits and bonuses). They are downloaded, never typed, and spot-checked against an independent source: HNGSNGBEES closed at ₹494.96 on 12 Jun 2026 and ₹496.38 on 15 Jun 2026 in both. Filings, reports and AI research come from `python -m finn.ingest` or the daily GitHub run.

## WhatsApp alerts

- **Share:** every important filing and alert has a **Share on WhatsApp** button that opens WhatsApp with a factual message. No setup is needed.
- **Automatic:** FINN sends important new events (big end-of-day moves from the latest session, top-priority filings from the last day) to your phone. Each alert is sent once, up to 10 a day, and every message carries a source link.

The easiest setup is CallMeBot (free, for personal use): message CallMeBot's WhatsApp number once to get an API key, then set these as GitHub secrets or environment variables:

```
FINN_WHATSAPP_PROVIDER=callmebot
FINN_WHATSAPP_TO=+9198xxxxxxxx
FINN_CALLMEBOT_APIKEY=<key from CallMeBot>
```

Twilio is also supported (`twilio`, plus `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_WHATSAPP_FROM`). Your number never leaves the server. `POST /api/notify/test` (with the cron secret) sends a test message.

## Real data without installing anything

- **GitHub Actions** (`.github/workflows/finn-phone-app.yml`): push the repo, add the secret `GEMINI_API_KEY`, set Pages → Source to "GitHub Actions", then run **FINN phone app (real data)** from the Actions tab. GitHub's servers ingest real data, build the app and publish it at your GitHub Pages URL, refreshing every weekday at 19:00 IST. The run's summary shows the coverage report.
- **Google Colab** (`notebooks/FINN_real_data.ipynb`): upload the notebook to colab.research.google.com, choose Run all, upload `finn.zip` when asked, and download the finished `index.html`.

Both run FINN's normal ingestion from cloud servers. If an exchange refuses a cloud IP, FINN keeps going with what it got, and the coverage report shows exactly what came through.

## Real-data phone app in one command (no server needed)

Run this on your laptop (internet needed; a Gemini key enables the AI research):

```bash
cd backend && pip install -r requirements.txt
export GEMINI_API_KEY=...          # optional but recommended
./scripts/phone_app.sh             # ingest -> export -> build
```

What it does:
1. Ingests the 18 real portfolio companies (`finn/portfolio.yaml`): EOD prices, BSE filings, Screener documents, and AI research for the demo companies.
2. Packages FINN's own API responses into `frontend/src/demo/snapshot.json`.
3. Builds `frontend/dist-demo/index.html`: one file you can open on any phone.

The exporter **refuses** to package anything that didn't come from FINN's real ingestion and prints a coverage report. Open the result as a Claude artifact (Ask FINN works live there) or put it on GitHub Pages (everything except live Ask works).

## Phone demo (no server needed)

The real FINN interface also builds as one self-contained HTML file. A small in-browser data layer (`frontend/src/demo/`) replaces the API:
- Its data comes from **FINN's real backend run on three fictional companies**. The promise verdicts and narrative checks are computed by FINN's own code.
- Alert rules, read states and preferences persist on the device.
- When hosted as a claude.ai artifact, Ask FINN answers live through Claude, using only the demo documents and the same citation and number checks.

Nothing in the demo is real market data, and the page says so in a banner.

```bash
cd backend && python scripts/export_demo.py     # regenerate frontend/src/demo/snapshot.json
cd ../frontend && npm run build:demo             # -> frontend/dist-demo/index.html (single file)
```

Normal builds alias the demo module to a stub, so production ships no demo code or data.

## Quick start (local)

Requires Python 3.11+ and Node 20+.

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export GEMINI_API_KEY=your_key                         # free at aistudio.google.com; optional

# 2. Load real data (run on your own machine: BSE/screener are friendlier to residential IPs)
python -m finn.ingest                                  # seed, 1y prices, 30d filings, enrich, research demo
#   or step by step:
#   python -m finn.ingest --step prices
#   python -m finn.ingest --step filings --days 30
#   python -m finn.ingest --step enrich
#   python -m finn.ingest --step research --symbols DIXON KAYNES

# 3. Run
uvicorn finn.api:app --reload --port 8000

# 4. Frontend (another terminal)
cd frontend && npm install && npm run dev               # http://localhost:5173 (proxies /api)
```

Tests (offline, no keys needed): `cd backend && pytest`. This runs 70 tests on SQLite, and the same suite passes on PostgreSQL 16 (`FINN_TEST_DB_URL=…`). Frontend: `cd frontend && npm test` runs 8 unit tests, and `python scripts/ui_journeys.py` clicks through 7 investor journeys in a real browser (see `docs/frontend.md`). The backend tests include an offline Gemini wire test that sends every response schema through the real SDK request builder, and adversarial prompt-injection fixtures.

**Data engine contracts (Part 1)**
- The registry, prices, announcements, documents, timeline, data-quality and source-health endpoints are listed in `docs/handoff.md`.
- Access and licensing notes are in `docs/data-sources.md`.
- Interactive OpenAPI docs are at `/docs` on the running server.

## Verify, then deploy

**1. Verify the live sources on your machine (2–5 minutes).** My build sandbox couldn't reach Yahoo, BSE, Screener or Gemini, so this is the step that turns "not verified" into pass or fail:

```bash
cd backend && export GEMINI_API_KEY=...        # optional; Gemini checks are skipped without it
python scripts/smoke_test.py                   # throwaway DB; prints PASS/FAIL/SKIP; writes smoke_report.json
```

It checks:
- EOD completeness and date alignment, plus idempotent storage.
- BSE code lookup, announcement parsing and a real PDF download.
- Screener tables, QoQ/YoY, and annual-report and transcript discovery with page-level text.
- The unseen-ticker flow.
- Gemini model IDs, classification, a summary whose numbers are checked against the source, and guidance quotes verified verbatim.

If the model check fails, it lists the model IDs your key can use. Set `FINN_MODEL_FAST` and `FINN_MODEL_REASON` to those.

**2. Durable database (recommended): free Postgres on [Neon](https://neon.tech).** Render's free disk is wiped on every restart, which would lose alert rules, read states and preferences. With Neon, nothing needs committing:

```bash
export FINN_DB_URL='postgresql://USER:PASS@HOST/neondb?sslmode=require'
python -m finn.ingest                          # loads real data straight into Neon from your laptop
```

The full test suite passes on PostgreSQL 16 as well as SQLite (`FINN_TEST_DB_URL=postgresql://… pytest`).

*Fallback without Neon:* commit `backend/data/finn.db` after ingesting (remove it from `.gitignore`). The demo data ships with the image, but rule and read-state changes reset whenever Render restarts the service. Say so in your covering note if you use this path.

**3. Render:** New → Blueprint → pick the repo (`render.yaml`). Set these environment variables:
- `GEMINI_API_KEY`.
- `FINN_DB_URL` (your Neon URL).
- `FINN_CRON_SECRET`: Render generates this one; copy it for the next step.

`/api/health` should return `{"ok": true, "llm": true}`.

**4. Scheduled refresh:** in cron-job.org, create a job for `https://<your-app>.onrender.com/api/cron` every 15 minutes, with the custom header `X-Cron-Secret: <FINN_CRON_SECRET>`.
- Without the header the route returns 403; with no secret configured it's disabled (503).
- The job keeps the free instance warm and checks BSE when filings are older than 30 minutes, prices when they're older than 4 hours.
- Each run is idempotent, so repeated runs never duplicate filings or alerts.

**Freshness model:** EOD prices only, with no streaming. Filings refresh three ways: when stale on a read, by the cron job, or from the **Refresh** button on Today, which is limited to once every 2 minutes. If a source blocks the server, FINN keeps serving stored data and shows its age.

**Security defaults:**
- `/api/cron` and the admin enrich route need the secret.
- Model-backed work has a per-visitor hourly cap and a global daily cap (`FINN_ASK_PER_IP_HOUR`, `FINN_RESEARCH_PER_IP_HOUR`, `FINN_LLM_RUNS_PER_DAY`). Cached research is never counted.
- Document downloads refuse private and loopback addresses, checked on every redirect.
- The API is same-origin by default (`FINN_CORS_ORIGINS` to open it).
- The API key is never logged or echoed in errors.

## Architecture

```
backend/finn/
  sources/   prices.py (yfinance), bse_filings.py (bse lib), screener.py, pdf.py, http.py
  store.py   one shared layer for screener snapshots + documents (page-level text) used by Push and Pull
  llm.py     Gemini: routing (fast/reason), structured output, persistent cache = cost ledger
  push/      classify.py  alerts.py  results.py  mgmt.py  digest.py  refresh.py
  pull/      periods.py  metrics.py  retrieve.py  citations.py  promises.py  agent.py
  api.py     FastAPI (+ serves frontend/dist)      ingest.py  CLI
frontend/src/
  views/     Today, Portfolio, Research          components/  Feed, Chrome (command bar, citations, settings), ui
  intent.ts  deterministic command parser
```

## Key decisions

| Decision | Why |
|---|---|
| Rules first, model second, for classification | About 90% of filings are placed by rules: free, instant, explainable. The cheap model sees only leftovers, in one batched call. |
| The LLM extracts, code judges | Model output is restricted to reading: numbers from results tables, and guidance with verbatim quotes from transcripts. Arithmetic, fiscal-period mapping and verdicts are deterministic and unit-tested. |
| Model routing | `gemini-3.5-flash-lite` handles bulk extraction. `gemini-3.6-flash` is used only for Q&A, bull/bear, and transcript-only promise checks. Both are configurable by environment variable. |
| Cache everything | Every model response is stored by hash of model, prompt and inputs. Re-runs and repeat visits cost nothing. The settings screen shows calls, tokens and cache hits. |
| Verification after generation | Citations to pages the model wasn't shown are dropped. Numbers missing from the cited page are flagged in the UI. Quotes are matched against page text. |
| BM25 instead of embeddings | Financial questions are keyword-heavy. BM25 has zero cost and no index service, and it's deterministic. |
| BSE only for filings | NSE's API needs browser cookies and rejects cloud IPs. Every NSE large- and mid-cap also files on BSE. The maintained `bse` library absorbs BSE's endpoint changes. |
| Ingest locally, ship the SQLite file | The thing that matters is that the demo runs. Live refresh is a best-effort layer on top. |

## Known limitations

- Screener parsers are tested against a fixture built to screener's current markup. Run ingestion once to confirm against live pages.
- **Scanned filings:** results and management PDFs without a text layer go to Gemini as PDFs, which costs more. Scanned transcripts and annual reports are skipped.
- **Guidance in USD or constant currency** (IT services) is flagged rather than force-compared with INR revenue.
- **Promise verdicts on vague horizons** ("medium term") use the run-rate since the call and are labelled as such.
- This is a single-user demo: preferences are global, with no authentication.

See `docs/COVERING_NOTE.md` for trade-offs, exclusions and next steps.
