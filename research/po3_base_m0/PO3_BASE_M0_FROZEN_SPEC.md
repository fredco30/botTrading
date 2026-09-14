# PO3-BASE-M0 — FROZEN SPEC

**Mission:** One minimal, deterministic PO3 / session-liquidity hypothesis on EURUSD:
Asia range → London liquidity sweep → quick reintegration → reversal trade → 2R target.
This is NOT a test of ICT terminology. No FVG / OB / breaker / BPR / MSS / HTF bias /
EMA / ATR / news filter / optimizer / parameter grid. The RAW SESSION PHENOMENON only.

**Status:** This file is committed BEFORE any EURUSD outcome is computed. Every decision
constant below is frozen. No parameter changes after outcomes are visible.

**Parent:** `1ff680a` (branch `main`). Research branch: `research/po3-base-m0`.

---

## 1 — Data (frozen manifest)

Store: `E:\ResearchData\botTrading\ticks\parquet\EURUSD` (validated Dukascopy BID/ASK,
int64 ns UTC, columns `timestamp_utc, bid, ask, mid, spread_pips, bid_volume, ask_volume`).
`mid` is recomputed as `(bid+ask)/2` and must equal the stored `mid` (asserted on load of
the first partition of each run).

- 108 monthly partitions, `year=2010..2018`, 209,682,628 ticks total.
- Per-partition SHA256, byte size, row count and exact first/last timestamp are recorded
  in `data_manifest.json` (committed in the SAME commit as this spec, BEFORE outcomes).
- The runner re-verifies each partition's SHA256 lazily before first use and aborts on
  mismatch (manifest is the freeze reference).
- Quote validity (frozen): ticks with non-finite or `<= 0` bid/ask are DROPPED from the
  book for ALL uses (signal and execution). No other cleaning. Crossed quotes (bid>ask)
  are kept as-is.
- Discovery window: **2010-01-04 .. 2018-12-31 inclusive** (Europe/London dates).
- HARD GUARDS (tested): any requested UTC range must lie inside
  `[2010-01-01T00:00:00Z, 2019-01-01T00:00:00Z)`; any partition path with `year >= 2019`
  is refused. 2019+ is FORBIDDEN. Protected OOS is FORBIDDEN. No new data downloads.

## 2 — Timezone

- All session definitions use **Europe/London** via the real IANA database
  (`zoneinfo.ZoneInfo`; `tzdata` fallback package). DST handled automatically; no
  hard-coded UTC offset anywhere in the pipeline (tested across BST/GMT).
- All internal market timestamps remain int64 nanoseconds UTC.
- A trading day D spans these frozen London wall-clock instants (converted to UTC per
  current DST): Asia `[00:00,07:00)`, London observation `[07:00,10:00)`,
  time exit `12:00`. Day data slice for the engine: `[D 00:00, D 12:36]` London.

## 3 — Trading day and eligibility (frozen)

A day D (Mon–Fri Europe/London, `2010-01-04 <= D <= 2018-12-31`) is ELIGIBLE iff:

1. Asian coverage: with the session boundaries `[D 00:00, D 07:00)` London padded as
   virtual ticks, `n_ticks_asia >= 3600` AND max inter-tick gap (including both boundary
   pads) `<= 300 s`;
2. `AsianRange > 0`.

No ATR/compression qualification. Nothing else.

## 4 — Asian range (frozen)

From MID ticks in `[D 00:00, D 07:00)` London (start inclusive, end exclusive):

- `AsianHigh = max(MID)`, `AsianLow = min(MID)`, `AsianRange = AsianHigh − AsianLow`.

## 5 — London observation window (frozen)

Setup observation only during `[07:00, 10:00)` London. After 10:00 NO NEW SETUP for that
day (an in-progress setup still completes per §7–§8; its reintegration may extend up to
`sweep_ts + 15 min <= 10:15`). Maximum ONE trade per day.

## 6 — Sweep (frozen)

`SWEEP_MIN = 0.20 × AsianRange`.
`upper_thr = AsianHigh + SWEEP_MIN`, `lower_thr = AsianLow − SWEEP_MIN`.

Scanning MID ticks chronologically in `[07:00,10:00)` London: the FIRST tick with
`MID >= upper_thr` (upper sweep) or `MID <= lower_thr` (lower sweep) is THE sweep of the
day; `sweep_ts` = that tick's timestamp; side recorded. A tick exactly at a threshold
counts (`>=` / `<=`). No sweep in the window → eligible day without setup.

## 7 — Reintegration (frozen)

M1 MID candles: bucket `[T, T+60s)`; a bucket with `>= 1` MID tick is a candle;
`close` = last MID of the bucket; `close_ts = T+60s` (bucket end, frozen — not the last
tick time). Empty buckets produce no candle. Causality: a candle completing at
`close_ts` is decided BEFORE any tick with `ts >= close_ts` (frozen tie rule).

After the sweep, the FIRST candle with all of:

- `bucket_start >= bucket_start(sweep_ts)` (the sweep's own candle may qualify),
- `close_ts <= sweep_ts + 900 s` (inclusive),
- upper sweep: `close < AsianHigh`; lower sweep: `close > AsianLow` (strict),

defines `decision_ts = close_ts`. Otherwise:

- no qualifying candle → `NO_REINTEGRATION` (day ends, no trade);
- the OPPOSITE threshold is crossed by any tick `sweep_ts < ts <= decision_ts` (i.e.
  before the decision event, with candle completion preceding same-timestamp ticks)
  → `DOUBLE_SWEEP_INVALID` (day ends, no trade).

Counter order is chronological by event: candle completions and tick crossings are
processed in time order; a candle completing at time T precedes ticks at `ts >= T`.

## 8 — Direction, decision, extreme (frozen)

- Upper sweep + reintegration → **SHORT**; lower sweep + reintegration → **LONG**.
- Stop extreme (frozen level, MID-based):
  SHORT: `stop = max(MID)` over ticks `sweep_ts <= ts <= decision_ts`;
  LONG: `stop = min(MID)` over the same interval.
  No tick after `decision_ts` may influence the stop (tested).

## 9 — Entry (frozen)

- Baseline delay: `ref = decision_ts + 5 s`. LONG: first **ASK** tick with
  `ts >= ref`; SHORT: first **BID** tick with `ts >= ref`.
- Fill bound: executable tick must satisfy `ts <= ref + 30 s`, else `NO_FILL`.
- Real historical spread is paid (entry on the executed side of the book).

## 10 — Risk and target (frozen)

- `R = |entry_price − stop|` (entry = executed baseline price).
- `INVALID_RISK` (no trade) iff LONG `entry_ask <= stop` or SHORT `entry_bid >= stop`.
- Target: LONG `entry + 2R`; SHORT `entry − 2R`. Frozen 2.0R. No alternative targets.

## 11 — Exit resolution (frozen, tick-accurate)

Scan chronologically from the entry tick (inclusive):

- STOP event: LONG first tick with `BID <= stop`; SHORT first with `ASK >= stop`
  → exit at that tick's actual executable price (gap-through fills at the worse real
  price; no retroactive stop-level fill).
- TARGET event: LONG first with `BID >= target`; SHORT first with `ASK <= target`
  → exit **capped at the target price** even if the tick passed beyond it.
- TIME exit: first tick with `ts >= 12:00` London → exit at its executable price
  (LONG BID / SHORT ASK); a tick must exist within `[12:00, 12:01)` London else
  `NO_TIME_EXIT_DATA` (day excluded from trades, counted).
- Earliest event index wins; if ONE tick satisfies both STOP and TARGET, **STOP wins**
  (pessimistic, frozen). The entry tick itself participates in the scan (handles an
  instant adverse gap at entry).
- No overnight positions (time exit is same-day by construction).

## 12 — Execution scenarios (frozen)

The signal (side, stop level, decision_ts) NEVER changes between scenarios.

- **BASELINE**: delay 5 s (§9).
- **LATENCY_30S**: `ref = decision_ts + 30 s`, same 30 s fill bound. Stop level
  unchanged. `R_lat = |entry30 − stop|`; `INVALID_RISK` re-checked against entry30;
  target `entry30 ± 2·R_lat`; exits re-scanned from the latency entry tick. Trades that
  fill under this scenario form the latency sample.
- **SLIPPAGE_050**: pure cost on the baseline trade: `net_R = (net_pips_base − 1.0) /
  R_base` (0.50 pip adverse per side × 2 sides).
- **REALISTIC_STRESS**: latency execution plus pure cost:
  `net_R = (net_pips_lat − 1.0) / R_lat` over the latency sample.

## 13 — Metrics (frozen)

Per trade: `r_mult = net_pips_base / R_base` (`net_pips` from executed side prices,
`1 pip = 1e-4`). Definitions:

- `WIN_RATE` = #(net_pips > 0)/N.
- `PROFIT_FACTOR` = Σwins / |Σlosses| on net_pips; if no losses, sentinel 999.0.
- `EXPECTANCY_R` = mean(r_mult). `AVG_WIN_R`/`AVG_LOSS_R` on r_mult.
- `MAX_DRAWDOWN_R`: trades ordered by entry_ts, max peak-to-trough of cumsum(r_mult).
- `MAX_CONSECUTIVE_LOSSES`: longest run of net_pips < 0 (wins > 0).
- `POSITIVE_YEARS` / `YEARS_ELIGIBLE`: UTC calendar year of entry_ts; a year counts as
  eligible if it has >= 1 trade; positive if its net_pips sum > 0.
- `REMOVE_BEST_1_PERCENT_MEAN_R`: drop k = max(1, ceil(0.01·N)) best r_mult, mean rest.
- `BOOTSTRAP_CI95_EXPECTANCY_R`: percentile [2.5, 97.5] of resampled mean of r_mult,
  2000 resamples, seed 42.
- `TRADES_PER_YEAR = N/9.0`; `TRADES_PER_MONTH = N/108.0`.
- Long/short split: N, expectancy_R per direction (baseline).

## 14 — Diagnostics (descriptive ONLY; never alter the verdict)

- Median `AsianRange` pips (eligible days).
- Median sweep extension beyond the swept boundary, in AsianRange units:
  upper `(extreme − AsianHigh)/AsianRange`; lower `(AsianLow − extreme)/AsianRange`
  (all first-sweep days).
- Median time 07:00 → sweep_ts (sweep days); median sweep_ts → decision_ts minutes
  (reintegrated setups).
- MFE in R after entry over 30/60/120 min: best reachable exit-side price
  (LONG max BID, SHORT min ASK) in `[entry_ts, entry_ts + X]`, `(px − entry)/R`
  signed by direction; NaN when no tick in window (excluded from the mean).
- `P(reach +1R / +1.5R / +2R before stop)` over executed baseline trades: first STOP
  event vs first tick reaching `entry ± k·R` on the exit side, scanned to the 12:00
  London time-exit tick; tie → stop (pessimistic, consistent with §11).
- 1R and 1.5R are diagnostics ONLY. No alternative strategy may be derived from them.

## 15 — Economic pass gate (frozen)

PO3_BASE qualifies as a genuine candidate only if ALL:

- `N_TRADES >= 200`
- `EXPECTANCY_R >= +0.10`
- `PROFIT_FACTOR >= 1.20`
- `TOTAL_NET_PIPS > 0`
- `POSITIVE_YEARS / YEARS_ELIGIBLE >= 0.67`
- `REMOVE_BEST_1_PERCENT_MEAN_R > 0`
- `LATENCY_30S_EXPECTANCY_R > 0`
- `REALISTIC_STRESS_EXPECTANCY_R > 0`
- `LONG_EXPECTANCY_R > 0`
- `SHORT_EXPECTANCY_R > 0`

Bootstrap CI95 is reported but is not an automatic gate.

## 16 — Interpretation (frozen)

- A) gate passes → `PO3_BASE_CANDIDATE` — STOP FOR HUMAN REVIEW (no MSS/FVG/OB added).
- B) baseline positive but gate missed → `PO3_BASE_WEAK_PHENOMENON` — STOP.
- C) expectancy <= 0 or PF <= 1 or realistic stress clearly destroys the result
  → `PO3_BASE_NO_EDGE` — STOP. No ICT rescue.

## 17 — Fail-fast (frozen)

If PO3_BASE clearly fails: NO sweep-threshold sweep (10/15/25/35/50%), no different Asia
hours, no different London windows, no different reintegration delays, no different stop
rules, no 1R/1.5R promotion, no HTF bias / MSS / FVG / OB / BPR. One frozen test = one
hypothesis.

## 18 — Audit plan (frozen)

- Clearly negative: only enough independent verification to exclude a coding error
  (spot re-derivation of day classification counts + a handful of trades), then STOP.
- Passes or materially close: independently re-derive >= 40 trades (separate audit
  implementation, event-loop re-walk) verifying AsianHigh/Low/Range, sweep side,
  threshold timestamp, extreme, reintegration candle, decision_ts, direction, entry
  side/time/price, stop, target, exit, R result.

## 19 — Tests (frozen list)

Synthetic (deterministic tick arrays, no real data): London DST handling (BST/GMT, no
hard-coded offset); Asia boundaries (00:00 inclusive / 07:00 exclusive); 07:00 inclusion;
10:00 exclusion; upper threshold (`>=` exact); lower threshold (`<=` exact); 15-minute
reintegration boundary (inclusive); double-sweep invalidation; completed-M1 causality
(bucket-end close timestamp; tick at bucket_end belongs to next bucket); no future
extreme in stop; 5 s entry delay; 30 s stress delay; NO_FILL bound; LONG ask entry;
SHORT bid entry; stop execution side; stop gap-through; target cap; stop-priority tie;
12:00 time exit; INVALID_RISK; eligibility coverage rule; 2019 cutoff; protected-OOS
guard; metrics (remove-best, bootstrap determinism, PF sentinel, DD, streaks); scenario
cost formulas. Relevant existing tick-execution suites (rates-lag-m0 branch) are re-run
on their branch to confirm shared store assumptions. CI must actually execute the new
suite (workflow step added) or CI may not be claimed.

## 20 — Constants table (single source of truth)

| Constant | Value |
|---|---|
| PIP | 1e-4 |
| ASIA_START / ASIA_END | 00:00 / 07:00 London (start incl., end excl.) |
| OBS_START / OBS_END | 07:00 / 10:00 London (start incl., end excl.) |
| SWEEP_MIN | 0.20 × AsianRange |
| REINTEGRATION_LIMIT_S | 900 |
| M1_BUCKET_S | 60 |
| ENTRY_DELAY_BASE_S | 5.0 |
| ENTRY_DELAY_STRESS_S | 30.0 |
| FILL_BOUND_S | 30.0 |
| TIME_EXIT | 12:00 London, quote bound 60 s |
| TARGET_R | 2.0 |
| SLIP_PER_SIDE_PIPS | 0.50 |
| MIN_ASIA_TICKS / MAX_ASIA_GAP_S | 3600 / 300 |
| DAY_SLICE_END | 12:36 London |
| BOOTSTRAP | 2000 resamples, seed 42 |
| PF sentinel | 999.0 |
| UTC data guard | [2010-01-01T00:00Z, 2019-01-01T00:00Z) |
| Discovery dates (London) | 2010-01-04 .. 2018-12-31 inclusive |
