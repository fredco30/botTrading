# RATES-LAG-M0 — FROZEN SPEC

**Mission:** Retail-feasible Treasury → EURUSD lead/lag screen (NFP + CPI only).
**Parent:** `968a0e48b19fb6cea3e64d42bf6016f0fcf08d5a` (branch `research/rates-event-hires-m1`).
**Status:** This file is committed BEFORE any EURUSD outcome is computed. No optimizer, no
parameter grid, no ML, no threshold rescue. Every decision constant below is frozen.

---

## 1 — Objective

Determine whether the Treasury-futures reaction to NFP/CPI leaves an economically
meaningful EURUSD move that is STILL exploitable at realistic non-HFT delays.
This is explicitly NOT an HFT project. An edge that exists only at 100 ms / 500 ms /
1 s / 2 s does not qualify. Exactly three frozen decision horizons are screened:

| Screen | Name           | Decision time      |
|--------|----------------|--------------------|
| A      | RATES_LAG_H10  | T0 + 10 seconds    |
| B      | RATES_LAG_H30  | T0 + 30 seconds    |
| C      | RATES_LAG_H60  | T0 + 60 seconds    |

A result existing only at H10 is NOT sufficient for promotion.

## 2 — Event universe

Only the RATES-EVENT-HIRES-M1 validated manifest
(`E:\ResearchData\botTrading\rates\databento_event_tbbo\manifests\manifest.json`).
NFP and CPI only. An event enters the universe iff BOTH its `ZF` and `ZN` manifest
entries have `status == "ok"`. Excluded statuses: `EXPECTED_MARKET_CLOSED`,
`CONFIRMED_DATA_GAP`, `zero_records` (any symbol), `ROLL_WINDOW_INVALID`.
Missing events are NOT repaired. Expected maximum 200 events.
Discovery window: `2010-06-07 inclusive → 2019-01-01 exclusive`.
2019+ is FORBIDDEN. Protected OOS is FORBIDDEN (hard guards in code, tested).

## 3 — Timestamp source

Treasury `ts_recv` (int64 ns, UTC) is the primary timing field for ALL rate-side
selection (PRE and horizon windows), per RATES-EVENT-HIRES-M1: pre-2017
`ts_event == ts_recv` at ms precision; 2017+ has independent ns fields.
No sub-ms precision is manufactured for pre-2017. All decision horizons are
>= 10 s, so this is safe. Data hygiene: TBBO records with `ts_recv` before the
M1 window start (T0 − 5 min) are dropped (M1 `boundary_batch_records` recommendation).

## 4 — Treasury price reference

For each of ZF and ZN, from the event's raw-contract TBBO parquet
(`bid_px_00`, `ask_px_00`, decoded Databento double price — no hard-coded scaling):

- `RATE_MID = (best_bid + best_ask) / 2`. A record is VALID iff both bid and ask
  are finite and > 0. Records failing this are skipped (never interpolated).
- `PRE_RATE_MID` = RATE_MID of the last valid record with `ts_recv < T0` (strictly).
- `RATE_MID_H` = RATE_MID of the LAST valid record with
  `T0 <= ts_recv <= T0 + H`. The window must contain >= 1 valid observation.
  If not: `HORIZON_UNAVAILABLE` for that symbol/horizon → no rate signal at H.
  H10/H30/H60 are separate causal screens: H10 selection never sees records
  beyond T0+10 s, etc. The H60 move never influences H10/H30 decisions.

## 5 — Minimum meaningful rate move

The minimum price increment (tick) for each raw contract (e.g. `ZFZ4`, `ZNZ4`) is
resolved from authoritative Databento **instrument definitions** (`definition`
schema, field `min_price_increment`), fetched once per distinct raw contract and
cached in-repo as `instrument_tick_sizes.json` (tiny JSON, no bulk data).
A cross-check against data-derived minimum abs mid delta is reported but is
diagnostic only. For each horizon H:

- `ZF_MOVE = ZF_RATE_MID_H − ZF_PRE_RATE_MID`
- `ZN_MOVE = ZN_RATE_MID_H − ZN_PRE_RATE_MID`

A **rate signal** exists iff ALL hold:

1. `ZF_MOVE` and `ZN_MOVE` have the SAME non-zero sign;
2. `|ZF_MOVE| >= ZF_tick`;
3. `|ZN_MOVE| >= ZN_tick`.

The one-tick floor is a micro-noise guard. No 2/3/4-tick sweep exists.

## 6 — Economic direction (frozen mapping)

Treasury futures UP → yields DOWN → USD weaker → **EURUSD LONG**.
Treasury futures DOWN → yields UP → USD stronger → **EURUSD SHORT**.
The mapping is never reversed after seeing results.

## 7 — Three frozen screens

`A = RATES_LAG_H10 (T0+10s)`, `B = RATES_LAG_H30 (T0+30s)`,
`C = RATES_LAG_H60 (T0+60s)`. Eligibility at each horizon is determined ONLY from
Treasury information available by that horizon (section 4). Each horizon is a
separate causal screen.

## 8 — Realistic EURUSD entry (non-HFT baseline)

EURUSD data: validated tick store `E:\ResearchData\botTrading\ticks\parquet\EURUSD`
(bid/ask, int64 ns UTC). 1 pip = 1e-4.

- BASELINE execution delay: `decision + 1.0 s`.
- LONG: first **ASK** tick with `ts >= decision + 1.0 s`.
- SHORT: first **BID** tick with `ts >= decision + 1.0 s`.
- Fill bound: if no executable quote exists in
  `[decision+delay, decision+delay+10.0 s]` → `NO_FILL` (trade excluded from N;
  counted and reported).
- The real historical spread is charged automatically (bid/ask side selection).
  No midpoint entry.

## 9 — Slow execution stress

Same signal, same side selection, delay `decision + 5.0 s` instead of +1.0 s,
fill bound still 10 s, exit still entry+120 s. Called `LATENCY_5S`.
The signal is NEVER changed.

## 10 — Exit (frozen)

Frozen exit: **120 seconds after ACTUAL entry**.

- LONG: first BID tick with `ts >= entry_ts + 120 s`.
- SHORT: first ASK tick with `ts >= entry_ts + 120 s`.

No stop, no target, no trailing, no breakeven, no pyramid. If no exit quote exists
within `[entry+120 s, entry+180 s]` (never expected intraday), the trade is marked
`EXIT_UNAVAILABLE` and excluded from N (counted).
Diagnostic mark-to-market returns are additionally reported at entry+30 s / +60 s /
+300 s, using the same side selector (LONG→bid, SHORT→ask, first tick at/after the
mark time). Diagnostics NEVER determine the primary verdict.
**PRIMARY VERDICT: 120-second exit only.**

## 11 — Additional cost stress

- `SLIPPAGE_050` = baseline net − 0.50 pip per side (= −1.00 pip total).
- `SLIPPAGE_100` = baseline net − 1.00 pip per side (= −2.00 pips total).
- `REALISTIC_STRESS` = LATENCY_5S net − 0.50 pip per side (= −1.00 pip total).
  This is the primary economic stress: real spread + slow path + adverse slippage.

## 12 — Metrics (per horizon, baseline path unless stated)

`EVENTS_AVAILABLE`, `RATE_SIGNALS`, `N_TRADES`, `NO_FILL`, `NFP_N`, `CPI_N`,
`NET_MEAN_PIPS`, `MEDIAN_NET_PIPS`, `TOTAL_NET_PIPS`, `WIN_RATE`, `AVG_WIN`,
`AVG_LOSS`, `PROFIT_FACTOR`, `POSITIVE_YEARS`, `YEARS_ELIGIBLE`,
`REMOVE_BEST_1_PERCENT_NET_MEAN`, `LATENCY_5S_MEAN`, `SLIPPAGE_050_MEAN`,
`SLIPPAGE_100_MEAN`, `REALISTIC_STRESS_MEAN`, `NFP_MEAN`, `NFP_PF`, `CPI_MEAN`,
`CPI_PF`, `BOOTSTRAP_CI95_MEAN`, and diagnostic mean MTM at +30 s/+60 s/+300 s.

Frozen definitions:

- Year buckets are calendar years UTC of ENTRY time (2010 … 2018).
  `YEARS_ELIGIBLE` = years with >= 1 trade. `POSITIVE_YEARS` = years whose trade
  net-pip sum > 0.
- `PROFIT_FACTOR` = sum(winning nets) / |sum(losing nets)|; if there are no losing
  trades it is capped and reported as `999.0` (documented sentinel).
- `REMOVE_BEST_1_PERCENT_NET_MEAN`: k = max(1, ceil(0.01 · N)) best trades (by net
  pips) removed; mean recomputed on the remaining N − k trades.
- `BOOTSTRAP_CI95_MEAN`: 2000 resamples with replacement of the N trade nets,
  `numpy.random.default_rng(42)`, percentile method (2.5 / 97.5). Frozen seed.

## 13 — Signal stability diagnostic (diagnostic only)

Over events where BOTH horizons of a pair have signals:
`H10_TO_H30_SAME_DIRECTION_PCT`, `H30_TO_H60_SAME_DIRECTION_PCT`,
`H10_TO_H60_SAME_DIRECTION_PCT`, plus per-horizon signal counts.
Diagnostic only — no strategy variant may be derived from it.

## 14 — Economic screen gate

A horizon is an `ECONOMIC_CANDIDATE` iff ALL of:

| Condition | Threshold |
|---|---|
| N_TRADES | >= 50 |
| NET_MEAN_PIPS | >= +2.0 |
| PROFIT_FACTOR | >= 1.20 |
| TOTAL_NET_PIPS | > 0 |
| POSITIVE_YEARS / YEARS_ELIGIBLE | >= 0.67 |
| REMOVE_BEST_1_PERCENT_NET_MEAN | > 0 |
| LATENCY_5S_MEAN | > 0 |
| REALISTIC_STRESS_MEAN | > 0 |
| NFP_MEAN | > 0 |
| CPI_MEAN | > 0 |

CI95 is reported; lower bound > 0 is diagnostic, not mandatory at Discovery.

## 15 — Real-world feasibility rule

- If H30 or H60 is an ECONOMIC_CANDIDATE → `RETAIL_FEASIBLE_CANDIDATE=YES`,
  `FINAL_STATUS=RETAIL_FEASIBLE_CANDIDATE`, STOP_FOR_HUMAN_REVIEW.
- If ONLY H10 passes while H30 and H60 fail → `RETAIL_FEASIBLE_CANDIDATE=NO`,
  `FINAL_STATUS=TOO_FAST_FOR_PROJECT`, STOP. No faster-entry variants allowed.
- If none pass → `FINAL_STATUS=NO_RETAIL_RATES_LAG_CANDIDATE`, STOP.

## 16 — No money-management rescue

Forbidden: stop optimization, TP optimization, pyramiding, martingale, averaging,
partials, trailing, reverse-on-stop, dynamic leverage. If the directional residual
is not economically meaningful, the mechanism is rejected.

## 17 — NFP / CPI robustness

A pooled positive result is insufficient. Both `NFP_MEAN > 0` AND `CPI_MEAN > 0`
are required (already in the gate). No family cherry-picking after results.

## 18 — Tests

Synthetic (no network, no E: dependency): ts_recv selection; PRE_RATE_MID
causality; H10/H30/H60 access bounds; valid-BBO midpoint; minimum-increment guard;
ZF/ZN same-sign; rate-UP→LONG / rate-DOWN→SHORT mapping; 1 s entry delay; 5 s
latency stress; LONG ask-entry/bid-exit and SHORT bid-entry/ask-exit; 120 s exit;
real-spread arithmetic; slippage stress; NO_FILL; 2019 cutoff; protected-OOS guard.
Plus the 9 RATES-EVENT-HIRES-M1 local tests are run. If practical, both suites are
wired into `research-engine-tests` CI; CI coverage is claimed ONLY if the actual
GitHub workflow executes them.

## 19 — Audit / token discipline

All three horizons run first. If all three clearly fail the gate → STOP after
basic sanity checks (no large secondary audit of a dead result). If any horizon
passes or comes materially close → independent implementation audit of >= 30
trades for that horizon, re-deriving rate direction, Treasury timestamp, EURUSD
entry side/time/price, exit side/time/price, and net pips with independent code.

## 20 — Git

Branch `research/rates-lag-m0`; PR base `research/rates-event-hires-m1`; PR NOT
merged; PR #37 NOT merged. No bulk TBBO or EURUSD data in git.

## 21 — Governance constants

- `PIP = 1e-4` (EURUSD).
- All timestamps int64 ns UTC; windows CLOSED on both ends where stated
  (`T0 <= ts <= T0+H`); PRE window open (`ts < T0`).
- Entry/exit/mark selection uses `>=` (first tick at or after the reference time).
- Determinism: single-threaded event loop, sorted arrays, frozen seed for bootstrap.
