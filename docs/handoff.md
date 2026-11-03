# Part 1 handoff: FINN data engine

The data engine lives inside the FINN backend (`backend/finn`) rather than as a separate service, so Push, Pull and the UI share one ingestion path and one database. Everything below is reachable over HTTP; no module needs to read the database directly.

## What Part 1 implements

| Area | Implementation |
|---|---|
| Company registry | `companies` table, seeded from `finn/portfolio.yaml` (18 companies). BSE codes are verified against BSE lookup at ingest. |
| Unseen tickers | `POST /api/companies/resolve`, or simply opening research on any symbol. Normalises the symbol, validates it via BSE lookup or a Yahoo quote, registers the company, and starts a background ingestion of 1 year of prices and 90 days of filings. |
| EOD prices | yfinance, batched. NSE first, with a BSE fallback per symbol. Upsert on (symbol, date). |
| Filings | BSE announcements via the maintained `bse` package. Upsert on BSE NEWSID. The original BSE category and subcategory are kept alongside FINN's normalised category. |
| Documents | Discovered from screener.in's index of primary documents, then downloaded on demand. Page-level text is stored with 1-based page numbers. Scanned PDFs are flagged rather than treated as text. |
| Financial observations | Results filings: Revenue, EBITDA, PBT and PAT for current, previous and year-ago quarters, unit-normalised and cross-checked against screener.in. Standardised multi-year tables come from screener.in. |
| Timeline | `GET /api/companies/{t}/timeline` merges filings, flagged market sessions, reported quarters and concalls. Same-window links are explicitly not causal. |
| Data quality | `GET /api/companies/{t}/data-quality` returns per-source status and confidence, deterministic checks, and conflicts. `GET /api/system/source-health` gives the global picture. |
| Schema | Generated from the models: `backend/financial_schema.sql` (SQLite) and `financial_schema.postgres.sql`. New nullable columns are auto-added on start-up. |

## Deliberately not implemented

- **NSE adapter:** NSE's API needs browser cookies and blocks cloud IPs. BSE carries the same filings for these companies, so cross-exchange deduplication isn't needed.
- **Alembic:** schema changes so far are additive and applied at start-up. A destructive change would need a real migration.
- **OCR:** scanned documents are flagged as such, never presented as extracted text.
- **Separate `document_chunks` table:** pages are the retrieval unit (BM25 over pages), which keeps every citation at page level.
- **Separate Data Explorer app:** the FINN app is the explorer. The Research tabs (Numbers, Timeline, the data sheet) are the Part 1 demo surface.

## Run, seed, refresh

```bash
cd backend && pip install -r requirements.txt
python -m finn.ingest                       # seed + 1y prices + 30d filings + enrichment + research demo
python -m finn.ingest --step filings --days 7
uvicorn finn.api:app --port 8000            # API docs at /docs (OpenAPI)
pytest                                      # 23 offline tests
```

## Identifiers

| Entity | ID format |
|---|---|
| Company | The NSE symbol, upper case (`DIXON`). Inputs `DIXON.NS`, `NSE:DIXON` and `DIXON.BO` normalise to it; a 6-digit BSE code resolves via BSE lookup. |
| Announcement | BSE NEWSID (UUID string). |
| Document | `sha1(url)[:16]`. Stable across runs. |
| Timeline event | `ann:{newsid}`, `mkt:{date}`, `qtr:{quarter-end label}`, `call:{month label}`. |

## Endpoints

| Method and path | Purpose | Main consumer |
|---|---|---|
| `GET /api/companies?portfolio=true` | Registry | 2, 4 |
| `GET /api/companies/search?q=` | Local and screener search | 4 |
| `GET /api/companies/{t}` | Identity plus ingestion job status | 4, 5 |
| `POST /api/companies/resolve {"symbol"}` | Add an unseen ticker | 4, 5 |
| `GET /api/companies/{t}/prices?period=1m\|3m\|6m\|1y\|2y\|5y\|max&start&end` | OHLCV plus change, % and volume multiple | 2, 4 |
| `GET /api/companies/{t}/announcements?category&start&end&has_document&sort&limit&offset` | Filings with original and normalised category | 2 |
| `GET /api/companies/{t}/documents?kind=` | Discovered and processed documents | 3 |
| `GET /api/documents/{id}?load=true` | Metadata, triggering download and extraction | 3 |
| `GET /api/documents/{id}/pages/{n}` | Page text plus `open_url` (`…#page=n`) | 3, 4 |
| `GET /api/companies/{t}/timeline?types=results,filings,market,documents,corporate_actions` | Unified chronology | 2, 4 |
| `GET /api/companies/{t}/data-quality` | Freshness, checks, conflicts | 4 |
| `GET /api/system/source-health`, `GET /health` | Operations | 5 |
| `POST /api/refresh`, `GET /api/refresh` | Manual refresh (rate-limited to once per 2 minutes) and its status | 4 |
| `GET /api/cron` | Scheduled polling plus keep-warm; point a free scheduler here | 5 |

Push and Pull endpoints (`/api/digest`, `/api/research/*`) are documented in the README. Part 2 alert endpoints are listed next.

## Part 2: Push engine additions

| Method and path | Purpose |
|---|---|
| `GET /api/alerts?unread&kind=market\|filing&symbol&limit&offset` | Alert inbox, with `unread_count` and `evaluated_at` |
| `PATCH /api/alerts/{id} {"read"}`, `POST /api/alerts/read-all` | Read state |
| `GET /api/alerts/rules`, `POST /api/alerts/rules`, `PATCH /api/alerts/rules/{id}`, `DELETE /api/alerts/rules/{id}` | Rule CRUD. Create and edit immediately evaluate the rule over the last 10 sessions and 7 days of filings, and return the result. |
| `POST /api/alerts/evaluate` | Manual evaluation. Deterministic, with no network or model call. |
| `GET /api/alerts?kind=price\|volume\|market\|filing&unread=true\|false` | Inbox filters. Each item carries `rule_kind`. |
| `GET /api/alerts/unread-count`, `POST /api/alerts/mark-all-read` | Aliases matching the Part 2 spec; `/read-all` still works. |
| `GET /api/alerts/runs` | The last 20 evaluation runs: rules checked, alerts created, per-rule failures. One failing rule doesn't block the others. |
| `GET /api/announcements/{id}/research-context` | The "Research this" handoff from Push to Pull. |

**Research-context contract** (stable):
- `symbol`, `company`, `event_id`, `category`, `category_label`, `headline`, `summary`, `published_at`.
- `related_filing_ids`: the event's results-day bundle, found even when you open a companion filing.
- `document_ids`, which resolve through `/api/documents/{id}`.
- `reporting_period`, from the results card when present.
- `suggested_question`, one per category.
- `target_tab`: `promises`, `numbers` or `ask`.

The frontend shows this as a banner on the Research screen with an "Ask this" button. The question is only sent to the model when the investor taps it.

**Why-now on alerts:** each market alert stores `provenance.nearby` (non-routine filings in the window) and `provenance.context`. When nothing is nearby, the context says so explicitly instead of offering an explanation.

**Clusters are computed, not stored.** Grouping is deterministic: same company, within 36 hours of a real results filing, results-family documents only. That makes it idempotent by construction, with no stored copy to drift out of sync. Filing alerts use the same function, so one results day produces one card and one alert.

**Rules** (`alert_rules`) come in three kinds:
- `price_move`: direction `either`, `up` or `down`, with a threshold in %.
- `volume`: a threshold as a multiple of average volume, over a lookback window of 5–120 sessions (default 20, excluding the current session).
- `filing`: a list of categories plus a minimum tier.

`symbol: null` means the whole portfolio. The portfolio-wide rules are the single source of truth for thresholds: they are mirrored into prefs, which the digest's move flags and the command-bar shortcuts use.

**Alerts** (`alerts`) are idempotent by `dedupe_key`: `r{rule}:{symbol}:{session}` for market rules, `r{rule}:ann:{newsid}` for filing rules.
- Market rules only read completed EOD sessions (`quality.expected_session`).
- Filing alerts respect results-day clustering, so one results day produces one alert, not one per companion document.
- Alerts are evaluated after every refresh (manual, cron or stale-read), after `ingest`, and on `POST /api/alerts/evaluate`.
- Each alert stores its detection time (`created_at`) separately from the filing time or session date.

**Digest additions:**
- `related[]` on a results card lists the companion filings: the results deck, press release, call schedule, and a dividend declared at the same board meeting. They're grouped within 36 hours, same company only. `counts.grouped` reports how many were folded in.
- `moves[].nearby[]` lists non-routine filings from the same company within 3 days before or 1 day after the session. It comes with a `context_note` stating that FINN doesn't infer cause.

**Attention modes** (Quick, Standard, Deep) are frontend views over the same digest response. Quick shows the top 5 that need you and the top 3 moves; Deep expands routine filings and bundles. The facts and citations are identical across modes.

## Provenance and confidence conventions

- Every timeline event carries a `provenance`:
  - `direct`: straight from the source.
  - `derived`: computed from prices.
  - `normalized`: standardised figures.
- Each event also carries a `source` and an original `url`.
- Confidence labels: `verified`, `direct`, `derived`, `partial`, `conflicting`, `unavailable`. They are defined in `finn/quality.py` and returned in every data-quality response. There are no made-up percentages.
- Conflicts keep both values and are marked `unresolved`. FINN never picks one silently.
- Freshness: EOD prices are judged against the latest expected weekday session (after 18:00 IST). Exchange holidays aren't modelled, so "one session behind" is reported as *possibly stale*, not *stale*.

## Part 3: Pull research additions

| Method and path | Purpose |
|---|---|
| `GET /api/research/{t}/promises` (alias `/promise-tracker`) `?run=true` | Promised vs delivered. Each item has `verdict`, a spec-facing `outcome` (`exceeded`, `met`, `partly_met`, `missed`, `in_progress`, `pending`, `not_comparable`), `variance` in pp or ₹ cr, `variance_text`, the transcript quote and page, and `actual.source_url` (the results filing for quarter-based checks). |
| `GET /api/research/{t}/narrative?run=true` | Narrative vs numbers: management's descriptive claims about delivered results, each with its verbatim quote and page, the matching reported figure with formula and results-filing link, and a verdict (`supported`, `partly`, `divergent`, `not_measurable`, `insufficient`). The interpretation is a fixed template, not model opinion. |
| `GET /api/research/{t}/business?run=true`, `/bullbear` (alias `/bull-bear`) `?run=true` | Business snapshot and bull vs bear case. |
| `POST /api/research/{t}/ask` `{question, history: [{question, summary}]}` | Cited Q&A. `history` (up to 3 turns) shapes retrieval and meaning but is never treated as evidence. |
| `GET /api/research/{t}/overview` | Deterministic metrics, now including `metrics.watch` (flagged items) and `metrics.watch_checks` (what was checked). |

**Run-on-request:** opening a research screen never spends model calls.
- Without `?run=true`, an uncached analysis returns `{"status": "not_run", "note"}`.
- Cached results return instantly, with `cached_at` and `stale`.
- Only `run=true` on uncached or stale work counts against the visitor and daily budget.
- `python -m finn.ingest` precomputes all four analyses for the demo companies.

**Hardening:**
- Every model prompt states that document text is untrusted data.
- Excerpt delimiters inside document text are neutralised, so injected text can't break out of an excerpt.
- Retrieval falls back to term overlap when BM25 scores nothing, which happens on tiny corpora.

## Example: `GET /api/companies/DIXON/prices?period=1m` (abridged)

```json
{"symbol":"DIXON","currency":"INR","interval":"1d","provider":"yfinance:NSE","adjusted":true,
 "freshness":"fresh","expected_session":"2026-10-30","count":21,"from":"2026-10-01","to":"2026-10-30",
 "bars":[{"date":"2026-10-30","open":1306.2,"high":1404.0,"low":1301.5,"close":1399.77,"volume":2690000,
          "change":91.3,"pct":7.0,"volume_multiple":2.7}]}
```
