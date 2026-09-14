# PO3-BASE-M0 — REPORT

**Hypothesis (one frozen test):** EURUSD Asia range (00:00–07:00 London, MID) → liquidity
sweep around London (≥ 0.20 × range beyond one side, 07:00–10:00 window) → M1 MID close
back inside within 15 min → reversal trade, stop at the manipulation extreme, frozen 2R
target, 12:00 London time exit. No ICT constructs, no filters, no optimizer.

**Verdict: `PO3_BASE_NO_EDGE` — STOP.** (Frozen interpretation rule C, spec §16/§18.)

---

## Governance

| Item | Value |
|---|---|
| BASE_HEAD | `1ff680a` (main) |
| FROZEN_SPEC_COMMIT | `b7b0efe` — committed BEFORE any outcome was computed |
| FINAL_HEAD | see git log of `research/po3-base-m0` |
| PR | non-merged, see GitHub |
| DATA_START / DATA_END | 2010-01-04 / 2018-12-31 (Europe/London dates) |
| Store | `E:\ResearchData\botTrading\ticks\parquet\EURUSD`, 108 partitions, 209,682,628 ticks, every partition SHA256-verified at run time against `data_manifest.json` (committed with the spec) |
| 2019+ accessed | NO (hard guards, tested) |
| Protected OOS accessed | NO (hard guard `[2010-01-01Z, 2019-01-01Z)`, tested) |
| Optimization executed | NO |

## Day funnel (2010-01-04 .. 2018-12-31)

| Counter | Value |
|---|---|
| DAYS_TOTAL (Mon–Fri) | 2346 |
| NOT_ELIGIBLE | 38 |
| ELIGIBLE_DAYS | 2308 |
| NO_SWEEP | 480 |
| SWEEP_DAYS | 1828 (UPPER 901 / LOWER 927) |
| NO_REINTEGRATION | 1187 |
| DOUBLE_SWEEP_INVALID | 0 |
| REINTEGRATED_SETUPS | 641 |
| NO_FILL / INVALID_RISK / NO_TIME_EXIT_DATA | 0 / 0 / 0 |
| **N_TRADES** | **641** (LONG 334 / SHORT 307) |
| TRADES_PER_YEAR / PER_MONTH | 71.2 / 5.9 |

## Primary metrics (baseline: 5 s delay, real historical spread)

| Metric | Value |
|---|---|
| WIN_RATE | 0.3354 |
| MEAN_NET_PIPS | +0.185 |
| MEDIAN_NET_PIPS | −5.60 |
| TOTAL_NET_PIPS | +118.3 |
| PROFIT_FACTOR | 1.031 |
| **EXPECTANCY_R** | **−0.0281** |
| AVG_WIN_R / AVG_LOSS_R | +1.903 / −1.003 |
| MAX_DRAWDOWN_R | 46.6 |
| MAX_CONSECUTIVE_LOSSES | 13 |
| POSITIVE_YEARS / YEARS_ELIGIBLE | 6 / 9 (0.667) |
| REMOVE_BEST_1_PERCENT_MEAN_R | −0.0505 |
| LONG_EXPECTANCY_R | −0.0454 |
| SHORT_EXPECTANCY_R | −0.0093 |
| LATENCY_30S_EXPECTANCY_R | +0.0076 |
| SLIPPAGE_050_EXPECTANCY_R | −0.1652 |
| **REALISTIC_STRESS_EXPECTANCY_R** | **−0.1527** |
| BOOTSTRAP_CI95_EXPECTANCY_R | [−0.1353, +0.0805] |

## Economic pass gate (spec §15)

| Gate | Threshold | Actual | Pass |
|---|---|---|---|
| N_TRADES | ≥ 200 | 641 | ✔ |
| EXPECTANCY_R | ≥ +0.10 | −0.028 | ✘ |
| PROFIT_FACTOR | ≥ 1.20 | 1.031 | ✘ |
| TOTAL_NET_PIPS | > 0 | +118.3 | ✔ |
| POSITIVE_YEARS ratio | ≥ 0.67 | 0.667 | ✘ |
| REMOVE_BEST_1_PERCENT_MEAN_R | > 0 | −0.051 | ✘ |
| LATENCY_30S_EXPECTANCY_R | > 0 | +0.008 | ✔ |
| REALISTIC_STRESS_EXPECTANCY_R | > 0 | −0.153 | ✘ |
| LONG_EXPECTANCY_R | > 0 | −0.045 | ✘ |
| SHORT_EXPECTANCY_R | > 0 | −0.009 | ✘ |

**GATE_PASS = false → interpretation C: `PO3_BASE_NO_EDGE`.**
Expectancy ≤ 0 AND realistic stress clearly destroys the result (−0.15R), and both
directions are non-positive.

## Diagnostics (descriptive only, spec §14)

| Diagnostic | Value |
|---|---|
| ASIAN_RANGE_MEDIAN_PIPS | 30.4 |
| SWEEP_STRENGTH_MEDIAN (extension / range) | 0.256 |
| LONDON 07:00 → SWEEP median | 57.6 min |
| SWEEP → REINTEGRATION median | 6.87 min |
| MFE30 / MFE60 / MFE120 (mean, R) | 0.97 / 1.56 / 2.16 |
| P(reach +1R before stop) | 0.488 |
| P(reach +1.5R before stop) | 0.378 |
| P(reach +2R before stop) | 0.310 |

Reading: the retrace phenomenon EXISTS (mean max favorable excursion ≈ 1R within 30
minutes of entry), but the frozen 2R objective is reached before the stop only 31.0% of
the time — below the 33.3% breakeven for a pure 2R/−1R structure — while the extreme-based
stop loses slightly more than 1R on average (gap-through fills) and the 12:00 time exit
caps some winners below 2R (AVG_WIN_R = 1.90). The raw session phenomenon is real as a
bounce but carries no exploitable edge under this frozen execution. Per §17 no alternative
thresholds/hours/targets were tested.

## Audit (spec §18 — clearly-negative path)

Independent re-derivation (different implementation: pandas resample M1, plain-Python
walk, `audit_po3_base_m0.py`) of 15 randomly sampled trades (seed 20260914): AsianHigh/
Low/Range, sweep side + threshold timestamp, sweep extreme, reintegration candle +
decision_ts, direction, entry side/time/price, stop, target, exit type/timestamp/price,
net pips — **15/15 exact matches, 0 failures**. All trade dates < 2019-01-01. Yearly
trade counts 55–90 (balanced). Existing relevant tick-execution suites (RATES-LAG-M0:
36 tests; RATES-EVENT-HIRES-M1 + others: 45 tests) re-run green on their branch.

## Tests / CI

- 35 synthetic tests (`test_po3_base_m0.py`): Europe/London DST (BST/GMT, no hard-coded
  offset), Asia boundaries (00:00 incl / 07:00 excl), 07:00 inclusion, 10:00 exclusion,
  upper/lower threshold exactness (>=/<=), 15-minute reintegration boundary (inclusive),
  double-sweep invalidation, completed-M1 causality (bucket-end close; same-instant tick
  belongs to next bucket), no-future-extreme stop, strict close-inside, sweep-candle own
  close, 5 s entry delay, 30 s stress delay, NO_FILL bound, LONG ask / SHORT bid entry,
  stop execution side, stop gap-through, target cap, entry-tick self-stop, INVALID_RISK,
  12:00 time exit (+ side), NO_TIME_EXIT_DATA, r-units regression (+2R target),
  slippage formula, metrics (PF + sentinel, remove-best-1pct, bootstrap determinism,
  drawdown, streaks, positive years), 2019 cutoff / OOS guards, discovery-date set.
- CI: workflow step added for `research/po3_base_m0` (unittest discover) — CI actually
  executes the suite on this PR.

## Conclusion

`FINAL_STATUS = PO3_BASE_NO_EDGE`. One frozen hypothesis, one answer: the Asia-range →
London-sweep → reintegration reversal on EURUSD has no economic edge as specified.
No rescue sweep, no parameter variation, no ICT constructs. STOP.
