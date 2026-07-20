# ETF Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development. Each task must commit its work and report tests.

**Goal:** Build a local, stateful ETF audit and monitoring module that deduplicates the supplied universe, evaluates transparent high-confidence gates, tracks real fills, and supplies Codex with actionable scheduled-check output without placing trades.

**Architecture:** Add an independent Python-standard-library module under `modules/etf-monitor`. Static, reviewed universe metadata is separate from mutable ignored position/alert state. Pure domain functions perform audit, portfolio, and signal calculations; network providers only fetch market inputs; the CLI composes them for humans and Codex automation.

**Tech Stack:** Python 3 standard library, `unittest`, JSON/CSV/Markdown, root npm workspace aliases, Codex recurring automation.

## Global Constraints

- Initial capital is CNY 100,000; risk-asset exposure is at most CNY 40,000 and cash reserve is CNY 60,000.
- At most two open ETFs; each ETF has at most two buy tranches of approximately CNY 10,000 and total cost at most CNY 20,000.
- A second tranche requires renewed confirmation; price decline alone never authorizes averaging down.
- Position alerts are once per holding cycle at +4.5%, +5%, and at signal invalidation or -3% from weighted cost, whichever exit condition occurs first.
- Portfolio high-watermark drawdown of 1.5% blocks new buys/adds; 2% emits risk-exit alerts and starts a 10-trading-day cooldown.
- A technical buy candidate requires: 20-day average turnover >= CNY 50,000,000; AUM >= CNY 200,000,000; domestic premium <= 0.5% or cross-border/commodity premium <= 1%; price above rising MA20 and MA60; positive 20-day relative strength; a valid pullback reclaim or >=1.2x-volume breakout; daily gain <=3%; distance above MA20 <=5%.
- The scanner never emits a final buy recommendation without a verified primary catalyst and independent corroboration; absent, stale, conflicting, holiday, or incomplete data produces a no-action result.
- Cross-market products remain separate; deduplication key is sector x market. `883432` is an index, not an ETF, and must never enter the tradable universe.
- No broker integration and no automatic orders. Alerts are decision support and must carry the data timestamp and risk/invalidation fields.

---

### Task 1: Verified Universe and Deduplication Reports

**Files:**
- Create: `modules/etf-monitor/data/universe.json`
- Create: `modules/etf-monitor/src/audit.py`
- Create: `modules/etf-monitor/tests/test_audit.py`
- Create: `modules/etf-monitor/reports/exact-duplicates.md`
- Create: `modules/etf-monitor/reports/sector-overlap.md`

**Requirements:**
- Encode the 107 unique supplied symbols, with code, name, instrument kind, market, sector, tracking index, screenshot turnover, and optional exact-duplicate group.
- Exactly 106 records are ETFs and one is the excluded index `883432`.
- Exact duplicate groups are: `512890/159525`; `159659/159941/159660`; `159500/510500`; `159937/518880`; `159995/159801`; `159713/516780`; `512000/512880`; `588000/588060/588950`; `588790/588760`; `159875/516160`; `159857/515790`; `516750/159745`; `588170/589020`.
- Generate two deterministic Markdown reports: exact-index choices and sector x market overlap. Recommend one ETF per group using eligibility first, then higher screenshot turnover, then lower code as deterministic fallback. Mark low-turnover unique products observation-only.
- Tests must first fail for absent implementation/data, then prove record counts, code uniqueness, excluded index behavior, duplicate group membership, cross-market separation, and deterministic recommendation.

### Task 2: Portfolio Accounting and Risk Alerts

**Files:**
- Create: `modules/etf-monitor/src/portfolio.py`
- Create: `modules/etf-monitor/tests/test_portfolio.py`
- Create: `modules/etf-monitor/state.example.json`

**Requirements:**
- Provide pure functions to record buys/sells, calculate weighted cost, enforce two tranches/two positions/CNY limits, calculate realized and unrealized equity, and update high-watermark drawdown.
- Persist alert acknowledgement flags per holding cycle so +4.5%, +5%, and stop alerts do not repeat. A new position cycle resets them.
- Block buys/adds at 1.5% drawdown; at 2% produce risk-exit alerts for every risk position and a 10-trading-day cooldown.
- Tests cover two buys, partial sell, full close/reopen, all limits, threshold boundaries, deduplication, and cooldown behavior.

### Task 3: Market Data and High-Confidence Scanner

**Files:**
- Create: `modules/etf-monitor/src/market_data.py`
- Create: `modules/etf-monitor/src/scanner.py`
- Create: `modules/etf-monitor/tests/fixtures/market/*.json`
- Create: `modules/etf-monitor/tests/test_market_data.py`
- Create: `modules/etf-monitor/tests/test_scanner.py`

**Requirements:**
- Implement injectable providers for current quotes, at least 61 daily bars, AUM, premium, benchmark bars, trading-calendar state, and catalyst confirmation.
- The default public provider may use public market endpoints but must timestamp data, reject malformed/stale responses, and surface source disagreements rather than guessing.
- Implement every numeric gate from Global Constraints. Output `BUY_CANDIDATE` only when all numeric gates and both catalyst confirmations pass; otherwise output explicit no-action reasons.
- Position stop/take-profit monitoring remains available even when catalyst data is absent.
- Tests use fixtures, not live network, and cover every veto, pullback and breakout paths, stale/conflicting data, and position alerts.

### Task 4: CLI, Runtime State, Documentation, and Automation Contract

**Files:**
- Create: `modules/etf-monitor/cli.py`
- Create: `modules/etf-monitor/package.json`
- Create: `modules/etf-monitor/README.md`
- Create: `modules/etf-monitor/automation-prompt.md`
- Create: `modules/etf-monitor/tests/test_cli.py`
- Modify: `.gitignore`
- Modify: `package.json`
- Modify: `docs/README.md`

**Requirements:**
- Commands: `audit`, `record-buy`, `record-sell`, `scan`, and `scheduled-check`. JSON output is stable and documented.
- Mutable state lives in ignored `modules/etf-monitor/state/`; commit only `state.example.json`.
- `scheduled-check` must be safe on repeated invocation and return no-action, buy-candidate-needs-catalyst, actionable buy, profit/stop alert, or data-error results without placing orders.
- Document the exact user fill format, data-source limitations, risk assumptions, and broker verification requirement.
- Provide a Codex automation prompt that runs on China trading days at approximately 11:15 and 14:45 Asia/Shanghai, verifies catalysts from authoritative sources, and emits Codex notifications without changing notification policy in the prompt.

### Task 5: Integration Verification and Scheduled Automation

**Requirements:**
- Run the full unit suite, compile checks, CLI smoke tests, audit generation, and a fixture-backed scheduled check.
- Confirm the reports contain 107 unique records, 13 exact duplicate groups, and exclude `883432` from tradable output.
- Configure a Codex local recurring automation for weekday checks at 11:15 and 14:45 Asia/Shanghai against this project, using `automation-prompt.md` and Codex app notifications.
- Do not create any broker connection, order, email, Slack, or other external-channel integration.
