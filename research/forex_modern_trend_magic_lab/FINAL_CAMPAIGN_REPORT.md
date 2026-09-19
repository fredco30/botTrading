# FOREX_MODERN_STRATEGY_LAB_M1 — FINAL CAMPAIGN REPORT

```
BRANCH              = research/forex-modern-trend-magic-lab-m1
HEAD_SHA            = (see git log; final commit of this file)
PERIOD              = 2020-01-01 .. 2025-12-31
2026_ACCESSED       = NO   (hard seal in tmlab.load_5m, tested; parquet store
                            physically contains 2026 bars — never returned)
CAPITAL_EUR         = 500
LIVE_TRADING        = NO
```

```
TREND_MAGIC_SOURCE_VERIFIED        = YES (pine-facade, open_no_auth, MPL-2.0,
                                     sha256 82de45d0..., input defaults cross-
                                     checked against official page metadata)
TREND_MAGIC_IMPLEMENTATION_VERIFIED= YES (30/30 fidelity+causality tests,
                                     frozen at cd221b1 before any PnL)
TREND_MAGIC_EVENT_STUDY_RESULT     = NO_EDGE (45 cells, 0 significant positive,
                                     6 significant negative; MFE~=|MAE|)
TREND_MAGIC_STRATEGY_RESULT        = DEAD (state filter adds no information vs
                                     unconditional baseline control)
```

```
FAMILIES_TESTED          = 6 distinct families (Trend Magic flips/filter,
                           multi-TF momentum, PDH/PDL break+reject,
                           session momentum, London false break)
MEANINGFUL_EXPERIMENTS   = 14 ledger entries (EXPERIMENT_LEDGER.csv)
FROZEN_CANDIDATES_COUNT  = 1
```

## Frozen candidate: FX_PDH_001

```
STRATEGY_ID   = FX_PDH_001
MECHANISM     = prior-day-high upside continuation
PAIR_OR_PAIRS = USDJPY (long only — measured asymmetry)
TIMEFRAME     = H1
SESSION       = none (24h)

TRADES        = 615          TRADES_PER_WEEK = 1.96
NET_PIPS_PER_TRADE = +5.22   NET_R_PER_TRADE = +0.30R
NET_EUR_PER_TRADE_AT_REALISTIC_SIZE = ~EUR 0.90 (0.01 lot, median stop)
PF = 1.37   WIN_RATE = 0.293   EXPECTANCY_R = +0.30
NORMAL_COST_RESULT = +5.22 net pips/trade
STRESS_COST_RESULT = +3.59 net pips/trade (PF 1.24, t +1.72)
REMOVE_BEST_1_PERCENT = +2.79 net pips/trade
MAX_DD_PERCENT_500EUR = 14.3 (0.5% risk) / 26.3 (1.0% risk)
MAX_DD_EUR_500EUR     = EUR 102 (0.5%) / EUR 180 (1.0%)

MIN_LOT = 0.01   NORMAL_STOP_PIPS = 17.2 median
RISK_EUR_AT_MIN_LOT = 1.40   RISK_PERCENT_AT_MIN_LOT = 0.28% (p90 0.48%)
MARGIN_COMPATIBLE_WITH_500 = YES (~EUR 85-128 at 0.03 lots, SCENARIO - NOT
                             BROKER VERIFIED)
REALISTIC_WITH_500_EUR = YES (no losing year; equity 500->913 at 0.5% risk)

2020 = +0.4   2021 = +4.3   2022 = +18.8   2023 = +5.3   2024 = +1.1   2025 = +1.7
DISCOVERY_2020_2021  = +4.3 blended net pips/trade (2020 flat)
VALIDATION_2022_2023 = +12.1 blended (best regime)
REPLICATION_2024_2025 = +1.4 blended (DECAY warning)
STATUS = FROZEN_CANDIDATE
```

Warnings recorded in candidates/FX_PDH_001/RESULTS.md: single-pair single-side
design; 2022 contributes ~60% of net pips; wide-stop plateau gradient
(default kept primary per protocol 24); 2025 barely clears costs. The sealed
2026 test is the real confirmation gate.

```
REJECTED_FAMILIES   = 5 (Trend Magic flips, Trend Magic filter, multi-TF
                        momentum, PDH/PDL rejection, session momentum +
                        London false break)  — see REJECTED_FAMILIES.md
ARCHIVED_NEAR_MISSES = 0 (Trend Magic B1-B5 gated pre-backtest, not a near miss)
CANDIDATE_CORRELATIONS = n/a (1 candidate; section 32 requires >= 2)
```

```
FINAL_STATUS = ONE_OR_MORE_500EUR_FOREX_STRATEGIES_FROZEN
```

## What was learned (for the next campaign)

1. The baseline-control gate is the single most valuable methodological
   upgrade of this campaign: it killed Trend Magic's filter hypothesis in
   one cheap experiment and would have killed the multipair-swing-era
   families for a fraction of their budget.
2. Modern-FX drift lives in USDJPY carry-aligned upside continuation
   (2021-2024), not in indicator state changes or session folklore.
3. FX_PDH_001's edge decays with the carry regime (2025 flat). A 2026
   confirmation test must precede any deployment thought.
4. Untested families remaining in budget (for a possible M2):
   volatility compression->expansion (S003 variant caveats), prior-day
   level REJECTION with n>=100 redefinition, NY-session variants of F05,
   carry differential x trend alignment (K), cross-pair confirmation (M).

## Credit discipline note

Per protocol sections 25/30/35: three families were killed at the screen
stage without running their entry backtests; Trend Magic B1-B5 were gated
out by two cheap experiments; no dead hypothesis was audited twice.
