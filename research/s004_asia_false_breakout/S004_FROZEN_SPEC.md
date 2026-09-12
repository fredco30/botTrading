# S004_FROZEN_SPEC — EURUSD Asia False Breakout → Range Reversion

Status: FROZEN before any execution. Discovery only. Fail fast.
Recorded hypothesis from P003 catalogue (registered before S001).
NOT a mechanical inversion of S001.

## Governance
- Branch: research/s004-eurusd-asia-false-breakout
- Base: main @ 1ff680a1369fa4753a68f8989d6a2b2cc1ce8068
- Commit 1: this file only. Execution only afterwards.
- Discovery window: 2010-01-01 inclusive → 2019-01-01 exclusive.
  2019+ data never loaded into the simulation. Protected OOS forbidden.

## Instrument & data
- EURUSD only, 5m OHLC (Dukascopy parquet, bar OPEN timestamp, UTC).
- Timezone: Europe/London (GMT/BST handled by real tz conversion).
- Pip = 0.0001.

## Asian range
- Per London day: bars with London time in [00:00, 07:00).
- ASIAN_HIGH = max HIGH; ASIAN_LOW = min LOW; MIDPOINT = (H+L)/2.
- Range fully known before any signal of that day.

## Breakout
- Window: London [08:00, 11:00).
- LONG breakout: first 5m bar CLOSED with CLOSE > ASIAN_HIGH.
- SHORT breakout: first 5m bar CLOSED with CLOSE < ASIAN_LOW.
- First break wins; sets state WAIT_FOR_REENTRY. No trade yet.

## False breakout / reentry
- After LONG breakout: first bar closed with CLOSE < ASIAN_HIGH → signal SHORT.
- After SHORT breakout: first bar closed with CLOSE > ASIAN_LOW → signal LONG.
- Reentry must occur within 60 minutes after the close of the breakout bar,
  else NO TRADE.

## Entry
- OPEN of the 5m bar following the reentry bar. Never at signal close.
- Max one trade per day.

## Stop
- SHORT (after upside break): highest HIGH from breakout bar through
  reentry bar inclusive.
- LONG (after downside break): lowest LOW over the same sequence.
- RISK_PIPS = |entry − stop|; if <= 0 → NO TRADE.

## Target
- MIDPOINT of the Asian range.
- If at entry the midpoint is already crossed in the trade's favor → NO TRADE.

## Time exit
- If neither stop nor target touched: exit at OPEN of the first bar
  >= 12:00 London. No position after 12:00 London.

## Execution
- Causal OHLC 5m. Stop/target via HIGH/LOW.
- Stop and target in the same bar → STOP-FIRST.
- Adverse gap beyond stop: fill at real OPEN. Favorable gap beyond target:
  credit capped at TARGET.

## Costs (gross PnL, costs subtracted)
- NORMAL = 2 pips RT. STRESS = 4 pips RT. Decision on NORMAL.

## Metrics
N_BREAKOUTS, N_FALSE_BREAKOUTS, FALSE_BREAKOUT_RATE, N_TRADES,
TRADES_PER_YEAR, GROSS_MEAN_PIPS, NET_NORMAL_MEAN_PIPS,
NET_STRESS_MEAN_PIPS, MEDIAN_NET, WIN_RATE, AVG_WIN, AVG_LOSS,
PROFIT_FACTOR_NORMAL, EXPECTANCY_R_NORMAL, TOTAL_NET_PIPS,
MAX_DRAWDOWN_PIPS, MAX_CONSECUTIVE_LOSSES, BY_YEAR (N, NET_PIPS,
MEAN_NET, PF), POSITIVE_YEARS, REMOVE_BEST_1_PERCENT_NET_MEAN,
bootstrap CI95_MEAN_NET_NORMAL (2000 resamples, seed 42). Nothing else.

## Discovery gate — S004_DISCOVERY_PROMISING iff ALL:
- NET_NORMAL_MEAN > +2 pips/trade
- PROFIT_FACTOR_NORMAL >= 1.20
- EXPECTANCY_R_NORMAL > +0.10R
- POSITIVE_YEARS >= 6/9
- REMOVE_BEST_1_PERCENT_NET_MEAN > 0
- TOTAL_NET_PIPS > 0
CI is informational only.

## Fail fast — REJECT & STOP if any:
- NET_NORMAL_MEAN <= 0, or PF <= 1.0, or REMOVE_BEST <= 0.
No tuning, no grids, no variants (pairs, windows, targets, stops, filters,
second breakouts, inversion, pyramiding). No extra audit if clearly negative.
