# NQ_OPR_MODERN_M1_FROZEN_SPEC — STATUS=FROZEN_CANDIDATE (2026-09-16)

CANONICAL_SOURCE_COMMIT=3122f1ea64aafb2c8952cc01189f9af63ff62f63
CANONICAL_SPEC=research/nq_opr_modern_m1/OPR_CANONICAL_SPEC.md (frozen pre-PnL;
the rules below are that spec, unchanged, with measured results attached)
ENGINE=nq_lib.py (faithful port of p000_lib.py; 9/9 causality tests PASS)
STRATEGY_ID=NQ_OPR_MODERN_M1 / P000A_LEVEL (primary; P000B_VWAP secondary, NOT frozen)

## FROZEN RULES (do not modify — any change = new strategy ID)

TIMEFRAME=5m bars (bucket-START labels), built from real CME NQ ohlcv-1m
SESSION=RTH [09:30, 16:00) America/New_York (real DST)
PREMARKET=[04:00, 09:30) ET; PMH=max high, PML=min low; >=12 pm 5m bars; PMH>PML
BREAKOUT=first 5m CLOSE strictly above PMH (long) / below PML (short), RTH only
RETEST=tap of the level (low/high) after confirmation; day invalidated on any
  5m CLOSE back through the level before entry
ENTRY=stop order at tap-bar extreme (fill worse-open on gap-through); 1 trade/day;
  1 position; one side/day; no pyramiding/averaging/adding
STOP=untrimmed: 5m CLOSE back through level (close-based, wick-immune);
  post-trim: gap-aware breakeven floor
TRIM=50% limit at first new running-day extreme (shifted cummax/cummin, ET day)
RUNNER=5m CLOSE through EMA8 (span 8, adjust=False, continuous series)
EXIT=flatten at last RTH bar (early closes mechanical)
COSTS (RT, 1 contract; 1 pt = $5): LOW 0.75 / NORMAL 1.5 / STRESS 3.0 pts
  ($3.75 / $7.50 / $15.00) — preregistered pre-PnL. MODELED_EXECUTION (ohlcv-1m;
  no tick-exact claims).

## RESULTS ON REAL NQ 2020-2025 (internal temporal blocks — 2026 is the only
## untouched external OOS and remains SEALED)

DISCOVERY_2020_2021 (N=123, 0.99 tpw): NORMAL +2.52 pts ($12.62) PF 1.396
  R +0.244 | STRESS +1.02 PF 1.140 | remove-best1% +1.74 | 2020 +1.02, 2021 +4.10
VALIDATION_2022_2023 (N=144, 1.16 tpw): NORMAL +1.56 pts ($7.79) PF 1.192
  R +0.058 | STRESS +0.06 PF 1.006 (marginal) | remove-best1% +0.91
  | 2022 +1.01, 2023 +2.05
REPLICATION_2024_2025 (N=153, 1.22 tpw): NORMAL +4.72 pts ($23.62) PF 1.485
  R +0.294 | STRESS +3.22 PF 1.305 | remove-best1% +2.79 | 2024 +3.72, 2025 +5.98
POOLED_2020_2025 (N=420, 1.33 tpw): NORMAL +2.99 pts ($14.97) PF 1.366 WR 41.4%
  boot95 CI [+0.72, +5.44] p=0.012 | STRESS +1.49 pts ($7.47) PF 1.164
  MAX_DD_USD_1_NQ=-1211 (NORMAL), -1584 (STRESS) | worst day -$561
BY_YEAR_NET_PTS_NORMAL=2020 +1.02 | 2021 +4.10 | 2022 +1.01 | 2023 +2.05
  | 2024 +3.72 | 2025 +5.98 — ALL SIX YEARS POSITIVE
EXIT_DIAGNOSTICS(pooled NORMAL)=BE_STOP 220 / EMA8 121 / LEVEL_STOP 70 / EOD 9
LONG/SHORT=224/196 (pooled NORMAL net: long ~+5.1, short ~+0.7 — long-dominant,
  short not negative overall; short negative only in 2022-2023 validation)

## GATES (mission section 23) — ALL PASS
positive net expectancy=YES (3/3 folds) | PF>=1.15=YES (1.40/1.19/1.49)
positive stress=YES (fold-wise; 2022-2023 marginal at +0.06)
remove-best positive=YES (3/3 folds) | single-year dependence=NO (6/6 years +)
credible 2022-2025 replication=YES

## STATUS
FINAL_STATUS=NQ_OPR_MODERN_CANDIDATE
2026_ACCESSED=NO
HIGH_RES_EXECUTION_DATA_ACQUIRED=NO (if deployed, BBO-1s replay on signal days
  would be the next execution check — requires separate authorization)
MNQ_NOTE=execution on MNQ ($2/pt) may be tested in a separate deployment study;
  NOT part of this campaign (mission section 26).
KNOWN_LIMITS=modeled execution; 1.33 tpw frequency; 2022-2023 stress ~0 (edge
  compresses in high-vol/chop regimes); short side regime-weak in 2022-2023;
  results are internal temporal blocks, NOT pristine OOS.


---

AUDIT ADDENDUM (2026-09-16, NQ_UNIT_AUDIT — reporting correction only):
The simulation NATIVE UNIT is INDEX POINTS for every quantity (prices, stops,
targets, ATR, EMA, costs: NORMAL=1.5 points=$30 RT, STRESS=3.0 points=$60 RT).
The USD figures printed in this spec were computed with $5 per point (the TICK
value) instead of $20 per point and are therefore 4x UNDERSTATED.
Correct rule: USD_1_NQ = index_points x 20 = ticks x 5.
All verdicts/gates were evaluated in points/PF/R and are UNCHANGED.
Corrected pooled figures: OPR +$59.88/trade (maxDD -$4,845);
H02 +$301.39/trade (maxDD -$26,505); O01 +$286.17/trade (maxDD -$12,250).
