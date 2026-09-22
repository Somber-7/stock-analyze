# Analysis quality and settings tabs implementation plan

**Goal:** Deliver the requested settings tabs and the three prioritized analysis fixes in the Windows EXE.
**Architecture:** Keep existing trading boundaries. Extend the sanitized analysis context with separately named account balances, excluded asset valuations, per-stock cash buying capacity and deterministic indicators. Require the model to distinguish a supported decision from insufficient evidence. Persist the data used with each run.
**Tech stack:** Python/FastAPI/Pydantic/SQLite, React, Electron.
**Spec:** User-approved scope in this task: AI model / web search / trading-account tabs; orderable cash and account assets; hold vs defer; quantitative indicators and investment horizon. Tavily credential management is included; actual search was subsequently authorized and is included below.

## Constraints
- Preserve saved keys, account choice, analysis configuration and history. No automatic trading/AI calls during deployment.
- No new arbitrary trade amount limits. Investment horizon is optional and must not be invented for the user.
- Non-stock asset valuations are context only, never target instruments or implicitly spendable cash.
- Use official NH balance fields `dca` (deposit), `orr_pbl_amt4` (100% orderable), `tot_aet_amt` (assets), `nas_amt` (net assets); verify per-symbol `csh_orr_pbl_amt/qty` via existing gateway.
- Unknown amounts remain null, never silently become zero. Show account scope and timestamps.

## Tasks
- [x] Add failing tests for balance optional fields, sanitized assets, capacity failures and deterministic indicators.
- [x] Extend balance mapping and context. Calculate 5/20-session returns, SMA20/60, 20-session daily-return volatility, 20-session volume ratio and 5-row flow persistence with explicit lookbacks and missing data.
- [x] Add failing tests for defer/nonzero-delta rejection and investment-horizon validation/migration; implement generation schema, run snapshots and order exclusion.
- [x] Add accessible settings tabs preserving drafts; separate AI model and Tavily panes. Add investment horizon to analysis configuration and compact account/indicator displays to results.
- [x] Verify API/unit suite, lint/build, isolated browser flow, preserved production configuration and packaged EXE. Update documentation.

## Authorized extension: actual Tavily retrieval
- Add an opt-in `include_web` analysis setting; require a saved Tavily key when enabled.
- Search publicly identified selected stocks only: one recent-news query and one DART/KIND report query per stock. Never send holdings, balances, objectives or AI credentials to Tavily.
- Bound requests, results and excerpts; preserve source URLs/dates and missing information; cache public results for 15 minutes per credential fingerprint/query. Do not fetch arbitrary result URLs.
- Feed retrieved excerpts to all existing model providers as untrusted evidence. Require source IDs on each decision and validate citations against retrieved sources for that stock.
- Persist/display sources, query status and credit usage; clearly show failed/empty/partial retrieval and stop on wholly failed retrieval. Keep cancellation/settings-version guards around retrieval and generation.
- Verify transport/redaction/caching/citation contracts, isolated full flow, and one bounded live search if a key is available. No real trading.

User clarification: NHKRCMA (CMA 발행어음) is the account cash-management balance. Distinguish it from API dca, include as cash-management assets, retain broker totals and orderable funds without double counting.
