# F08_LONGITUDINAL_M1 — FINAL REPORT

FINAL_STATUS = **NO_PERSISTENT_MULTIYEAR_EDGE** → STOP (mission 9)

FROZEN_SPEC_COMMIT = 482c02c (AUTONOMOUS_EDGE_DISCOVERY_M1 frozen spec;
branch research/f08-longitudinal-m1 branched FROM that exact commit — the
frozen feature `make_feat(180,2)` / `sign_both` and frozen replay engine were
imported verbatim, zero rule changes).
FEATURE_CAUSALITY = PASS — gate re-run on UNSEEN 2010 data before replay:
T1 max-input-ts <= decision T, T2 truncation identity, T3 future-mutation
identity (24 firing signals tested).

Periods (mission 3 labels):
- 2010–2016: UNSEEN_BY_F08_SELECTION
- 2017: DISCOVERY / CONTAMINATED (known result: N=259, +1.615 PIPS, PF 1.455,
  expR +0.1077 R, 10/12 months)
- 2018H1: FAILED CONFIRMATION / CONTAMINATED (known result: N=133, −2.436
  PIPS, PF 0.614, expR −0.162 R, 1/6 months)

## YEAR BY YEAR — baseline native (all values: PIPS unless marked R; DD in R)

| Year | N  | Trd/Mo | MEAN  | TOTAL  | PF    | EXP_R   | WR%  | LONG_R  | SHORT_R | PosMon | MaxDD_R | MaxConsecLoss | REMOVE_BEST | STRESS_COMMON_EV (PF) |
|------|----|--------|-------|--------|-------|---------|------|---------|---------|--------|---------|---------------|-------------|-----------------------|
| 2010 | 415 | 34.6 | −1.056 | −438.1 | 0.856 | −0.0704 | 47.2 | −0.1141 | +0.0770 | 4/12  | 40.31 | 8 | −1.313 | −1.534 (0.800) |
| 2011 | 180 | 15.0 | +0.264 | +47.6  | 1.041 | +0.0176 | 53.9 | −0.0313 | +0.0712 | 7/12  | 13.57 | 5 | +0.099 | −0.667 (0.902) |
| 2012 | 162 | 13.5 | −0.359 | −58.1  | 0.937 | −0.0239 | 47.5 | −0.0880 | +0.0386 | 7/12  | 16.63 | 7 | −0.551 | −1.857 (0.714) |
| 2013 | 172 | 14.3 | +0.301 | +51.8  | 1.061 | +0.0201 | 51.7 | +0.0869 | −0.0550 | 7/12  | 14.37 | 8 | +0.072 | −0.478 (0.910) |
| 2014 | 200 | 16.7 | +0.428 | +85.6  | 1.112 | +0.0285 | 48.5 | +0.0171 | +0.0436 | 8/12  | 5.58  | 6 | +0.281 | −0.749 (0.833) |
| 2015 | 212 | 17.7 | +1.498 | +317.6 | 1.276 | +0.0999 | 53.3 | +0.0430 | +0.1612 | 9/12  | 13.05 | 8 | +0.435 | +0.958 (1.165) |
| 2016 | 256 | 21.3 | −0.713 | −182.5 | 0.870 | −0.0475 | 50.4 | +0.0505 | −0.1456 | 4/12  | 19.99 | 8 | −0.899 | −1.843 (0.694) |

Common-intersection stress is negative in 6 of 7 unseen years (only 2015
positive) — the execution stress test is uniformly destructive.

## AGGREGATE_2010_2016 (primary longitudinal evidence, baseline native)
N=1597 | MEAN_PIPS=−0.110 | TOTAL_PIPS=−176.1 | PF=0.981 | EXPECTANCY_R=−0.0074
WIN_RATE=49.97% | POSITIVE_YEARS=4/7 | POSITIVE_MONTHS=46/84
LONG_R=−0.0272 | SHORT_R=+0.0208 | REMOVE_BEST_1PCT=−0.400 PIPS
STRESS_COMMON: N=1583, EV=−0.978 PIPS (−0.0652 R), PF=0.844, 1/7 positive years
MAX_DD_R=45.09 | MAX_CONSEC_LOSSES=8

## KNOWN_2017 (discovery/contaminated)
MEAN_PIPS=+1.615 | PF=1.455 | EXPECTANCY_R=+0.1077

## KNOWN_2018H1 (failed confirmation/contaminated)
MEAN_PIPS=−2.436 | PF=0.614 | EXPECTANCY_R=−0.162

## AGGREGATE_2010_THROUGH_2018H1 (all known trades, baseline native)
N=1989 | TOTAL_PIPS≈−81.8 | MEAN_PIPS≈−0.041 | PF≈0.997 | EXPECTANCY_R≈−0.006
(computed from pooled per-period totals: −176.1 / +418.3 / −324.0 PIPS)

## CLASSIFICATION (mission 8 vs 9)
- Aggregate 2010–2016 mean is negative (−0.110 PIPS), PF 0.981 < 1.10,
  expectancy −0.007 R, remove-best NEGATIVE (−0.400 PIPS).
- Stress-common is materially negative (−0.978 PIPS, PF 0.844).
- Profitability is not just "some losing years": only 1 of 7 unseen years
  (2015) exceeded PF 1.10; the 2017 discovery result is the single outlier
  of nine periods and its immediate neighbor reversed sign.
- LONG and SHORT expectancy flip signs across years (no stable side either).

→ **NO_PERSISTENT_MULTIYEAR_EDGE.** The 2017 discovery result (+1.6 PIPS,
PF 1.46) does not survive multi-year validation: across 2010–2016 the exact
frozen strategy is indistinguishable from zero before stress and clearly
negative under the frozen stress. No tuning was performed and none is
permitted after this verdict.

## GOVERNANCE
2018_H2_ACCESSED=NO
2019_PLUS_ACCESSED=NO
PROTECTED_OOS_ACCESSED=NO
RULES_CHANGED=NO
PARAMETER_SEARCH=NO
No previous PRs merged; no prior artifacts modified.
