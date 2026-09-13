# MTF_M1 — FROZEN SPEC (tick-accurate multi-timeframe strategy discovery)

Branch `research/mtf-m1-tick-execution` (parent head `27b6e24`, TICK-M1 PR #29, NOT merged).

**Commit-order guarantee:** this file is committed BEFORE any Discovery outcome
is computed. All thresholds below are frozen. No optimizer, no ML, no parameter
grid, no rescue variants, no A2/B2/C2. Exactly THREE complete strategies are
run; when each has produced one frozen verdict, the mission STOPS.

Scope: Discovery only. EURUSD, 2010-01-01 inclusive → 2019-01-01 exclusive.
2019+ FORBIDDEN. Protected OOS FORBIDDEN. No merge. Research only.

Pre-spec descriptive audit (timestamps only, no prices/outcomes; committed in
this spec before backtests): 108 monthly partitions, 208,003,917 ticks, first
tick 2010-01-01T00:00:03.964Z, last tick 2018-12-31T22:00:03.048Z, 530
inter-tick gaps >1h of which 433 are regular Fri→Sun weekend closures
(last Fri tick 21:59:56.125–.673, first Sun tick 22:00:02.765–22:00:22.563),
5 long holiday gaps (2013-01-01 22.0h; Christmas 14.0–14.5h in 2013, 2014,
2017, 2018), and ~92 one-hour holes at exact hour boundaries (the 136 absent
hourly files). No other structural gaps.

---

## 1. Governance

- Discovery window: **[2010-01-01T00:00:00Z, 2019-01-01T00:00:00Z)**.
- The loader HARD-REFUSES to open any partition outside 2010-01..2018-12
  (`assert_month_in_discovery`, same guard as TICK-M1).
- No partition, tick, or derived value with timestamp ≥ 2019-01-01T00:00:00Z
  is ever read. `2019_PLUS_ACCESSED=NO`, `PROTECTED_OOS_ACCESSED=NO`.

## 2. Data

- EURUSD only. Tick parquet reused from `BOTTRADING_TICK_DATA_ROOT`
  (`parquet/EURUSD/year=YYYY/month=MM/ticks.parquet`; 2.57 GB; NOT
  reduplicated, NOT redownloaded).
- Causal MID bars: per tick `mid = (bid+ask)/2`; bar OHLC built from mid
  values of ticks inside the bar interval (O=first, H=max, L=min, C=last).
- Timeframes: **M15 (900s), H1 (3600s), H4 (14400s)**, left-labelled `[t, t+TF)`
  on UTC grid (M15/H1 aligned to the hour; H4 aligned to 00:00 UTC).
- A bar exists only if it contains ≥1 tick. A bar is usable only after its
  interval is fully closed: decision time = exact grid close time `t+TF`.
- **Data gaps (frozen):** an inter-tick delta `(t1, t2)` with
  `t2 − t1 > 3600s` whose portion OUTSIDE the frozen weekend window exceeds
  3600s. **Weekend window (frozen from the audit above):** every week
  `[Friday 21:59:00Z, Sunday 22:01:00Z]`. Regular weekend closures are NOT
  data gaps. The gap intervals computed over the full 2010–2019 stream are
  the single frozen `GAP LIST` used by bars and by trade invalidation.
- **Gap-affected bar (frozen):** a bar `[t, t+TF)` is INVALID iff a gap
  interval `(g1, g2)` in the GAP LIST satisfies `g1 < t+TF AND g2 > t`
  (the gap boundary falls strictly inside the bar, or the gap spans the whole
  bar). Invalid bars are REMOVED from the series at every timeframe; all
  indicators and signals use the remaining bar sequence. This is the only
  bar exclusion; weekend hours produce no bars (market closed).

## 3. Execution engine

- Signals are computed on MID bars. Execution uses REAL BID/ASK ticks.
- Decision time = exact close time of the signal bar.
- Frozen latency: **250 ms**.
  - LONG entry: first tick with `ts >= decision + 250ms`, fill at its **ASK**.
  - SHORT entry: first tick with `ts >= decision + 250ms`, fill at its **BID**.
- LONG exits at **BID**; SHORT exits at **ASK**. The real historical spread is
  charged by construction; NO additional synthetic spread is subtracted.
- **NO_FILL (frozen):** if no executable-side tick exists with
  `decision+250ms <= ts <= decision+3600s`, the setup is discarded (counted
  `NO_FILL`). If the chosen entry tick is the first tick after a GAP LIST
  interval that began after the decision time, the setup is discarded
  (counted `NO_FILL_GAP`) — no fills on stale decisions.
- Entry evaluation of stop/target begins at the first tick STRICTLY AFTER the
  entry fill tick.
- **Stress (frozen):** `net_stress(x) = net − 2x` pips, x = 0.10 (STRESS_010)
  and x = 0.25 (STRESS_025) — adverse per side (entry+exit). No favorable
  slippage anywhere.
- **HARD_END (frozen):** an entry whose frozen time-exit timestamp
  `entry_ts + T` (T = 24h/48h/12h per strategy) is ≥ 2019-01-01T00:00:00Z is
  NEVER taken (counted `SKIPPED_HARD_END`). No 2019+ tick is ever touched.
  Time exit = first tick with `ts >= entry_ts + T` (BID/ASK per side); if no
  such tick exists before the dataset end, the exit is the LAST tick of the
  dataset and is still classified `TIME` (affects at most the final hours).

## 4. Common indicators (causal on completed MID bars)

All indicators use only bars with close time ≤ decision time.

- **EMA(p):** recursive `e_t = e_{t-1} + α(x_t − e_{t-1})`, `α = 2/(p+1)`,
  seeded `e_1 = x_1` (first completed bar). EMA20, EMA50, EMA200 on H4 and H1
  as required.
- **ATR14 (Wilder):** `TR_t = max(H−L, |H−C_{t-1}|, |L−C_{t-1}|)`
  (`H−L` for the first bar). First ATR = simple mean of TR_1..TR_14; then
  `ATR_t = (13·ATR_{t-1} + TR_t)/14`.
- **ADX14 (Wilder):** `+DM = H_t − H_{t-1}` if `> L_{t-1} − L_t` and `> 0`,
  else 0; `−DM = L_{t-1} − L_t` if `> H_t − H_{t-1}` and `> 0`, else 0.
  Wilder-smoothed (RMA, seed = simple mean of first 14) `+DM, −DM, TR`;
  `+DI = 100·sm(+DM)/ATR`, `−DI = 100·sm(−DM)/ATR`;
  `DX = 100·|+DI − −DI|/(+DI + −DI)`; ADX = RMA of DX seeded with the simple
  mean of the first 14 DX values. Undefined (NaN) until fully formed.
- **Bollinger (20, 2):** SMA20 of closes ± 2·σ20, σ = POPULATION standard
  deviation (ddof=0) over the last 20 completed bars including the current
  one (TA-Lib / Bollinger convention).
- No alternative definition of any indicator is permitted after results.

## 5. Strategy A — `MTF_A_TREND_PULLBACK`

H4 trend → H1 pullback → M15 continuation.

- **Regime** (LONG), evaluated at each completed H4 close:
  `EMA50_H4 > EMA200_H4` AND `EMA50_H4[t] > EMA50_H4[t−3 bars]` (3 completed
  H4 bars earlier in series). SHORT: exact inverse
  (`EMA50_H4 < EMA200_H4` AND falling).
- **H1 pullback LONG** (evaluated at H1 close, using the latest COMPLETED H4
  bar for the regime): within a valid LONG regime,
  `LOW <= EMA20_H1` AND `CLOSE > EMA20_H1` AND `CLOSE > EMA50_H1`.
  SHORT: mirror (`HIGH >= EMA20_H1` AND `CLOSE < EMA20_H1` AND
  `CLOSE < EMA50_H1`).
- **M15 continuation:** after the pullback H1 bar closes, observe the next at
  most 4 completed M15 bars in series. LONG trigger: first M15 bar whose
  `CLOSE > HIGH of the M15 bar immediately preceding it`. SHORT: first M15
  `CLOSE < previous M15 LOW`. If none within 4 completed M15 bars, the setup
  expires. If a NEW pullback completes before a trigger, it replaces the
  active setup (stop recomputed from the new pullback bar).
- **Entry:** 250ms after the trigger M15 close, executable side.
- **Stop:** LONG = LOW of the H1 pullback bar; SHORT = HIGH of the pullback
  bar. If the stop is not beyond the entry in the correct direction, the
  trade is INVALID (counted `INVALID_STOP`, not a trade).
- **Target:** 2.0R from the executed entry
  (LONG: `entry + 2·(entry − stop)`; SHORT mirror).
- **Time exit:** 24h after entry.
- One open A-position at a time; new A signals ignored while open.

## 6. Strategy B — `MTF_B_TREND_BREAKOUT`

- Same H4 regime as A (evaluated at H1 close vs latest completed H4).
- LONG signal on completed H1: `CLOSE > max(HIGH of previous 20 completed H1
  bars)` (the signal bar is NOT in the reference window). SHORT mirror
  (`CLOSE < min(LOW of previous 20)`).
- Entry 250ms after the H1 signal close.
- Stop = `entry − 1.5·ATR14_H1` (LONG) / `entry + 1.5·ATR14_H1` (SHORT),
  ATR at signal close. Same INVALID_STOP rule.
- Target 2.0R from executed entry. Time exit 48h. One open B-position.

## 7. Strategy C — `MTF_C_RANGE_REVERSION`

- **Range regime:** latest completed H4 bar has `ADX14_H4 < 20`
  (evaluated at H1 close). No direction regime.
- LONG signal on completed H1: `LOW < lowerBB(20,2)` AND
  `CLOSE > lowerBB`. SHORT: `HIGH > upperBB` AND `CLOSE < upperBB`
  (Bollinger of the signal bar, 20 completed H1 closes including it).
- Entry 250ms after H1 signal close.
- Stop = `entry − 1.0·ATR14_H1` (LONG) / `entry + 1.0·ATR14_H1` (SHORT).
  Same INVALID_STOP rule.
- **Target = SMA20_H1 (Bollinger midline) frozen at signal close.**
  If the target is already crossed by the entry fill (LONG: `ask_entry >=
  target`; SHORT: `bid_entry <= target`) → **NO_TRADE** (counted).
- Time exit 12h. One open C-position.

## 8. Tick stop/target execution (frozen)

After entry, every subsequent tick is evaluated in chronological order; the
FIRST event wins.

- LONG: STOP when `BID <= stop` → fill at that BID. TARGET when
  `BID >= target` → fill at the TARGET (favorable overshoot capped).
- SHORT: STOP when `ASK >= stop` → fill at that ASK. TARGET when
  `ASK <= target` → fill at the TARGET (capped).
- If a GAP LIST interval begins while the position is open (gap onset strictly
  after entry fill and strictly before the otherwise-resolving tick), the
  trade is **DATA_GAP_INVALID**: no path is invented, the trade is excluded
  from all main metrics, and only counted.
- Time exits: first executable tick at/after the frozen time-exit timestamp,
  at BID (LONG) / ASK (SHORT), no capping.
- `net_pips(LONG) = (exit_fill − entry_fill)/1e-4`;
  `net_pips(SHORT) = (entry_fill − exit_fill)/1e-4`.
- `gross_mid_pips = direction · (mid(exit tick) − mid(entry tick))/1e-4`.

## 9. No pyramid / money management

No pyramid, martingale, reverse, partial exits, trailing stop, break-even, or
dynamic sizing. Trades are measured in pips and R only.

## 10. Metrics (frozen, per strategy)

Over all trades excluding DATA_GAP_INVALID (which is only counted):

- N_TRADES; TRADES_PER_YEAR = N/9
- GROSS_MID_MOVE_PIPS = mean per-trade gross mid move
- NET_EXECUTABLE_MEAN_PIPS = mean net; MEDIAN_NET; TOTAL_NET_PIPS = sum
- STRESS_010_MEAN; STRESS_025_MEAN
- WIN_RATE (net > 0); AVG_WIN; AVG_LOSS; PROFIT_FACTOR =
  Σwins/|Σlosses| (inf if no losses); EXPECTANCY_R =
  mean(net / planned_risk_pips), planned risk = |entry − stop|
- MAX_DRAWDOWN_PIPS: peak-to-trough of cumulative net in chronological entry
  order; MAX_CONSECUTIVE_LOSSES
- POSITIVE_YEARS: years (of entry fill) with TOTAL_NET_PIPS > 0, out of 9
- BY_YEAR: N, MEAN_NET, TOTAL_NET, PF
- REMOVE_BEST_1_PERCENT_NET_MEAN: remove the top `k = ceil(0.01·N)` trades by
  net, mean of the remainder
- CI95_MEAN_NET: percentile bootstrap, 2000 resamples, `numpy
  default_rng(42)`
- Exit counts: STOP, TARGET, TIME, DATA_GAP_INVALID (plus NO_FILL,
  NO_FILL_GAP, INVALID_STOP, SKIPPED_HARD_END setup counts)

## 11. Economic gate (frozen)

`MTF_DISCOVERY_PROMISING` requires ALL of:

- NET_EXECUTABLE_MEAN_PIPS ≥ +2.0
- PROFIT_FACTOR ≥ 1.20
- EXPECTANCY_R > +0.10
- POSITIVE_YEARS ≥ 6/9
- REMOVE_BEST_1_PERCENT_NET_MEAN > 0
- STRESS_010_MEAN > 0
- N_TRADES ≥ 150
- TOTAL_NET_PIPS > 0

CI95 is reported and informative.

## 12. Fail fast (frozen)

Per strategy, if `NET_MEAN <= 0` OR `PF <= 1.0` OR `REMOVE_BEST <= 0` →
**REJECT**. No tuning, no variants (no A2/B2/C2, no alternate EMAs/ATRs/
targets/ADX/BB/latency/pair). All three frozen strategies are still run;
nothing is rescued.

## 13. Scientific stop rule

All of A, B, C are run. Once each has produced one frozen verdict, the
mission STOPS. No fourth strategy, no rescue research.

## 14. Engine validation (required, synthetic)

Bar aggregation M15/H1/H4 · bar-close causality · EMA causality · ATR · ADX ·
Bollinger · 20-bar breakout excludes current bar · M15 trigger uses previous
completed M15 bar · 250ms latency · LONG-ASK entry · SHORT-BID entry ·
LONG-BID exit · SHORT-ASK exit · real spread charged once · stop execution ·
target execution (cap) · time exit · data-gap invalidation · 2019 cutoff.
Plus the existing TICK-M0 and TICK-M1 test suites must stay green.

## 15. Performance

Month-partitioned processing only; the full history is never held in RAM.
Bars are precomputed per month with causal overlap handling for gaps;
trade execution scans only the required tick ranges (no O(N²) scans).
32 GB machine.

## 16. Output

Non-merged PR + `MTF_M1_TICK_ACCURATE_DISCOVERY` block. Verdicts:
`MTF_DISCOVERY_PROMISING` / `REJECT`. If none pass → `NO_MTF_CANDIDATE`;
if ≥1 passes → `STOP_FOR_HUMAN_REVIEW`. DO NOT MERGE.
