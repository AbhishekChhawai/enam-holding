# Supervisor demo and release status

## The demo (about 6 minutes, on a phone, no database edits)

0. **First visit:** the 3-step tour (skippable, with plain English on by default). Tap any dotted term, like EBITDA, to see what it means. The header switch flips between Plain and Detailed.
1. **Today:** "N of M filings need you". The strip settles to show which filings were set aside. Switch the window to **7d** if the last 24 hours were quiet. That's the true empty state; FINN never backfills it.
2. Tap a results card. You get Revenue, EBITDA, PBT and PAT with QoQ and YoY, a ✓ when the filing and screener.in agree, and **Why it's at the top** with the score's reasons.
3. Tap **+N related filings** for the results-day bundle, then **Open filing** for the original BSE PDF.
4. **Depth:** Quick → Standard → Deep. The density changes; the facts don't.
5. **Unusual moves:** a price or volume row shows **Around this session** with nearby filings, stated as context, not cause.
6. **Alerts → Edit rules:**
   - Add *DIXON, price, either way, 3%*. Saving reports how many recent sessions matched.
   - Add *Any holding, Filings, Management change*.
7. **Alerts:** open an alert to mark it read. Reload the page and the read state is still there. Tap **Check now** and the count doesn't grow, because alerts are deduplicated.
8. A price alert's **Why now?** line names the nearby filings, or says plainly that there were none.
9. From a results filing, tap **Research this**. The banner shows the period and a suggested question. **Ask this** sends it, and only then is the model called.
10. **Research → Promises:** promised vs delivered. Each verdict has its variance, a quote with page citation, and **Open results filing**. Scroll to **Narrative vs numbers** for management's claims against the reported figures. On a company that isn't precomputed, tap **Run promise check**: opening the screen alone never calls the model. **Timeline** shows filings, moves and quarters together. Tap the freshness line under the name for sources, checks and conflicts.
11. Type an unseen symbol (e.g. `KAYNES`) in the command bar. FINN registers it, fetches its prices and filings, and runs research.

## Phone checklist (run on a real device before submitting)

- [ ] The HTTPS URL loads on Chrome (Android) and Safari (iOS), and the bottom bar isn't hidden under the system bars.
- [ ] The command bar works with the on-screen keyboard, and the suggestions are tappable.
- [ ] Today loads, the window and depth switches work, and Refresh shows a result toast.
- [ ] Filing sheets open, and **Open filing** opens the PDF.
- [ ] The Alerts badge updates. Rules save, edit, pause and delete. Read and unread state survives a reload.
- [ ] Research tabs load, a citation sheet opens at the right page, and **Open PDF at page N** works.
- [ ] Reloading a deep link (e.g. `/#research/DIXON/timeline`) returns to the same screen.

## Final acceptance report (this build)

**Statuses:**
- PASS: tested and verified.
- FAIL: tested and didn't work.
- BLOCKED: couldn't run because of missing access in the build environment.
- NOT TESTED: not yet checked.

A mocked or fixture test is never counted as live-provider verification. The live checks belong to `scripts/smoke_test.py`, which labels its rows "PASS (real provider)", "FAIL" or "NOT VERIFIED".

| # | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Backend tests | PASS | 70/70 from a clean checkout in a fresh virtualenv (`pip install -r requirements.txt`, `pytest`) |
| 2 | PostgreSQL tests | PASS | 70/70 on PostgreSQL 16; the server also ran against Postgres with `sslmode=require` |
| 3 | Frontend build | PASS | `npm ci` and `npm run build` from scratch |
| 4 | Yahoo Finance | BLOCKED | Sandbox has no route to Yahoo. Smoke test checks completeness, alignment, idempotent storage and read-back through the API |
| 5 | BSE filings | BLOCKED | No route to BSE. Field names match the `bse` package's real sample response; URL patterns confirmed on the live screener page |
| 6 | Annual report retrieval | BLOCKED | Discovery parser corrected against the live page layout ("Annual Report 2026"); download is in the smoke test |
| 7 | Transcript retrieval | BLOCKED | Live links use BSE's viewer URL, now with direct-file fallbacks; download is in the smoke test |
| 8 | Gemini authentication | BLOCKED | No key or network. Offline: every schema passes the real SDK request builder; truncated output is retried with more room |
| 9 | Source-grounded research | PASS (logic) / BLOCKED (live) | Citation and number checks, including the tiny-corpus retrieval fallback. Live Q&A plus an unanswerable-question check are in the smoke test |
| 10 | Promise tracker | PASS (logic) / BLOCKED (live) | Exceeded, missed, pending and in-progress outcomes, variance, and both source links tested |
| 11 | Narrative vs numbers | PASS (logic) / BLOCKED (live) | All five verdicts; quotes not found verbatim are dropped |
| 12 | Follow-up context | PASS | Three-turn conversation keeps the topic in retrieval; history is labelled "not evidence" |
| 13 | Watch items | PASS | Flags appear only when inputs cross the line; fiscal-year comparisons |
| 14 | Evidence inspector | PASS (logic) / BLOCKED (real PDFs) | Page API, highlight and open-at-page link |
| 15 | Research This | PASS | Context contract tested. Opening research makes no model calls (tested, and repeated in the smoke test) |
| 16 | Prompt-injection safety | PASS | 12 adversarial fixtures. Found and fixed: hostile titles could forge excerpt attributes, and promise-check excerpts weren't sanitised. No secrets reach prompts; fabricated citations and numbers are caught. The model has no tools to invoke |
| 17 | Database persistence | PASS | A real server was killed and restarted on Postgres: rules, read states, preferences and prices survived, and deduplication held across restarts |
| 18 | Cron security | PASS | Running server: 503 with no secret configured, 403 with a missing or wrong header, 200 with the secret. Credentials never appeared in logs |
| 19 | Public deployment | BLOCKED | No hosting credentials. The Dockerfile's start command was replayed on an empty database: index, assets, SPA fallback, JSON 404s, seeding and health all pass |
| 20 | Mobile browser | PASS (headless) / NOT TESTED (physical phone) | `scripts/ui_journeys.py`: 7 clicked-through journeys plus 9 routes × 5 widths with no overflow, on a synthetic fixture; phone checklist above |
| 21 | Frontend unit tests | PASS | `npm test`: 8 Vitest tests (intent parser, formatting) |
| 22 | Beginner experience | PASS (scripted) | FINN Explain (44 terms), Plain/Detailed, structured insight sheet, 3-step tour; 6 beginner walkthroughs in `ui_journeys.py` (synthetic fixture, not a real-user study) |
| 23 | Touch-target size | PASS | Automated WCAG 2.2 2.5.8 check across 6 screens; inline-text and documented equivalent-control exceptions only |

## Acceptance matrix (as of this build)

PASS means it was executed here. NOT VERIFIED means it needs network access or a device that this build environment didn't have. Update the right-hand column from `smoke_report.json` and your phone check.

| # | Requirement | Status | Evidence or reason |
|---|---|---|---|
| 1 | Backend test suite | PASS | 55/55 on SQLite and on PostgreSQL 16 |
| 2 | Frontend production build | PASS | `tsc` and `vite build`, no errors |
| 3 | EOD data ingestion | NOT VERIFIED | Sandbox can't reach Yahoo. Run `scripts/smoke_test.py` |
| 4 | Corporate-filing ingestion | NOT VERIFIED | Sandbox can't reach BSE. Field names were checked against the `bse` package's real sample response |
| 5 | Annual report retrieval | NOT VERIFIED | Needs network. Smoke test |
| 6 | Transcript retrieval | NOT VERIFIED | Needs network. Smoke test |
| 7 | PDF text extraction | PASS (offline) / NOT VERIFIED (live) | PyMuPDF page extraction runs in tests; no real exchange PDF has been fetched yet |
| 8 | Gemini classification | NOT VERIFIED | No key or network here. Schemas pass the real SDK's request builder offline (`test_llm_wire.py`) |
| 9 | Gemini summary grounding | NOT VERIFIED | Same. The number and citation checks are unit-tested |
| 10 | Alert rule persistence | PASS | API tests; durable in deployment only with `FINN_DB_URL` (Neon) |
| 11 | Alert deduplication | PASS | Database-enforced unique key; repeated evaluations tested |
| 12 | Unread inbox | PASS | API and UI; read state persisted |
| 13 | Digest generation | PASS | Windows, tiers, ordering, collapsed routine filings |
| 14 | Quarterly results calculations | PASS | QoQ/YoY, units, loss bases, filing vs screener cross-check |
| 15 | Smart event clustering | PASS | Groups related filings, keeps unrelated ones separate, one alert per results day |
| 16 | Why-Now | PASS | Nearby filings, plus an explicit "none nearby" case |
| 17 | Attention mode | PASS | Same data in all three modes; preference remembered |
| 18 | Research This handoff | PASS | Context contract tested; the model is called only on "Ask this" |
| 19 | Unseen ticker | PASS (mocked) / NOT VERIFIED (live) | Resolution and ingestion logic tested with mocks; live run in the smoke test |
| 20 | Mobile responsiveness | PASS | No horizontal overflow at 320, 375, 390, 768 or 1280px across all screens and research tabs (headless Chromium) |
| 21 | Database persistence | PASS with Neon / FAIL on Render disk alone | Free Render disk is ephemeral; documented |
| 22 | Cron endpoint security | PASS | 503 when no secret is set, 403 for a wrong or missing header; tested |
| 23 | Deployment | NOT VERIFIED | No hosting credentials here. `render.yaml` and Dockerfile are ready |
| 24 | Real phone accessibility | NOT VERIFIED | Needs a device. Checklist above |
| 25 | Submission documentation | PASS | README, handoff, data sources, covering note, this file |
| 26 | Narrative vs numbers | PASS (logic) / NOT VERIFIED (live) | All five verdicts and quote verification tested with fixtures; live extraction needs Gemini |
| 27 | Promise variance and both sources | PASS | Variance, exceeded and pending outcomes, and the results-filing link tested |
