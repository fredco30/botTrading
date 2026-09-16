# NQ P000 HIGHRES M1 — FINAL VERDICT (BBO-1s replay, 2020-2025)

AUTHORIZATION=human-approved BBO-1s ONLY, ceiling USD 4.00 (actual download
66.7 MB / 420 windows; per-window get_cost identity => BBO1S_ACTUAL_COST_USD=3.128).
NO MBP-1 / TBBO purchased. No strategy change. 2026 never accessed.

## Frozen vs BBO replay (420 trades, NORMAL-equivalent fees unless stated)

                         FROZEN_1M    BBO_L1_BASE   L1_CONSERVATIVE  L1_STRESS
N                        420          420           420              420
NET_POINTS/TRADE         +2.994       +1.169        +0.768           -1.133
NET_USD_1NQ              +$59.88      +$23.38       +$15.36          -$22.67
PF                       1.366        1.114         1.073            0.903
WIN_RATE                 0.414        0.436         0.429            0.388
REMOVE_BEST_1%           +1.74        -0.09         -0.49            -2.39
MAX_DD_USD               -$4,845      -$7,862.5     -$8,232.5        -$14,870
YEARS POSITIVE           6/6          3/6           3/6              2/6

EXECUTION_EDGE_DECAY_POINTS=1.825  (2.994 -> 1.169, L1_BASE)
EXECUTION_EDGE_DECAY_PERCENT=60.9%

SPREAD_MEDIAN=0.50 pt   SPREAD_P90=0.75   SPREAD_P95=1.00   SPREAD_P99=2.00
ENTRY_DELTA (adverse vs frozen fill): median 0.75 pt, P95 4.01
EXIT_DELTA  (adverse vs frozen fill): median 0.25 pt, P95 0.75

BY_YEAR (L1_BASE net pts/trade):
2020 -0.121 | 2021 +1.496 | 2022 -1.176 | 2023 +0.961 | 2024 +2.312 | 2025 +3.226

## AMBIGUITY

BBO_RESOLVED_TRADES=406
BBO_AMBIGUOUS_TRADES=14  (12 TRIM_QUEUE_UNCERTAIN, 2 ENTRY_NEVER_MARKETABLE)
AMBIGUOUS_FRACTION=0.033
MBP1_AMBIGUITY_LIST.csv written. Exact MBP-1 estimate for the 14 windows:
MBP1_COST_ESTIMATE_USD=0.9789 (NOT downloaded; requires separate authorization).

## WHY NOT CONFIRMED (mechanism, not noise)

The decay is uniform across ALL 420 trades and every year, driven by
(a) entering at the ASK on stop triggers during the opening drive (median
0.75 pt adverse vs the 1m fill), (b) exiting at the BID, with a 0.5 pt median
spread, and (c) the residual fixed-fee component. The 14 ambiguous trades are
NOT the cause: resolved-only trades average +1.38 pts/trade — far below the
frozen +2.99 and below the PF 1.15 gate. Event-level MBP-1 resolution could
refine 14 trim/entry cases but cannot plausibly recover a ~1.8 pt/trade
structural spread/trigger cost paid on every single trade.

## GATE CHECK (mission section 22)

NET_EXPECTANCY>0        L1_BASE PASS (+1.17) / CONSERVATIVE PASS (+0.77)
PF>=1.15                FAIL (1.114 / 1.073)
STRESS_EXPECTANCY>0     FAIL (-1.13)
REMOVE_BEST_1_PERCENT>0 FAIL (-0.09)
multi-year credible     FAIL (3/6 negative years at BASE)
=> P000_HIGHRES_EDGE_NOT_CONFIRMED

## VERIFICATION (section 28)

10/10 execution-causality tests PASS (bid/ask side correctness long/short
entries, long/short stops, market exits, no pre-activation fills, trim queue
conservatism, slippage signs, fee tiers, pts/ticks/USD identity, 2026 guard).
Manual raw-record traces 3 LONG + 3 SHORT documented (triggers, first eligible
quotes, proven passive fills, BE-at-ask for shorts, one sell-stop price
improvement). Data quality note: Databento flags 2025-11-28 as degraded
quality (one window).

FINAL_STATUS=P000_HIGHRES_EDGE_NOT_CONFIRMED
The frozen candidate stays frozen; its 1m status is downgraded from
FROZEN_CANDIDATE to NOT CONFIRMED UNDER REALISTIC TOP-OF-BOOK EXECUTION.
2026_ACCESSED=NO | STRATEGY_CHANGED=NO | NEW_STRATEGY_SEARCH=NO
