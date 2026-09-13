# macro_tick_m0 — MACRO_TICK_M0 causal macro event database

Causally-valid historical macro-event database for EURUSD research over
Discovery 2010-2018 (2010-01-01 inclusive, 2019-01-01 exclusive).
**Data/provenance only — NO strategy backtest, NO returns, NO PnL.**

* `REPORT.md` — full provenance, metrics, pass gate, consensus feasibility
* `data/macro_events_2010_2018_aligned.csv` — the dataset (289 events, tick-lag columns)
* `data/tick_alignment.csv` — event/tick timestamp alignment only
* `data/tick_store_month_coverage.csv` — per-month tick-source coverage audit
* `data/quality_report.json` — family metrics, exceptions, cross-checks
* `source_manifests/` — committed fetch evidence (BLS archive/schedule manifests,
  Fed statement extractions, DFEDTARU cross-check series)
* `build_scripts/` — fetchers + builders (`macro_lib.py` holds the pure logic)
* `test_macro_tick_m0.py` — 22 synthetic tests (DST, duplicates, ordering,
  discovery-range guard, causality, tick alignment, missing ticks,
  scheduled vs unscheduled FOMC)
* `data_raw/` — bulky local fetch artifacts (gitignored)

Event families: `NFP` (Employment Situation), `CPI` (headline + core),
`FOMC` (72 scheduled + 1 unscheduled 2010-05-09). Values are first-release
ALFRED vintages (`PAYEMS`, `CPIAUCSL`, `CPILFESL`), never today's revised history.

Timestamps: exact official where the official record carries a time
(BLS 100%; FOMC 36/73 with a documented pre-2016 blocker, never guessed);
all conversions via `America/New_York` zoneinfo with validated EST/EDT labels.
