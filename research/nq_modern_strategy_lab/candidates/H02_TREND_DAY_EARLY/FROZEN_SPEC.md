# FROZEN_SPEC — H02_TREND_DAY_EARLY (STATUS=FROZEN_CANDIDATE)

STRATEGY_ID=H02_TREND_DAY_EARLY
DATE_FROZEN=2026-09-16
2026_ACCESSED=NO
MECHANISM=Trend-day early detection. The opening auction and first half-hour
set directional repricing; sessions whose first 30 minutes combine strong
directional efficiency with above-normal range expansion continue into a trend
because institutional execution programs and late chasers persist all morning.
TIMEFRAME=5m (bucket-START labels), real CME NQ (GLBX.MDP3 NQ.v.0, unadjusted)
SESSION=RTH [09:30, 16:00) America/New_York (real DST)
ENTRY=
  Decision at the CLOSE of the 10:00 bar (first 30m completed):
    eff30 = (close_10:00 - open_09:30) / (max high - min low of 09:30-10:00)
    range30 = (max high - min low of 09:30-10:00)
    IF |eff30| >= 0.6 AND range30 >= 0.5 x ATR14(prior days, causal):
       side = sign(eff30); fill = NEXT bar open (market-at-signal)
  One trade/day, one base position, no pyramiding/averaging.
STOP=hard stop at the opposite 09:30-10:00 extreme (long: min low; short:
  max high); intrabar touch fills at the stop, worse open on gap.
EXIT=chandelier trail on the runner: highest high since entry - 1.0 x ATR14
  (long; symmetric short), exit on 5m CLOSE crossing the trail; mandatory EOD
  flatten at the last RTH bar close. No profit target (trend mechanism).
PARAMETERS=eff_thr=0.6; range_thr=0.5 ATR; trail_k=1.0 (preregistered cells:
  H01 eff 0.4 = near-miss; H02 eff 0.6 = candidate)
COST_MODEL=MODELED_EXECUTION, RT per contract: LOW 0.75 / NORMAL 1.5 /
  STRESS 3.0 pts ($3.75/$7.50/$15.00). 1 pt = $5. 2020-2025 internal sample.
DISCOVERY_METRICS(2020-2021)=net/trade +0.36 pts (flat; 2020 is a NEGATIVE
  year for this mechanism: -17.7 pts/trade)
2022_2023_METRICS=+27.98 pts/trade | 2024_2025_METRICS=+15.40 pts/trade
POOLED_2020_2025(NORMAL)=N=226, 0.73 tpw, +15.07 pts/trade ($75.36), PF 1.284,
  WR 48.7%, EXP_R +0.069, remove-best1% +4.31, STRESS +13.57 (PF 1.252),
  LOW +15.82
BY_YEAR=2020 -17.74 | 2021 +12.12 | 2022 +40.57 | 2023 +15.04 | 2024 -4.76 |
  2025 +38.02 (4/6 positive; concentration 49% of annual-mean sum)
MAX_DD=-6626 USD (1 contract, NORMAL, trade-sequence peak-to-trough)
FREQUENCY=0.73 trades/week (226 trades / 6y)
CORRELATION_WITH_OTHER_CANDIDATES=daily PnL corr: OPR +0.27, O01 +0.16;
  weekly ~0.01-0.16 (independent mechanisms)
SOURCE=../families.py H02 (entry), ../lab_lib.py (engine, causality-tested),
  ../results_lab.json + candidates/H02_res.json (results)
LIMITS=internal temporal blocks, NOT pristine OOS (only 2026 is sealed);
  2020 negative year (covid vol regime); modeled execution (OHLCV-1m);
  DISCOVERY fold ~flat — the edge concentrated 2021-2025.


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
