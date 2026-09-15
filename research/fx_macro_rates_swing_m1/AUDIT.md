# FX-MACRO-RATES-SWING-M1 — PHASE A AUDIT (read-only)

Date: 2026-09-16. Branch `research/fx-macro-rates-swing-m1` cut from
`7e3bd46baea6dcd6ec4e5bf763e8d3c6eda1233b` (= remote tip of
`research/fx-multipair-swing-discovery-m1`, verified via `git ls-remote`).
Previous branch NOT modified, NOT merged. No downloads, no purchases, no
charged APIs, no keys exposed during this audit.

## Dataset inventory

| DATASET | INSTRUMENT | SOURCE | START | END | FREQ | TIMESTAMP_SEMANTICS | CAUSALITY_CONFIDENCE | SUITABLE_FOR_SWING_RESEARCH | NOTES |
|---|---|---|---|---|---|---|---|---|---|
| E:\ResearchData\botTrading\rates\databento\parquet\{ZT,ZF,ZN}.parquet | US 2Y/5Y/10Y Treasury futures (continuous vol-ranked) | Databento GLBX.MDP3 ohlcv-1m (batch GLBX-20260913-PJ387FJNFC, 24.28 USD, RATES-DATA-M0) | 2010-06-07 | 2018-12-31 21:59 UTC | 1m OHLCV+volume | `ts_event` = exchange trade time (UTC, tz-aware); bars print only when trades occur | HIGH — exchange-timestamped; validated 0 dup / 0 non-monotonic / 0 OHLC-invalid / 0 NaN; prior campaign audited 500/500 exact checks on same store | YES — primary rates source | Unadjusted continuous: roll_map.csv (rates-macro-m1 branch) maps raw contracts per interval; compute returns within contract intervals only. ZT thin overnight (47% 1m alignment vs EURUSD); ZF 72%, ZN 79%. Gives curve info ZT/ZF/ZN |
| research/rates_macro_m1/data/macro_events_2010_2018_aligned.csv (on branch `research/rates-macro-m1`; extractable read-only via `git show`) | NFP + CPI + FOMC, 289 events 2010-01→2018-12 | BLS schedule pages + federalreserve.gov + ALFRED real-time vintages (prior campaign artifact) | 2010-01-08 | 2018-12 | per-event | `release_timestamp_utc` EXACT_SCHEDULE_PAGE for NFP/CPI; FOMC DATE_ONLY (12:30 ET convention flagged NOT exact) | HIGH for NFP/CPI (exact minute + ALIGNED tick checks in prior campaign); MEDIUM for FOMC (date-exact, intraday time convention) | YES — event conditioning at H1+ horizons | Real-time initial vintages (no future revisions), previous published values, revision schedule. 192 events passed prior validity gates |
| data_raw/official/DGS2.csv | US 2Y CMT yield (daily) | FRED (H.15) | 1976-06-01 | 2026-09-10 | daily | observation_date = observation day; H.15 published ~16:15 ET same day at earliest | MEDIUM — publication lag not proven to the minute; use T+1-close at earliest if used at all | Secondary only | Spot 2Y NOT directly traded; futures ZT preferred. Curve context only |
| data_raw/official/DFEDTARU.csv, ECBDFR.csv, BOERUKM.csv | Fed target upper / ECB depo / BoE Bank Rate | FRED | 2008-12 / 1999-01 / 1694 | current | decision-dated daily | value changes on decision date; intraday announcement time NOT in file (use next-bar conservative rule) | HIGH for day-level (decision-dated) | Context only (regime segments) | No intraday timestamps ⇒ never gate intraday entries on same-day value change |
| data_raw/parquet/{EURUSD,GBPUSD,USDJPY,EURJPY,EURGBP,GBPJPY}_5m.parquet | FX majors + crosses 5m BID OHLCV | Dukascopy 1m BID candles → 5m (built by phenomena_discovery_v1/build_5m.py) | 2010-01-01 | 2026-04-08 | 5m | index = UTC 5m bucket; prior campaigns re-label CLOSE time and trade next bar (causal convention, swing_lib) | HIGH — cross-validated 0.0-pip vs LAB_PASS tick store (EURUSD 2015-03-02) | YES — primary FX layer | Discovery access ONLY [2010-01-04, 2018-01-01); 2018H2 + USDJPY + 2019+ sealed |
| E:\ResearchData\botTrading\ticks\parquet\EURUSD\year=* | EURUSD BID/ASK ticks | Dukascopy (validated tick store, mtf_m1_tick_execution) | 2010 | 2018 (H1 used) | tick | exchange-independent vendor clock; validated by prior campaigns (LAB_PASS) | HIGH | Execution layer only | TICK_EXACT replay for EURUSD via m3lib.mtf_replay |
| data_raw/{PAIR}/{YYYY}/*.bi5 | EURUSD,GBPUSD,USDJPY,EURJPY,EURGBP,GBPJPY ticks | Dukascopy daily .bi5 (LZMA) | 2010 | 2026 | tick | vendor clock; decompression pipeline exists in infra_lib | MEDIUM-HIGH (validated on EURUSD 2010-2018; 2019+ sealed) | Execution refinement | 2019+ access FORBIDDEN this campaign |
| data_raw/tick_m0/EURUSD/20180604..08 | EURUSD 5-day lab sample ticks | prior lab audit | 2018-06-04 | 2018-06-08 | tick | as above | HIGH (lab-certified) | No (tiny sample) | Cross-validation reference only |
| news_calendar.csv (repo root) | 2026 events only | MQL5 market export | 2026-04 | 2026-04 | event | no provenance | LOW | NO | Irrelevant to 2010-2018 discovery |
| fomc_decisions.json (data_raw/official) | FOMC dates 2011-2026, release_time=null | federalreserve.gov | 2011 | 2026 | date | DATE only | MEDIUM (day-level) | Context only | Superseded by macro_events CSV for 2010-2018 |

## Key answers

```
AVAILABLE_RATES_INSTRUMENTS=ZT(2Y), ZF(5Y), ZN(10Y) US Treasury futures, 1m OHLCV, 2010-06-07..2018-12-31, validated, unadjusted continuous + roll_map
AVAILABLE_MACRO_DATA=NFP+CPI+FOMC event table 2010-2018 w/ exact NFP/CPI release timestamps + ALFRED real-time vintages (289 events); FRED daily series DGS2/DFEDTARU/ECBDFR/BOERUKM (day-level, conservative semantics)
AVAILABLE_FX_PAIRS=EURUSD, GBPUSD, USDJPY(holdout), EURJPY, EURGBP, GBPJPY — 5m BID parquet 2010-01..2026-04; EURUSD tick-exact execution 2010..2018H1
AVAILABLE_OVERLAP_PERIOD=2010-06-07 .. 2018-01-01 (rates ∩ FX discovery era); effective discovery window 2010-06-07 .. 2017-12-31
DATA_SUFFICIENT=YES
DATA_CAUSALITY_PROVEN=YES
```

Causality provenance: rates = exchange trade timestamps on a validated store
(RATES-DATA-M0: 0 duplicates/non-monotonic/invalid/NaN, gaps classified,
roll audit, 13/13 tests); macro = exact BLS schedule timestamps + ALFRED
real-time vintages (no look-ahead revisions), tick-alignment checked in
RATES-MACRO-M1; FX = Dukascopy ticks cross-validated against a lab-certified
tick store; execution via proven TICK_EXACT replay (EURUSD) or documented
MODELED_EXECUTION (others). FRED spot series carry unprovable intraday
publication lag ⇒ restricted to T+1/decision-day+1 conservative use, never
as intraday gates.

## Stop-rule decision

At least one meaningful rates/macro mechanism (rate impulse / curve regime /
macro-regime conditioning) is evaluable across 7.5+ overlapping years on
three Treasury maturities + multi-pair FX, with causal timestamps.

DECISION: PROCEED to discovery. Discovery window:
**2010-06-07 → 2017-12-31** (UTC). Sealed: USDJPY, EURUSD 2018H2, 2019+.

Dead territory NOT to be repeated (per brief + prior reports):
RATES-MACRO-M1 (NFP/CPI event-minute repricing, all REJECT);
RATES-LAG-M0 (30s residual, sub-economic);
event-minute FX-lag continuation; pure price-only EMA/RSI/breakout/fade;
G11/G08 multipair near-misses (failed plateau).

Budget: 10 families max, 60 experiments max (IDs MR_E001..MR_E060).
