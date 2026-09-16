# FINAL REPORT — NQ_MODERN_STRATEGY_LAB (+ NQ_OPR_MODERN_M1)

DATE=2026-09-16 | PERIOD=2020-2025 (real CME NQ, Databento GLBX.MDP3 NQ.v.0)
2026_ACCESSED=NO | ADDITIONAL_DATA_PURCHASED=NO | LIVE_TRADING=NO
DATA_SPEND_DISCLOSURE=initial quoted estimate of $0.08 was a unit bug in our
  estimate script (API returns dollars); actual total = $7.73, disclosed and
  documented mid-campaign (see nq_opr_modern_m1/COST_GUARD_REPORT.md).

FAMILIES_TESTED=15 (A..O)
EXPERIMENTS=29 of 100 (27 preregistered + 2 near-miss robustness waves)
OPR_STATUS=NQ_OPR_MODERN_CANDIDATE (frozen #1)
FROZEN_CANDIDATES_COUNT=3

#1 NQ_OPR_MODERN_M1  — +2.99 pts/trade, PF 1.366, 420 trades (1.33 tpw),
   stress +1.49, 6/6 positive years, maxDD -$1211/contract, boot95 p=0.012
#2 H02_TREND_DAY_EARLY — +15.07 pts/trade, PF 1.284, 226 trades (0.73 tpw),
   stress +13.57, 4/6 positive years, maxDD -$6626/contract
#3 O01_ON_TRANSFER — +14.31 pts/trade, PF 1.515, 133 trades (0.43 tpw),
   stress +12.81, 5/6 positive years, maxDD -$3062/contract
CORRELATIONS (daily): OPR-H02 +0.27 | OPR-O01 -0.13 | H02-O01 +0.16
  (weekly ~0) => independent mechanisms; no portfolio constructed (per brief).

REJECTED_FAMILIES=A,B,C,C',E[G wave],F[G wave],G,I,J,K,L,M,N — see
  REJECTED_FAMILIES.md. ALL reversion/fade/sweep/failed-auction families lost
  after costs; ALL surviving mechanisms are CONFIRMED-REPRICING CONTINUATION
  (retest, early efficiency, overnight transfer). Raw level-breaks lose; the
  confirmation filter is the edge.

METHODOLOGY=mechanism-first, cells preregistered before PnL, one
  causality-tested engine (9/9 unit tests + raw-bar spot checks), pessimistic
  same-bar rule, market-at-next-open fills, EOD flatten, no pyramiding,
  conservative preregistered frictions, dead-family rule enforced, near-miss
  waves limited to one per family.
LIMITATIONS=internal temporal blocks (2022-2025 not pristine OOS); modeled
  OHLCV-1m execution; 2020 negative for H02/O01; frequency 0.43-1.33 tpw.

NEXT STEPS (separate missions, not run here):
  1. all three candidates face the SAME untouched 2026 as final external test;
  2. HIGH_RES_VALIDATION_RECOMMENDED=YES (BBO-1s on signal days) — requires
     explicit authorization before any purchase;
  3. optional MNQ deployment study.

FINAL_STATUS=ONE_OR_MORE_NQ_STRATEGIES_FROZEN
STOP.
