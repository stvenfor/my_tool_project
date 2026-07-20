# ETF Enhanced Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible Python 3.12 report pipeline with official ETF share-flow windows, KDJ, MACD, sentiment, and four-dimensional reasons for all 68 representative ETFs.

**Architecture:** Add a standard-library exchange-share provider and a pure calculation/reporting layer. Keep network I/O injectable, persist provenance and per-window missing reasons, and render the same typed report model to Markdown, CSV, and JSON.

**Tech Stack:** Python 3.12 standard library, `unittest`, existing ETF `DailyBar` model, official SSE/SZSE HTTP endpoints, Markdown/CSV/JSON, `lark-cli` for the final Feishu overwrite.

## Global Constraints

- Net flow means primary-market ETF share creation/redemption cash flow, never secondary-market main-force flow.
- Missing or unresolved data is `N/A` with a stable reason; it is never zero and is never estimated.
- Unit tests are fixture-only and must not access the network.
- Existing advisory-only and no-auto-order boundaries remain unchanged.
- Local report generation and tests use Python 3.12.

---

### Task 1: Technical and sentiment calculations

**Files:**
- Create: `modules/etf-monitor/src/reporting.py`
- Create: `modules/etf-monitor/tests/test_reporting.py`

**Interfaces:**
- Consumes: `Sequence[DailyBar]`, normalized `SharePoint` values, report breadth.
- Produces: `KdjValue`, `MacdValue`, `FlowWindow`, `SentimentValue`, `analyze_bars()`, `calculate_share_flows()` and `score_sentiment()`.

- [ ] **Step 1: Write failing tests for KDJ and MACD**

Create deterministic OHLC fixtures and assert K, D, J, DIF, DEA and histogram values against independently precomputed constants. Assert that fewer than 26 bars raises `ReportDataError("insufficient_bars_for_macd")`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `python3.12 -m unittest modules.etf-monitor.tests.test_reporting -v`

Expected: import failure because `src.reporting` does not exist.

- [ ] **Step 3: Implement minimal indicator functions**

Use explicit EMA recursion seeded from the first close and KDJ recursion seeded at 50. Return frozen dataclasses and stable Chinese state labels.

- [ ] **Step 4: Write and verify failing share-flow tests**

Cover 5/10/20 trading-day sums, missing dates, nonzero negative redemption, close-price basis and unresolved split detection.

- [ ] **Step 5: Implement share-flow calculation**

Align by trading date, calculate daily share delta × price, and return per-window values or reason codes without affecting other windows.

- [ ] **Step 6: Write and verify failing sentiment tests**

Assert weighted score, label thresholds, missing-flow reweighting and the list of missing inputs.

- [ ] **Step 7: Implement sentiment scoring and run the full file**

Run: `python3.12 -m unittest modules.etf-monitor.tests.test_reporting -v`

Expected: all tests pass.

### Task 2: Official exchange share providers

**Files:**
- Create: `modules/etf-monitor/src/report_sources.py`
- Create: `modules/etf-monitor/tests/fixtures/report/sse_scale.json`
- Create: `modules/etf-monitor/tests/fixtures/report/szse_scale.xlsx`
- Create: `modules/etf-monitor/tests/test_report_sources.py`

**Interfaces:**
- Consumes: date/date-range, injectable `opener` returning SSE JSON or SZSE XLSX bytes.
- Produces: `SharePoint(code, date, shares, source, fetched_at)`, `SseShareProvider.fetch_date()` and `SzseShareProvider.fetch_range()`.

- [ ] **Step 1: Write failing SSE parser tests**

Assert `TOT_VOL=5533716.68` becomes `55_337_166_800` shares, code is zero-padded, and malformed/incorrect-date rows are rejected.

- [ ] **Step 2: Run SSE tests and verify RED**

Run: `python3.12 -m unittest modules.etf-monitor.tests.test_report_sources.ReportSourceTests.test_sse_parser -v`

Expected: import or missing-function failure.

- [ ] **Step 3: Implement the SSE parser/provider and verify GREEN**

Use `urllib.request.Request` with SSE Referer and User-Agent. Parse only `result` rows and preserve `STAT_DATE`.

- [ ] **Step 4: Write failing SZSE XLSX parser tests**

Fixture rows must include two dates and two codes. Assert exact share units, dates and names without pandas/openpyxl.

- [ ] **Step 5: Implement minimal XLSX parsing and SZSE provider**

Use `zipfile` plus `xml.etree.ElementTree` for workbook relationships, shared strings and the first sheet. Request `CATALOGID=scsj_fund_jjgm`, `jjlb=ETF`, `SHOWTYPE=xlsx`.

- [ ] **Step 6: Test provider error boundaries**

Cover HTTP failure, invalid ZIP/XML, missing columns, empty date range and dates outside the requested interval.

- [ ] **Step 7: Run source tests**

Run: `python3.12 -m unittest modules.etf-monitor.tests.test_report_sources -v`

Expected: all tests pass.

### Task 3: Four-dimensional context and report rendering

**Files:**
- Create: `modules/etf-monitor/data/sector_context.json`
- Modify: `modules/etf-monitor/src/reporting.py`
- Modify: `modules/etf-monitor/tests/test_reporting.py`

**Interfaces:**
- Consumes: universe sector, evidence theme, technical result, sentiment result.
- Produces: one `ReportRow` with `policy_reason`, `fundamental_reason`, `technical_reason`, `sentiment_reason`, plus Markdown/CSV/JSON renderers.

- [ ] **Step 1: Write failing context-schema tests**

Assert every representative sector maps to exactly one theme; every theme has nonempty policy/fundamental text, `as_of`, source title, publisher, date and HTTPS URL.

- [ ] **Step 2: Write failing renderer tests**

Assert headers include KDJ, MACD, sentiment, 5/10/20 share flow and all four reason dimensions. Assert Markdown escapes pipes and renders missing windows as `N/A（reason）`.

- [ ] **Step 3: Add reviewed context data**

Group sectors into auditable policy/fundamental themes. Use current official sources where present; otherwise state the lack of a recent direct catalyst and retain the last applicable official background date.

- [ ] **Step 4: Implement reason builders and renderers**

Technical reasons combine MA/RSI/KDJ/MACD; sentiment reasons combine flow, volume ratio, breadth and score. Policy/fundamental text comes only from the validated context file.

- [ ] **Step 5: Run reporting tests**

Run: `python3.12 -m unittest modules.etf-monitor.tests.test_reporting -v`

Expected: all tests pass.

### Task 4: Reproducible report CLI

**Files:**
- Create: `modules/etf-monitor/generate_report.py`
- Create: `modules/etf-monitor/tests/test_generate_report.py`
- Modify: `modules/etf-monitor/package.json`
- Modify: `package.json`
- Modify: `modules/etf-monitor/README.md`

**Interfaces:**
- Consumes: `--date YYYY-MM-DD`, universe/report seed, injected providers in tests.
- Produces: date-named Markdown, CSV and JSON reports through atomic replacement.

- [ ] **Step 1: Write failing end-to-end fixture test**

Use three representative ETFs across SSE/SZSE and assert all output formats share row counts, values and provenance. Assert an existing report remains intact if rendering fails.

- [ ] **Step 2: Run the test and verify RED**

Run: `python3.12 -m unittest modules.etf-monitor.tests.test_generate_report -v`

Expected: missing generator failure.

- [ ] **Step 3: Implement CLI orchestration**

Load 68 representative codes from the prior reviewed JSON seed, fetch 120 bars and 21+ share dates, compute report rows, validate all artifacts, then replace outputs atomically.

- [ ] **Step 4: Add scripts and documentation**

Expose `npm run etf:report -- --date 2026-07-20` using `python3.12`. Document flow formula, source URLs, indicator formulas and `N/A` semantics.

- [ ] **Step 5: Run module and repository ETF tests**

Run: `python3.12 -m unittest discover -s modules/etf-monitor/tests -p 'test_*.py' -v`

Expected: all tests pass without network access.

### Task 5: Live generation and Feishu verification

**Files:**
- Update: `modules/etf-monitor/reports/representative-technical-review-2026-07-20.md`
- Update: `modules/etf-monitor/reports/representative-technical-review-2026-07-20.csv`
- Update: `modules/etf-monitor/reports/representative-technical-review-2026-07-20.json`

**Interfaces:**
- Consumes: official exchange responses, current bars, reviewed sector contexts.
- Produces: validated local artifacts and revision 3+ of Feishu doc `ArHadXq8Xo2n55xJLhjc4aJen3g`.

- [ ] **Step 1: Generate the live report**

Run: `npm run etf:report -- --date 2026-07-20`

Expected: 68 rows, exact source dates, nonidentical flow fields or scoped `N/A` reasons, and no global repeated `DATA_ERROR`.

- [ ] **Step 2: Validate artifacts**

Check schema, 68 unique codes, finite indicators, flow arithmetic samples from both exchanges, four nonempty reason fields and source appendix coverage.

- [ ] **Step 3: Overwrite the existing Feishu body**

Stream the Markdown without its first H1 to `lark-cli docs +update --as user --doc ArHadXq8Xo2n55xJLhjc4aJen3g --command overwrite --doc-format markdown --content -`.

- [ ] **Step 4: Read back and verify**

Fetch Markdown and assert one title, 68 ETF rows, KDJ/MACD/sentiment headers, four-dimensional reasons, source appendix and a newer revision ID.

- [ ] **Step 5: Final regression**

Run the ETF test suite once more and report any live-source fields that remain scoped `N/A` with exact reasons.
