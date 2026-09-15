# AUTONOMOUS_EDGE_DISCOVERY_M1 — FINAL REPORT (terminal)

FINAL_STATUS = **NO_CONFIRMED_EDGE_FOUND** → STOP (mission 22/27)

- Branch: research/autonomous-edge-discovery-m1 (base 78afc50, LAB_PASS).
  PR NON-MERGED. Prior research artifacts untouched.
- EXPERIMENTS_TOTAL = 81 (ledger + disk counter; includes 6 duplicate rows
  from an import side-effect of f08_plateau.py, since guarded — duplicates of
  E060..E065, no new information).
- FAMILIES_TOTAL = 13 of 20 allowed (F01..F13, no F09-style reuse).
- Budget respected: no experiment #82+ after the terminal decision.
- Mandatory causality gate ran BEFORE any PnL for every family:
  T1 max-input-timestamp, T2 truncation identity, T3 future-mutation identity,
  targeted sampling of firing bars, 24-28 samples per family. Two design bugs
  (F06 units, F10 tightness) were fixed and re-gated BEFORE their screens.
- 2018 H1 was read ONLY after FROZEN_SPEC_COMMIT 482c02c (git-enforced).
  2018 H2, 2019+, protected OOS: NEVER accessed.

## Discovery summary (2017, all features causally gated)

| Family | Mechanism | Verdict |
|---|---|---|
| F01 | serial dependence x vol regime | dense but sign-flips Sep-Dec (trend beta) — rejected |
| F02 | compression -> box breakout | +0.40p/120m, sub-cost — rejected |
| F03 | failed break fade | +1.33p/240m t=1.46, one-sided, mixed months — rejected |
| F04 | overnight->London flip | N=136, t=1.26 — rejected |
| F05 | London->NY reversal handoff | N=83 +3.0p/240m — NEAR MISS (see below) |
| F06 | directional deceleration | +0.73p/240m t=0.95 — rejected |
| F07 | fresh 24h extreme continuation | +0.71p/240m t=0.48 — rejected |
| F08 | absorption reversal at fresh extreme | CANDIDATE — confirmed in discovery, FAILED 2018H1 |
| F09 | weekday x hour calendar drift | max t=1.51 across 10 cells — killed at screen |
| F10 | range-persistence expansion breakout | screen +2..+2.7p gross; tick-exact after costs PF 0.99-1.04 — dead |
| F11 | tick-activity surge continuation | +2.1p/240m Jan-Aug, negative Sep-Dec (trend beta) — rejected |
| F12 | vol-expansion directional continuation | +1.31p/240m t=1.09, Q4 negative — rejected |
| F13 | NY-window breakout w/ day-trend align | +1.31p/240m t=0.54 — rejected |

## TOP_NEAR_MISSES

1. **C1 — F08 absorption reversal (lb=180, fade=2)**, frozen at 482c02c:
   Discovery 2017 tick-exact: N=259, +1.615 PIPS/trade, PF 1.455,
   expectancy +0.1077 R, LONG +0.1273 R / SHORT +0.0896 R (symmetric),
   10/12 positive months, remove-best-1% = +1.379 PIPS, stress-common
   EV = +0.658 PIPS (PF 1.161). Plateau: lb=90/120/180 all profitable
   (+0.77/+1.12/+1.62 PIPS).
   **Confirmation 2018H1 (frozen, unchanged): FAILED every clause** —
   N=133, mean −2.436 PIPS, PF 0.614, expectancy −0.1624 R,
   LONG −0.2038 R / SHORT −0.1304 R, 1/6 positive months,
   remove-best −2.702 PIPS, stress-common EV −0.2114 R.
   The 2017 edge inverted out-of-sample: fading fresh 3h extremes stopped
   working when 2018 trends extended. Family is contaminated for 2018H1;
   no tuning was attempted.
2. **F05 — London->NY reversal handoff (thr=5p)**: discovery N=83,
   +1.118 PIPS, PF 1.231, L +0.092R / S +0.058R, stress-common +0.816 PIPS
   (PF 1.167). Not forwarded: N < 100 and razor threshold (thr=3 variant
   collapses to +0.055 PIPS, PF 1.01) — OVERFIT_RISK per mission 16.
3. **F10 — daily expansion breakout**: strongest gross screens of the
   campaign (+2.0..+2.7 PIPS/240m, 9-11/12 positive months, both sides)
   but tick-exact replay with real spread after position occupancy:
   k=1.01 PF 0.99, k=0.85 PF 1.04, k=0.75 PF 1.01 — the screen edge was
   persistent-state drift, not executable edge. Dead after costs.

## REASONS_FOR_REJECTION (campaign-level)

Across 13 causally-verified mechanism families on 2017, no effect was
simultaneously (a) direction-symmetric, (b) stable across months, (c) above
realistic BID/ASK costs after tick-accurate execution, and (d) persistent in
2018H1. The dominant 2017 intraday structure was one-way drift (long-EURUSD
trend beta), which reversed in Q4-2017; strategies built on it (F01, F11,
F12) flip sign exactly there. The one candidate that passed all discovery
targets with a symmetric, plateaued, causally-clean construction failed
confirmation with an inverted sign — evidence that the 2017 discovery window
does not generalize at these horizons and costs.

## GOVERNANCE

2018_H2_ACCESSED=NO
2019_PLUS_ACCESSED=NO
PROTECTED_OOS_ACCESSED=NO
RULES_CHANGED_AFTER_FREEZE=NO (2018H1 run used the frozen code verbatim)
PARAMETER_SEARCH=inside 2017 only, coarse grids, <=10 configs/family
NO_MERGE; PR opened at terminal state only.
