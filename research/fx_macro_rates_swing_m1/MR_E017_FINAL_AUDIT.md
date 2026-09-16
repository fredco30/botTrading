# MR_E017 FINAL INDEPENDENT AUDIT — CLOSURE

Branch head audited: `a895d793ddda61679f220dbeb55b00ecca89a313`.
Frozen spec: `708cfab0a68276efd86edfd4e8d341307b4a6831`. No rules changed.

Method: `run_final_audit.py` is a standalone scalar implementation importing
nothing from the research code (no swing_lib / mrlib / run_screens). It
re-derives from raw parquet + roll_map.csv: ZN back-adjustment, 24h
impulse z (30d trailing vol), H4 close-labelled FX bars, ATR(H4,14), fx24,
the frozen decision/side rule, entry/stop/target fills, 48h max hold, AND
the one-position-at-a-time state machine (suppression while a position is
open; next eligible signal after exit). Reference trade lists were dumped
unchanged from the frozen implementations (`dump_reference_trades.py`,
N = 93 / 23 / 5 as expected). The audit's own entry-bar semantics bug (first
draft searched 5m bars by close time instead of open time) was found and
fixed in the AUDIT implementation only — the strategy and reference were
never touched.

```
MR_E017_FINAL_INDEPENDENT_AUDIT

FROZEN_SPEC=708cfab0a68276efd86edfd4e8d341307b4a6831

EURUSD_DISCOVERY:
REFERENCE_N=93
AUDIT_N=93
MATCHED_N=93
MISSING=0
EXTRA=0
CONTENT_MISMATCHES=0

USDJPY_STAGE_A:
REFERENCE_N=23
AUDIT_N=23
MATCHED_N=23
MISSING=0
EXTRA=0
CONTENT_MISMATCHES=0

EURUSD_2018H2_STAGE_B:
REFERENCE_N=5
AUDIT_N=5
MATCHED_N=5
MISSING=0
EXTRA=0
CONTENT_MISMATCHES=0

CAUSALITY=PASS — per audited trade: max rates input close <= decision ts and
all FX inputs (H4 closes, fx24 lookback, ATR window) closed at/before
decision; 121/121 trades verified (93+23+5).

Verified per trade: decision timestamp, max rates input timestamp, FX feature
inputs, side, entry timestamp, entry price, ATR at decision, stop distance,
target distance, exit timestamp, exit reason, exit price, net pips, R
(tolerances 1e-6; timestamps exact).

2019_PLUS_ACCESSED=NO
PROTECTED_OOS_ACCESSED=NO
RULES_CHANGED=NO

FINAL_STATUS=FULL_INDEPENDENT_AUDIT_PASS

STOP.
```

Artifacts: `cache/final_independent_audit.json` (per-set results),
`cache/reference_trades_final.json` (reference lists),
`dump_reference_trades.py` (reference extraction, frozen code unchanged),
`run_final_audit.py` (standalone audit).
