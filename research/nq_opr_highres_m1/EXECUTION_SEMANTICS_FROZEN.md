# EXECUTION SEMANTICS — FROZEN BEFORE ANY HIGH-RES PnL

Candidate: NQ_OPR_MODERN_M1 (frozen P000 premarket breakout/retest).
Signal source: existing 1m/5m OHLCV backtest (NEVER rediscovered from BBO).
This file documents the deterministic, CONSERVATIVE execution readings fixed
BEFORE any high-resolution replay. None of these choices may be revised after
seeing execution PnL. No strategy rule is modified.

## Frozen order semantics (from the frozen engine)

* ENTRY: stop order at the tap-bar extreme (long: tap-bar high; short: tap-bar
  low), marketable when triggered -> fills against the OPPOSITE side of the
  book (long entry at ASK, short entry at BID). Gap-through fills at the
  (worse) open in the 1m model -> at BBO, executable price of the first
  eligible quote after activation.
* ORDER_ACTIVE_TS = the END of the tap 5m bar (tap_ts + 5min): the stop order
  cannot exist before the tap bar completed. CONSERVATIVE: the first eligible
  BBO observation is the FIRST sampled quote with timestamp STRICTLY AFTER
  ORDER_ACTIVE_TS. No backward interpolation, no use of quotes before
  activation.
* LEVEL_STOP (close-based invalidation): decision known at the bar's close;
  exit is a MARKET order -> long exit at BID / short exit at ASK, first
  eligible quote at/after the decision second (conservative: strictly after
  the bar-close timestamp).
* TRIM: PASSIVE LIMIT at the running-day extreme. Top-of-book cannot prove a
  passive fill. CONSERVATIVE rule: the trim is assumed filled ONLY if the
  BID (long trim sell-limit) reached >= the trim level at some sampled BBO
  second within the trim bar's interval; otherwise the event is classified
  QUEUE_UNCERTAIN and the trim is EXCLUDED from the high-res PnL (remaining
  size keeps the original fraction -> conservative: no trim credit).
* BE floor and EMA8/EOD exits: market orders at the bar close -> long exit at
  BID, short exit at ASK (first eligible quote at/after the decision second).
* SESSION EXIT 15:55: market -> same side convention.

## Ambiguities resolved conservatively (fixed now)

A1. Same-second ambiguity: BBO-1s samples one quote per second. If the frozen
    decision second contains multiple book states, we take the FIRST sampled
    observation STRICTLY AFTER the decision timestamp (never the favorable
    one). Trades whose frozen bar close and stop/target occur within the same
    second are flagged BBO_AMBIGUOUS (stop counted first, pessimistic).
A2. If no BBO observation exists within 60 seconds after an activation/decision
    instant (halt/missing data), the trade is flagged BBO_AMBIGUOUS and uses
    the frozen 1m price as fallback, marked as such (never silently).
A3. Spread is never double-counted: the frozen RT cost decomposition is
    OBSERVED_SPREAD (from BBO) + MODELED_SLIPPAGE (scenario ticks) +
    FIXED_FEES (frozen 1.5/3.0-point RT model MINUS the spread component it
    already bundled). The frozen NORMAL 1.5pt RT bundled ~0.5pt spread + fees
    + slippage; for BBO replay the OBSERVED spread replaces that bundled
    spread assumption, and FIXED_FEES keeps the residual commission/fee
    component (1.0pt NORMAL / 2.5pt STRESS) so costs are never reduced by
    using BBO (documented decomposition, no silent removal).
A4. Roll safety: every execution window must lie within one ET trading day of
    one actual contract (roll manifest). Any window crossing a roll -> STOP.
A5. 2026 hard guard: any timestamp >= 2026-01-01Z aborts the campaign.

## Slippage scenarios (preregistered, none chosen post hoc)

L1_BASE: first eligible BBO quote + fixed fees (residual component).
L1_CONSERVATIVE: + 1 tick adverse per marketable execution.
L1_STRESS: + 2 ticks adverse per marketable execution.
