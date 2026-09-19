# FX_PDH_001 STRICT — CROSS-PAIR REPLICATION RESULTS

```
MISSION            = CROSS-PAIR REPLICATION / GENERALIZATION TEST (not discovery)
SOURCE_STRICT_SHA  = 033f6f0c82d8489dc39b52545632c2b09468b9ae (frozen engine, unchanged)
PERIOD             = 2020-01-01 .. 2025-12-31
2026_ACCESSED      = NO (hard seal; last exits Dec-2025 across all pairs)
PAIRS_TESTED       = 6 (EURUSD GBPUSD USDJPY EURJPY GBPJPY EURGBP)
COSTS              = pre-registered conservative table (COST_ASSUMPTIONS.md),
                     sourced from validated fx_currency_network_m1 research.
                     MODELED_EXECUTION (BID-only local stores).
ENGINE CONTROL     = USDJPY reproduces STRICT V1 EXACTLY
                     (N 639 / PF 1.379 / +4.90 / stress +3.82 / rb1 +2.54 /
                     t +2.52 / by-year identical; 7/7 control tests PASS).
                     Sizing-layer equity differs by ~EUR 1 (944 vs 943)
                     because the replication runner values the JPY pip at
                     the USDJPY close BEFORE the entry bar (more causal);
                     engine PnL is untouched.
```

## Per-pair strict results (NORMAL costs; STRESS in its own column)

| pair | N | /wk | NET pips/tr | PF | STRESS | rb1% | t | maxDD_R | TOTAL pips |
|--------|-----|------|--------|-------|--------|-------|-------|-------|---------|
| EURUSD | 642 | 2.05 | **-1.08** | 0.893 | -2.05 | -2.54 | -0.93 | 118.5 | -691 |
| GBPUSD | 645 | 2.06 | **-0.50** | 0.962 | -1.33 | -2.85 | -0.31 | 77.7 | -325 |
| USDJPY | 639 | 2.04 | **+4.90** | 1.379 | +3.82 | +2.54 | +2.52 | 47.4 | +3130 |
| EURJPY | 671 | 2.14 | **+2.08** | 1.143 | +0.83 | -0.51 | +1.12 | 38.6 | +1395 |
| GBPJPY | 671 | 2.14 | **-0.12** | 0.994 | -0.81 | -3.69 | -0.05 | 67.1 | -78 |
| EURGBP | 644 | 2.06 | **-0.67** | 0.902 | -1.68 | -2.20 | -0.69 | 173.5 | -430 |

## By year (net pips/trade)

| pair | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | best-yr share |
|--------|-------|-------|--------|-------|-------|-------|------|
| EURUSD | +0.36 | +0.31 | -5.71 | -3.43 | -4.15 | +6.77 | -0.98* |
| GBPUSD | +2.69 | +3.42 | -3.60 | -1.46 | -5.71 | +1.70 | -1.10* |
| USDJPY | -0.17 | +5.01 | +18.78 | +5.75 | -1.14 | +1.78 | 0.61 |
| EURJPY | +0.28 | +1.38 | +1.49 | +4.76 | -3.58 | +8.59 | 0.67 |
| GBPJPY | -3.61 | +3.92 | -0.70 | +9.05 | -2.67 | -5.84 | -12.25* |
| EURGBP | +5.63 | -2.21 | -1.19 | -3.61 | -2.16 | -0.21 | -1.34* |

*share negative because the pair's TOTAL is negative (best year still
smaller than the sum of losses). Reported for completeness, not hidden.

## EUR500 practical gate (0.5% target risk, MIN_LOT 0.01)

| pair | stop med (p10/p90) | risk@0.01 med | rounded lot med | END EQUITY | maxDD% |
|--------|--------------------|---------------|-----------------|-----------|--------|
| EURUSD | 12.9 | 0.29% | 0.01 | 431 (-14%) | 40.5% |
| GBPUSD | 16.9 | 0.38% | 0.01 | 482 (-4%) | 23.4% |
| USDJPY | 17.2 | 0.28% | 0.01 | 944 (+89%) | 15.0% |
| EURJPY | 19.8 | 0.32% | 0.01 | 641 (+28%) | 11.5% |
| GBPJPY | 24.6 | 0.42% | 0.01 | 525 (+5%) | 25.5% |
| EURGBP | 8.2 | 0.24% | 0.02 | 296 (-41%) | 53.1% |

Margin scenarios (0.01-0.02 lots, 1-4k USD notional): ~EUR 2-190 at 1:20-1:30.
SCENARIO - NOT BROKER VERIFIED. All six pairs are mechanically min-lot
compatible (median risk 0.24-0.42% < 0.5% target); compatibility is not the
problem — profitability is.

## Classification (pre-registered gates, CROSS_PAIR_PROTOCOL.md)

```
USDJPY : ROBUST_REPLICATION (reference/discovery pair; = frozen FX_PDH_001)
EURJPY : WEAK_POSITIVE_REPLICATION (NET>0 but PF 1.143 < 1.15, t +1.12,
         rb1 NEGATIVE -0.51; profit years 2023/2025 do NOT match USDJPY's
         2022-heavy pattern)
EURUSD : NO_REPLICATION
GBPUSD : NO_REPLICATION
GBPJPY : NO_REPLICATION (widest spread 2.0; total -78 pips)
EURGBP : NO_REPLICATION (worst R-drawdown 173.5R; equity -41%)
```

```
JPY_PAIRS_POSITIVE     = 2 of 3 (USDJPY, EURJPY)
JPY_PAIRS_ROBUST       = 1 of 3 (USDJPY only)
NON_JPY_PAIRS_POSITIVE = 0 of 3
NON_JPY_PAIRS_ROBUST   = 0 of 3
ROBUST_REPLICATIONS    = USDJPY only (the discovery pair itself)
WEAK_REPLICATIONS      = EURJPY
FAILURES               = EURUSD, GBPUSD, GBPJPY, EURGBP
EUR500_COMPATIBLE_PAIRS = USDJPY, EURJPY (positive-research pairs; all six
                          pass the mechanical min-lot gate)
```

## Generalization pattern

**1_OF_6_REPLICATED** (robustly), plus 1 weak positive echo.

Pattern = **USDJPY_SPECIFIC**, with these diagnostics:

1. The mechanism does NOT exist in EUR/GBP crosses (0/3, all negative net,
   rb1 negative) — prior-day-high upside continuation has no independent
   non-JPY life on 2020-2025 local data under strict costs.
2. The JPY family is split: USDJPY robust, EURJPY weak, GBPJPY negative.
   EURJPY's positive years (2023, 2025) do not coincide with USDJPY's
   dominant 2022 — so it is not simply "JPY carry beta" reproducing; it may
   be a weaker, differently-timeddovish-JPY continuation, but it FAILS the
   robustness gates (rb1 < 0 means the average trade is negative after
   removing the best 1%).
3. Per section 18 (no second-round rescue): EURJPY stays a near miss.
   No candidate directory created for it. No filters, no tuning, no
   session/volatility variants were tried.
4. Correlation analysis (section 17) NOT triggered: requires >= 2 NEW
   robust replications; there are zero.

## Multiple-testing honesty (section 16)

All six results are shown. The one robust replication is the discovery pair
itself — i.e., the campaign found exactly one robust pair-specific edge and
this replication confirms it does not generalize. Any future 2026 test of
FX_PDH_001 STRICT must therefore be understood as a test of a USDJPY-specific
mechanism, not a general FX regularity. The multiple-comparison burden of the
original discovery (3 pairs screened) is modest but nonzero; 2026 remains the
only clean confirmation.

## Reproduction

- Engine: `replay_all.py` (imports the frozen `audit/replay_strict.py`
  unchanged; per-pair constants are the ONLY variation).
- Tests: `test_replay_all.py` — 20/20 PASS (USDJPY engine control 7/7 exact,
  quote-currency pip valuation 5/5, cost accounting incl. no-double-charge,
  2026 seal on all six loaders).
- Data: `CROSS_PAIR_RESULTS.json` (full precision), `CROSS_PAIR_RESULTS.csv`
  (summary table).
```
REPLICATION_STATUS = COMPLETE — 1_OF_6_REPLICATED (USDJPY_SPECIFIC)
NO second-round rescue. NO optimization. NO 2026 access. STOP.
```
