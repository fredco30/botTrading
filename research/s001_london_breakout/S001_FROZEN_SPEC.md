# S001 — GBPUSD London / Asian-Range Breakout — Discovery (FAIL-FAST, frozen)

Status: FROZEN before execution. This file is committed (commit 1) BEFORE any
price access to the Discovery window. One complete strategy, one version, no
optimization, no parameter grid, no rescue variants. Philosophy change vs the
micro-anomaly missions: we test a FULL strategy (context, signal, entry, stop,
target, time exit, costs, per-trade results, PF, drawdown).

## Instrument / data

- GBPUSD only. Pip = 0.0001.
- Data: `data_raw/parquet/GBPUSD_5m.parquet` (5-min UTC OHLCV bars).
- Strategy timezone: **Europe/London** (GMT/BST handled by tz conversion —
  never a fixed UTC offset for London hours).
- DISCOVERY window: 2010-01-01 (inclusive) → 2019-01-01 (exclusive), cut on
  the UTC index IMMEDIATELY after load. NO access to 2019+ prices.
  2019-2022 reserved for a possible later validation. Protected OOS remains
  totally off-limits.

## Frozen rule

For each London trading day D (calendar date of each 5m bar in Europe/London):

- ASIAN_RANGE = bars with London open time in [00:00, 07:00) of day D.
  ASIAN_HIGH = max(HIGH); ASIAN_LOW = min(LOW). Fully known before signal
  search; no future data. Day with no bar in this window → NO TRADE.
- SIGNAL WINDOW: bars with London OPEN time in [08:00, 11:00) of day D.
  - LONG signal: FIRST 5m bar whose CLOSE > ASIAN_HIGH.
  - SHORT signal: FIRST 5m bar whose CLOSE < ASIAN_LOW.
  - The signal bar must be CLOSED before the decision (decision instant =
    signal-bar open time + 5 min; entry fills at the same instant).
- ENTRY: OPEN of the 5m bar immediately AFTER the signal bar (never at the
  close that created the signal). If that bar does not exist → NO TRADE.
  First valid breakout wins. ONE trade max per day. No breakout → NO TRADE.
- STOP: LONG → ASIAN_LOW. SHORT → ASIAN_HIGH.
  RISK_PIPS = |ENTRY − STOP| / 0.0001. If RISK_PIPS <= 0 → trade invalid
  (NO TRADE).
- TARGET = fixed 1.5R:
  LONG_TARGET = ENTRY + 1.5 × (ENTRY − STOP);
  SHORT_TARGET = ENTRY − 1.5 × (STOP − ENTRY).
  No trailing, no break-even, no partial, no pyramid.
- TIME EXIT: if neither STOP nor TARGET touched before 12:00 London, exit at
  the OPEN of the FIRST bar with London open time >= 12:00 of day D. No
  position held past this exit. Degenerate fallback (expected ~never, counted
  and reported): if day D has no bar at/after 12:00, exit at the CLOSE of the
  last bar of day D.

## Intrabar execution (causal OHLC)

- Conservative causal simulation on 5m OHLC.
- Gaps at bar OPEN:
  - open beyond the STOP (adverse) → exit at the OPEN (gap-through-stop,
    worse than stop).
  - open beyond the TARGET (favorable) → credited at TARGET, never better.
- Within a bar, if both STOP and TARGET are touchable via HIGH/LOW and the
  true order is unknown → **STOP-FIRST** (mandatory conservative rule).
- Entry bar: entry at its OPEN, then the same intrabar rules apply to its
  HIGH/LOW (TARGET can never gap at entry open since TARGET is derived from
  the entry price; STOP can never gap at entry open since RISK_PIPS <= 0
  trades are rejected).

## Costs (three levels reported)

- GROSS: no cost.
- NORMAL: 2 pips round-trip (NET_NORMAL = GROSS − 2.0). Decision criteria
  use NORMAL only.
- STRESS: 4 pips round-trip (NET_STRESS = GROSS − 4.0).
- No optimal-spread search.

## Metrics (only these)

N_TRADES; TRADES_PER_YEAR (= N_TRADES / 9); GROSS_MEAN_PIPS;
NET_NORMAL_MEAN_PIPS; NET_STRESS_MEAN_PIPS; MEDIAN_NET_PIPS (net normal);
WIN_RATE (share of trades with NET_NORMAL > 0); AVG_WIN_PIPS (mean NET_NORMAL
of winners); AVG_LOSS_PIPS (mean NET_NORMAL of losers, negative);
PROFIT_FACTOR_NORMAL (Σ NET_NORMAL wins / |Σ NET_NORMAL losses|; +inf if no
loser); EXPECTANCY_R_NORMAL (mean of NET_NORMAL / RISK_PIPS per trade);
TOTAL_NET_PIPS (normal); MAX_DRAWDOWN_PIPS (peak-to-trough on cumulative
NET_NORMAL, trade by trade); MAX_CONSECUTIVE_LOSSES (NET_NORMAL < 0);
BY_YEAR (year of London entry date): N, NET_PIPS, MEAN_NET, PROFIT_FACTOR;
POSITIVE_YEARS (years with NET_PIPS > 0, out of 9);
REMOVE_BEST_1_PERCENT_NET_MEAN (repo convention: sort NET_NORMAL ascending,
drop k = floor(N × 0.01) best, mean of the remainder);
CI95_MEAN_NET_NORMAL (per-trade bootstrap, 2000 resamples, seed 42,
percentile 2.5/97.5, `np.random.default_rng(42)`).

## Discovery criteria — PASS requires ALL of:

1. NET_NORMAL_MEAN_PIPS > +2.0 pips/trade
2. PROFIT_FACTOR_NORMAL >= 1.20
3. EXPECTANCY_R_NORMAL > +0.10 R/trade
4. at least 6/9 years with NET_PIPS > 0
5. REMOVE_BEST_1_PERCENT_NET_MEAN > 0
6. TOTAL_NET_PIPS > 0

CI95 is informative only; it does NOT need to be entirely > 0 at Discovery if
all economic criteria pass.

Classification: `S001_DISCOVERY_PROMISING` if all six pass, else
`S001_DISCOVERY_REJECT`.

## Fail-fast

If NET_NORMAL_MEAN <= 0 OR PROFIT_FACTOR_NORMAL <= 1.0 OR
REMOVE_BEST_1_PERCENT_NET_MEAN <= 0, and the final classification is REJECT:
STOP. Do NOT test: 00:00-06:00 or 00:00-08:00 ranges, no-confirmation entry,
15m, 30m, TP 1R, TP 2R, midpoint stop, ATR stop, range/weekday/trend/news
filters, EURUSD, USDJPY, inversion, second breakout, trailing, break-even,
pyramid. Any improvement will be a NEW mission after human review.

## Bug policy / sobriety

Fix only: lookahead, timezone error, PnL error, stop/target error, cost
error, 2019+ contamination, verdict-changing bugs. No multiple audit cycles
on an already-clearly-rejected result. No cosmetic documentation work.

## Minimal tests (synthetic only, no extra framework)

Europe/London GMT/BST; Asian range uses only 00:00→07:00; signal after bar
close; entry = next bar open; LONG / SHORT; STOP = opposite range side;
TARGET = 1.5R; stop-first on same-bar stop+target; gap-through-stop; time
exit 12:00; costs 2/4 pips; <2019 boundary.

## Governance

- Branch: `research/s001-gbpusd-london-breakout` (base `main` @ `1ff680a1369fa4753a68f8989d6a2b2cc1ce8068`).
- Commit 1: this SPEC alone, before execution.
- Commit 2: code + tests + results after execution.
- PR not merged.
