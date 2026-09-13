# MACRO_TICK_M1 — EVENT STRATEGY DISCOVERY REPORT

**Mission:** MACRO-TICK-M1 — event-driven EURUSD strategy discovery, NFP + CPI, tick-accurate.
**Verdict: NO_MACRO_TICK_CANDIDATE — zero strategies pass the frozen economic gate. Per §18: STOP, no rescue variants.**

## Governance chain

| Item | Value |
|---|---|
| BASE_HEAD | `f968f4ae353e79fef80311e646987dc3add38b2b` (MACRO-TICK-M0, PR #31) |
| FROZEN_SPEC_COMMIT | `b701d95f75cde0893905311509871834a53be28d` (committed BEFORE any outcome computation) |
| Engine commit | `3864067` (engine + 47 synthetic tests + CI registration) |
| Branch | `research/macro-tick-m1-event-strategies` |
| PR | NON MERGED, base `research/macro-tick-m0` |
| Discovery | 2010-01-01 inclusive → 2019-01-01 exclusive |
| 2019+ accessed | NO (hard month-partition guard, tested) |
| Protected OOS accessed | NO |
| FOMC | `FOMC_PRIMARY_RESEARCH=DEFERRED` — nothing computed |

## Events

- M0 database: 108 NFP + 108 CPI = 216 candidates (FOMC dropped first).
- Excluded from primary: `NOT_ALIGNED` = 2 (`MACRO-NFP-201002`, first
  post-release tick 7291 ms; `MACRO-CPI-201003`, 5958 ms — both > 5 s frozen
  rule; reported here separately as required by §2).
- **EVENTS_PRIMARY_VALID = 214** (107 NFP + 107 CPI), 0 inside data gaps.
- **QUALIFYING_SHOCKS (pooled) = 147 / 214 (68.7%)** with the frozen
  `SHOCK_SCORE >= 2.0 AND |shock| >= 1.0 pip` rule
  (NOISE_SCALE = max(Q95 of 30 s baseline MID moves, baseline median spread),
  baseline = T0−60m → T0−5m).

## Strategy A — MACRO_A_30S_CONTINUATION (30 s shock continuation, P0 stop, 1.5R, T60m)

| Metric | Value |
|---|---|
| QUALIFYING_SHOCKS / N_TRADES | 147 / **120** (13.3/yr) |
| MEAN/MEDIAN_SHOCK_PIPS (traded) | −1.39 / +5.60 |
| MEAN_SHOCK_SCORE | 9.96 |
| **NET_EXECUTABLE_MEAN_PIPS** | **+2.05** |
| MEDIAN_NET | −4.50 |
| STRESS_025 / **050** / 100 | +1.55 / **+1.05** / +0.05 |
| WIN_RATE / AVG_WIN / AVG_LOSS | 45.8% / +23.19 / −15.84 |
| **PROFIT_FACTOR** | **1.239** |
| **EXPECTANCY_R** | **+0.083R** |
| TOTAL_NET / MAX_DD | +246.1 pips / 226.3 pips |
| MAX_CONSEC_LOSSES / POSITIVE_YEARS | 6 / **5 of 9** |
| REMOVE_BEST_1_PERCENT_NET_MEAN | +0.82 |
| CI95_MEAN_NET (2000, seed 42) | [−2.20, +6.46] → CI_POSITIVE=NO |
| Exits | STOP 54 · TARGET 37 · TIME 29 · GAP 0 · SPREAD_TOO_WIDE 27 · NO_FILL 0 |
| NFP: n/mean/PF | 65 / **−0.54** / 0.95 |
| CPI: n/mean/PF | 55 / +5.11 / 1.98 |
| **VERDICT** | **FAIL_GATE** (passes fail-fast, below §17 gate: net < 3.0, PF < 1.25, expectancy < 0.10R, 5 < 6 positive years, NFP mean < 0) |

By year (n / total_net / PF): 2010: 8/−32.3/0.64 · 2011: 11/−18.8/0.76 ·
2012: 11/+5.4/1.08 · 2013: 9/+70.1/3.33 · 2014: 12/+63.0/2.27 ·
2015: 16/+211.6/2.33 · 2016: 19/−134.9/0.59 · 2017: 18/+102.9/2.07 ·
2018: 16/−20.7/0.84.

## Strategy B — MACRO_B_FAILED_SHOCK_REVERSAL (50% retrace, extreme stop, target P0, T30m)

| Metric | Value |
|---|---|
| QUALIFYING_SHOCKS / N_TRADES | 147 / **62** (6.9/yr) |
| MEAN/MEDIAN_SHOCK_PIPS (traded) | +3.43 / +7.50 |
| MEAN_SHOCK_SCORE | 7.35 |
| **NET_EXECUTABLE_MEAN_PIPS** | **−0.23** |
| MEDIAN_NET | +2.58 |
| STRESS_025 / **050** / 100 | −0.73 / **−1.23** / −2.23 |
| WIN_RATE / AVG_WIN / AVG_LOSS | 61.3% / +7.44 / −12.38 |
| **PROFIT_FACTOR** | **0.953** |
| **EXPECTANCY_R** | **−0.115R** |
| TOTAL_NET / MAX_DD | −14.1 pips / 64.1 pips |
| MAX_CONSEC_LOSSES / POSITIVE_YEARS | 3 / 4 of 9 |
| REMOVE_BEST_1_PERCENT_NET_MEAN | −0.74 |
| CI95_MEAN_NET | [−3.18, +2.63] → CI_POSITIVE=NO |
| Exits | STOP 24 · TARGET 38 · TIME 0 · GAP 0 · SPREAD_TOO_WIDE 7 · NO_FILL 0 |
| Setups | NO_TRIGGER 78 · SHOCK_NOT_QUALIFYING 67 · SPREAD_TOO_WIDE 7 · TRADED 62 |
| NFP: n/mean/PF | 37 / +2.62 / 1.67 |
| CPI: n/mean/PF | 25 / **−4.44** / 0.27 |
| **VERDICT** | **REJECT** (fail-fast §18: NET mean <= 0, PF <= 1.0, REMOVE_BEST <= 0) |

By year (n / total_net / PF): 2010: 6/−21.6/0.39 · 2011: 7/−2.8/0.88 ·
2012: 8/+6.5/1.34 · 2013: 3/−18.8/0.12 · 2014: 10/+60.0/2.81 ·
2015: 2/+10.7/∞ · 2016: 13/−17.0/0.83 · 2017: 4/+4.5/1.87 ·
2018: 9/−35.7/0.43.

## Strategy C — MACRO_C_5M_DIGESTION_BREAKOUT (5 m range freeze, breakout to 35 m, NEWS_MID stop, 1.5R, T120m)

| Metric | Value |
|---|---|
| QUALIFYING_SHOCKS / N_TRADES | 147 / **124** (13.8/yr) |
| MEAN/MEDIAN_SHOCK_PIPS (traded) | +0.50 / +6.68 |
| MEAN_SHOCK_SCORE | 8.93 |
| **NET_EXECUTABLE_MEAN_PIPS** | **−0.97** |
| MEDIAN_NET | −8.95 |
| STRESS_025 / **050** / 100 | −1.47 / **−1.97** / −2.97 |
| WIN_RATE / AVG_WIN / AVG_LOSS | 40.3% / +23.75 / −17.68 |
| **PROFIT_FACTOR** | **0.908** |
| **EXPECTANCY_R** | **−0.048R** |
| TOTAL_NET / MAX_DD | −120.9 pips / 197.4 pips |
| MAX_CONSEC_LOSSES / POSITIVE_YEARS | 7 / 5 of 9 |
| REMOVE_BEST_1_PERCENT_NET_MEAN | −2.07 |
| CI95_MEAN_NET | [−5.03, +3.37] → CI_POSITIVE=NO |
| Exits | STOP 64 · TARGET 39 · TIME 21 · GAP 0 · SPREAD_TOO_WIDE 5 · NO_FILL 0 |
| Setups | NO_BREAKOUT 18 · SHOCK_NOT_QUALIFYING 67 · SPREAD_TOO_WIDE 5 · TRADED 124 |
| NFP: n/mean/PF | 71 / **−0.76** / 0.94 |
| CPI: n/mean/PF | 53 / **−1.27** / 0.86 |
| **VERDICT** | **REJECT** (fail-fast §18) |

By year (n / total_net / PF): 2010: 7/−88.6/0.38 · 2011: 14/+15.7/1.11 ·
2012: 11/+35.0/1.38 · 2013: 10/+13.7/1.14 · 2014: 16/−99.4/0.36 ·
2015: 13/−31.5/0.83 · 2016: 16/+74.9/1.47 · 2017: 19/−60.4/0.69 ·
2018: 18/+19.8/1.13.

## Family breakdown (DIAGNOSTIC ONLY — no family selection performed)

| Family | A mean | B mean | C mean |
|---|---|---|---|
| NFP | −0.54 | +2.62 | −0.76 |
| CPI | +5.11 | −4.44 | −1.27 |

No pooled strategy can pass (§15): A has negative NFP mean, B negative CPI
mean, C both negative. The apparent A-on-CPI / B-on-NFP complementarity is
NOTED and NOT pursued — selecting families after seeing results is forbidden
by the frozen spec.

## Real-data audit (§21)

Independent audit path (`audit_m1.py`: direct month-parquet reads, Python
lists + `bisect`, scalar loops — no numpy vectorisation, no `mtf_lib`),
10 trades per strategy, deterministic chronological spread:

- A: 10/10 exact (t0, P0, P30, shock dir, trigger, entry ts/side/price, SL,
  TP, exit ts/side/price, PnL)
- B: 10/10 exact
- C: 10/10 exact

**REAL_DATA_AUDIT = 30/30 ALL_MATCH.**
(The first audit run flagged a direction-convention bug INSIDE the audit
script itself — it assumed all strategies trade in the shock direction; B
reverses by definition and C follows the breakout. The production engine was
verified correct; the audit path was fixed and re-run.)

## Validation (§20)

- 47/47 synthetic tests green (`test_macro_tick_m1.py`): P0/P30 definitions,
  baseline window isolation, no-future-value invariance, Q95 + median spread,
  shock score sign/magnitude, LONG/SHORT direction, 250 ms latency, entry
  ASK/BID sides, exit BID/ASK sides, A P0 stop, B 50% trigger + observed
  extreme stop, C range freeze at T0+5m + no-trigger-before + 35 m window
  close, spread-safety skip (incl. exactly-3× allowed), stop overshoot fill,
  target cap, time exit, stress arithmetic, data-gap invalidation, weekend
  not-a-gap, 2019 hard cutoff (month guard + event filter + entry guard).
- Existing suites re-run on this branch: MACRO-TICK-M0 22 OK · MTF-M1 39 OK ·
  TICK-M1 22 OK · TICK-M0 18/18 (direct script run).
- CI: suite registered in `.github/workflows/research-engine-tests.yml`.

## Execution notes

- No DATA_GAP_INVALID trades occurred in any strategy (news mornings are
  continuously quoted); the path is synthetic-tested.
- SPREAD_TOO_WIDE skipped 39 setups overall (27 A / 7 B / 5 C) — the frozen
  3× baseline-spread guard bites exactly in the post-release minutes.
- Stress: no strategy survives STRESS_050 positively except A (+1.05), and A
  already fails the gate on PF/expectancy/years/NFP.

## Final status

```
STRATEGIES_PASSING_GATE = 0
FINAL_STATUS = NO_MACRO_TICK_CANDIDATE
```

Per §18: verdicts are frozen, no rescue variants investigated, no further
credits spent. The first 30 seconds after NFP/CPI show a large, clean
causal shock (mean shock score ≈ 9–10× the pre-event noise scale) but the
frozen executable continuations/reversals/breakouts do not clear the
economic gate net of real spread and latency. DO NOT OPEN V1. DO NOT MERGE.
