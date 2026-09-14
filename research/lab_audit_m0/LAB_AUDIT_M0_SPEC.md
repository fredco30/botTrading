# LAB_AUDIT_M0 — FROZEN SPECIFICATION

Status: **FROZEN BEFORE EXECUTION** (this commit contains expected results only; no control has been run).
Mission: meta-validation of the backtest laboratory (positive/negative controls). NO strategy research, NO optimization, NO 2019+ data, NO protected OOS.
BASE_HEAD: `21cac5f05e454bbd7a2ef892dc5c3a23cd14bce1` (tip of research/legacy-reverse-m1).
Branch: `research/lab-audit-m0`. No merge. No modification of any historical strategy result.

## 1. Scope and data

- Real tick data: ONLY `E:\ResearchData\botTrading\ticks\parquet\EURUSD` (Dukascopy BID/ASK store, 108 monthly partitions, validated). Real-data controls restricted to 2010-01-04 .. 2018-12-31 inclusive. The 2019+ guard (`po3_base_m0_lib.UTC_GUARD_END_NS = 2019-01-01Z`) must hold for every code path exercised.
- Synthetic controls: fully synthetic BID/ASK streams constructed in-process; no external market data; deterministic seed 42.
- No bulk market data enters git; only small synthetic fixtures and small result JSON/CSV artifacts.

## 2. Conventions (binding for all controls)

- PIP = 1e-4 (EURUSD). R unit = 10.0 pips where an R unit is needed (synthetic controls).
- Timestamps: int64 nanoseconds UTC. Wall-clock session times via IANA `Europe/London`.
- Execution semantics tested = the production pipeline semantics:
  - PO3 `execute()` (research/po3_base_m0/po3_base_m0_lib.py:258): entry at first tick >= decision+delay (fill bound 30 s, else NO_FILL); LONG entry ASK, LONG exits (stop/target/time) on BID; SHORT mirrored on BID/ASK; stop = touch, fills at exit-side tick price with adverse gap recorded; target fills exactly at target (favorable overshoot capped); time exit at first tick in [time_exit, time_exit+60 s) else NO_TIME_EXIT_DATA; same-tick event priority stop(0) > target(1) > time(2).
  - LEGACY `simulate()`/`_exit_scan()` (research/legacy_reverse_m1/legacy_reverse_m1_lib.py): levels built from the UNSLIPPED executable fill price; slippage applied adversely per side (entry fill; STOP and window-end exits; TARGET exact); optional breakeven: favorable move of 1.5R moves SL to entry ± 1 pip (entry = unslipped ref price); r = |ref_px − sl| (unslipped); net measured on effective (slipped) prices.
- Metrics semantics tested = PO3 metrics (po3_base_m0_lib.py:365-417): PF with zero losses → cap 999.0; zero wins → 0.0; expectancy in R = net_pips / risk_pips; bootstrap CI95 = percentile bootstrap, 2000 resamples, seed 42; max drawdown on cumsum of R vs running peak; `positive_years` on entry-year sums; `remove_best_1pct_mean` removes k = max(1, ceil(0.01n)) best trades.

## 3. Controls A/B/C — synthetic stream construction (shared, frozen)

Deterministic generator (seed 42, `np.random.default_rng(42)`), built in this exact order so the stream is reproducible:

1. Tick cadence: one tick every 5 s. Trades are non-overlapping, one per 2-hour window: decision at window start T_i = i·7200 s, entry reference T_i+5 s, exit reference T_i+3900 s (65 min). Trade i occupies ticks [T_i, T_i+3900 s]; 5 s cadence ⇒ 781 ticks per window.
2. Mid path per trade: mid starts at m0, ends exactly at m1 = m0 + Δ_i at the exit tick, linear interpolation in between plus a seeded zero-mean wiggle of amplitude ≤ 0.5 pip that decays linearly to 0 at the window end (so the exit-tick mid is exactly m1). Next trade's m0 = previous m1 (continuous path).
3. Explicit spread: bid = mid − 0.25 pip, ask = mid + 0.25 pip (full spread S = 0.5 pip).
4. Direction d_i = ±1 drawn from the seeded RNG (~50/50). Outcome designation: winner with probability p (seeded Bernoulli). If winner, the mid displacement is FAVORABLE by +10.0 pips (Δ_i = +10 pips for long, −10 for short); if loser, UNFAVORABLE by 10.0 pips. No stop, no target: stop is placed 200 pips away (can never be touched; target consequently ≥ 390 pips away, never touched) — every synthetic trade exits TIME at T_i+3900 s exactly.
5. Cost model (frozen): baseline execution = PO3 `execute()` unmodified (cost = explicit spread). Deterministic slippage of 0.15 pip per side is applied adversely at the entry fill and at the TIME-exit fill by a thin audit wrapper (mirrors the production stress convention: non-target exits slipped). Total deterministic cost = 0.8 pip/trade.
6. Expectancy is reported in the frozen unit R = 10 pips. The pipeline's internal r (~200 pips) is a bypass artifact, not the R unit.

### Analytical expectations (computed BEFORE execution)

For p = P(winner), gross (mid-to-mid) EV = (2p − 1) × 10 pips; net EV = gross − 0.8 pips. Per-trade outcome is exactly ±1 R gross (sampling noise only from designation draws; SD = 1 R exactly, SE = 1/√N R).

| Control | N | p | gross EV | **net EV (pre-registered)** | SE |
|---|---|---|---|---|---|
| A | 1000 | 0.65 | +0.30 R (+3.0 pips) | **+2.2 pips = +0.22 R** | 0.0316 R |
| B | 1000 | 0.35 | −0.30 R (−3.0 pips) | **−3.8 pips = −0.38 R** | 0.0316 R |
| C | 5000 | 0.50 | 0 (0.0 pips) | **−0.8 pips = −0.08 R** (pure cost drag) | 0.01414 R |

Expected PF: A ≈ (0.65·9.2)/(0.35·10.8) ≈ 1.58; B ≈ 0.63; C ≈ 0.91.
Expected win rate: A 65 %, B 35 %, C 50 %.

### PASS gates (frozen)

- A: sign positive; |est − 0.22 R| ≤ 0.08 R; PF > 1; bootstrap CI95 lower bound > 0 and CI contains 0.22 R.
- B: sign negative; |est + 0.38 R| ≤ 0.08 R; PF < 1; CI95 upper bound < 0.
- C: est < 0 (must NOT produce a material positive edge); |est + 0.08 R| ≤ 0.04 R (≈ 2.8 SE); PF < 1.
- Any A/B/C fail ⇒ LAB FAIL.

## 4. Control D — randomized real-market signals (frozen)

- Timestamps: one fixed timestamp per eligible trading day: 10:00:00 Europe/London, every Mon–Fri from 2010-01-04 to 2018-12-31 (`po3.discovery_dates()`); the SAME frozen timestamp list is used by D, E, F. A day is eligible if a fill tick exists within the 30 s fill bound and an exit tick within the 60 s exit bound; ineligible days are dropped identically for all randomizations and both oracles (drops are direction-independent by construction).
- Execution: real BID/ASK, 5 s entry delay, side-correct exit, NO artificial slippage (baseline). Holding horizon frozen: exit reference = decision + 65 min (fixed wall-clock), PO3 time-exit semantics.
- 100 independent direction randomizations, seeds declared NOW: perm i uses `np.random.default_rng(4200 + i)`, i = 0..99; direction d = +1 if `rng.integers(0, 2) == 1` else −1, drawn per eligible day in chronological order.
- Pre-registered expectation: per-trade expectancy centered on negative cost drag (≈ −average spread; the 2010–2018 10:00-London EURUSD spread is of order 0.5–1.5 pips), i.e. grand mean in [−2.0, 0.0] pips; spread of perm means ≈ ±0.5 pip (per-trade SD ~ 15–25 pips, ~2300 trades/perm).
- PASS gates: grand mean < 0; P95 of perm means ≤ +0.5 pips; number of perms with PF > 1.20 ≤ 15 (of 100). Report mean, median, P05, P95, #profitable, #PF>1.20.

## 5. Controls E/F — oracle lookahead and anti-oracle (frozen)

- Same frozen timestamps as D. ORACLE (explicitly named `oracle_lookahead_invalid_direction`, labeled ORACLE_LOOKAHEAD_INVALID, used by NO research code path): at each timestamp look 65 minutes ahead; materiality gate frozen at 3.0 pips: if |mid(exit-ref tick) − mid(entry-ref tick)| < 3.0 pips the day is skipped; else oracle direction = sign of that mid move. Execution then runs through the same baseline pipeline (5 s delay, real BID/ASK, side-correct exit, no slippage).
- E PASS gates: mean net pips > +5.0; PF > 2. (Expected: mean ≈ E[|60-min move| | ≥3 pips] − spread ≈ +15..+25 pips; losses possible only when 3 pips ≤ |move| < spread ⇒ near-zero; PF may hit the 999 cap — cap behavior itself is unit-tested in Control H.)
- F (anti-oracle, exact opposite direction, same days): PASS gates: mean net pips < −5.0; PF < 0.5. (Expected: mean ≈ −E[|move||≥3] − spread ≈ −15..−25 pips; expected PF = 0.0 — zero wins.)
- These controls prove the pipeline DISPLAYS strong edges when fed guaranteed information. If E is not strongly positive ⇒ LAB FAIL (execution/metric pipeline defect). If F is not strongly negative ⇒ directional symmetry defect.

## 6. Control G — execution unit test matrix (frozen)

Closed-form synthetic tick scenarios; every case hand-calculated in the script comments; automated result must match hand value within 1e-9 (price) / 1e-6 (pips/R). Cases:

1. LONG entry at ASK (1-pip spread; net −1.0 pip round trip at flat mid); 2. SHORT entry at BID (mirror); 3. LONG exit on BID / 4. SHORT exit on ASK at time exit; 5. target exact touch (LONG bid == target ⇒ fill exactly target, +2.0 R); 6. target overshoot (favorable overshoot capped at target); 7. stop exact touch (bid == stop ⇒ fill at stop, −1.0 R, gap 0); 8. stop gap-through (bid beyond stop ⇒ fill at tick price, gap recorded in pips); 9. same-tick event conflict: stop vs time-exit at the same tick index ⇒ stop wins (priority 0); target vs time at same index ⇒ target wins; entry-tick stop (stop hit at the fill tick itself). Note frozen: a same-index stop+target co-hit is geometrically impossible in this engine (one exit-side series; stop and target strictly on opposite sides of entry), so the priority tie-break for that pair is exercised indirectly via (idx, kind) ordering with artificial equal-index events if reachable — otherwise documented as unreachable.
10. latency: same scenario under delay = 30 s vs 5 s ⇒ different fill tick, both hand-calculated; 11. NO_FILL (no tick within [decision+delay, +30 s]); 12. time exit (first tick ≥ time_exit within 60 s); 13. time-exit quote bound: no tick in [time_exit, +60 s) ⇒ NO_TIME_EXIT_DATA; 14. slippage: audit wrapper (0.15 pip/side) hand-calculated; legacy `_exit_scan` STOP with 0.5 pip/side slip hand-calculated; 15. breakeven via LEGACY `simulate()` on a synthetic in-memory store: 1.5R favorable touch moves SL to entry+1 pip (long), later stop-out at locked level ⇒ net +1.0 pip = +0.1 R, be_moved = True; plus a BE-not-triggered case; 16. partial sample / unavailable quote: array ends before fill ⇒ NO_FILL; array ends before any exit ⇒ PO3 NO_TIME_EXIT_DATA and LEGACY EOD_WINDOW close at last tick (hand-calculated).

## 7. Control H — metrics unit test matrix (frozen)

Hard-coded trade list (10 trades, hand-computed in comments): mean, median, total, PF, expectancy R, win rate, max drawdown R, positive years, remove-best-1 %, bootstrap sanity (CI contains sample mean; width plausible vs SE; identical across two calls with same seed ⇒ deterministic), long/short split by mask. Edge cases: zero losses ⇒ PF = 999.0 (cap); zero wins ⇒ PF = 0.0; R-denominator units: r_mult = net_pips / risk_pips (verified against a real recorded PO3 trade hand-recalculated from its JSON fields); pip conversion 1 pip = 1e-4 price units (verified against store `spread_pips` column on one real partition sample). Metrics computed by BOTH the production PO3 functions and an independent audit implementation; exact/tolerance-bounded equality (1e-9 relative on aggregates, bootstrap bounds equal exactly under same seed/algorithm).

## 8. Control I — two independent engines (frozen)

- Trade sources (frozen NOW, no selection bias): (a) ALL 641 real PO3_BASE_M0 trades from `research/po3_base_m0/po3_base_m0_trades.json`; (b) the FIRST 150 H2 trades (file order) with status TRADE from `research/legacy_reverse_m1/h2_trades.csv`. EMA-legacy note: the canonical EMA M15 stream is bar-geometry-native (not tick-executed); its integrity rests on the previously frozen TRADE_STREAM_MATCH identity check (results_baseline.csv, committed); it is NOT re-derived here — scope limit documented, tick-executed studies cover the tick pipeline.
- Implementation A = production engines (PO3 `execute()` for (a); LEGACY `simulate()` semantics for (b), invoked on the real store).
- Implementation B = a fresh scalar per-tick engine written inside this audit (straightforward Python loop, tick-by-tick decisions; direct pyarrow reads; NO import of any production execution function; BE rule and slippage convention re-implemented from the frozen spec text above). Re-execution inputs = only frozen per-trade parameters (decision ts, direction, stop level / risk distance r0); stops/targets/fills/exit derived independently by B.
- Compared fields: decision timestamp, direction, entry timestamp, entry side, entry price, stop, target, exit timestamp, exit side, exit price, net pips, R multiple (plus stop-gap for PO3 stops; be_moved for legacy where applicable).
- Target: 100 % agreement. Allowed deviation: floating rounding only, ≤ 1e-9 price / ≤ 1e-6 pips, documented per field. Any structural mismatch ⇒ LAB FAIL until explained.

## 9. Control J — common-sample stress audit (frozen)

- Reproduce the LEGACY-REVERSE Test04 benchmark EXACTLY as frozen (`run_h1` on `t4_triggers(pyr)`, variants base=(5 s, 0 slip), lat30=(30 s, 0), stress=(30 s, 0.5 pip/side), rev_max_sl_pips=25, consec_gate=3). Expected reproduction: baseline N=93, PF ≈ 1.319; stress N=92, PF ≈ 1.532 (tolerance ±0.02 PF; the run is deterministic so exact equality is expected).
- Compute BOTH sampling conventions on the SAME run: (A) NATIVE — each scenario keeps its own filled trades; (B) COMMON INTERSECTION — triggers that filled and exited in BOTH baseline and stress (trigger identity = trigger trade entry_time + level).
- Report: N_baseline, N_stress, N_intersection, PF/EV baseline native, stress native, baseline common, stress common.
- Decomposition (frozen): selection effect = PF_base_native − PF_base_common; execution effect = PF_base_common − PF_stress_common. Classify the historical 1.319 → 1.532 increase as REAL_EXECUTION_EFFECT / SAMPLE_SELECTION_EFFECT / METRIC_BUG / OTHER_EXPLAINED_EFFECT, from this decomposition plus per-trade evidence (which trade(s) drop and their baseline contribution; per-trade net changes from latency/slippage). A-priori expectation (written before running): the added 0.5 pip/side cost (~ −0.05 R at ~10-pip risk) cannot by itself raise PF, so a material part of the increase is expected to be sample composition (dropped trigger and/or latency-shifted fills); the classification will follow the measured decomposition, not this expectation.
- PASS: frozen numbers reproduced; decomposition computed; cause classified with per-trade evidence. This audit does not modify historical results.

## 10. Control K — time/causality guards (frozen)

Tests, all hand-specified: (1) `guard_partition_path` refuses year=2019; (2) `assert_utc_range` refuses ranges touching 2019-01-01Z; (3) `assert_discovery_date` refuses 2019+; (4) `TickStore.load_range` refuses end > guard end; (5) audit loader refuses year=2019 partitions; (6) Europe/London DST correctness: 2011-03-27 10:00 London == 09:00:00Z and 2011-10-30 10:00 London == 10:00:00Z (hand-known UTC offsets); server-time legacy conversion Europe/Helsinki spot check (2010-01-19 09:15 Helsinki == 07:15:00Z); (7) completed-bar causality: the M1-candle decision event fires at bucket END, never before (synthetic ticks); (8) explicit future reads: entry with no tick within the fill bound returns NO_FILL (never reads past the bound); time exit with no tick within the quote bound returns NO_TIME_EXIT_DATA; (9) oracle isolation: the oracle function lives ONLY in the audit module under an ORACLE_LOOKAHEAD_INVALID name; a grep test asserts no production lib (po3_base_m0_lib, legacy_reverse_m1_lib, m1_engine, research_engine.py) references it. PASS: all sub-tests pass.

## 11. Data integrity reconfirmation (frozen)

Expectations frozen from the previously validated state: partition_count = 108; total_rows = 209,682,628; per-partition row counts equal the frozen manifest (`research/po3_base_m0/data_manifest.json`); SHA256 spot-check of 3 partitions (2010-01, 2014-06, 2018-12) matches the frozen manifest (no full re-hash; existing validated manifest independently spot-checked, per mission §15); first timestamp in 2010-01-01..2010-01-04, last in 2018-12-28..2018-12-31; timestamps monotonic non-decreasing within every partition (expected violations: 0); bid ≤ ask everywhere (expected violations: 0); positive bid/ask everywhere (expected violations: 0); exact-duplicate timestamps counted and documented (no pass/fail gate; behavior recorded). No re-download. No 2019+ access.

## 12. Verdict commitments

CAN_LAB_DETECT_KNOWN_POSITIVE_EDGE / CAN_LAB_DETECT_KNOWN_NEGATIVE_EDGE / CAN_LAB_RETURN_NO_EDGE_FOR_RANDOM / CAN_LAB_DETECT_LOOKAHEAD_ORACLE / EXECUTION_ENGINE_VALIDATED / METRIC_ENGINE_VALIDATED / CAUSALITY_GUARDS_VALIDATED / STRESS_COMMON_SAMPLE_VALIDATED — answered YES/NO strictly from control outcomes against the gates above. LAB_PASS requires ALL major controls (A–K) pass; any failure ⇒ LAB_FAIL, identify defect, STOP, no strategy research.

Execution order: spec commit (this commit) → integrity → G/H (unit matrices) → A/B/C → D → E/F → I → J → K → report. Every result lands in `research/lab_audit_m0/RESULTS.json` and `LAB_AUDIT_M0_REPORT.md`.
