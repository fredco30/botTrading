# O01_PAPER_FROZEN_SPEC — paper engine spec (mirrors the validated candidate)

SOURCE OF TRUTH = the high-res validated implementation:
  research/nq_modern_strategy_lab/families.py :: O01 (entry)
  research/nq_modern_strategy_lab/lab_lib.py  :: run_experiment_full/_manage
  research/nq_h02_o01_highres_m1/o01_replay.py:: execution conventions
CROSS-CHECKED against FROZEN_SPEC.md. No disagreement found between the
families.py entry logic, lab_lib walk and the frozen spec: the paper spec
below is their verbatim restatement. STRATEGY_CHANGED=NO.

## Context (all America/New_York, DST-aware; completed bars only)

OVERNIGHT_WINDOW   = [09:30 ET - 15.5h, 09:30 ET)  (covers prior 18:00 open)
OVERNIGHT_RETURN   = open_09:30 / prior_RTH_close - 1
OVERNIGHT_RANGE    = high - low over the overnight window (5m bars)
Z_SCORE            = (on_ret - mean(20 prior RTH days)) / std(20 prior days),
                     shifted 1 day (strictly causal; needs >=20 days history)
PREMARKET_RANGE    = high - low over [04:00, 09:30) ET same calendar day
PREMARKET_GATE     = pm_range <= 0.5 * overnight_range
ATR14              = mean(TR of the last 14 completed DAILY RTH bars),
                     TR includes gap vs prior close; usable value is the
                     shift(1) series (prior days only) — lab convention.
DIRECTION          = sign(z): BULL (long) if z>0, BEAR (short) if z<0.

## Signal (frozen)

At the CLOSE of the 09:35 ET 5m bar (decision instant = 15:40 UTC in EDT /
14:40 UTC in EST... [editorial: engine uses tz database, never fixed offsets]):
  IF |z| >= 1.0 AND premarket_gate:
     SIDE = sign(z); ENTRY = MARKET at the NEXT 5m bar OPEN (activation =
     next bar start; first executable quote at/after activation)
  ELSE NO_TRADE (reason recorded: z insufficient / premarket too wide /
     context missing)

## Stop (frozen)

INITIAL_STOP = opposite extreme of 09:30-09:35 (long: min low; short: max
high). HARD TOUCH stop, live from entry: LONG triggers when executable BID
<= stop (market sell at BID); SHORT when executable ASK >= stop (market buy
at ASK). Gap fills at the actual quote (conservative).

## Chandelier trail (frozen)

TRAIL = running extreme since entry (LONG: highest high; SHORT: lowest low)
-/+ 1.0 * ATR14(at entry day). LONG exits when a completed 5m CLOSE < TRAIL;
SHORT when CLOSE > TRAIL. Exit = MARKET at that bar END (LONG at BID, SHORT
at ASK). The trail is evaluated only on completed bars and never moves back.

## EOD (frozen)

Force-flat at the last RTH bar of the ET day (16:00 close = 15:55 bucket end):
MARKET at first executable quote at/after that instant.

## Priority (frozen)

Per 5m bar: initial stop first (intrabar touch), then chandelier (close),
then EOD. One trade/day; one position; no pyramiding/averaging.

## Execution (high-res validated conventions)

LONG: marketable buy at ASK; exits at BID.
SHORT: marketable sell at BID; exits at ASK.
No midpoint, no OHLC-theoretical fills, no backward interpolation, no fill
before activation. Shadow ledgers: BASE (validated fill), CONSERVATIVE
(+1 adverse tick per marketable leg), STRESS (+2 adverse ticks).

## Costs

FIXED_FEES residual: NORMAL 1.0 pt RT (base scenario tier), STRESS 2.5 pt.
OBSERVED spread lives inside executable bid/ask (never double-counted).
1 pt = USD 20; 1 tick = 0.25 pt = USD 5 (USD = pts*20 = ticks*5).

## Rolls / sessions

Rolls are read from the existing roll manifest: the engine trades the actual
contract named for each ET day (no continuous-symbol exposure).
Sessions: RTH [09:30, 16:00) ET; the daily maintenance halt and weekends
naturally produce no bars; early closes flatten at their own last bar.
