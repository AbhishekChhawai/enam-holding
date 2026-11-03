# Data sources, access and limitations

| Source | Used for | Access method | Verification status |
|---|---|---|---|
| Yahoo Finance via `yfinance` | EOD OHLCV | Public library. One batched call for the portfolio, with bounded retries. | Library calls written to its documented API. **Live check happens on the first `python -m finn.ingest` run.** |
| BSE via the `bse` package | Announcements, attachments, symbol and code lookup | The maintained package (v3.3.3, Sept 2026) tracks BSE's headers and endpoints and throttles requests. | Field names verified against the package's real sample responses (`tests/fixtures/bse_announcements.json`). |
| screener.in | Standardised financials and links to annual reports and transcripts | Public company pages. Cached 12–24 hours, and the cached copy is served if a refresh fails. | Parser verified against a fixture built to screener's current markup, cross-checked with two maintained open-source scrapers. |
| Company and BSE PDFs | Primary documents | Downloaded only from links found on BSE or screener. 60 MB cap and `%PDF` magic-byte check. | Exercised on the first ingestion run. |
| Gemini API (free tier) | Extraction and reasoning | `google-genai`. Only public filings are sent. | Requires `GEMINI_API_KEY`. Without it, all deterministic features still work. |

## Access and licensing notes

- **yfinance:** Yahoo's data is intended for personal use. That fits a non-commercial prototype; a production deployment would switch the price provider to a licensed feed. Prices sit behind `sources/prices.py`, so only that module changes.
- **BSE:** FINN reads publicly disseminated announcements at a throttled rate and never bypasses access controls. A 403 is logged and the cached data is served.
- **NSE:** not used, because automated access requires browser session cookies and is typically refused for cloud IPs.
- **screener.in:** public pages only. No login and no premium data. Requests are cached to keep volume low.
- **No user-supplied URLs are ever fetched.** `resolve` takes a symbol, and documents come only from links discovered on BSE or screener. This closes the server-side request forgery route.

## Synthetic data

None ships. Tests build their own fixtures in a temporary database; one test simulates a conflicting value and one a broken price bar to exercise the quality checks. The committed `finn.db` (after you run ingestion) contains only fetched data, with retrieval timestamps.

## Live layout check (1 Nov 2026)

The build sandbox couldn't reach the providers, so Dixon's live screener.in page was inspected with a separate fetch tool. FINN's own code did not run against it, so this is evidence about the page layout, **not** provider verification.

**Confirmed:**
- Quarter columns are labelled like "Sep 2026".
- The row labels are "Sales +", "Operating Profit", "OPM %", "Net Profit +" and "Raw PDF", and the Raw PDF row links to `/company/source/quarter/…`.
- The AI-extracted "Insights" tables are a separate section after Ratios.

**Changed, now handled** (regression fixtures in `tests/test_live_layout.py`):
- Annual reports are titled "Annual Report 2026" rather than "Financial Year 2026".
- Transcripts link through BSE's viewer (`stockinfo/AnnPdfOpen.aspx?Pname=<id>.pdf`). FINN falls back to `xml-data/corpfiling/AttachLive/<id>` and `AttachHis/<id>`.
- The cash-flow table has a "Free Cash Flow" row, which FINN now uses (the old proxy is only a fallback).
- The balance sheet ends with a half-year column. Three-year comparisons now use fiscal year-ends.
