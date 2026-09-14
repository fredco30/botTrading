# AUTONOMOUS_EDGE_DISCOVERY_M0 — FROZEN CANDIDATE SPEC (pre-confirmation)

Committed BEFORE any 2017H2 (confirmation) data access. Rules below are the
complete, deterministic strategy definitions. NO parameter may change after
the confirmation run is executed.

## Data / execution basis (mission §6)
- Dukascopy BID/ASK tick store, month parquet partitions (validated store,
  LAB_AUDIT_M0 manifest; 2017 partitions only).
- M1 MID bars for signal computation (decision at bar close, causal).
- Entry: first tick at/after decision + 5s (baseline) on the execution side
  (LONG -> ASK, SHORT -> BID); search bound 30 min.
- Exits: tick-accurate, first event wins, STOP priority on ties.
  LONG exits on BID, SHORT exits on ASK. TIME exit at entry+T.
- Stress: entry latency 30s + 0.50 pip adverse slippage per side.
- One open position per strategy; signals during occupancy are skipped.
- Data gaps (validated rule, weekends excluded): entry abort, open trade
  invalidation.

## CANDIDATE C1 — "H1-trend impulse continuation" (family F07)
Context : latest COMPLETED H1 mid bar close vs EMA20 of H1 mid closes
          (close > EMA20 -> up regime; < -> down regime)
Entry   : at an M1 bar close, if 15-minute MID return (close[i]-close[i-15])
          > +4.0 pips in up regime  -> LONG
          if 15-minute MID return < -4.0 pips in down regime -> SHORT
Stop    : 12 pips from entry (execution-side fill)
Target  : 12 pips from entry
TimeExit: 60 minutes after entry fill
Sessions: none (24/5)

## CANDIDATE C2 — "4-hour momentum continuation" (family F12)
Context : return over the last 4 COMPLETED H4 mid closes (close[i4]-close[i4-4])
Entry   : at an M1 bar close, if 4h return > +10 pips -> LONG
          if 4h return < -10 pips -> SHORT
Stop    : 15 pips from entry
Target  : 15 pips from entry
TimeExit: 120 minutes after entry fill
Sessions: none (24/5)

## Discovery-window evidence (2017-01-01..2017-06-30, tick-exact baseline)
C1 LONG : N=1022 mean +1.28p PF 1.41 expR +0.107 remove_best +1.16
C1 SHORT: N=967  mean +1.10p PF 1.37 expR +0.091 remove_best +0.98
C1 stress (30s+0.5p): LONG +0.39p PF 1.11 / SHORT +1.11p PF 1.37 (both > 0)
C2 LONG : N=592  mean +2.55p PF 1.71 expR +0.170 remove_best +2.42
C2 SHORT: N=602  mean +2.28p PF 1.69 expR +0.152 remove_best +2.13
C2 stress (30s+0.5p): LONG +1.53p PF 1.38 / SHORT +2.41p PF 1.74 (both > 0)
Monthly: every candidate positive in ALL SIX discovery months, both sides.

## Parameter plateau (established in M1-sim stage, ledger F07p/F12d)
C1: x in {3,4,5,6} x SL/TP in {10,12,15,12/20,20/12} x T in {30..120} — all
profitable (PF 1.31-1.58), honest decay at x=8 (PF ~1.2).
C2: thr in {10,15} x SL/TP in {15,20,15/30} x T in {120,180,240} — all 16
profitable (PF 1.62-3.08).

## Confirmation gate (mission §17)
PF > 1.10, net expectancy > 0, stress >= ~0, not dominated by best 1%
(remove_best > 0), direction consistent with discovery.
