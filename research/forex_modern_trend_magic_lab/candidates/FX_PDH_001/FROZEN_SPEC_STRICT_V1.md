# FX_PDH_001 — FROZEN SPEC STRICT V1 (causal correction, 2026-eligible)

This is NOT parameter tuning. The mechanism and parameters are unchanged from
FROZEN_SPEC.md (stop 1.0 x ATR14 / trail 3.0 x ATR14 / 48h hold). STRICT V1 is
the causal/execution correction identified by the independent audit
(see ../../audit/FX_PDH_001_STRICT_AUDIT.md). From this document onward,
STRICT V1 is the ONLY version eligible for the protected 2026 test.

```
PAIR              = USDJPY
SIDE              = LONG
TIMEFRAME         = H1 (left-labelled resample of completed 5m BID bars)
SIGNAL            = first H1 touch/break of the prior COMPLETED UTC day's high
                    (high[i] > PDH; one signal per day; decision at bar close)
ENTRY             = next H1 bar open, modeled fill = open + spread + entry-slip
STOP              = entry_fill - 1.0 x ATR14(signal bar)
TRAIL             = max(high since entry through bar i-1) - 3.0 x ATR14(bar i-1)
MAX_HOLD          = 48 H1 bars (time exit at bar close)
TAKE PROFIT       = NONE
POSITIONS         = one at a time; no pyramiding; max one entry per day
COSTS             = NORMAL: spread 0.9 pip, no slip
                    STRESS:  spread 0.9 + 0.5 pip slip per side (1.9 total)
PERIOD            = 2020-01-01 .. 2025-12-31     2026_ACCESSED = NO
```

## Critical execution rules (each enforced and unit-tested)

1. The initial stop is active IMMEDIATELY from the entry fill: the entry H1
   bar CAN stop out (`l[entry] <= stop` -> exit on the entry bar, fill at
   `min(open[entry], stop) - exit_slip`). [audit defect D1, fixed]
2. No current-bar ATR may affect an intrabar stop: the trailing level for
   bar i is computed from ATR14 of bar i-1 only (that value is final at the
   close of bar i-1). The current bar's range never sets its own stop.
   [audit defect D2, fixed]
3. ATR value available at the entry open — precise definition:
   the stop uses **ATR14 of the SIGNAL bar** (the bar whose break fired the
   signal). The signal bar is COMPLETE at its close; the entry order is
   placed at that moment and fills at the next bar's open. Therefore
   ATR14(signal) is fully known strictly BEFORE the entry bar opens and
   before the fill exists. No information from the entry bar or later
   enters the initial stop.
4. Conservative intrabar handling: if a bar opens below the active stop,
   the fill is taken at the OPEN (worse), not at the stop level.
   Time exits fill at the bar close.
5. A bar that exits a position cannot trigger a new entry in the same bar.
6. Round-trip cost model (corrected in STRICT V1, see audit defect D3):
   long pays ONE spread (buy at ask = bid + spread, sell at bid) plus
   modeled slippage per side. The pre-strict replay formula double-charged
   the spread; STRICT V1 charges exactly one.

## Reproduction

Engine: `../../audit/replay_strict.py` (deterministic, no randomness).
Tests: `../../audit/test_replay_strict.py` (17 checks incl. trade-exact
reproduction against `../../audit/FX_PDH_001_STRICT_RESULTS.json`).
Result summary (NORMAL): N=639, PF 1.379, +4.90 net pips/trade, t=+2.52,
remove-best-1% +2.54, STRESS +3.82; see the JSON for by-year and equity.
