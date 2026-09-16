# LST_OPR_CANONICAL_V2 — RESULTS (internal historical test, 2020-2025)

SPEC=LST_OPR_CANONICAL_V2_FROZEN_SPEC.md (committed BEFORE PnL: 391d4ad)
DATA=existing E:\ NQ ohlcv-1m -> 5m/15m/1h. 2026 SEALED. No new purchase.
COSTS=unit-audited: NORMAL 1.5 pts RT ($30) primary, STRESS 3.0 pts ($60).
CLASSIFICATION=internal historical test; no pristine OOS subperiod.
ENGINE=lst_v2_lib.py; causality tests 9/9 PASS (completed-bars-only H1/OPR/M5,
retest-after-confirmation, next-open entries, no-future stops/targets, GAP
aborts, 2R/opposite-boundary targets, cycle reform, RR gate, runaway cancels).

## ELIGIBILITY FUNNEL (no width filter in V2)

  1296 directional days (BULL 786 / BEAR 510); NEUTRAL 252 = no trade.
  A: 737 confirmed breakouts -> 314 cancelled by 1-ATR runaway,
     58 obstacle-1R rejects -> 278 executed trades.
  B: 863 reintegrations -> 256 cancelled by +1R runaway, 179 RR<2 rejects
     -> 102 executed trades.
  C: first valid entry wins -> 371 executed trades.

## RESULTS (NORMAL cost; USD = points x 20 = ticks x 5)

                     A_BREAKOUT_PULLBACK   B_REINTEGRATION    C_COMBINED
TRADES               278                   102                371
TRADES_PER_WEEK      0.898                 0.329              1.198
GROSS_PTS_PER_TRADE  -1.16                 +0.67              -0.74
NET_POINTS_PER_TRADE -2.66                 -0.83              -2.24
NET_TICKS            -53.2                 -16.5              -44.9
NET_USD_PER_NQ       -$53.18               -$16.52            -$44.85
PF                   0.823                 0.955              0.860
EXPECTANCY_R         -0.320                -0.107             -0.269
WIN_RATE             0.277                 0.245              0.267
AVG_WIN_R / AVG_LOSS_R  +1.62 / -1.09      +1.75 / -1.13      +1.64 / -1.10
STRESS_POINTS        -4.16                 -2.33              -3.74
STRESS_PF            (neg)                 (neg)              (neg)
REMOVE_BEST_1%       -4.38                 -2.28              -3.96
MAX_DD_R             -107.9                -33.4              -125.9
MAX_DD_POINTS        -1135.5               -407.8             -1297.8
MAX_DD_USD_1NQ       -$22,710              -$8,155            -$25,955
LONG / SHORT         168 (-2.10) / 110 (-3.51)   57 (+1.7) / 45 (-3.8)   224 / 147
EXITS                STOP 199 / 2R 78 / EOD 1   STOP 76 / TGT 24 / EOD 2   mixed
BY_YEAR (pts)        2020 -3.52 | 2021 -9.87 | 2022 +15.87 | 2023 -6.54
                     2024 -9.98 | 2025 -3.03   (only 2022 positive)
B years              2020 +1.50 | 2021 -5.18 | 2022 +8.66 | 2023 -1.00
                     2024 -5.43 | 2025 -5.50   (only 2020/2022 positive)

DIAGNOSTICS (2O, report-only): negative in essentially every OPR-width/ATR/
flow-strength quartile, both sides, every entry bucket; every fold negative
(2020-21, 2022-23, 2024-25 all negative for A and C). Full JSON:
results/lst_v2_results.json.

## ANALYSIS (no tuning performed, mechanisms only)

* A's 2R geometry needs WR >= 33.3% before costs to break even; observed
  27.7% (and 24.8% for B on its own target geometry) — the canonical
  breakout-retest on the FIRST-15-MINUTE NQ range carried by an H1 EMA filter
  does not deliver the Masterclass's claimed completion rate on modern
  2020-2025 real futures data at 5m resolution.
* B is ~flat gross (+0.67 pts) and dies on costs; its +1R-cancel removes many
  of the would-be winners (256 cancels vs 102 trades).
* Consistency with the lab: the POSITIVE OPR candidate (P000) used the
  PREMARKET 04:00-09:30 range with retest + trim/BE/EMA8 management — not the
  first-15-minute OPR. The first-15m canonical automation is negative in this
  sample. That contrast is an observation, not a rescued variant.

## VERDICT

FINAL_STATUS=NO_USEFUL_LST_OPR_CANONICAL_EDGE

No candidate frozen. No rescue. No rule changes. 2026 never accessed.

2026_ACCESSED=NO | NEW_DATA_PURCHASED=NO
HIGH_RES_VALIDATION_RECOMMENDED=NO (no candidate to validate)
