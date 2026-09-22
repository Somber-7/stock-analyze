# Analysis reliability implementation plan

Approved design: the five-part correction proposal in the conversation, approved by “진행 해줘”.

Goal: correct retrieved evidence, buying-capacity diagnostics, valuation bases and indicators; preserve reproducible inputs and add explicitly labelled post-analysis observations.

Architecture: keep broker/order boundaries intact. Separate public research filtering, deterministic snapshot/metrics, and read-only performance observation. No real orders or paid model requests during verification.

Constraints: existing project is not a Git repository; work directly in the authorized project. Never export credentials or account identifiers. Preserve existing user configuration and old runs. No fabricated retrospective data. New inputs default to unspecified. Use current compact dark UI with detail disclosures.

- [x] Task 1: web research relevance/date/body validation, bounded fallback search, deduplication; mocked regression tests. Files: ai/web_search.py, new research filter, tests/test_ai_web_search.py.
- [x] Task 2: diagnose buyableQuantity using safe error metadata and verify official contract; use balance valuation for weights, retain sufficient candles, expose price bases; tests for missing data and 61/60 bars.
- [x] Task 3: store sanitized immutable analysis inputs and config, compact model input (no duplicated sources), explicit DART disabled status and purpose/risk inputs; keep decision-vs-execution semantics.
- [x] Task 4: deterministic future-price observation at 5/20/60 trading observations, close-based drawdown and domestic benchmark comparison; separate deferred decisions and never call it actual trading return. Missing/old snapshots unavailable. UI manual refresh of bounded observations, no new scheduler.
- [x] Task 5: integrate details and settings, whole suite, review and isolated UI verification; build 1.18.0 installer/portable.

Rulings: analysis review is not an authorization to place orders. Historical comparisons require an immutable baseline, and after-hours analyses start observing from later completed sessions. A domestic ETF benchmark is labelled ETF reference, not an index return. Original API prices are not presumed adjusted. No profit hit-rate for supported hold/defer; report eligible counts instead.

Interface preflight: research supplies unique sources and diagnostics; generation consumes sanitized compact sources once. Snapshot supplies full validated daily series and timestamps; observations consume them without modifying the original result. Account valuation uses balance snapshot only. Quote/close/order prices have separate labels. Settings fields participate in comparison scope so old incompatible runs are not compared.

Progress: implementation and review completed; Python 262 tests, Node 9 tests and ESLint passed. Isolated UI verified stored observations across reload, optional criteria save/clear, 1280px results and 900px settings, with no browser console errors. Vite, PyInstaller and Electron portable/installer 1.18.0 builds completed successfully. Actual broker read-only checks succeeded for all three held stocks; no real orders or paid AI/Tavily calls were made.


