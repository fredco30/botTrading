# EMA20_RT_M0 — SIGNAL STUDY REPORT (EMA20 M15 reclaim → first retest, LONG only)

Branch `research/ema20-rt-m0-signal-study` · base `def3a943dfdd9ee0c59249080e5c1318815b11ae`
(tip of `research/mtf-m1-tick-execution`, NOT merged) · frozen spec committed
BEFORE any outcome (`EMA20_RT_M0_FROZEN_SPEC.md`).

## FINAL STATUS

**`NO_EMA20_RT_SIGNAL` → STOP.**

No horizon comes close to the frozen §12 signal gate. Per the frozen §13/§17
scientific stop rule: no variants, no rescue research, no SL/TP design.

## Setup counts (Discovery 2010-01-01 .. 2019-01-01 exclusive, EURUSD)

| Count | Value |
|---|---|
| N_RECLAIM_BARS | 15,624 |
| N_RECLAIMS (armed setups) | 15,624 |
| N_RETESTS (first retest events) | 15,623 |
| N_INVALIDATED_BEFORE_RETEST | 0 |
| N_NO_FILL (60 s window) | 5 |
| N_UNRESOLVED_AT_END | 1 |
| MEDIAN_RECLAIM_TO_RETEST_BARS | 0 |
| MEDIAN_RECLAIM_TO_RETEST_MINUTES | 7.13 |

Notes. (a) `N_INVALIDATED_BEFORE_RETEST = 0` is structural, not a bug: for a
period-20 EMA, `CLOSE[j] < EMA20[j]` ⟺ `CLOSE[j] < EMA20[j−1]`, and the
closing tick is itself a MID at/below the active EMA — so a from-above first
touch (the retest) essentially always precedes any invalidating close.
(b) The median retest fires ~7 minutes after the reclaim close, i.e. inside
the following M15 bar — the "first return from above" is almost immediate.

## Data

- Validated tick store `E:\ResearchData\botTrading\ticks`
  (manifest digest `c2982340c6269744`, incl. the audited JUNE2018 repair);
  the M15 MID bar cache was rebuilt from it for this study.
- M15 bars: 224,174 built, 204 gap-flagged removed → 223,970 used.
- GAP LIST: 102 non-weekend inter-tick gaps > 1 h (weekends excluded by the
  frozen rule). 2019+ partitions never opened (`2019_PLUS_ACCESSED=NO`).

## Primary metrics per horizon (executable: ASK entry +250 ms latency, BID exit)

| H | N | MEAN_MID | MED_MID | MEAN_NET | MEDIAN_NET | WIN_RATE | CI95 | POS_YRS | REMOVE_BEST |
|---|---|---|---|---|---|---|---|---|---|
| 15m | 15,615 | +0.19 | +0.25 | **−0.37** | −0.20 | 0.469 | [−0.50, −0.25] | 1/9 | −0.70 |
| 30m | 15,608 | +0.29 | +0.30 | **−0.27** | −0.20 | 0.480 | [−0.44, −0.09] | 1/9 | −0.73 |
| 60m | 15,594 | +0.32 | +0.35 | **−0.24** | −0.20 | 0.487 | [−0.49, −0.001] | 2/9 | −0.91 |
| 120m | 15,564 | +0.34 | +0.40 | **−0.23** | −0.10 | 0.493 | [−0.57, +0.12] | 2/9 | −1.12 |
| 240m | 15,499 | +0.50 | +0.45 | **−0.10** | −0.10 | 0.497 | [−0.59, +0.38] | 5/9 | −1.31 |

(all values in pips; STD ranges 8.0 → 30.3 pips from 15m to 240m; per-horizon
exclusions: GAP_INVALID 3/10/24/54/118, NOT_MEASURABLE 0/0/0/0/1)

## NON_OVERLAP_4H (diagnostic only)

| H | N | MEAN_NET | MEDIAN_NET | POS_YRS | REMOVE_BEST | CI95 |
|---|---|---|---|---|---|---|
| 15m | 7,478 | −0.34 | −0.20 | 1/9 | −0.66 | [−0.52, −0.17] |
| 30m | 7,476 | −0.32 | −0.10 | 3/9 | −0.75 | [−0.56, −0.08] |
| 60m | 7,471 | −0.38 | −0.30 | 3/9 | −1.06 | [−0.74, −0.04] |
| 120m | 7,457 | −0.29 | −0.20 | 3/9 | −1.21 | [−0.79, +0.20] |
| 240m | 7,426 | +0.08 | 0.00 | 4/9 | −1.11 | [−0.58, +0.78] |

Only the 240m non-overlap mean is (barely) positive; its remove-best is
negative and its CI firmly crosses zero. It cannot support the gate.

## Gate evaluation (§12, raw values)

| Criterion | 30m | 60m | 120m | 240m |
|---|---|---|---|---|
| N ≥ 500 | ✓ | ✓ | ✓ | ✓ |
| MEAN_NET ≥ +1.5 | ✗ (−0.27) | ✗ (−0.24) | ✗ (−0.23) | ✗ (−0.10) |
| MEDIAN_NET > 0 | ✗ | ✗ | ✗ | ✗ |
| POSITIVE_YEARS ≥ 6/9 | ✗ (1) | ✗ (2) | ✗ (2) | ✗ (5) |
| REMOVE_BEST > 0 | ✗ | ✗ | ✗ | ✗ |
| CI95 lower > 0 | ✗ | ✗ | ✗ | ✗ |
| NON_OVERLAP_4H mean > 0 | ✗ | ✗ | ✗ | ✓ (+0.08) |

`GATE_PASSING_HORIZONS = []` → **NO_EMA20_RT_SIGNAL**.

Diagnostic observation (reporting only, NOT a variant proposal): the MID-to-MID
drift after the first retest is faintly positive at every horizon
(+0.19 … +0.50 pips mean) — the visual setup does carry a tiny mean-reverting
bias, but it is an order of magnitude below the real historical round-trip
spread, so the executable reference return is negative everywhere. 2010 is the
only strongly positive year (wider spreads-era caveat NOT explored per §13).

## Engine validation

- 26 synthetic tests green (`test_ema20_rt_m0.py`): M15 causal aggregation,
  loader gap-bar removal + 2019 hard-cut assertion, EMA20 causal + bit-exact
  formula, reclaim conditions (prev ≤ EMA / current strictly > EMA), no
  reclaim from forming candle, armed-state exclusivity, first retest only,
  tick-level retest inside forming bar, approach-from-above, active-EMA = latest
  completed bar, no invalidation from forming candle, invalidation on completed
  close + rearm, unresolved at hard end, 250 ms latency, ASK entry / BID exit,
  spread naturally charged, 60 s NO_FILL window (inclusive boundary),
  five horizons, per-horizon gap invalidation, NOT_MEASURABLE at hard
  end/data end, NON_OVERLAP_4H greedy, frozen gate conditions, metric
  definitions (positive years, remove-best, bootstrap CI).
- Existing suites stay green: MTF-M1 OK, TICK-M1 OK, TICK-M0 18/18
  (script-style runner, unchanged since before base). CI step registered.

## Real-data audit (§16) — independent code path

`audit_real.py` re-derives bars (own slot aggregation + own gap-flag removal),
the GAP LIST (own pandas-calendar weekend math), EMA20 (own recursion, verified
bit-identical), the full chronological armed/retest/invalidation walk (literal
bar-close walk, different formulation from the engine's vectorized sweep), and
entry/horizon exits, directly from the raw monthly tick parquet.

**AUDIT PASS — full replication, not just 20 events:**

- Engine events 15,623 = audit events 15,623 (the audit's first draft
  skipped the frozen gap-bar removal, produced 7 extra reclaims and was
  corrected — the engine was verified correct, the audit path was fixed).
- All 6 study counters match exactly (reclaim bars, reclaims, retests,
  invalidated, no-fill, unresolved).
- Detailed field-by-field verification: **24/24 exact** on spread events
  covering every discovery year 2010–2018 (reclaim bar / reclaim close /
  EMA20 at reclaim / retest timestamp / active EMA20 / previous MID / retest
  MID / entry timestamp / ASK entry / every available horizon's exit
  timestamp / BID exit / net return — exact equality on ints and floats).
- `ALL_MATCH=True` (`ema20_rt_m0_audit.json`).
- The complete per-event dump (26 MB, `ema20_rt_m0_events.json`) is
  intentionally NOT committed (§18: small results only).

## Governance

- `SHORT_SIDE_TESTED=NO` (screenshot: "DANS LE CAS LONG" only).
- `2019_PLUS_ACCESSED=NO`, `PROTECTED_OOS_ACCESSED=NO`.
- Exactly ONE setup tested; no variants; mission STOPS here.
- DO NOT MERGE.
