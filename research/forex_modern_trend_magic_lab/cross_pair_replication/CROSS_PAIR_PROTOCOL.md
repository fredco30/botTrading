# FX_PDH_001 STRICT — CROSS-PAIR REPLICATION PROTOCOL

```
MISSION           = CROSS-PAIR REPLICATION / GENERALIZATION TEST
SOURCE_FREEZE_SHA = 033f6f0c82d8489dc39b52545632c2b09468b9ae
REFERENCE         = candidates/FX_PDH_001/FROZEN_SPEC_STRICT_V1.md (authoritative)
PERIOD            = 2020-01-01 .. 2025-12-31        2026_ACCESSED = NO
DATA              = data_raw/parquet/{PAIR}_5m.parquet (validated 5m BID OHLCV),
                    H1 built with the project's causal resample (left-labelled)
PAIRS             = EURUSD GBPUSD USDJPY EURJPY GBPJPY EURGBP (all six, no exclusions)
MODE              = REPLICATION. No redesign, no tuning, no filters, no rescue.
```

## Frozen rule set (identical for every pair — FX_PDH_001 STRICT V1)

```
ATR_PERIOD       = 14 (H1, Wilder RMA, completed bars only)
SIGNAL           = first H1 bar of the UTC day with high > prior COMPLETED
                   UTC day's high; one signal per day; decision at bar close
SIDE             = LONG
ENTRY            = next H1 bar open (fill = open + spread + entry slip)
STOP             = entry_fill - 1.0 x ATR14(signal bar); active from fill;
                   the entry bar CAN stop out
TRAIL            = max(high since entry .. bar i-1) - 3.0 x ATR14(bar i-1)
MAX_HOLD         = 48 H1 bars, time exit at close
TAKE PROFIT      = none
POSITIONS        = one at a time, no pyramiding/averaging/martingale
INTRABAR         = conservative: fill at open if a bar opens through the stop
SAME-BAR RULE    = a bar that exits a position cannot trigger a new entry
```

Per-pair ONLY mechanical quantities change: pip size, pip value/EUR
conversion (quote-currency aware), modeled spread/slippage, margin scenario.

## Engine control (section 10)

USDJPY must reproduce `audit/FX_PDH_001_STRICT_RESULTS.json` EXACTLY
(same engine code object, same data): N 639, PF 1.379, +4.90, stress +3.82,
rb1 +2.54, t +2.52, by-year as frozen. Any mismatch => STOP and report
REPLICATION_ENGINE_MISMATCH before touching other pairs.

## Classification gates (pre-registered, no forcing)

```
ROBUST_REPLICATION   : N >= 100 AND NET > 0 AND PF >= 1.15 AND STRESS_NET > 0
                       AND REMOVE_BEST > 0 AND worst-year >= -3 net pips/trade
WEAK_POSITIVE        : NET > 0 but not all robust gates
NO_REPLICATION       : NET <= 0 or PF < 1
UNUSABLE_WITH_500    : research-positive but min-lot risk > 1% of 500 EUR
                       (median)
```

All six results are reported regardless of outcome. Discovery pair USDJPY is
the reference benchmark; other pairs are cross-pair replication, NOT pristine
external OOS (prior broad PDH/PDL screens may have touched them). 2026
remains the protected temporal confirmation period.

## EUR500 practical gate (section 14)

For research-positive pairs: 0.5% target risk, MIN_LOT 0.01, LOT_STEP 0.01,
quote-currency-aware pip value (USD/JPY/GBP quote handled explicitly),
EUR conversion via sealed EURUSD closes; margin shown as 1:20 / 1:30
SCENARIOS ONLY (not broker-verified).
