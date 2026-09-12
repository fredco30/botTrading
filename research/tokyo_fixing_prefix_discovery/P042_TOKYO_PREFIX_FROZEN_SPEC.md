# P042 — Tokyo Fixing Pre-Fix USD Demand — Discovery (FAIL-FAST, frozen)

Status: FROZEN before execution. One hypothesis, no variants, no optimization.

## Hypothesis

The Tokyo fixing literature documents pre-fix order flow biased toward USD buying
and a predictable price pattern BEFORE the 09:55 JST fixing. We test only this
mechanism. Distinct from the rejected post-fix reversal (P041).

## Frozen rule

- Instrument: USDJPY only.
- Fixing: 09:55 JST (Asia/Tokyo, no DST).
- Trade: LONG USDJPY only.
- ENTRY: OPEN of the 09:50 JST bar (00:50 UTC).
- EXIT:  OPEN of the 10:00 JST bar (01:00 UTC).
- One trade per available FX day. No conditional signal, no stop, no TP, no filter.

## Data

- `data_raw/parquet/USDJPY_5m.parquet` (5-min UTC bars, source 2010+).
- Window: 2010-01-01 → 2019-01-01 EXCLUSIVE. No access to 2019+ prices.
- 2019-2022 reserved for a possible later validation.

## PnL (pips)

- GROSS_PIPS = (exit_open - entry_open) / 0.01
- NET_NORMAL = GROSS - 2  (2 pips round-trip)
- NET_STRESS = GROSS - 4  (4 pips round-trip)

## Metrics (only these)

N_TRADES, GROSS_MEAN, NET_NORMAL_MEAN, NET_STRESS_MEAN, MEDIAN_NET,
WIN_RATE_NET, BY_YEAR_NET, POSITIVE_YEARS, REMOVE_BEST_1_PERCENT_NET,
CI95_NET (day bootstrap, 2000 resamples, seed 42).

## Economic gate — PASS requires ALL of:

1. NET_NORMAL_MEAN >= +2.0 pips/day
2. POSITIVE_YEARS >= 6/9
3. REMOVE_BEST_1_PERCENT_NET > 0
4. NET_STRESS_MEAN > 0

Otherwise: `TOKYO_PREFIX_DISCOVERY_REJECT`.

## Fail-fast

If REJECT: STOP. No variants (09:45/09:55/10:05 entries, other exits, SHORT,
weekday filters, month-end, other pairs, volatility/trend filters, stops/TP,
pyramiding). No further explanation required.

## Bug policy

Fix only bugs that can change the verdict. No cosmetic work.

## Minimal tests

UTC→JST conversion; entry at 09:50; exit at 10:00; LONG sign; costs;
<2019 boundary; remove-best-1% computation.

## Governance

- Commit 1: this SPEC alone, before execution.
- Commit 2: results after execution.
- Branch: `research/tokyo-fixing-prefix-discovery`. PR not merged.
