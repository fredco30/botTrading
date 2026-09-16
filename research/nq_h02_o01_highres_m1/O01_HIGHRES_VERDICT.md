# O01_ON_TRANSFER — HIGH-RES EXECUTION VERDICT (BBO-1s, 2020-2025)

STATUS=O01_HIGHRES_VALIDATED (frozen; no retuning; H02 NOT started)
AUTHORIZATION=O01 BBO-1s ONLY, ceiling USD 2.00. Actual downloads 133/133
windows (35.8 MB) in highres/bbo_1s_o01/, each window delivered exactly once;
per-window get_cost identity => O01_BBO1S_ACTUAL_COST_USD=1.5685 (ceiling kept).
INCIDENT LOGGED: the first download run wrote into the shared P000 folder due
to a path-patch bug; stopped at 25 files; 0 P000 files corrupted (sha256 all
intact — 4 same-name windows were skipped, not overwritten); 21 O01 files moved
to the correct folder and 4 collision days re-downloaded into it. No P000 data
integrity loss. 2026 never accessed.

## Frozen vs BBO replay (133 trades)

                      FROZEN_1M    BBO_L1_BASE   L1_CONSERV   L1_STRESS
N                     133          133           133          133
NET_POINTS/TRADE      +14.3083     +13.3853      +12.8853     +10.8853
NET_USD_1NQ           +$286.17     +$267.71      +$257.71     +$217.71
PF                    1.515        1.467         1.444        1.357
WIN_RATE              0.256        0.256         0.256        0.256
EXPECTANCY_R          +0.063       +0.007        -0.042       -0.237
STRESS (pts)          +12.81       +10.89        n/a          n/a
REMOVE_BEST_1%        +12.06       +11.14        +10.64       +8.64
MAX_DD_USD            -$12,250     -$12,285      -$12,615     -$13,935
YEARS POSITIVE        5/6          5/6           5/6          5/6

EXECUTION_EDGE_DECAY_POINTS=0.923  (14.3083 -> 13.3853)
EXECUTION_EDGE_DECAY_PERCENT=6.4%

SPREAD_MEDIAN=0.50 pt  SPREAD_P95=1.00  SPREAD_P99=1.93
ENTRY_DELTA_MEDIAN=0.25 pt  ENTRY_DELTA_P95=1.00
EXIT_DELTA_MEDIAN=0.50 pt   EXIT_DELTA_P95=5.75 (tail rides exit through
wide-spread moments; median remains half a tick)

BY_YEAR (L1_BASE net pts/trade):
2020 -13.00 | 2021 +28.24 | 2022 +42.18 | 2023 +9.32 | 2024 +21.10 | 2025 +3.67

## AMBIGUITY

131/133 BBO_RESOLVED. 2 ambiguous (1.5%), both resolved CONSERVATIVELY via
frozen-price fallback: 1 NO_QUOTE_60S_ENTRY, 1 STOP_NEVER_TOUCHED_BBO
(no BBO bid touched the stop within the frozen bar -> fallback). Neither can
plausibly flip a +13.4 pt/trade edge. MBP-1 not needed (and not authorized).

## GATE CHECK (mission section 8) — ALL PASS

NET_EXPECTANCY>0 (+13.39) | PF>=1.15 (1.467) | STRESS>0 (+10.89)
REMOVE_BEST>0 (+11.14) | multi-year credible (5/6, decay uniform)
no execution artifact explains the result (decay 0.92 pt = observed spread
+ bid/ask crossing; the candidate's trend amplitudes dominate it)

## VERIFICATION

10/10 execution tests PASS (long/short market entries, long/short stops,
chandelier close-based exit, EOD, no pre-activation fill, slippage direction,
spread decomposition, pts/ticks/USD identity, 2026 guard). Manual traces
3 LONG + 3 SHORT from raw BBO records to net PnL (results/o01_manual_traces.txt).

FINAL_STATUS=O01_HIGHRES_VALIDATED
2026_REQUESTED=NO / 2026_ACCESSED=NO / STRATEGY_CHANGED=NO /
NEW_STRATEGY_SEARCH=NO / H02_NOT_STARTED (waits for separate human decision)
