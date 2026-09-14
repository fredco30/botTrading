# LAB_AUDIT_M0 — FINAL REPORT

Mission: meta-validation of the backtest laboratory (positive & negative controls).
No strategy research, no optimization, no 2019+ data, no protected OOS.
Spec frozen BEFORE execution; every synthetic expectation pre-registered.

- BASE_HEAD: `21cac5f05e454bbd7a2ef892dc5c3a23cd14bce1`
- FROZEN_SPEC_COMMIT: `3ec8a224c53e6634e8cf99819814f910e154cba8`
- FINAL_HEAD: `95180ba151d405ea68b95e9fa7a92d2bc4c7efd9`
- BRANCH: `research/lab-audit-m0` (no merge; PR opened for review)

## Verdict

**FINAL_STATUS = LAB_PASS**

All major controls A-K PASS. The laboratory is validated: it produces positive
results when a positive edge is injected, negative results when a negative edge
is injected, no-edge results for random signals, strongly positive results for a
deliberate lookahead oracle, and its execution, metrics, causality and
stress-sampling machinery match independent re-implementations and hand
calculations. No production lab defect was found; strategy research may resume.

## Controls

| Ctrl | What is tested | Expected (frozen before run) | Observed | Pass |
|---|---|---|---|---|
| A | synthetic positive edge, N=1000, p=0.65, 0.5-pip spread + 0.15 pip/side slip | net +0.22R ±0.08R, PF>1, CI95 low>0 | **+0.210R**, PF **1.548**, CI [0.154, 0.272], WR 64.5% | YES |
| B | synthetic negative edge, p=0.35 | net −0.38R ±0.08R, PF<1 | **−0.388R**, PF **0.451**, CI [−0.446, −0.328] | YES |
| C | zero edge + cost drag, N=5000, p=0.50 | net −0.08R ±0.04R, est<0 | **−0.0576R**, PF 0.891, CI [−0.086, −0.030] | YES |
| D | 100 random direction perms on real 2010-2018 10:00-London timestamps, 65-min hold | mean<0, P95≤+0.5 pip, ≤15 perms PF>1.20 | mean **−0.505 pips** (≈ measured 0.557-pip spread), P05 −1.057, P95 **−0.024**, 4/100 profitable, **0/100** PF>1.20 | YES |
| E | ORACLE_LOOKAHEAD_INVALID (65-min lookahead, 3-pip gate, same timestamps) | mean>+5 pips, PF>2 | **+13.28 pips**, PF **999-cap** (100% wins, 1836 days) | YES |
| F | anti-oracle (opposite of oracle) | mean<−5 pips, PF<0.5 | **−14.32 pips**, PF **0.0** (0% wins) | YES |
| G | execution unit matrix (sides, spread, touch/overshoot/gap, same-tick priority, latency, NO_FILL, quote bounds, slippage, breakeven, partial samples) | 26 hand-calculated exact matches | 26/26 within 1e-9/1e-6 | YES |
| H | metrics matrix vs hand-calc + independent implementations; PF zero-loss cap 999 / zero-win 0; R units; pip conversion | exact/tolerance equality | clean | YES |
| I | two independent engines: B (fresh scalar per-tick, written in this audit, no production execution imports) vs A (production) on real trades | 100% agreement | **791/791 trades exact** (641 PO3 + 150 H2; 13 fields each) | YES |
| J | common-sample stress audit + Test04 explanation | reproduce 1.319/1.532 and explain | reproduced exactly; cause = **SAMPLE_SELECTION_EFFECT** (below) | YES |
| K | 2019+/UTC/DST/bar-completion/future-read/oracle-isolation guards | all guards fire, no future leak | clean | YES |

## Data integrity (reconfirmation)

108 partitions, **209,682,628 rows** (footer counts = frozen manifest, all 108);
per-partition first/last timestamps = frozen manifest; timestamps monotonic
(0 violations); bid ≤ ask everywhere; no non-finite/non-positive quotes;
SHA256 spot-checks of 2010-01, 2014-06, 2018-12 all match the frozen manifest.
No re-download. Duplicate timestamps exist in the store (Dukascopy property,
documented, no gate).

## Test04 stress-PF increase — exact cause (Control J)

The frozen numbers reproduce deterministically (base N=93 PF 1.3187; stress
N=92 PF 1.5321). The naive N-difference (93 vs 92) hides the real story: the
common intersection is **86 trades** — 13 trades differ in composition between
scenarios. The 30 s latency shifts every fill; 7 baseline trades do not execute
under stress (5× SKIP_REVMAXSL: the unslipped 30s-later ref price pushed risk
across the 25-pip gate; 2× INVALID_LEVELS), and **all 7 are baseline losers**
(five −21..−25 pip stop-outs, ≈ −95 pips of losses removed from the stress
sample). Classification: **SAMPLE_SELECTION_EFFECT**. On the common sample the
stress scenario is genuinely WORSE: EV +0.546R → +0.476R (mean ΔR −0.0696 ≈ the
injected −1 pip slippage; 79/86 trades worsened). The residual common-PF rise
(1.624 → 1.697) is a ratio-metric artifact of 11 exit-type flips toward 2.5R
targets. No metric bug. A stress scenario must not look better because losers
disappeared — and here it did; the common-sample convention exposes it.

## Audit-side defects found and fixed during the audit (transparency)

None of these are production-lab defects; all were caught by the audit's own
cross-checks, which is what the audit is for:
1. Audit day-quote loader initially cached per-day slices under month keys
   (first D run showed 102 eligible days instead of 2325). Fixed; D re-run.
2. Engine B (independent) initially had LONG/SHORT exit sides inverted — the
   B-vs-A comparison flagged 100% of affected fields immediately. Fixed; I
   re-run: 791/791 exact. (This is direct evidence the two-engine control
   detects execution-semantics errors.)
3. Hand-calc float-equality issues in synthetic touch cases (G) were resolved
   with robust margins, not by loosening the engine tolerances.

## Scope notes

- Control I covers the two tick-executed studies (PO3, LEGACY-REVERSE). The
  EMA-legacy canonical stream is M15-bar-native and rests on the previously
  frozen TRADE_STREAM_MATCH identity check (committed in legacy_bots_m1);
  it was not re-derived here.
- E/F PF values hit the engine's documented edge conventions (zero losses →
  999 cap; zero wins → 0.0); those conventions are themselves unit-validated
  in Control H.
- Historical strategy results were not modified. No bulk market data in git.

## Final output

```
LAB_AUDIT_M0

BASE_HEAD=21cac5f05e454bbd7a2ef892dc5c3a23cd14bce1
FROZEN_SPEC_COMMIT=3ec8a224c53e6634e8cf99819814f910e154cba8
FINAL_HEAD=95180ba151d405ea68b95e9fa7a92d2bc4c7efd9
PR=research/lab-audit-m0 (pushed, not merged)

CONTROL_A_POSITIVE_SYNTH=PASS
  EXPECTED=net +0.22R +-0.08R, PF>1, CI95 lower>0
  OBSERVED=+0.210R, PF 1.548, CI95 [0.154, 0.272], WR 64.5%, N=1000
CONTROL_B_NEGATIVE_SYNTH=PASS
  EXPECTED=net -0.38R +-0.08R, PF<1, CI95 upper<0
  OBSERVED=-0.388R, PF 0.451, CI95 [-0.446, -0.328], WR 34.6%, N=1000
CONTROL_C_ZERO_SYNTH=PASS
  EXPECTED=net -0.08R +-0.04R, est<0, PF<1
  OBSERVED=-0.0576R, PF 0.891, CI95 [-0.086, -0.030], WR 51.1%, N=5000
CONTROL_D_RANDOM_REAL=PASS
  MEAN=-0.505 pips/trade (avg entry spread 0.557)
  P05=-1.057 pips
  P95=-0.024 pips
  (4/100 profitable perms; 0/100 with PF>1.20; 2325 eligible days x 100 seeds 4200..4299)
CONTROL_E_LOOKAHEAD_ORACLE=PASS
  MEAN_PIPS=+13.28
  PF=999.0 (cap; 100% wins; ORACLE_LOOKAHEAD_INVALID; 1836 gated days)
CONTROL_F_ANTI_ORACLE=PASS
  MEAN_PIPS=-14.32
  PF=0.0 (0% wins)
CONTROL_G_EXECUTION_MATRIX=PASS (26/26 hand-calculated checks)
CONTROL_H_METRICS_MATRIX=PASS (hand-calc + independent implementations + real-data units)
CONTROL_I_INDEPENDENT_ENGINE=PASS
  N=791
  MATCHES=791 (100%; 641 PO3 + 150 LEGACY-H2; 13 fields/trade)
CONTROL_J_COMMON_SAMPLE=PASS
  BASE_N=93
  STRESS_N=92
  INTERSECTION_N=86
  BASE_COMMON_EV=+0.5455R
  STRESS_COMMON_EV=+0.4759R
  (native PF 1.3187 / 1.5321 reproduced exactly)
  TEST04_PF_INCREASE_CAUSE=SAMPLE_SELECTION_EFFECT
CONTROL_K_CAUSALITY=PASS
DATA_INTEGRITY=PASS (108 partitions; 209,682,628 rows; monotonic; bid<=ask; SHA spot-checks OK)

CAN_LAB_DETECT_KNOWN_POSITIVE_EDGE=YES
CAN_LAB_DETECT_KNOWN_NEGATIVE_EDGE=YES
CAN_LAB_RETURN_NO_EDGE_FOR_RANDOM=YES
CAN_LAB_DETECT_LOOKAHEAD_ORACLE=YES
EXECUTION_ENGINE_VALIDATED=YES
METRIC_ENGINE_VALIDATED=YES
CAUSALITY_GUARDS_VALIDATED=YES
STRESS_COMMON_SAMPLE_VALIDATED=YES

2019_PLUS_ACCESSED=NO
PROTECTED_OOS_ACCESSED=NO

FINAL_STATUS=LAB_PASS
```
