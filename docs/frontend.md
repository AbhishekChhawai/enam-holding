# Frontend: architecture, design system and Part 4 audit

## Architecture

| | |
|---|---|
| Stack | React 18, TypeScript, Vite 6, Tailwind 4. No UI library and no chart library: the charts are small hand-written SVGs, keeping the bundle around 70 KB gzipped. |
| Routing | Hash routes, so deep links survive a refresh on any static host: `#today`, `#alerts`, `#portfolio`, `#research`, `#research/{SYMBOL}/{promises\|numbers\|timeline\|business\|ask}`. |
| State | Local React state plus `useApi` (fetch, then loading/error/data, with stale-response protection). Shared actions pass through `UIContext`: open a citation, open research, open a filing, open settings, and Research this. |
| Persistence | Server state lives in the API: rules, read states and preferences. Browser state is limited to the attention mode and recent companies, both in `localStorage` and guarded. |
| API | `src/api.ts`. The base URL comes from `VITE_API_BASE` (default same-origin) and contains no localhost. |
| Files | `views/` (Today, Alerts, Portfolio, Research, Insight), `components/` (ui, Feed, Chrome, PriceChart), `intent.ts` (command parser), `format.ts`, `types.ts`. |

## Design system

- **Tokens:** CSS variables on `:root` with a full dark theme.
  - Paper `#F6F7F9`, ink `#1D2433`, muted `#667085`, hairlines `#E3E7EE`.
  - Marigold `#F2A900` is the single accent, reserved for things that need attention.
  - Up and down colours are muted greens and reds.
- **Type:** Anek Latin (Ek Type, an Indian foundry) for headings and symbols; Public Sans with tabular numerals for figures.
- **Status is never colour-only:** verdict chips carry a glyph and a word (✓ Delivered, ✕ Missed, ◐ Partly, ▲ Exceeded), and moves carry a sign.
- **One layout:** a mobile-first single column, max 36rem, with a fixed command bar and bottom navigation. Safe-area insets are respected.
- **Shared components:** `Sheet` (bottom sheet with Escape and focus return), `Segmented`, `Spark`, `VerdictChip`, `CiteChip`, `Loading`, `Notice`, `SectionHead`, `RunGate` (run-on-request), and `PriceChart`.

## Part 4 audit: gaps found and fixed

| Outcome | Before | Fix |
|---|---|---|
| Premium mobile experience | No historical price chart; long names wrapped to 3 lines | `PriceChart`: 1M/3M/6M/1Y, volume bars, drag to read any session, explicit min/max labels and an EOD note. Responsive heading size |
| Push → Pull round trip | Research This was one-way | **Back to the filing** in the handoff banner reopens the originating event |
| Evidence-first | The citation sheet didn't say which document it was | Header with title, type, period, company, page N of M and source host; flags scanned documents; the highlight ends exactly at the quote |
| AI-native glance | The brief line omitted moves and alerts; the top item wasn't singled out | Brief adds unusual moves and an unread-alerts link; the first card is labelled "Highest priority right now" |
| Every control works | Research landing had no visible search. **Ask showed nothing without a model key.** Two controls shared the name "Ask" | Landing search with recents and portfolio chips. Ask renders no-key and no-document states. The submit button is named "Send question" |

## Tests

- `cd frontend && npm test`: Vitest, 8 tests on the intent parser and financial formatting.
- `cd backend && python scripts/ui_journeys.py`: a real browser against a real server, with a fictional synthetic company (FINNDEMO) in a throwaway database. It runs 7 journeys (morning review, Push → Pull and back, promise to both sources, alert lifecycle with persistence, price chart on a reloaded deep link, search, Ask without a key) plus a sweep of 9 routes × 5 widths for overflow. Needs `pip install playwright && playwright install chromium`.
- Not covered here: live data (`scripts/smoke_test.py`) and a physical phone (checklist in `SUPERVISOR_DEMO.md`).

## Part 5 handoff

- **Build:** `npm ci && npm run build`. The Dockerfile already serves `frontend/dist` from FastAPI, so no frontend environment variables are needed for same-origin deployment.
- **Separate frontend host:** set `VITE_API_BASE` at build time, and `FINN_CORS_ORIGINS` on the API.
- **Known limits:** no route-level code splitting (it isn't needed at this size), no offline mode, and no push notifications.

## Part 5: beginner experience (audit → gaps → fixes)

| Gap found | Fix | Evidence |
|---|---|---|
| Finance terms (EBITDA, PAT, QoQ, YoY, ROCE…) were unexplained | **FINN Explain**: 44 prewritten entries in `src/glossary.ts`, each with "In simple terms / What it is / Why it matters / Related". Dotted terms are tappable in results tables, metric rows, promise text, the alert builder and Help. No model call | B2 walkthrough |
| Results shown only as tables; promises as "15–17%, +3.0 pp" | **Plain English / Detailed** switch in the header, Plain by default. `src/plain.ts` builds sentences in code from the same data ("Sales were ₹1,560 crore in Q2 FY27, up 20.0% from a year earlier") | B1, B4 |
| The filing sheet's "why" was scoring internals | Plain sheet reads **What happened → Why it matters** (fixed per-category text) **→ The proof** (numbers and original filing) **→ What next** (Research this). Scoring moves under "How FINN ranked this" | B3 |
| No first-run guidance or help | 3-step skippable tour (remembered; replay from Help). Help holds the mode switch, "good to know" notes (EOD prices, sources, no advice) and a searchable glossary | B0 |
| Alert types assumed knowledge | Each rule type explained in everyday words, with EOD and volume terms tappable | B5 |
| Many controls under 24 px | Automated WCAG 2.2 2.5.8 check; 37 controls fixed. The attention-strip ticks use the documented equivalent-control exception: full-height tap area, and every filing also has a full-size card | A11y check |

The walkthroughs in `scripts/ui_journeys.py` are scripted persona tests on a synthetic fixture, **not** a study with real users.

## Visual refresh: blue glass

**Look:** a soft sky gradient backdrop (midnight with a blue glow in dark mode), frosted cards (`.bg-surface` adds blur and a soft shadow) and a deep-navy hero (`.navy`). The hero re-themes everything inside it to light-on-navy by overriding the colour variables, so no component needed rewriting. It also adds pill chips, monogram avatars, round icon buttons and a floating icon tab bar. Type is Plus Jakarta Sans.

**Motion (all CSS, honours `prefers-reduced-motion`):**
- Buttons compress on press.
- Segmented controls and the tab bar have a springy sliding thumb.
- Cards rise in one after another.
- Hero numbers count up.
- The price line draws itself, and portfolio ring arcs fade in.
- The theme icon spins between sun and moon; unread badges pop in; sheets spring up.

**Theme:** Auto, Light or Dark (Help → Appearance, or the header toggle), remembered on the device. Auto follows the phone or the viewer's `data-theme`.

**Inspiration:** patterns from Groww/Robinhood (one hero number with chips, a chart you scrub), Apple Wallet/iOS (glass, springy controls) and Zerodha (dense monogram lists). The layout and branding are FINN's own.
