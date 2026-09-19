# FX_PDH_002 — FROZEN SPEC V1 (C1 entry + D2 daily-chandelier exit)

New candidate created by the FX_PDH_002 LAB. It does NOT modify, replace,
or reinterpret FX_PDH_001 STRICT V1 (vault, commit `033f6f0`, replication
`617f9b1`); both candidates remain frozen side by side and will be compared
on the same untouched 2026 period. FX_PDH_002 = the ONE pre-registered
composite (`../../FX_PDH_002_COMPOSITE_PREREG.md`, written and committed
BEFORE the composite PnL existed) of the two strongest independently
validated components:

* C1 close-confirm entry (002C: 1 of 3 alternatives survived),
* D2 daily-chandelier exit (002D: 2 of 3 alternatives survived).

Pyramiding (002B) was validated separately (B1_P075) and is intentionally
NOT part of this candidate (its layer exits were only validated under the
strict 3-ATR trail; combining would have required untested rules).
FX_PDH_002A (short mirror) is DEAD.

```
PAIR              = USDJPY
SIDE              = LONG
TIMEFRAME         = H1 (left-labelled resample of completed 5m BID bars,
                    tmlab conventions, hard 2026 seal)
SIGNAL (C1)       = first H1 bar of the UTC day whose CLOSE is above the
                    prior COMPLETED UTC day's high (one signal per day;
                    days with < 4 completed H1 bars skipped)
ENTRY             = next H1 bar open, fill = open + 0.9 pip spread
                    (+ stress: 0.5 pip slip per side)
INITIAL STOP      = entry_fill - 1.0 x ATR14(H1, Wilder RMA) of the SIGNAL
                    bar; active IMMEDIATELY from the fill; the entry bar CAN
                    stop out (fill = min(open, stop) - exit slip)
TRAIL (D2)        = daily chandelier: until the first COMPLETED UTC day
                    boundary after entry only the initial stop is active;
                    from the first H1 bar of the next completed day,
                    trail = max(DAILY high of completed days since entry)
                            - 3.0 x daily ATR14(last completed day)
                    eff_stop = max(initial stop, trail); never widened
                    (daily ATR14 = Wilder RMA of daily true range)
MAX HOLD          = 48 H1 bars (time exit at bar close)
TAKE PROFIT       = NONE
POSITIONS         = one at a time; a bar that exits cannot enter again in
                    the same bar; one signal per day
COSTS             = NORMAL: spread 0.9 pip, no slip (ONE round-trip)
                    STRESS:  + 0.5 pip adverse slippage per side (1.9 total)
                    conservative intrabar fills; stops fill at
                    min(open, level) - slip; time exits at close - slip
PERIOD            = 2020-01-01 .. 2025-12-31 UTC     2026_ACCESSED = NO
```

## Critical rules (inherited from STRICT V1 and unit-tested)

1. Initial stop active from the entry fill; entry bar can stop out.
2. No current-bar ATR sets its own intrabar stop; the daily-chandelier trail
   uses only COMPLETED daily bars (day boundary rule above).
3. Conservative fills (open when gapped through the stop; close for time).
4. One spread round-trip only (net = gross - spread - slip).
5. All data through `forex_modern_trend_magic_lab.tmlab.load_5m` — hard
   2026 seal on every load (2026_ACCESSED = NO).

## Reproduction

Engine: `code/engine.py` (identical to the lab engine at freeze commit).
Runner: `code/run_frozen.py` — writes `RESULTS.json` (deterministic, no
randomness). Tests: `tests/test_frozen.py` (trade-exact reproduction of the
frozen numbers, seal checks, C1/D2 definition checks).

Frozen headline (NORMAL): N=517, trades/week 1.65, PF 1.573,
+8.43 net pips/trade, t=+3.13, remove-best-1% +5.59, STRESS +6.63,
EUR500@0.5% -> EUR 1145, maxDD 6.7%, all six years positive,
2022 = 30.5% of gross profit. See RESULTS.json / RESULTS.md.
