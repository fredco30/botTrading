# HISTORICAL_SIGNAL_EXIT_AUDIT_M1 — EXIT PRE-REGISTRATION

Written and committed BEFORE any new-exit PnL was computed. The three exit
architectures below are transcribed from the mission charter (§8/§9/§10);
this file pins the implementation choices that the charter leaves open, so
that no code decision is made after seeing results. There is EXACTLY ONE new
exit per signal. The original historical exit is rerun as CONTROL only.

## Signal A — MTF F08 (EURUSD, tick-exact)

ENTRY (frozen, `families_m3.py@29dfb7b f08_asia_transfer("continuation", 10)`):
London 07:00 UTC M15-bar-close decision, continuation of the Asia move
(close 06:45 bar minus close 00:00 bar, same UTC day), |move| >= 10 pips.
CONTROL exit (historical): no stop, no target, time exit 960 min (= best
generic horizon 64 M15 bars), tick-exact engine, 5 s latency / 30 s window.

NEW EXIT A:
- INITIAL STOP: 2.0 x ATR(H1,14) at entry. ATR = rolling-mean true range
  over the last 14 COMPLETED H1 bars as of the decision timestamp
  (last H1 bar with close_time <= decision), in pips, frozen per event.
  Stop level = executed entry price -/+ 2.0 x ATR0 (side-adjusted).
- NO FIXED PROFIT TARGET.
- TRAIL: 3.0 x ATR(H1,14) Chandelier-style. ATR recomputed causally at every
  H1 bar completion during the trade (completed bars only). Anchor = highest
  H1 high (long) / lowest H1 low (short) over H1 bars with
  entry_ts < close_time <= update_time (bars completed since entry).
  Candidate = anchor -/+ 3.0 x ATR(H1,14)_at_update. Stop can ONLY tighten.
  Updates become effective for ticks with ts >= update_time (the H1 close
  time) — never retroactively.
- MAX HOLD: 24 h = 1440 min from the entry tick (same time-exit semantics as
  the historical engine: first tick strictly after t_end).
- Exit reasons recorded: STOP_INIT (initial 2xATR stop), TRAIL (trailed
  stop), TIME.
- 1R for expectancy reporting = 2.0 x ATR0 (initial stop distance).
- Baseline execution: 5 s latency, 30 s entry window, 0 slip. Stress: 30 s
  latency, +0.5 pip/side. Identical to historical MTF conventions.

## Signal B — SWING G10 (EURUSD + GBPUSD, 5m BID frame + spread model)

ENTRY (frozen, `families_sw.py@7e3bd46 g10_state_machine`):
D1 EMA20 vs EMA50 trend state (as-of at H4 close) + H4 close breaks previous
20-H4-bar close extreme. Signal TF H4; decision at H4 close.
CONTROL exit (historical registered cell SW_E029): entry first 5m bar with
open_ts >= decision, time exit after 6 H4 bars = 24 h, no stop, no target
(the historical scan was gross mid-price; the CONTROL rerun applies the same
hold through the validated conservative spread model: EURUSD 0.6 pip,
GBPUSD 1.0 pip full-spread-cross on long entry / short exit).

NEW EXIT B:
- INITIAL STOP: 2.0 x ATR(H4,14) at decision (last completed H4 bar =
  the decision bar), frozen per event. Levels follow the historical
  bar_replay fill conventions (long stop is a BID level; short stop is
  triggered on BID high at entry+sd-spread and fills at entry+sd).
- NO FIXED TP.
- TRAIL: 3.0 x ATR(H4,14) Chandelier-style on completed H4 bars, anchor =
  H4 extreme since entry (bars with entry_ts < close_time <= update),
  tighten-only, effective for 5m bars whose open_ts >= the H4 close time.
- REGIME EXIT: the D1 trend state as-of each completed D1 close (same
  EMA20/EMA50 relation as the entry). If the state no longer supports the
  trade direction, exit at the OPEN of the first 5m bar whose open_ts >=
  that D1 close (long: bid open; short: ask open = bid open + spread).
- MAX HOLD: 10 calendar days = 240 h from the entry 5m bar open.
- Exit reasons: STOP_INIT, TRAIL, REGIME, TIME. REGIME checked at bar open,
  before that bar's intrabar stop check.
- 1R = 2.0 x ATR0(H4). Stress: +0.5 pip/side on every fill (historical
  swing convention).

## Signal C — MTF F04b (EURUSD, tick-exact)

ENTRY (frozen, `families_m3.py@29dfb7b f04_prev_day("fade")`): M15 close
re-cross back inside after piercing previous UTC day High/Low, first fire
per side per UTC day, 07:00-17:00 UTC window.
CONTROL exit (historical, M3_E023): SL20 / TP30 / T240 tick-exact.
T240 AUDIT: t_exit_min = 240 min anchored at the ENTRY TICK timestamp; the
time exit executes at the FIRST TICK STRICTLY AFTER entry_ts+240 min at the
executable side price (mtf_replay semantics). Confirmed against the cached
historical trade list.

NEW EXIT C:
- INITIAL/PROTECTIVE STOP: KEEP 20 pips (unchanged from historical).
- TARGET: previous-day midpoint M = (PDH + PDL)/2, computed from the SAME
  previous-UTC-day M15 series the entry used, FROZEN at the decision
  timestamp. Fade from PDH (short): target = M. Fade from PDL (long):
  target = M. Never recomputed during the trade. Capped fill at M exactly
  (historical mtf_replay target convention).
- NO TRAILING STOP.
- MAX HOLD: T240 semantics unchanged (240 min, first tick strictly after).
- Exit reasons: STOP, TARGET (midpoint), TIME.
- 1R = 20 pips (unchanged). Stress: 30 s latency + 0.5 pip/side.

## Frozen analysis protocol (applies to all three)

1. PRIMARY comparison: EVENT-LEVEL audit — every frozen entry event replayed
   independently (no occupancy suppression) under CONTROL and NEW exit.
2. DEPLOYABLE replay: historical occupancy idiom (A/C: one position at a
   time per year replay; B: one position per pair), NEW exit only, plus
   native CONTROL for reference; common intersection on (decision_ts, side)
   reported. COMMON-SAMPLE ECONOMICS HAVE PRIORITY (LAB_AUDIT_M0).
3. Usefulness gate on DEPLOYABLE NEW: >= 2.0 trades/week, mean net
   >= +3.0 pips, PF >= 1.10, expR > 0, remove-best-1% > 0, stress mean > 0,
   stress PF >= 1.00, no catastrophic period; improvement must hold on the
   COMMON EVENT SET.
4. NO exit parameter sweeps: one architecture per signal, exactly the
   multipliers above. The CONTROL is rerun once. No partial profits,
   no break-even logic, no activation tuning.
5. Period: 2010-01-04 .. 2017-12-31 (the exact historical signal period;
   entry identity is defined there). Stability blocks 2010-2014, 2015-2016,
   2017. 2019+ never accessed; 2018 never loaded.
