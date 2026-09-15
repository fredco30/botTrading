# AUTONOMOUS_EDGE_DISCOVERY_M1 — FROZEN SPEC (committed BEFORE any 2018 access)

Candidate C1 — "Absorption reversal at fresh extreme" (family F08).
This file freezes ALL rules. After this commit, only 2018-01-01..2018-06-30
may be read, with these exact rules, unchanged.

## Feature (STRICTLY CAUSAL, gate-verified)

Decision instants: every completed M1 mid bar, decision time T = bar_start+60s.

Trailing window (EXCLUDES the decision bar): over the 180 completed M1 bars
immediately before the decision bar,
  HH = max(high), LL = min(low)   (MID bars: high/low are mid-series)

UP-branch (SHORT signal) — distribution at a fresh 3-hour high:
  high[T] > HH
  AND close[T-1] < mid[T-1]          (mid = (high+low)/2 of that bar)
  AND close[T]  < mid[T]
  AND close[T]  < close[T-1]         (fading closes)

DOWN-branch (LONG signal) — absorption at a fresh 3-hour low:
  low[T] < LL
  AND close[T-1] > mid[T-1]
  AND close[T]  > mid[T]
  AND close[T]  > close[T-1]

Max feature input timestamp = last tick of the decision bar <= T. Proven:
T1 max-input-ts (24/24), T2 truncation identity, T3 future-mutation identity
(families.py f08 make_feat(lb=180, fade=2); gate run F08p_lb180f2 PASS).
Trace: frozen_feature_trace.json (20 random signals, assert PASS).

## Strategy rules (frozen)

- Direction: UP-branch -> SHORT, DOWN-branch -> LONG.
- Entry: first tick >= T + 5 s on the execution side (SHORT sells at BID,
  LONG buys at ASK); maximum entry wait 30 s after the delay, else NO_FILL.
- Stop: 15 pips from actual entry price. Target: 15 pips from actual entry.
- Time exit: 120 minutes after entry fill, on the executable side
  (SHORT covers at ASK, LONG exits at BID).
- Exit priority on the same tick: STOP before TARGET; gap-through stop fills
  at the actual adverse tick; target fills capped at target.
- One open position; signals while a position is open are ignored.
- No pyramiding, no martingale, fixed normalized risk (1R = 15 pips).
- Sessions: none (24/5).

## Stress definition
Entry latency 30 s + 0.50 pip adverse slippage per side (entry AND exit).

## Discovery evidence (2017-01-01..2017-12-31, tick-exact baseline)
N=259 | trades/month=21.6 | mean=+1.615 PIPS | PF=1.455 | expR=+0.1077 R
win rate and totals in RESEARCH_LEDGER.csv E064 | LONG_R=+0.1273 R
SHORT_R=+0.0896 R | pos months=10/12 | remove_best_1pct=+1.379 PIPS
STRESS COMMON: EV=+0.658 PIPS, PF=1.161 (intersection reported at confirm)

## Plateau (discovery, same family, tick-exact)
lb=90/fade2: +0.77 PIPS PF 1.19 | lb=120/fade2: +1.12 PF 1.30 |
lb=180/fade2: +1.62 PF 1.46 (selected) | fade=3 variants: N<=28, unprofitable
(over-restrictive formulation, not a neighborhood of the selected rule).
Both neighbouring lookbacks profitable -> broad plateau along lookback.

## Parameter search disclosure
Selection was made on 2017 (contaminated discovery): lb=180 was chosen after
observing the plateau. 2018 H1 is untouched as of this commit and decides
confirmation. Confirmation gate (mission 20): mean>0, PF>=1.10, expR>0,
remove_best>0, STRESS_COMMON_EV>=0, directional consistency.
