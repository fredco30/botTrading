# EXECUTION SEMANTICS — H02_TREND_DAY_EARLY / O01_ON_TRANSFER
# Frozen BEFORE any high-res PnL. No rule may change after seeing BBO data.

## Frozen order semantics (lab engine, both candidates)

* ENTRY: MARKET order at the OPEN of the bar following the decision bar
  (H02: decision at 10:00-bar close; O01: at 09:35-bar close).
  ORDER_ACTIVE_TS = decision bar END (= fill bar START).
  LONG buys at ASK; SHORT sells at BID. Gap handling is inherent (market).
* INITIAL STOP: hard touch stop. LONG: low <= stop triggers a marketable
  sell-stop executed at BID (worse of open/stop on gap). SHORT mirrored on
  ASK. Decisions/triggers inside the frozen bar timeline are preserved
  exactly; BBO only replaces the execution PRICE.
* TRAILING: chandelier 1.0 x ATR14 (H02/O01) exits on a completed-bar CLOSE
  crossing the trail — MARKET order at that bar END: LONG exit at BID,
  SHORT exit at ASK. The trail level is always the frozen bar-based value.
* EOD: force-flat at the last RTH bar close — MARKET (BID/ASK by side).
* There are NO passive limit orders in H02 or O01 (no targets): every
  execution is marketable, so no QUEUE_UNCERTAIN class exists for these two
  candidates. Any missing/unprovable quote is handled by the NO_QUOTE_60S
  fallback (use the frozen 1m price, flag BBO_AMBIGUOUS, never silently).
* Causality: no quote with ts_recv <= ORDER_ACTIVE_TS may fill the entry;
  trailing/stop/EOD scans start strictly at their frozen decision instants
  (touch-stops from the start of the triggering bar; close-based exits from
  the bar end second, first sample with ts_recv >= that second).
* Same-second ambiguity: stop-before-target/pessimistic ordering per bar as
  frozen; flagged BBO_AMBIGUOUS when a single second covers both sides.

## Cost decomposition (audited units)

1 NQ point = USD 20; 1 tick = 0.25 pt = USD 5.
Frozen NORMAL 1.5 pt RT / STRESS 3.0 pt RT bundled (spread + fees + slippage).
BBO replay decomposition:
  OBSERVED_SPREAD_COMPONENT = embedded in executable bid/ask prices
  FIXED_FEES_COMPONENT      = 1.0 pt RT (NORMAL) / 2.5 pt RT (STRESS) residual
  MODELED_SLIPPAGE          = scenario ticks (L1_BASE 0 / CONS 1 / STRESS 2)
Spread is never double-counted and never silently removed.

## Scenarios (preregistered; not run in this cost-guard mission)

L1_BASE          = first eligible BBO quote + fixed fees
L1_CONSERVATIVE  = + 1 adverse tick per marketable execution
L1_STRESS        = + 2 adverse ticks per marketable execution

## 2026 guard

Any timestamp >= 2026-01-01Z aborts. 2026_REQUESTED=NO / 2026_ACCESSED=NO.
