# TICK_M1 — TICK MICROSTRUCTURE DISCOVERY REPORT (STAGE A)

EURUSD Dukascopy tick data, 2010-01-01 .. 2019-01-01 exclusive.
Pre-registered hypothesis set: `TICK_M1_FROZEN_HYPOTHESES.md`
(committed c709b80 BEFORE any Discovery data was downloaded or inspected).
Machine-readable results: `tick_m1_results.json`.

## Verdict: **NO_MICROSTRUCTURE_CANDIDATE**

**ZERO of the 13 frozen configurations pass the economic gate.**
Per the frozen two-stage rule (hypotheses §0.9): STOP, no rescue variants,
no candidate strategies, no V1 work.

## Compliance

- 2019_PLUS_ACCESSED = **NO** (hard cut in loader; `assert_month_in_discovery` refuses 2019+ partitions; December-2018 exits past the cut are skipped, never filled)
- PROTECTED_OOS_ACCESSED = **NO**
- PR is NOT merged. Paper/research only, no broker, no live trading.

## Data

| item | value |
|---|---|
| DATA_ROOT | `E:\ResearchData\botTrading\ticks` (env `BOTTRADING_TICK_DATA_ROOT` / `--data-root`; never hardcoded in repo) |
| DISCOVERY_RANGE | 2010-01-01 (incl) .. 2019-01-01 (excl), 108 monthly partitions |
| RAW_DATA_GB | 1.21 (78,752 hourly `.bi5` files) |
| PARQUET_GB | 2.57 (zstd, partitioned year=/month=) |
| N_TICKS | 208,003,917 |
| completeness | 136/78,888 hours absent (0.17%, scattered ≤4h/month, no clustering); 0 false `.missing` markers; 0 corrupt files |
| validation | June-2018 rebuild reproduces the TICK-M0 committed reference **exactly**: 474,506 ticks, median spread 0.30 pips, median bid_volume 1.87 |
| C: drive | untouched by tick data (all bulk data on E:) |

## Execution & cost model (frozen)

LONG enters at ASK / exits at BID; SHORT enters at BID / exits at ASK — the
real historical spread is charged by construction; no synthetic spread added.
Stress = additional adverse slippage per side. All inference uses
NON-OVERLAPPING events (greedy chronological suppression per horizon).

## All 13 frozen configurations (complete, ranked by frozen primary metric)

| config | hyp | H | N_raw | N_nonoverlap | mean net | median | win% | posY | rem-best-1% | CI95 | stress .10 | stress .25 | BH-q | gate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| H6a | H6 | 30s | 944,623 | 137,994 | +0.032 | 0.000 | 49.3 | 7/9 | −0.041 | [+0.023,+0.041] | −0.168 | −0.468 | 0.000 | fail |
| H4a | H4 | 30s | 17,048,751 | 1,182,815 | +0.031 | 0.000 | 49.3 | 8/9 | −0.034 | [+0.021,+0.034] | −0.169 | −0.469 | 0.000 | fail |
| H4b | H4 | 60s | 17,048,751 | 908,521 | +0.030 | 0.000 | 49.3 | 8/9 | −0.047 | [+0.030,+0.047] | −0.170 | −0.470 | 0.000 | fail |
| H6b | H6 | 60s | 944,623 | 126,013 | +0.026 | 0.000 | 49.2 | 7/9 | −0.065 | [+0.015,+0.037] | −0.174 | −0.474 | 1e-05 | fail |
| H2a | H2 | 30s | 4,591,990 | 917,412 | +0.012 | 0.000 | 48.1 | 7/9 | −0.064 | [+0.001,+0.018] | −0.188 | −0.488 | 0.000 | fail |
| H3a | H3 | 30s | 397,407 | 73,888 | +0.009 | 0.000 | 49.2 | 5/9 | −0.178 | [−0.023,+0.040] | −0.191 | −0.491 | 0.390 | fail |
| H2b | H2 | 60s | 4,591,990 | 734,022 | +0.006 | 0.000 | 48.4 | 5/9 | −0.085 | [−0.002,+0.018] | −0.194 | −0.494 | 0.014 | fail |
| H1c | H1 | 60s | 4,278,782 | 318,364 | +0.004 | 0.000 | 48.6 | 6/9 | −0.085 | [−0.009,+0.013] | −0.196 | −0.496 | 0.203 | fail |
| H1b | H1 | 30s | 4,278,782 | 384,424 | +0.004 | 0.000 | 48.3 | 5/9 | −0.070 | [+0.001,+0.016] | −0.196 | −0.496 | 0.167 | fail |
| H1a | H1 | 10s | 4,278,782 | 504,857 | +0.001 | 0.000 | 48.3 | 7/9 | −0.055 | [−0.003,+0.011] | −0.199 | −0.499 | 0.390 | fail |
| H5b | H5 | 60s | 41,714,104 | 2,124,156 | −0.005 | 0.000 | 48.4 | 1/9 | −0.095 | [−0.004,+0.016] | −0.205 | −0.505 | 1.000 | fail |
| H3b | H3 | 60s | 397,407 | 61,837 | −0.007 | 0.000 | 49.1 | 4/9 | −0.238 | [−0.046,+0.033] | −0.207 | −0.507 | 0.749 | fail |
| H5a | H5 | 30s | 41,714,104 | 3,234,524 | −0.009 | 0.000 | 48.1 | 1/9 | −0.085 | [−0.017,+0.001] | −0.209 | −0.509 | 1.000 | fail |

Gate (frozen §0.7): mean net ≥ +0.30 pip AND positive years ≥ 6/9 AND
remove-best-1% > 0 AND stress +0.10 > 0 AND N ≥ 500.
**Best mean net is +0.032 — 10× below the gate.**

## Direction balance & time-of-day

Direction balance ~50/50 for all sign-symmetric hypotheses (H4a 46% LONG,
H4b 47%, H6 48%, rest ≈ 50%); no side bias. Time-of-day histograms (4h UTC
buckets) are in `tick_m1_results.json` per config; events concentrate in the
London/NY session buckets as expected from tick-density, with no anomalous
bucket dominating any config.

## Interpretation (why the verdict is credible)

1. **Magnitude, not noise, is the problem.** Several configs have
   p ≈ 0 (huge N), but the effects are +0.03 pips/event against a real
   spread of ~0.3–1.0 pip. The frozen +0.30 threshold exists precisely to
   separate "statistically visible with N in the millions" from "economically
   usable".
2. **No robustness anywhere.** remove-best-1% mean is negative for ALL 13
   configs: every positive mean is carried by its top-1% events.
3. **Stress kills everything instantly.** One extra +0.10 pip/side of adverse
   slippage (−0.20 pip/event) makes every config deeply negative.
4. **H4/H6 micro-effect decays with spread regime.** H4a yearly means:
   +0.029 (2010, wide-spread era) then |mean| ≤ 0.015 for 2011-2018 with
   2014-2017 ≈ 0 or negative — the residual "edge" tracks spread width, not
   information.
5. **H3 falsified mechanistically:** after a spread shock the mean gross mid
   move is −0.44 pips for the reversal trade, i.e. the mid CONTINUES in the
   shock direction on average — no liquidity-withdrawal reversion at these
   horizons in this feed.
6. **H5 falsified:** feed quote-move imbalance has slightly negative net —
   no predictive value once spread is charged.
7. Volumes caveat (frozen §0.1): Dukascopy feed volumes, not global FX
   volume — conclusions apply to this feed.

## Two-stage rule applied

- Stage A screen: done, all 13 configs reported above. Zero pass.
- FINAL_STATUS = **NO_MICROSTRUCTURE_CANDIDATE** → STOP.
  No rescue variants were created, no thresholds were changed post-hoc,
  no V1 access, nothing merged.

## Tests & CI

- `research/tick_m1_microstructure/test_tick_m1.py`: 22/22 PASS (execution
  sides, real spread cost, long/short PnL, timestamps, causal rolling window,
  no-future-leakage, overlap suppression, prediction horizon, imbalance sign,
  spread calc, discovery cutoff incl. Dec-2018 exit-skip, gap/rollover
  filters, reversal direction, qdir sign, BH-FDR).
- `research/tick_m0/test_tick_m0.py`: 18/18 PASS (existing suite, still green).
- CI: added `research/tick_m1_microstructure` unittest step to
  `research-engine-tests.yml` (numpy/pandas/pyarrow only; no data, no network).

## Engineering notes

- Downloader (`download_ticks.py`): threaded, idempotent, resumable,
  retry/backoff, spurious-404-safe (`--verify-missing` repair pass: 0 false
  markers), per-hour corruption validation (LZMA + 20-byte record divisibility)
  before atomic persist, empty-hour markers, progress logging.
- Builder (`build_parquet.py`): month partitions via the validated TICK-M0
  decoder; per-month manifest with ok/empty/missing/absent/corrupt counts.
- Engine (`microstructure_lib.py`, `run_discovery.py`): month-chunked
  (≤15-min padding, context partitions always inside discovery), vectorized
  searchsorted features, greedy non-overlap suppression, 32 GB-safe.
- Full 9-year screen runtime: ~7 minutes (108 months, 13 configs).
- Data layout: `E:\ResearchData\botTrading\ticks\{raw,parquet}\EURUSD\...`
  — nothing committed to Git except manifests/reports.
