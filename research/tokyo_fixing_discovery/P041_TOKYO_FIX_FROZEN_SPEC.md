# P041 — Tokyo Fixing Post-Fix Reversal — DISCOVERY (FROZEN SPEC)

Status: FROZEN BEFORE ANY DATA ACCESS (2010-2019 window untouched as of this commit).

## Hypothesis (single, from Tokyo-fixing literature)

- Fixing at 09:55 JST; structural USD demand before fixing; transitory USDJPY rise
  around the fixing; reversion after. We test ONLY the post-fix leg.

## Rule (exact, no variants)

- Instrument: USDJPY only.
- SHORT at OPEN of the 10:00 JST bar (bar 09:55-10:00 contains the fixing; we wait
  for its completion to avoid intrabar ambiguity).
- EXIT at OPEN of the 10:30 JST bar.
- No stop, no TP, no filters, no day-of-week filter.
- One trade per available FX day.

## Timezone

- Asia/Tokyo (Japan has no DST). Source data UTC (Dukascopy, documented in
  research/phenomena_discovery_v1/data_manifest.md, DS3..DS5).

## Discovery window

- 2010-01-01 (inclusive) → 2019-01-01 (exclusive). NO access to 2019+ data.

## Costs (frozen)

- NORMAL = 2 pips round-trip. STRESS = 4 pips round-trip. Pip = 0.01 (USDJPY 3-decimal feed).

## Metrics (minimal)

N_TRADES, GROSS_MEAN_PIPS, NET_NORMAL_MEAN_PIPS, NET_STRESS_MEAN_PIPS,
MEDIAN_NET_NORMAL, WIN_RATE_NET_NORMAL, BY_YEAR_NET_NORMAL, POSITIVE_YEARS,
REMOVE_BEST_1_PERCENT_NET (mean after dropping best 1% of trades by net pips),
day-level bootstrap, 2000 draws, seed 42, CI95_NET_NORMAL (percentile 2.5/97.5).

## Economic gate (FROZEN)

TOKYO_FIX_DISCOVERY_PASS iff ALL of:
1. NET_NORMAL_MEAN_PIPS >= +2.0 pips/day
2. POSITIVE_YEARS >= 6 of 9
3. REMOVE_BEST_1_PERCENT_NET > 0
4. NET_STRESS_MEAN_PIPS > 0

Else TOKYO_FIX_DISCOVERY_REJECT → immediate STOP, no variants (09:55 entry, 10:05
entry, 10:15/11:00 exit, long pre-fix, other pairs, weekday filters, vol/trend/macro
filters, stop/TP, pyramiding — all forbidden).

CI is informative only, not decisional.

## Data

- data_raw/parquet/USDJPY_5m.parquet (UTC, bid, 2010-01-01 → 2026-04-08).
  Only rows < 2019-01-01 UTC are read/loaded.
