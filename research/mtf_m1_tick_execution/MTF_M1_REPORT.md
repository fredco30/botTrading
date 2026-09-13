# MTF_M1 — TICK-ACCURATE MULTI-TIMEFRAME STRATEGY DISCOVERY REPORT

EURUSD 2010-01-01 .. 2019-01-01 exclusive. Frozen spec:
`MTF_M1_FROZEN_SPEC.md` (committed `7dd5a02` BEFORE any outcome computation).
Parent head `27b6e24` (TICK-M1 PR #29, NOT merged). Machine-readable results:
`mtf_m1_results.json`, per-trade records: `mtf_m1_trades.json`.

## Verdict: **NO_MTF_CANDIDATE**

- **A `MTF_A_TREND_PULLBACK`** → **REJECT** (fail-fast §12: net mean ≤ 0, PF ≤ 1.0, remove-best ≤ 0)
- **B `MTF_B_TREND_BREAKOUT`** → **FAIL_GATE** (positive but fails every demanding gate criterion; CI95 crosses 0)
- **C `MTF_C_RANGE_REVERSION`** → **REJECT** (fail-fast §12)

All three strategies produced one frozen verdict each → per §13 the mission
STOPS. No fourth strategy, no rescue research, no tuning.

## Engine validation

- 39 synthetic tests (`test_mtf_m1.py`): bar aggregation M15/H1/H4, bar-close
  causality, EMA causality + formula, Wilder ATR14, Wilder ADX14 (independent
  reference), Bollinger (population σ), 20-bar breakout excludes current bar,
  M15 trigger uses previous completed M15 bar, A-window expiry/supersession,
  H4 regime completed-bar rule, 250 ms latency boundary, LONG-ASK / SHORT-BID
  entry, LONG-BID / SHORT-ASK exit, spread charged once, stop fill (overshoot
  kept), target fill (overshoot capped), time exit (first tick at/after),
  data-gap invalidation (and no invalidation when resolution precedes the
  gap), NO_FILL / NO_FILL_GAP, INVALID_STOP (incl. float-noise guard),
  C target-crossed-at-entry, HARD_END 2019 skip, loader 2019 refusal,
  weekend-closure TIME exit (regression), occupancy, deterministic bootstrap.
- Existing suites still green: TICK-M0 18/18, TICK-M1 22/22.
- **Real-data audit:** 34 sampled trades independently re-verified against
  raw parquet ticks via a separate code path (entry tick + executable-side
  price, exit tick + price per rule, net-pips arithmetic, 2019 bounds, gap
  onsets with genuine >1h holes). 34/34 exact.
- **Bug found and fixed during validation (pre-report):** the execution
  window originally ended exactly at `entry+T`; when the time-exit timestamp
  fell inside a weekend closure the window contained no tick at/after it, so
  the trade was mis-classified DATA_GAP_INVALID (the next GAP-LIST onset,
  possibly months later, won) and its occupancy suppressed later signals.
  Fixed by padding the window past the time-exit (regression test added);
  trade counts went A 403→1632, B 257→1120, C 466→1855 and gap-invalidations
  124→38. All reported results are from the FIXED engine.

## Data

| item | value |
|---|---|
| DATA_ROOT | `E:\ResearchData\botTrading\ticks` (env `BOTTRADING_TICK_DATA_ROOT`) |
| N_TICKS | 208,003,917 (108 monthly partitions, reused — no redownload) |
| DISCOVERY_RANGE | 2010-01-01T00:00:00Z .. 2019-01-01T00:00:00Z (exclusive) |
| GAP LIST | 104 non-weekend inter-tick gaps > 1 h (≈92 one-hour feed holes, Christmas/New-Year closures 14–22 h); weekend = Fri 21:59 → Sun 22:01 UTC (frozen from descriptive audit) |
| Bars (gap-free) | M15 222,430 · H1 55,461 · H4 14,262 (left-labelled mid bars) |
| Signals | A 2,993 · B 2,226 · C 2,615 trigger events |

## Results (DATA_GAP_INVALID trades excluded; only counted)

| metric | A TREND_PULLBACK | B TREND_BREAKOUT | C RANGE_REVERSION |
|---|---|---|---|
| N_TRADES | 1,632 | 1,120 | 1,855 |
| DATA_GAP_INVALID | 17 | 16 | 5 |
| TRADES_PER_YEAR | 181.3 | 124.4 | 206.1 |
| GROSS_MID_MOVE_MEAN_PIPS | +0.397 | +2.730 | −0.069 |
| **NET_EXECUTABLE_MEAN_PIPS** | **−0.420** | **+1.786** | **−0.853** |
| MEDIAN_NET | −10.4 | −19.7 | −6.6 |
| TOTAL_NET_PIPS | −685.3 | +2,000.6 | −1,581.8 |
| STRESS_010_MEAN | −0.620 | +1.586 | −1.053 |
| STRESS_025_MEAN | −0.920 | +1.286 | −1.353 |
| WIN_RATE | 0.356 | 0.380 | 0.483 |
| AVG_WIN / AVG_LOSS | +39.6 / −22.5 | +53.6 / −29.9 | +18.8 / −19.2 |
| PROFIT_FACTOR | 0.971 | 1.096 | 0.914 |
| EXPECTANCY_R | −0.070 | +0.058 | −0.052 |
| MAX_DRAWDOWN_PIPS | 2,247.9 | 981.1 | 2,017.9 |
| MAX_CONSEC_LOSSES | 11 | 19 | 9 |
| POSITIVE_YEARS | 3/9 | 5/9 | 2/9 |
| REMOVE_BEST_1PCT_MEAN | −2.052 | +0.514 | −1.703 |
| CI95_MEAN_NET (2000×, seed 42) | [−2.22, +1.28] | [−0.80, +4.51] | [−1.90, +0.24] |
| Exits STOP / TARGET / TIME | 984/414/234 | 654/342/124 | 893/744/218 |
| Setup funnel (signals → ignored-while-open / invalid / other / trades) | 2993 → 1296 / 43+4 / 1 / 1632 | 2226 → 1085 / 0+1 / 4 / 1120 | 2615 → 578 / 172+5+0 / 5 / 1855 |
| **VERDICT** | **REJECT** | **FAIL_GATE** | **REJECT** |

### By year

| year | A: n / mean / total / PF | B: n / mean / total / PF | C: n / mean / total / PF |
|---|---|---|---|
| 2010 | 188 / +3.07 / +577.5 / 1.16 | 132 / +8.71 / +1,149.8 / 1.33 | 188 / +0.20 / +37.9 / 1.01 |
| 2011 | 193 / −4.02 / −775.7 / 0.81 | 126 / +3.94 / +496.1 / 1.15 | 242 / −1.29 / −312.7 / 0.91 |
| 2012 | 182 / −1.68 / −305.7 / 0.89 | 123 / +3.87 / +476.5 / 1.23 | 189 / +0.75 / +140.9 / 1.08 |
| 2013 | 177 / −1.00 / −176.7 / 0.92 | 107 / −4.93 / −527.6 / 0.75 | 246 / −0.03 / −7.8 / 1.00 |
| 2014 | 195 / −1.58 / −307.9 / 0.84 | 128 / +3.04 / +388.7 / 1.29 | 159 / −0.80 / −127.0 / 0.88 |
| 2015 | 204 / −0.76 / −155.5 / 0.96 | 137 / −2.00 / −274.6 / 0.91 | 218 / −0.63 / −138.1 / 0.94 |
| 2016 | 162 / +0.77 / +124.4 / 1.06 | 115 / −1.92 / −220.4 / 0.89 | 237 / −2.26 / −535.8 / 0.75 |
| 2017 | 171 / +3.35 / +573.0 / 1.37 | 135 / +4.70 / +634.5 / 1.40 | 195 / −2.68 / −522.9 / 0.68 |
| 2018 | 160 / −1.49 / −238.7 / 0.88 | 117 / −1.05 / −122.3 / 0.93 | 181 / −0.64 / −116.3 / 0.91 |

## Interpretation

1. **B is the only strategy that is not outright rejected, and it still fails
   everything that matters.** NET mean +1.79 pips is below the +2.0 gate; PF
   1.096 is below 1.20; expectancy +0.058R is below +0.10R; 5/9 positive
   years is below 6/9; the bootstrap CI95 [−0.80, +4.51] comfortably includes
   zero. Its gross mid edge (+2.73 pips) survives execution but the frozen
   gate demands more than "barely positive and statistically indistinguishable
   from zero".
2. **A and C lose before and after costs.** A's gross mid mean (+0.40) is
   already ~zero: the H4-trend + H1-pullback + M15-continuation structure has
   no measurable mid-price edge in this feed. C's gross mean is −0.07 pips:
   H1 Bollinger mean reversion under H4 ADX<20 nets nothing even before the
   spread. Median trade is negative for all three (winners are the rare 2R
   runners).
3. **Fragility:** REMOVE_BEST_1PCT is negative for A and C — their few
   positive years are carried by outliers. B's +0.51 is positive but its
   year-by-year sign flips constantly (2013 −4.9, 2015 −2.0, 2018 −1.0).
4. **Costs matter but are not the story:** STRESS_010 (one extra 0.10
   pip/side) keeps B positive (+1.59) yet the gate fails long before stress
   becomes the binding constraint.

## Compliance

- 2019_PLUS_ACCESSED = **NO** (`assert_month_in_discovery` hard guard; entries
  whose frozen time-exit reaches ≥ 2019-01-01 are skipped, never filled;
  SKIPPED_HARD_END: A 4, B 1, C 0)
- PROTECTED_OOS_ACCESSED = **NO**
- PR NOT merged. Research only; no broker, no live trading.
- Frozen spec committed (`7dd5a02`) before any outcome was computed; the two
  engine fixes made during validation were correctness fixes caught by the
  frozen validation program (regression-tested), not parameter changes.

## Tests & CI

- `research/mtf_m1_tick_execution/test_mtf_m1.py`: **39/39 PASS**
- `research/tick_m0/test_tick_m0.py`: **18/18 PASS**
- `research/tick_m1_microstructure/test_tick_m1.py`: **22/22 PASS**
- CI: MTF-M1 synthetic suite added to `research-engine-tests.yml`.

## Two-stage conclusion

`STRATEGIES_PASSING_GATE = []` → **NO_MTF_CANDIDATE** → STOP.
