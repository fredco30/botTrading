# LST_OPR_CANONICAL_V2 — FROZEN SPEC (committed BEFORE any PnL)

STRATEGY_ID=LST_OPR_CANONICAL_V2
DATE_FROZEN=2026-09-16
OBJECTIVE=faithful, objective automation of the LST Opening Range Masterclass.
V1 IS TERMINAL (NO_USEFUL_LST_OPR_EDGE) and is NOT modified. V2 removes every
engineered rule V1 had added: NO OPR-width gate, NO 6-bar timeout, NO 0.30-ATR
stop minimum, NO BE@1R, NO EMA8 trail, NO OPR_BACK early exit.
DATA=existing E:\ NQ ohlcv-1m -> 5m/15m/1h aggregates. 2020-01-01..2025-12-31.
2026_ACCESSED=NO. No new data purchase. No live trading. Classification:
INTERNAL HISTORICAL TEST (no pristine OOS subperiod).

SESSION=RTH 09:30-16:00 America/New_York (DST-aware).
OPR=high/low of the M15 bar 09:30-09:45 ET; usable only from 09:45.
WINDOW=setup decisions only on completed M5 bars with 09:45 <= time < 11:30 ET;
entry fills at the NEXT M5 open (so the last possible fill is the 11:30 open).
Max 1 executed trade/day per variant; one attempt per strategy per day.

FLOW (H1, unchanged from the V1 preregistered translation):
last completed H1 bar before 09:30 ET (08:00-09:00 ET).
BULL: close>EMA50 AND EMA20>EMA50 AND EMA50[t]>EMA50[t-5]; BEAR inverse;
else NEUTRAL = no trade. EMA ewm(span,adjust=False) on continuous completed
H1 closes. ATR14 H1 = mean TR of last 14 completed H1 bars incl. decision bar.

## A — BREAKOUT_PULLBACK (flow direction only)
SETUP: first completed M5 CLOSE beyond the boundary in-window
(long: close > OPR_HIGH). The breakout bar's own extreme is checked against
the runaway rule at confirmation.
RETEST (any LATER completed M5 bar IN-WINDOW, no time limit beyond the window):
long: low <= OPR_HIGH AND close >= OPR_HIGH. SHORT mirrored.
CANCELS: completed M5 high >= OPR_HIGH + 1.0*ATR_H1 at any moment before the
entry fill (long; incl. the breakout/retest bars themselves — checked BEFORE
retest validity on the same bar); OR window expiry.
OBSTACLE 1R FILTER (at retest decision): projected entry = retest close;
R_proj = |retest_close - retest_ext| (NO minimum). Nearest known level among
{prev RTH high, overnight high} ABOVE it (long; mirrored below for short):
if distance < R_proj -> OBSTACLE_REJECT (day dead for A). None -> pass.
ENTRY: next M5 open. STOP: retest-bar extreme (no minimum, never tightened);
if fill gaps beyond the stop -> trade aborted at fill, gross 0 (GAP_STOP).
R = |fill - stop|. TARGET = fill + 2R (long) / fill - 2R (short) — exact +2R,
limit (better open honored). MANAGEMENT: hard stop / 2R target / force-flat at
the 15:55 ET bar close. NOTHING ELSE (no BE, no trail, no OPR invalidation).

## B — REINTEGRATION_PULLBACK (flow direction only; bull case)
SETUP: price trades below OPR_LOW (false break), then a LATER completed M5
CLOSES back inside (close > OPR_LOW) = reintegration; structure extreme =
lowest low from the false-break bar through the reintegration bar.
PULLBACK RETEST (any LATER completed M5 bar in-window): low <= OPR_LOW AND
close >= OPR_LOW. If before the entry a completed M5 CLOSES below OPR_LOW
again, the cycle simply re-forms (back to waiting for the reintegration, with
the structure extreme still tracking) — no invented cancel.
CANCELS: intended-direction move reaches +1R before the entry: high >=
(reintegration close) + R_proj where R_proj = |reintegration_close -
structure_extreme| (bull; checked at reintegration confirmation and on every
subsequent bar BEFORE retest validity); OR window expiry.
RR GATE (at retest decision): projected entry = retest close;
R_proj = |retest_close - structure_extreme|; RR = |OPR opposite boundary -
retest_close| / R_proj; RR < 2.0 -> RR_REJECT (day dead for B).
ENTRY: next M5 open. STOP: structure extreme (no minimum). TARGET: opposite
OPR boundary (limit; better open honored). GAP through target at fill ->
aborted, gross 0 (GAP_TARGET). R = |fill - stop|. Management: hard stop /
target / 15:55 force-flat. NOTHING ELSE.

## C — COMBINED: first chronologically executable valid trade wins the day;
exact same-bar tie -> BREAKOUT (A) precedence (fixed now, not after results).

## COSTS (unit-audited)
INDEX POINTS native. NORMAL 1.5 pts RT ($30), STRESS 3.0 pts RT ($60).
USD = points*20 = ticks*5 (consistency verified in every report).

## MECHANICAL RESOLUTIONS (fixed before PnL)
V2-1. Retest candidates are bars AFTER the confirming bar (same-bar retest
       excluded).
V2-2. Runaway/obstacle/RR projections use the current completed bar's close /
      extremes only (no future data).
V2-3. Same-bar priority when a position is open: hard stop first, then target
      (pessimistic), then EOD at the 15:55 bar.
V2-4. One attempt per strategy per day: cancel/expiry/RR-reject/obstacle-reject
      kills that strategy for the day (the other strategy may still trade;
      in C the first valid entry wins).
V2-5. Entry fill uses the next M5 bar OPEN; abort conventions GAP_STOP /
      GAP_TARGET recorded with gross 0 (costs still applied).
V2-6. Diagnostics (width/ATR quartile, ATR quartile, side, entry-hour bucket,
      flow-strength |H1 close-EMA50|/ATR quartile, folds) are REPORT-ONLY.
