# MACRO_TICK_M1_FROZEN_SPEC

**Mission:** MACRO-TICK-M1 — Event-driven EURUSD strategy discovery, NFP + CPI, tick-accurate.
**Status:** FROZEN BEFORE ANY OUTCOME COMPUTATION.
**Parent commit:** `f968f4ae353e79fef80311e646987dc3add38b2b` (MACRO-TICK-M0, PR #31, DO NOT MERGE).
**Branch:** `research/macro-tick-m1-event-strategies`.
**Discovery window:** 2010-01-01 inclusive → 2019-01-01 exclusive. **2019+ FORBIDDEN. Protected OOS FORBIDDEN.**

This document freezes every rule used by the MACRO-TICK-M1 engine. It is
committed before any post-event strategy outcome is computed. No threshold,
window, variant or rule below may be changed after seeing results. Exactly
**3 strategies** (A, B, C) — no variants, no grid, no optimizer, no ML, no
threshold sweep, no alternative TP/SL.

---

## 0. Objective and epistemology

Discover whether the first seconds following major US macro releases (NFP,
CPI) contain a robust, economically meaningful EURUSD trading opportunity.

This is NOT a generic indicator strategy, an NFP "guess", a CPI forecast
strategy, a parameter optimization, or a consensus-surprise strategy. No
reliable historical consensus forecasts are used. **The market reaction
itself is the causal information source.**

Primary event families: **NFP, CPI** only.
**FOMC is EXCLUDED from primary research** (heterogeneous pre-2016 intraday
timestamp provenance). `FOMC_PRIMARY_RESEARCH=DEFERRED`. No exploratory FOMC
return calculations are permitted.

---

## 1. Governance

1. Branch `research/macro-tick-m1-event-strategies`, parent exactly
   `f968f4ae353e79fef80311e646987dc3add38b2b`.
2. This spec is committed BEFORE any post-event strategy outcome is computed.
3. Discovery = 2010-01-01 inclusive → 2019-01-01 exclusive. The engine holds a
   hard guard: no month partition outside 2010-01..2018-12 can ever be opened
   (raises). Trades whose entry+time-exit crosses 2019-01-01 are not possible
   here (last eligible release is 2018-12-12) but the guard exists and is
   tested.
4. Protected OOS (2019-2022, 2023+) is never inspected.
5. Commit order: (1) this frozen spec → (2) engine + tests → (3) results +
   report. No bulk tick data in git.

---

## 2. Events

Source: **validated MACRO-TICK-M0 database**
`research/macro_tick_m0/data/macro_events_2010_2018_aligned.csv`
(official exact release timestamps, BLS schedule pages; ALFRED vintages).

- Families used: `NFP`, `CPI` only (216 events). `FOMC` rows are dropped
  before anything else.
- An event is **PRIMARY_ELIGIBLE** iff ALL of:
  1. `release_timestamp_utc` inside the Discovery window;
  2. `tick_alignment_status == "ALIGNED"` (from M0);
  3. `post_tick_lag_ms <= 5000` — first post-release tick within 5 seconds;
     events with first post-release tick > 5 s are **excluded from PRIMARY
     metrics and reported separately**;
  4. a valid tick exists strictly before T0 (pre-tick exists);
  5. no data gap (frozen definition §11) intersects `[T0 − 60 min, T0 + 30 s]`
     — this protects the baseline window and the shock window. Data gaps
     after T0+30 s are handled at setup/trade level (§11), never by
     inventing price paths;
  6. baseline computable (≥ 1 valid tick in the baseline window and
     `NOISE_SCALE > 0`).
- FORBIDDEN as inputs anywhere: forecast consensus, revised values, future
  macro values. ALFRED actual values may be retained as metadata but MUST NOT
  determine trade direction. In this engine they are not read at all.

## 3. Market price definitions

Tick data contains BID and ASK. A tick is **VALID** iff `bid > 0`, `ask > 0`,
both finite, and `ask >= bid`.

- `MID = (BID + ASK) / 2`
- `T0` = exact official release timestamp (ns UTC, from the M0 database).
- `P0` = MID of the **last valid tick strictly BEFORE T0**.
- `P30` = MID of the **first valid tick at or after `T0 + 30 s`**; search
  window `[T0 + 30 s, T0 + 90 s]`; if no valid tick exists in that window the
  event is excluded from PRIMARY (`POST_TICK_MISSING_P30`, reported
  separately).
- `SHOCK = P30 − P0`; `SHOCK_PIPS = SHOCK / PIP` with `PIP = 1e-4`.
- `SHOCK_DIR`: LONG if `SHOCK > 0`, SHORT if `SHOCK < 0`.

All times causal. Nothing after the decision timestamp may influence the
signal. 1 pip = `1e-4` price units. Timestamps are int64 nanoseconds UTC.

## 4. Pre-event baseline (causal noise scale)

For each event use ONLY `[T0 − 60 min, T0 − 5 min)` (the last 5 minutes
before release are excluded).

**A. ABS_MOVE_30S_Q95** — non-overlapping 30-second MID changes:
- grid anchored at `T0 − 60 min`: bucket k = `[T0−60m + 30s·k, T0−60m + 30s·(k+1))`,
  k = 0..109 (110 buckets = 55 min exactly);
- a bucket contributes iff ≥ 1 valid tick lies in `[bucket_start, bucket_end)`;
  its change = `MID(last valid tick < bucket_end) − MID(first valid tick ≥ bucket_start)`;
- buckets with no tick inside are skipped (no invented prices);
- `ABS_MOVE_30S_Q95` = 95th percentile of the absolute bucket changes in
  pips (numpy `np.percentile`, linear interpolation — frozen).

**B. MEDIAN_SPREAD** = median of `(ask − bid)/PIP` over all valid ticks in
the baseline window (numpy `np.median` — frozen).

```
NOISE_SCALE  = max(ABS_MOVE_30S_Q95, MEDIAN_SPREAD)      # pips
SHOCK_SCORE  = abs(SHOCK_PIPS) / NOISE_SCALE
```

**QUALIFYING_SHOCK** iff `SHOCK_SCORE >= 2.0` AND `abs(SHOCK_PIPS) >= 1.0`.
Thresholds **FROZEN**: 2.0 and 1.0. No alternative 1.5 / 2.5 / 3.0 sweep.

## 5. Entry spread safety (FROZEN, not optimized)

At any proposed entry tick: `CURRENT_SPREAD = (ask − bid)/PIP` of that tick.
If `CURRENT_SPREAD > 3 × MEDIAN_SPREAD` the trade is `SPREAD_TOO_WIDE` and
**skipped** (counted, not traded). Multiplier **3** frozen.

## 6. Real execution

- Signal/structure use MID; execution uses REAL BID/ASK ticks.
- Frozen processing latency: **250 ms**.
- LONG ENTRY: first valid tick with `ts >= decision + 250 ms`, filled at its
  **ASK**. SHORT ENTRY: first valid tick with `ts >= decision + 250 ms`,
  filled at its **BID**.
- LONG EXIT: **BID**. SHORT EXIT: **ASK**.
- The real historical spread therefore enters naturally; no additional
  synthetic spread is subtracted.
- Entry search bound: if no valid tick exists within `[decision + 250 ms,
  decision + 1 h)` the setup is `NO_FILL` (counted).
- Post-entry evaluation starts at the tick **strictly after** the entry tick
  (a trade opened at tick k cannot be exited by tick k itself). Same
  convention as the validated MTF-M1 engine.

## 7. STRATEGY A — `MACRO_A_30S_CONTINUATION`

Hypothesis: a sufficiently abnormal 30-second reaction to a major macro
release represents genuine information assimilation and continues.

- Eligibility: `QUALIFYING_SHOCK = TRUE` (else `SHOCK_NOT_QUALIFYING`, no trade).
- Decision timestamp: `T0 + 30 s` (exact).
- Direction: same direction as SHOCK.
- ENTRY: first executable tick `>= decision + 250 ms` (§6 sides).
- Structural STOP: `P0` (pre-release MID) for both LONG and SHORT.
- If the stop is invalid (LONG: `P0 >= entry`; SHORT: `P0 <= entry`) →
  `NO_TRADE_INVALID_STOP`. If effective risk `|entry − stop| < 1.0 pip` →
  `NO_TRADE_RISK_TOO_SMALL`. Both are NO TRADE (setup-level counts).
- `R = |executable entry − P0|`.
- TARGET = `1.5R` from executable entry.
- TIME EXIT: first tick at/after `entry + 60 minutes`, filled at exit side.
- Maximum **one** A trade per macro event.

## 8. STRATEGY B — `MACRO_B_FAILED_SHOCK_REVERSAL`

Hypothesis: some large initial macro reactions are liquidity overshoots; a
rapid 50% retracement indicates failure of the initial repricing.

- Eligibility: `QUALIFYING_SHOCK = TRUE`.
- Observe causally from `T0 + 30 s` until `T0 + 5 min` (trigger search on
  ticks with `T0 + 30 s <= ts <= T0 + 5 min`).
- `D = P30 − P0`; 50% retracement level `= P0 + 0.50 × D` (both directions).
- Initial UP shock (`D > 0`): trigger when `MID <= level` → direction SHORT.
- Initial DOWN shock (`D < 0`): trigger when `MID >= level` → direction LONG.
- The **FIRST causal trigger only**; if none by `T0 + 5 min` →
  `NO_TRIGGER` (setup expires).
- ENTRY: first valid tick `>= trigger_ts + 250 ms` (§6 sides), then spread
  safety (§5) at that tick.
- STOP: most extreme MID observed between T0 (inclusive) and the trigger tick
  (inclusive): UP-shock reversal SHORT → highest MID in `[T0, trigger]`;
  DOWN-shock reversal LONG → lowest MID in `[T0, trigger]`.
- TARGET: `P0`. "Target already crossed at executable entry" is evaluated
  with the frozen exit-side rule (§10): SHORT → `ask_entry <= P0`;
  LONG → `bid_entry >= P0` → `NO_TRADE_TARGET_CROSSED`.
- If risk `|entry − stop| < 1.0 pip` → `NO_TRADE_RISK_TOO_SMALL`; if the stop
  is not beyond the entry in the correct direction → `NO_TRADE_INVALID_STOP`.
- TIME EXIT: first tick at/after `entry + 30 minutes`.
- Maximum **one** B trade per event.

## 9. STRATEGY C — `MACRO_C_5M_DIGESTION_BREAKOUT`

Hypothesis: after the first chaotic minutes of a real information shock, a
break of the completed post-news range may identify the second-stage
institutional repricing.

- Eligibility: `QUALIFYING_SHOCK = TRUE`.
- Causal post-release MID range over ticks with `T0 <= ts < T0 + 5 min`:
  `NEWS_HIGH` = highest MID, `NEWS_LOW` = lowest MID,
  `NEWS_MID = (NEWS_HIGH + NEWS_LOW) / 2`.
- No trade before `T0 + 5 min`.
- Breakout search on ticks with `T0 + 5 min <= ts <= T0 + 35 min`:
  first tick with `MID > NEWS_HIGH` (LONG) or `MID < NEWS_LOW` (SHORT)
  (strict inequalities; `MID == NEWS_HIGH` is not a breakout). If none →
  `NO_BREAKOUT`.
- Decision timestamp = first breakout tick timestamp.
- ENTRY: first valid tick `>= decision + 250 ms` (§6 sides), then spread
  safety (§5).
- STOP: `NEWS_MID`. Invalid (LONG: `NEWS_MID >= entry`; SHORT:
  `NEWS_MID <= entry`) → `NO_TRADE_INVALID_STOP`; risk `< 1.0 pip` →
  `NO_TRADE_RISK_TOO_SMALL`.
- TARGET: `1.5R`.
- TIME EXIT: first tick at/after `entry + 120 minutes`.
- Maximum **one** C trade per event.

## 10. Stop / target execution (tick accurate)

After entry, scanning ticks strictly after the entry tick. **First event
wins**, tie order frozen: `STOP` > `TARGET` > `TIME EXIT` > `DATA GAP`.

- LONG: STOP triggered when `BID <= stop`, filled at the **current BID**
  (actual executable tick — gaps/slippage are real, never filled magically at
  the requested stop). TARGET triggered when `BID >= target`, favorable fill
  **capped at target**.
- SHORT: STOP triggered when `ASK >= stop`, filled at the current **ASK**.
  TARGET triggered when `ASK <= target`, favorable fill capped at target.
- A data gap invalidates only if its onset **strictly precedes** the resolved
  exit timestamp (the gap-onset tick itself is present and usable).

## 11. Data gaps

- Reuse the validated TICK pipeline gap handling: an inter-tick delta is a
  **data gap** iff its non-weekend portion exceeds 1 hour. Frozen weekend
  windows: every week `[Fri 21:59:00Z, Sun 22:01:00Z)`. Regular weekend
  market closure is NOT a data gap.
- If an unresolved real data gap occurs while a trade is open →
  `DATA_GAP_INVALID`, excluded from primary metrics, counted; no price path
  is invented.
- If a data gap occurs inside a pre-trade observation window (B trigger
  search after T0+30 s, C breakout search after T0+5 m) before the trigger is
  found → the setup is unobservable → `GAP_SETUP_INVALID`, counted, no trade.

## 12. Macro execution stress

Baseline = real BID/ASK execution. Additional adverse slippage per side
(never favorable):

- `STRESS_025`: +0.25 pip per side → net − 0.50 pip
- `STRESS_050`: +0.50 pip per side → net − 1.00 pip (PRIMARY GATE)
- `STRESS_100`: +1.00 pip per side → net − 2.00 pip

## 13. No money-management rescue

FORBIDDEN: pyramid, martingale, averaging down, reverse-on-stop, partial
exits, trailing stop, break-even manipulation, dynamic risk sizing.
Evaluation in **pips and R only**.

## 14. Primary config count

Exactly 3 strategies: A, B, C. No A2/A_60SEC/A_15SEC/B_25PCT/B_75PCT/
C_10MIN/C_15MIN. No parameter grid, no optimizer, no ML, no threshold sweep,
no alternative TP/SL.

## 15. Family breakdown

Primary verdict is **pooled** NFP + CPI. NFP and CPI are reported separately
(N, mean net, PF, positive years) — **DIAGNOSTIC only**; no family selection
after seeing results. A pooled strategy cannot PASS if either NFP or CPI has
a negative mean net.

## 16. Metrics (per strategy A/B/C)

`EVENTS_ELIGIBLE` (primary-eligible events), `QUALIFYING_SHOCKS`, `N_TRADES`,
`TRADES_PER_YEAR` (÷ 9 discovery years), `MEAN_SHOCK_PIPS`,
`MEDIAN_SHOCK_PIPS`, `MEAN_SHOCK_SCORE` (over the strategy's traded events),
`NET_EXECUTABLE_MEAN_PIPS`, `MEDIAN_NET`, `STRESS_025_MEAN`,
`STRESS_050_MEAN`, `STRESS_100_MEAN`, `WIN_RATE` (net > 0), `AVG_WIN`,
`AVG_LOSS`, `PROFIT_FACTOR` (Σwins/|Σlosses|), `EXPECTANCY_R`
(mean of net_pips/risk_pips), `TOTAL_NET_PIPS`, `MAX_DRAWDOWN_PIPS`
(cumulative net, chronological entry order), `MAX_CONSECUTIVE_LOSSES`,
`POSITIVE_YEARS` (years with total net > 0 among 2010..2018),
`BY_YEAR` (N, MEAN_NET, TOTAL_NET, PF), NFP/CPI breakdown,
`REMOVE_BEST_1_PERCENT_NET_MEAN` (remove ceil(1%·N) largest net trades, mean
of the remainder), bootstrap CI95 of the trade mean (2000 resamples, seed 42,
`numpy.random.default_rng(42)`, 2.5/97.5 percentiles), exit counts:
`STOP`, `TARGET`, `TIME`, `DATA_GAP_INVALID`, `SPREAD_TOO_WIDE`, `NO_FILL`
(plus setup-level counters: qualifying shocks, no-trigger/no-breakout,
no-trade reasons, gap-invalidated setups).

`DATA_GAP_INVALID` trades are excluded from all primary metrics and only
counted.

## 17. Economic gate — `MACRO_TICK_PROMISING`

A strategy is MACRO_TICK_PROMISING only if ALL:

```
N_TRADES                    >= 40
NET_EXECUTABLE_MEAN_PIPS    >= +3.0
PROFIT_FACTOR               >= 1.25
EXPECTANCY_R                >= +0.10
POSITIVE_YEARS              >= 6 of 9
REMOVE_BEST_1_PERCENT_NET_MEAN > 0
STRESS_050_MEAN             > 0
TOTAL_NET_PIPS              > 0
NFP_MEAN_NET                > 0
CPI_MEAN_NET                > 0
```

CI95 is reported; if the CI95 lower bound > 0 the additional robustness flag
`CI_POSITIVE=YES` is set. CI-positive is NOT mandatory for Discovery PASS.

## 18. Fail fast / token discipline

Run all three frozen strategies. Per strategy: if `NET mean <= 0` OR
`PF <= 1.0` OR `REMOVE_BEST <= 0` → **REJECT**. No rescue variants. Once
A/B/C each have a frozen verdict: STOP. No polishing of non-decision-changing
statistics; no credits spent explaining an already decisive failure.
Verdicts: `MACRO_TICK_PROMISING` / `FAIL_GATE` (economically interesting but
gate-missing) / `REJECT`.

## 19. FOMC

`FOMC_PRIMARY_RESEARCH=DEFERRED`. Nothing more. No exploratory FOMC return
calculations.

## 20. Engine validation (synthetic tests, all mandatory)

P0 last tick before T0; P30 first tick >= T0+30 s; baseline uses only
T0−60m → T0−5m; no future values; Q95 computation; median spread;
shock-score sign + magnitude; LONG/SHORT direction; 250 ms latency; LONG
entry ASK / SHORT entry BID; LONG exit BID / SHORT exit ASK; A structural P0
stop; B 50% retracement trigger; B observed-extreme stop; C 5-minute range
freezes exactly at T0+5m; C cannot trigger before T0+5m; spread safety skip;
stop execution with overshoot; target cap; time exit; stress arithmetic;
data-gap invalidation; 2019 hard cutoff. Plus: run the existing suites
MACRO-TICK-M0, MTF-M1, TICK-M1, TICK-M0.

## 21. Real data audit

Before accepting final results: independently re-verify at least 10 trades
from A, 10 from B, 10 from C (or all if < 10), with a **separate audit path**
(different implementation from the production executor), confirming: event
timestamp, P0, P30, shock direction, trigger timestamp, entry timestamp,
entry side/price, SL, TP, exit timestamp, exit side/price, PnL.

## 22. Performance

No 208M-tick RAM loads. Only event-adjacent windows are loaded
(frozen per-event slice `[T0 − 62 min, T0 + 200 min]` through the
month-partition LRU `TickStore`). Reuse existing parquet partitions. No new
download, no raw data duplication.

## 23. Git

Commit: frozen spec → code → tests → small results → report. No bulk tick
data. PR **NON MERGED**, base `research/macro-tick-m0` so the PR contains
only MACRO-TICK-M1 work.

## 24. Final output

`MACRO_TICK_M1_EVENT_STRATEGY_DISCOVERY` with BASE_HEAD, FROZEN_SPEC_COMMIT,
FINAL_HEAD, PR, event counts, per-strategy A/B/C metrics + verdicts,
STRATEGIES_PASSING_GATE, BEST_STRATEGY, FOMC_PRIMARY_RESEARCH=DEFERRED,
2019_PLUS_ACCESSED=NO, PROTECTED_OOS_ACCESSED=NO, TESTS, REAL_DATA_AUDIT,
CI, FINAL_STATUS. If zero pass → `NO_MACRO_TICK_CANDIDATE`; if >= 1 passes →
`STOP_FOR_HUMAN_REVIEW`. DO NOT OPEN V1. DO NOT MERGE. STOP.

---

*Frozen by MACRO-TICK-M1 governance commit. Any change after this commit
invalidates the discovery.*
