# Daily briefing and order plan preview

User-authorized continuation after DART 1.14.0. No new order execution path or model calls.

- [x] Calculate buy/sell totals from validated final decisions and persist analysis-time plans.
- [x] Count available cash once across buys; exclude projected sales, CMA and per-symbol capacities as additional funds. Preserve unknown values and flag capacity shortfalls.
- [x] Show compact plan totals and expandable stock amounts/target account weights in AI reports. Existing reports without plans remain readable.
- [x] Add Portfolio briefing using cached watch quotes, Korea-date triggered alerts, live-account order history and same-scope saved AI results.
- [x] Retain account/config version checks, isolate partial failures, and link to the specific summarized AI run. No extra balance fetches, symbol polling, or alert acknowledgments.
- [x] Regression tests for shared cash, unknown amounts, defer exclusion, stale quotes, dates, account isolation and configuration changes.
- [x] Isolated fake-account UI flow and responsive inspection at 900px and 2560px.
- [x] Final code review and 1.15.0 Windows packaging verification.

Data limits: quote cache must be within 120 seconds of briefing retrieval; displayed prices remain a snapshot until refresh. Order history is the KST query day's remaining orders. Unresolved local submissions are counted across saved dates separately. AI comparisons may predate today and always display completion time. The preview excludes taxes/fees/slippage and is not a buying-power authorization.

Verification: 218 Python tests, 2 Node selection regression tests, ESLint, Vite and full Windows build passed. Fake-account UI checked fresh/stale quote handling, alert/order details, specific analysis navigation, plan arithmetic and 900/2560px layouts with no page-level overflow or browser errors. Review fixed explicit analysis selection outside the 50-run display window; it now shows unavailable instead of another report. Packaged PYZ includes backend.briefing and backend.ai.order_plan. Portable EXE 104,599,919 bytes; installer 104,767,070 bytes. No production credentials, live orders or paid analysis calls were used.
