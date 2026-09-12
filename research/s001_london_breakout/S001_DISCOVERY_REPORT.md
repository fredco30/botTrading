# S001 — GBPUSD London / Asian-Range Breakout — DISCOVERY RESULTS

Classification: **S001_DISCOVERY_REJECT** — all six criteria fail. Gross mean is
already negative (−1.32 pips/trade before costs), so no cost regime can rescue
it. FAIL-FAST: STOP, no variants tested (per S001_FROZEN_SPEC.md §Fail-fast).

## Run

- Window: 2010-01-01 → 2019-01-01 EXCLUSIVE (discovery only). 674,496 bars,
  last bar 2018-12-31 23:55 UTC. No 2019+ access, protected OOS untouched.
- Days with an Asian range: 2,621. Trades: 2,183 (83% of range-days; 1,093
  LONG / 1,090 SHORT). One trade max per day respected. Time-exit fallback
  used 0 times.
- Exit reasons: TIME_1200 1,307 / STOP 596 / TARGET 280 (no same-bar
  stop+target collision and no gap-through-stop occurred; conservative
  rules were armed but never triggered).

## Metrics (NORMAL = 2 pips round-trip; STRESS = 4 pips)

| Metric | Value |
|---|---|
| N_TRADES | 2,183 |
| TRADES_PER_YEAR | 242.6 |
| GROSS_MEAN_PIPS | −1.3205 |
| NET_NORMAL_MEAN_PIPS | **−3.3205** |
| NET_STRESS_MEAN_PIPS | −5.3205 |
| MEDIAN_NET_PIPS | −5.40 |
| WIN_RATE | 42.92% |
| AVG_WIN_PIPS | +27.86 |
| AVG_LOSS_PIPS | −26.77 |
| PROFIT_FACTOR_NORMAL | **0.7827** |
| EXPECTANCY_R_NORMAL | −0.0786 R |
| TOTAL_NET_PIPS | −7,248.6 |
| MAX_DRAWDOWN_PIPS | 8,042.6 |
| MAX_CONSECUTIVE_LOSSES | 12 |
| POSITIVE_YEARS | 2 / 9 (2013, 2018) |
| REMOVE_BEST_1_PERCENT_NET_MEAN | −4.2559 |
| CI95_MEAN_NET_NORMAL | [−4.7429, −1.9118] |

## BY_YEAR

| Year | N | NET_PIPS | MEAN_NET | PF |
|---|---|---|---|---|
| 2010 | 242 | −2,359.0 | −9.75 | 0.60 |
| 2011 | 236 | −842.2 | −3.57 | 0.82 |
| 2012 | 244 | −848.8 | −3.48 | 0.72 |
| 2013 | 237 | +236.8 | +1.00 | 1.09 |
| 2014 | 247 | −1,293.3 | −5.24 | 0.61 |
| 2015 | 238 | −955.8 | −4.02 | 0.73 |
| 2016 | 243 | −942.7 | −3.88 | 0.76 |
| 2017 | 243 | −471.5 | −1.94 | 0.85 |
| 2018 | 253 | +227.9 | +0.90 | 1.07 |

## Criteria (frozen) — ALL FAIL

1. NET_NORMAL_MEAN > +2.0 → **FAIL** (−3.32)
2. PROFIT_FACTOR_NORMAL >= 1.20 → **FAIL** (0.78)
3. EXPECTANCY_R_NORMAL > +0.10 R → **FAIL** (−0.079)
4. >= 6/9 positive years → **FAIL** (2/9)
5. REMOVE_BEST_1_PERCENT > 0 → **FAIL** (−4.26)
6. TOTAL_NET_PIPS > 0 → **FAIL** (−7,248.6)

## Verification (single audit pass, per bug policy)

- 17 synthetic tests pass (GMT/BST conversion incl. 2010/2011 DST
  transitions, Asian-range bounds 00:00→07:00 exclusive, signal-after-close,
  entry = next open, LONG/SHORT, opposite-side stop, 1.5R target,
  stop-first, gap-through-stop, target-gap cap, 12:00 time exit, costs 2/4,
  invalid risk, one-trade-per-day, signal-window bounds, <2019 boundary).
- Manual audit of 3 trades (GMT day, BST day, TARGET/STOP exits) against raw
  bars with explicit UTC-bounded Asian windows: exact match, including DST
  edge days (2011-03-25/28, 2011-10-28/31).
- Weekday mix Mon–Fri only, balanced; LONG/SHORT balanced.

## Verdict

The London breakout of the 00:00–07:00 London range with 1.5R fixed target
and 12:00 London time exit has no edge on GBPUSD 2010–2018: it loses before
costs. STOP_REJECTED — any improvement (range bounds, filters, targets,
inversion, other pairs…) is a NEW mission requiring human review.
