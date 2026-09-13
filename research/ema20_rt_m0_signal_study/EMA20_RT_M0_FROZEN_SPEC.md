# EMA20_RT_M0 — FROZEN SPEC (EMA20 reclaim → first retest, signal study, LONG only)

Branch `research/ema20-rt-m0-signal-study` (base `def3a94`, tip of
`research/mtf-m1-tick-execution`, NOT merged).

**Commit-order guarantee:** this file is committed BEFORE any Discovery outcome
is computed. Every rule below is frozen. This is a SIGNAL STUDY, not a
strategy: no SL, no TP, no money management, no optimization, no variants.
Exactly ONE setup is tested. If the signal fails the frozen gate → STOP; if it
passes → STOP_FOR_STRATEGY_DESIGN. No SL/TP may be invented in this mission.

Scope: Discovery only. EURUSD only. LONG side only. `SHORT_SIDE_TESTED=NO`
(the supplied screenshot describes "DANS LE CAS LONG" only; no symmetry is
assumed). 2010-01-01 inclusive → 2019-01-01 exclusive. 2019+ FORBIDDEN.
Protected OOS FORBIDDEN. No merge. Research only.

Pre-spec descriptive audit (data-side facts only, no outcomes; committed in
this spec before any event is measured): the validated MTF-M1 derived store at
`<data_root>/derived/mtf_m1` was rebuilt from the current tick store
(manifest digest `c2982340c6269744`, which includes the audited JUNE2018
repair): M15 = 224,174 bars (204 gap-flagged), H1 = 56,052 (203), H4 = 14,510
(144); frozen GAP LIST = 102 non-weekend inter-tick gaps > 1 h. First M15 bar
label 2010-01-01T00:00:00Z, last 2018-12-31T22:00:00Z (inside Discovery).

---

## 1. Governance

- Discovery window: **[2010-01-01T00:00:00Z, 2019-01-01T00:00:00Z)**.
- The tick loader HARD-REFUSES any partition outside 2010-01..2018-12
  (`mtf_lib.assert_month_in_discovery`, same validated guard as TICK-M1/MTF-M1).
- `2019_PLUS_ACCESSED=NO`, `PROTECTED_OOS_ACCESSED=NO`.
- No tick, bar, or derived value with timestamp ≥ 2019-01-01T00:00:00Z is ever
  read or used.

## 2. Data and bars

- EURUSD only. Existing validated month-partitioned tick parquet
  (`parquet/EURUSD/year=YYYY/month=MM/ticks.parquet`). NOT redownloaded,
  NOT duplicated.
- M15 MID bars are reused from the validated MTF-M1 builder
  (`research/mtf_m1_tick_execution/build_bars.py` + `mtf_lib.bars_from_ticks`):
  per tick `mid = (bid+ask)/2`; left-labelled `[t, t+15m)` on the UTC grid;
  a bar exists only if it contains ≥ 1 tick; O=first, H=max, L=min, C=last
  mid of the ticks inside the interval.
- **Gap-flagged bars are REMOVED from the bar series** (frozen MTF-M1 rule):
  bar `[t, t+15m)` is invalid iff a GAP LIST interval `(g1,g2)` satisfies
  `g1 < t+15m AND g2 > t`. The remaining bar sequence is the ONLY series used
  for reclaims, EMA20, and "previous bar" references. This is the only bar
  exclusion; weekend hours produce no bars (market closed).
- **GAP LIST (frozen):** inter-tick delta `(t1,t2)` with `t2−t1 > 3600s` whose
  portion OUTSIDE the frozen weekend window `[Friday 21:59:00Z, Sunday
  22:01:00Z)` exceeds 3600s. Regular weekend closures are NOT data gaps.

## 3. EMA20 (causal)

- Standard EMA on COMPLETED M15 MID closes only, over the remaining bar
  series: `e_1 = x_1` (first remaining completed close), `e_t = e_{t-1} +
  α(x_t − e_{t-1})`, `α = 2/(20+1)`. Same validated implementation as MTF-M1
  (`mtf_lib.ema`). No alternative definition is permitted after results.
- The EMA value of bar `i` becomes known only at its exact close time
  `close_ts[i] = start[i] + 900s`. No intrabar or forming-candle knowledge.

## 4. Reclaim (arming event, LONG)

A LONG reclaim occurs on completed M15 bar `i` (with a predecessor bar `i−1`
in the remaining series) iff:

- `CLOSE[i−1] <= EMA20[i−1]` AND `CLOSE[i] > EMA20[i]`.

The reclaim becomes known ONLY at `close_ts[i]`. Bars are never inspected
while forming. On reclaim: state = `ARMED_LONG`. No event, no entry yet.

## 5. Retest (the event)

While `ARMED_LONG` (armed by bar `i` at `reclaim_ts = close_ts[i]`), ticks are
scanned causally forward over the half-open window
`[reclaim_ts, T_END)` where:

- `T_END = close_ts[j]` of the FIRST later completed bar `j` in the remaining
  series with `CLOSE[j] < EMA20[j]` (the invalidation time, §6), or
  `DISCOVERY_END` if no such bar exists (setup still armed at the hard cut →
  counted `UNRESOLVED_AT_END`; never a retest).
- **Active EMA at tick `ts`:** `EMA20` of the latest COMPLETED remaining bar
  with `close_ts <= ts`. A bar closing exactly at `ts` IS active at `ts`.
- **RETEST** at the FIRST tick in the window where
  `prev_mid > active_EMA AND mid <= active_EMA`
  (first touch/cross from above). `prev_mid` = MID of the immediately
  preceding tick in the stream. By construction the reclaim bar's close tick
  is the immediately preceding tick of the first scanned tick (no tick exists
  between a bar's close tick and the bar's close time), so the chain starts at
  `prev_mid = CLOSE[i] > EMA20[i]`.
- Equal-timestamp precedence (frozen): the invalidating close is evaluated
  FIRST; ticks at exactly `T_END` are not part of the window. A retest tick at
  exactly `reclaim_ts` IS part of the window.
- `EVENT_TIMESTAMP` = retest tick timestamp; `EVENT_MID` = that tick's MID.
- FIRST retest only. No second/third retest. No timeout, no maximum number of
  bars: the setup stays armed until retest or invalidation.

## 6. Invalidation

The armed setup is invalidated BEFORE a retest iff a completed M15 bar `j`
(later than the reclaim bar in the remaining series) satisfies
`CLOSE[j] < EMA20[j]` (strictly below). The invalidation becomes known at
`close_ts[j]` (= `T_END`); no intrabar close can invalidate. After
invalidation the setup is discarded (counted `N_INVALIDATED_BEFORE_RETEST`);
state returns to neutral; a later valid reclaim may arm a new setup.

## 7. One armed setup at a time

Only one `ARMED_LONG` setup at a time. Additional above-EMA closes and
reclaim conditions occurring while armed are IGNORED (a new reclaim can never
overwrite an armed setup). After RETEST or INVALIDATION, state returns to
neutral and the NEXT reclaim whose `close_ts` is strictly after the resolution
time may arm again.

## 8. Executable reference entry (measurement reference only)

At the retest (`EVENT_TIMESTAMP`), frozen latency **250 ms**:

- LONG entry = first ASK tick with `ts >= EVENT_TIMESTAMP + 250ms`.
- **NO_FILL** iff no tick exists with
  `EVENT_TIMESTAMP + 250ms <= ts <= EVENT_TIMESTAMP + 250ms + 60s`.
  (A GAP LIST interval starting between the retest and the window end
  automatically produces NO_FILL once the next tick lies beyond the 60 s
  window; there is no additional post-gap entry rejection rule.)
- Entry price = ASK of that tick. This entry is a reference for forward-return
  measurement only. No SL, no TP.

## 9. Forward horizons

Exactly these horizons after the ENTRY FILL timestamp `entry_ts`:
**15, 30, 60, 120, 240 minutes**.

- Exit for horizon H = first BID tick with `ts >= entry_ts + H`.
- If `entry_ts + H >= DISCOVERY_END`, horizon H is NOT measurable for that
  event (`NOT_MEASURABLE`, counted per horizon; excluded from that horizon
  only). No 2019+ tick is ever touched. The exit search window extends past
  weekends (frozen pad 4 days, grow ×4 — same validated mechanism as MTF-M1).
- **Per-horizon data-gap invalidation:** if a GAP LIST interval `(g1,g2)`
  satisfies `g1 < exit_tick_ts AND g2 > entry_ts`, the event is INVALID for
  that horizon only (`GAP_INVALID_H`, counted per horizon, excluded from that
  horizon's metrics). No prices are invented.
- **Executable net return (pips):** `(BID_exit − ASK_entry) / 1e-4`. The real
  historical spread is charged by construction; NO synthetic spread is
  subtracted.
- **MID-to-MID signed return (diagnostic):** `(mid_exit − mid_entry) / 1e-4`
  with `mid = (bid+ask)/2` at the exit and entry ticks.

## 10. Metrics (frozen, per horizon)

Over events valid for that horizon (excluding `NOT_MEASURABLE` and
`GAP_INVALID_H` for that horizon):

- N; MEAN_MID_RETURN_PIPS; MEDIAN_MID_RETURN_PIPS
- MEAN_EXECUTABLE_NET_PIPS; MEDIAN_EXECUTABLE_NET_PIPS
- WIN_RATE_NET (net > 0)
- STD (sample, ddof=1); STANDARD_ERROR = STD/√N
- CI95_MEAN_NET: percentile bootstrap of the mean, 2000 resamples,
  `numpy default_rng(42)` (same as MTF-M1); lower and upper bounds reported
- POSITIVE_YEARS: number of years y in 2010..2018 with `N_y > 0` AND
  `MEAN_NET_y > 0`, by ENTRY year (denominator 9)
- BY_YEAR: N, MEAN_NET, MEDIAN_NET, WIN_RATE (executable net)
- REMOVE_BEST_1_PERCENT_NET_MEAN: drop the top `k = ceil(0.01·N)` events by
  executable net, mean of the remainder (same as MTF-M1)

Study-level counts:

- `N_RECLAIM_BARS`: all bar-level reclaim crossings (diagnostic)
- `N_RECLAIMS`: arming reclaims (state transitions into ARMED_LONG = setups)
- `N_RETESTS`; `N_INVALIDATED_BEFORE_RETEST`; `N_NO_FILL`;
  `N_UNRESOLVED_AT_END` (armed at the hard cut)
- `MEDIAN_RECLAIM_TO_RETEST_BARS`: median over retest events of
  `#{close_ts <= retest_ts} − #{close_ts <= reclaim_ts}` (completed M15 bar
  closes from the reclaim close up to and including the retest moment)
- `MEDIAN_RECLAIM_TO_RETEST_MINUTES`: median of
  `(retest_ts − reclaim_ts) / 60s`

## 11. Non-overlap robustness (diagnostic only)

`NON_OVERLAP_4H`: chronological greedy selection over retest events with a
valid entry — keep an event iff its `entry_ts >= last_kept_entry_ts + 4h`
(14400s); otherwise ignore it. The kept set is selected once (by entry time)
and reused for all horizons; events lacking a horizon drop out of that
horizon's non-overlap metrics. Same headline metrics recomputed (N, mean net,
median net, win rate, positive years, remove-best, CI95). Diagnostic ONLY —
never used to choose a winning horizon.

## 12. Signal-promising gate (NOT a strategy gate)

`EMA20_RT_SIGNAL_PROMISING` iff at least ONE of horizons 30m / 60m / 120m /
240m satisfies ALL:

- N ≥ 500
- MEAN_EXECUTABLE_NET_PIPS ≥ +1.5
- MEDIAN_EXECUTABLE_NET_PIPS > 0
- POSITIVE_YEARS ≥ 6 (of 9)
- REMOVE_BEST_1_PERCENT_NET_MEAN > 0
- CI95 lower bound > 0
- AND the corresponding NON_OVERLAP_4H mean executable net > 0

The 15-minute horizon is diagnostic only and can NEVER independently pass.
This is a signal gate, not a strategy gate.

## 13. Scientific stop rule

Do NOT optimize the setup. No EMA10/21/25, no wick or 0.5-pip tolerance, no
close-retest, no second retest, no 3-bar/8-bar timeout, no trend filter, no
EMA slope, no RSI, no ATR, no sessions, no London-only, no NY-only, no
variants of any kind. Exactly ONE setup. If the signal fails → STOP
immediately after tests + required metrics + audit + report + PR. Do not
explore why, do not generate rescue variants. If it passes →
STOP_FOR_STRATEGY_DESIGN. No SL/TP in this mission.

## 14. Short side

DO NOT TEST SHORT. `SHORT_SIDE_TESTED=NO`. The supplied screenshot describes
"DANS LE CAS LONG" only; the original short rules are not available and no
symmetry is assumed.

## 15. Engine validation (required, synthetic)

M15 causal aggregation · EMA20 causal calculation · reclaim requires previous
close ≤ EMA20 · reclaim requires current completed close > EMA20 · no reclaim
from a forming candle · armed state · first retest only · retest must approach
from above · EMA reference uses latest completed bar · invalidation on
completed close below EMA20 · no invalidation from a forming candle · rearm
only after retest/invalidation · 250 ms latency · LONG entry at ASK · exit at
BID · spread naturally charged · 15/30/60/120/240 horizons · per-horizon
data-gap exclusion · 2019 hard cutoff · non-overlap 4h. Plus the existing
MTF-M1, TICK-M1 and TICK-M0 suites must stay green. CI registration for this
directory.

## 16. Real-data audit

An INDEPENDENT code path (no shared event-derivation code: direct parquet
reads, its own EMA recursion, its own state machine, its own tick scans)
re-derives at least 20 real events across different years and verifies, for
each: reclaim bar, reclaim close, EMA20 at reclaim, retest timestamp, active
EMA20, previous MID, retest MID, entry timestamp, ASK entry, every available
horizon's exit timestamp, BID exit, and calculated net return. Minimum
20/20 EXACT. Any mismatch aborts the study.

## 17. Performance

Month-partitioned tick access only (`mtf_lib.TickStore`); the full history is
never held in RAM; armed-window tick scans are numpy-vectorized and disjoint.

## 18. Output

Non-merged PR (base `research/mtf-m1-tick-execution`) + `EMA20_RT_M0_SIGNAL_STUDY`
block. Commit only: frozen spec, code, tests, small results, report. No tick
data. Verdict: `EMA20_RT_SIGNAL_PROMISING` → STOP_FOR_STRATEGY_DESIGN, else
`NO_EMA20_RT_SIGNAL` → STOP. DO NOT MERGE.
