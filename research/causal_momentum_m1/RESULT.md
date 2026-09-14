# CAUSAL_MOMENTUM_M1 — FINAL REPORT

FINAL_STATUS = **NO_CAUSAL_MOMENTUM_CANDIDATE** → STOP (mission 13/19)

BASE_HEAD = 78afc5066f486d6abde44cba75cbee20b1615f25 (LAB_AUDIT_M0 LAB_PASS)
BRANCH = research/causal-momentum-m1 (clean; PR NON-MERGED)
DISCOVERY_START = 2017-01-01T00:00:00Z
DISCOVERY_END = 2017-12-31T23:59:59Z (21,669,401 ticks, validated store)

FEATURE_CAUSALITY_TESTS = PASS (both features, 30 random timestamps each)
- T1 MAX_INPUT_TIMESTAMP: max consumed tick ts <= decision T — PASS
- T2 TRUNCATION: dataset cut exactly at T, signal recomputed identical — PASS
- T3 FUTURE_MUTATION: +50 pips on all prices after T, signal unchanged — PASS
FEATURE_TRACE (mission 17): 20 signals/hypothesis in feature_trace.json;
assert MAX_FEATURE_INPUT_TS <= DECISION_TS PASS for all 40.
Lookback clock hours: H1 = 4.00..4.001 (true 4-clock-hour rolling).
H2 = 16.02..63.30 (4 completed H4 slots; >16h values are weekend effects,
honestly labelled ~16h H4-close momentum).

PARAMETERS (mission 10, no search): threshold 10p, SL 15p, TP 15p,
time exit 120 min, entry wait 30s after 5s (30s stress) delay. 1R = 15 pips.

## H1_MOM4H_ROLLING (baseline native, 2017)
N=3594 COUNT | trades/month=299.5
MEAN_PIPS=-0.428 | MEDIAN_PIPS=-1.0 | TOTAL=-1539.3 PIPS
PF=0.923 | EXPECTANCY_R=-0.0286 R | WIN_RATE=47.36 PERCENT
POS_MONTHS=3/12 | LONG_R=-0.0036 R | SHORT_R=-0.0567 R
REMOVE_BEST_1PCT=-0.647 PIPS | CI95 expectancy=[-0.0565, -0.0001] R
maxDD=115.15 R | max consec losses=11 COUNT
STRESS_NATIVE: N=3555, mean=-1.393 PIPS, expR=-0.0929 R, PF=0.769
COMMON SAMPLE: INTERSECTION_N=2356 (BASE_N=3594, STRESS_N=3555)
  BASE_COMMON_EV=-0.564 PIPS (-0.0376 R), PF=0.896
  STRESS_COMMON_EV=-1.385 PIPS (-0.0924 R), PF=0.764
GATE (mission 12): FAIL — mean<+0.75p, PF<1.20, expR<+0.05, total<=0,
pos_months<8, remove_best<=0, STRESS_COMMON_EV<0.

## H2_MOM16H_H4_COMPLETED (baseline native, 2017)
N=3573 COUNT | trades/month=297.75
MEAN_PIPS=-0.354 | MEDIAN_PIPS=-0.7 | TOTAL=-1265.9 PIPS
PF=0.933 | EXPECTANCY_R=-0.0236 R | WIN_RATE=47.91 PERCENT
POS_MONTHS=3/12 | LONG_R=+0.0103 R | SHORT_R=-0.0598 R
REMOVE_BEST_1PCT=-0.534 PIPS | CI95 expectancy=[-0.0503, +0.0025] R
maxDD=127.54 R | max consec losses=12 COUNT
STRESS_NATIVE: N=3545, mean=-1.345 PIPS, expR=-0.0896 R, PF=0.768
COMMON SAMPLE: INTERSECTION_N=1681 (BASE_N=3573, STRESS_N=3545)
  BASE_COMMON_EV=-0.260 PIPS (-0.0173 R), PF=0.950
  STRESS_COMMON_EV=-1.151 PIPS (-0.0768 R), PF=0.795
GATE (mission 12): FAIL — mean<+0.75p, PF<1.20, expR<0.05 (native), total<=0,
pos_months<8, LONG>0 but SHORT<0, remove_best<=0, STRESS_COMMON_EV<0.

## INTERPRETATION (factual, no rescue attempted)
Both strictly causal momentum signals perform at or below random-entry
level net of costs (LAB_AUDIT_M0 control D measured random entries at
~-0.5 PIPS ≈ spread; H1/H2 here: -0.43/-0.35 PIPS baseline native).
The PR #42 candidate's apparent +2.4..+2.8 PIPS/trade was produced by the
bucket-final-close lookahead (up to 239 min of future price) and disappears
completely under strict causality. Common-sample stress is strictly worse
than baseline on the identical trade subset (no sample-selection artifact).
Per mission 19: no inversion, no H3, no filters, no parameter search
(0 experiments beyond the 2 specified hypotheses).

## GOVERNANCE
2018_ACCESSED_BEFORE_FREEZE=NO (2018 never accessed at all: zero hypotheses
passed the discovery gate, so no freeze was created and confirmation was
not run — mission 13).
2019_PLUS_ACCESSED=NO
PROTECTED_OOS_ACCESSED=NO
PARAMETER_SEARCH_EXECUTED=NO
RULES_CHANGED_AFTER_FREEZE=N/A (no freeze; rules never changed after start)
NO_MERGE of PR #42; no historical artifacts modified.

FROZEN_SPEC_COMMIT=NONE (nothing survived to freeze)
SURVIVING_CANDIDATES=NONE
INDEPENDENT_AUDIT=N/A (only required after a confirmation pass)
