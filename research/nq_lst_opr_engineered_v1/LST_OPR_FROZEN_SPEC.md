# LST_OPR_ENGINEERED_V1 — FROZEN SPEC (defined by the user BEFORE the NQ lab
# results were produced; implemented verbatim, no rule modified, no tuning)

STRATEGY_ID=LST_OPR_ENGINEERED_V1
DATE_FROZEN=2026-09-16 (user brief) / implemented 2026-09-16
MARKET=CME NQ (existing E:\ Databento GLBX.MDP3 NQ.v.0 ohlcv-1m -> 5m)
SESSION=RTH 09:30-16:00 America/New_York (DST-aware; never hard-coded 15:30 Paris)
TIMEFRAMES=H1 context / M15 opening range (09:30-09:45 ET) / M5 execution.
  All bars completed only.
2026_ACCESSED=NO. 2020-2025 = INTERNAL HISTORICAL TEST (not pristine OOS).

## FLOW (H1, frozen)
Last COMPLETED H1 bar before 09:30 ET (= the 08:00-09:00 ET bar).
BULL: close>EMA50 AND EMA20>EMA50 AND EMA50[t]>EMA50[t-5].
BEAR: inverse. Else NEUTRAL = NO TRADE. EMAs ewm(span,adjust=False) on the
continuous completed-H1 close series. ATR14 H1 = mean TR of the last 14
completed H1 bars INCLUDING the decision bar (it completed at 09:00 ET).

## OPENING RANGE (M15, frozen)
OPR = high/low of the 09:30-09:45 ET M15 bar (first three M5 bars); usable
only after completion (from the 09:45 bar). Gate: 0.25*ATR_H1 <= OPR_WIDTH
<= 1.00*ATR_H1, else no trade that day (RANGE_FILTER_REJECT).

## WINDOW (frozen)
Setup decisions only on completed M5 bars with 09:45 <= time < 11:30 ET.
Max 1 executed trade/day. One attempt per strategy per day (a cancelled or
expired setup kills that strategy for the day; the OTHER strategy may still
fire — relevant for variant C).

## A — BREAKOUT_PULLBACK (direction = FLOW; long case)
1. FLOW=BULL. 2. completed M5 CLOSE > OPR_HIGH (first occurrence = confirmed
breakout). 3. retest within the NEXT 6 completed M5 bars: bar TOUCHES
OPR_HIGH (low<=OPR_HIGH) AND CLOSES >= OPR_HIGH. 4. entry = NEXT M5 bar OPEN.
CANCEL if: no valid retest within 6 bars; OR any completed M5 high >=
OPR_HIGH + 1.0*ATR_H1 before execution (runaway); OR window ends.
SHORT = exact inverse. No market-entry breakout variant.

## A STOP/EXIT (frozen)
Stop = low of the qualifying retest bar (long), minimum distance
0.30*ATR_H1 from entry: if technical distance < 0.30 ATR, stop =
entry - 0.30*ATR (never tightened). Obstacle filter (2H): nearest known
structural level ABOVE the projected entry among {prev RTH high, overnight
high} (long; symmetric below for short) must satisfy
distance >= 1R (projected); none above -> pass. Exit mechanics: hard stop
(touch; worse open on gap); BE stop armed ONLY after a completed M5 CLOSE
>= entry+1R (BE active from the NEXT bar); EMA8-M5 trail armed after a
completed M5 CLOSE >= entry+2R, exit on completed M5 close < EMA8 (long);
exit on completed M5 CLOSE back inside the OPR (close < OPR_HIGH long);
force-flat at the 15:55 ET bar close.

## B — REINTEGRATION_PULLBACK (distinct mean-reversion mechanism; direction
## = FLOW; bull case)
1. FLOW=BULL. 2. price trades below OPR_LOW (false break). 3. a later
completed M5 CLOSES back inside (close > OPR_LOW) = reintegration; the stop
structure = lowest low from the false-break bar through the reintegration bar.
4. retest within the next 6 completed M5 bars: touches OPR_LOW and closes
>= OPR_LOW. 5. entry = NEXT M5 open. CANCEL if: close < OPR_LOW again before
entry; OR price runs +1R in the intended direction before the retest
(high >= reintegration_close + projected_R); OR 6 bars pass; OR window ends.
BEAR inverse via OPR_HIGH.
STOP = the false-break extreme, minimum 0.30*ATR from entry (never tightened).
TARGET = opposite OPR boundary (limit; better open honored). NO trailing.
The trade is allowed ONLY if RR >= 2.0 before costs.

## PREREGISTERED MECHANICAL RESOLUTIONS (fixed before any PnL; verbatim-rule
## gaps that need one deterministic reading each)
R1. Retest candidates are the bars AFTER the breakout/reintegration bar
    (the confirming bar is not its own retest).
R2. Obstacle/RR projections use the retest bar's CLOSE as the projected entry
    (the actual fill is the next open; the final stop applies the 0.30-ATR
    minimum from the ACTUAL fill; R is finalized at fill).
R3. A runaway-cancel uses completed M5 EXTREMES (high for long) vs boundary
    +1.0*ATR; B runaway-cancel uses ref=reintegration close + projected_R.
R4. One attempt per strategy per day: any cancel/expire kills that strategy
    for the day. C = first VALID ENTRY wins (A precedence if same bar).
R5. If the market-at-open fill gaps beyond the stop (A) or beyond the target
    (B), the trade is aborted at fill (gross 0, costs apply) — recorded as
    GAP_STOP / GAP_TARGET.
R6. BE is a hard stop at entry, active only from the bar after the >=+1R
    close (no intrabar BE before that close, per 2I).

## COSTS (unit-audited model from Phase 1)
MODELED_EXECUTION, round trip, 1 contract, INDEX POINTS:
LOW 0.75 / NORMAL 1.5 / STRESS 3.0 pts = $15 / $30 / $60.
USD_1_NQ = index_points * 20 = ticks * 5 (audit-verified consistency).
