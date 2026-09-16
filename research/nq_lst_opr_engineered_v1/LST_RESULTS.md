# LST_OPR_ENGINEERED_V1 — RESULTS (internal historical test, 2020-2025)

RULES=LST_OPR_FROZEN_SPEC.md (user-defined pre-specified architecture;
implemented verbatim + 6 documented mechanical resolutions R1-R6)
DATA=existing E:\ NQ ohlcv-1m -> 5m; 2026 SEALED, never accessed.
COSTS=unit-audited model: NORMAL 1.5 / STRESS 3.0 INDEX POINTS RT ($30/$60).
Classification: INTERNAL HISTORICAL TEST — no subperiod is pristine OOS.

## ELIGIBILITY FUNNEL (the binding constraint, reported not tuned)

  1548 RTH days
  FLOW: BULL 786 / BEAR 510 / NEUTRAL(+missing H1 history) 252
  RANGE GATE 0.25*ATR_H1 <= width <= 1.00*ATR_H1: PASS 39, REJECT 1255 (97%)
  window breakout in flow direction: 24 of 39 eligible days
  A trades: 15 | B trades: 2 | C: 17

  WHY: ATR14 H1 is computed on the 24h H1 series (literal spec reading);
  quiet overnight hours make ATR_H1 small relative to the modern NQ
  first-15-minute range (width/ATR typically 1.2-4.2, sample-checked), so the
  frozen upper bound rejects almost every day. This IS the frozen rule working
  as written; the mission forbids threshold sweeps and post-PnL
  reinterpretation, so no alternative ATR basis was tried. Any change here is
  a NEW hypothesis requiring fresh pre-registration and human sign-off.

## RESULTS (NORMAL cost; USD = points x 20)

                      A_BREAKOUT    B_REINTEGRATION   C_COMBINED
TRADES                15            2                 17
TRADES_PER_WEEK       0.048         0.006             0.055
NET_PTS_PER_TRADE     -7.73         -14.97            -8.58
NET_TICKS             -30.9         -59.9             -34.3
NET_USD_1NQ           -$154.57      -$299.30          -$171.59
PF                    0.083         0.0               0.067
EXPECTANCY_R          -0.707        -1.111            -0.755
WIN_RATE              0.067         0.0               0.059
STRESS_NET_PTS        -9.23         -16.47            -10.08
STRESS_PF             (neg)         (neg)             (neg)
REMOVE_BEST_1%        -9.03         -15.0             -9.77
MAX_DD_R              -10.61        -2.22             -12.83
MAX_DD_USD_1NQ        -$2,318.5     -$598.6           -$2,917.1
EXITS                 OPR_BACK 9/STOP 5/EMA8 1   STOP 2   OPR_BACK 9/STOP 7/EMA8 1
BY_YEAR (pts)         all six years negative    n/a      all six years negative

DIAGNOSTICS (2O — report-only, nothing optimized): negative in every OPR-width
quartile, every ATR quartile, both sides, every entry-time bucket, every fold.

## VERDICT

FINAL_STATUS=NO_USEFUL_LST_OPR_EDGE

Frequency-dead (0.05/week) AND decisively negative in every cut. Per the
no-rescue rules: no filter added, no threshold touched, no ATR-basis
reinterpretation, no news filters, no variant search. The 15-trades sample
cannot support any candidate claim; the sign is uniformly negative anyway.

If the human wishes to test the same architecture against an RTH-hours ATR14
(or any other pre-registered ATR basis), that is a NEW frozen hypothesis to
define BEFORE its PnL — not run in this mission.

2026_ACCESSED=NO | NEW_DATA_PURCHASED=NO
