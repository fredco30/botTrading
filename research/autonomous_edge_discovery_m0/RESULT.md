# AUTONOMOUS_EDGE_DISCOVERY_M0 — FINAL REPORT

FINAL_STATUS = **CONFIRMED_CANDIDATE_FOUND** → STOP FOR HUMAN REVIEW
(no 2010–2018 full validation run, per mission §19A/§25)

- Branch: `research/autonomous-edge-discovery-m0` (based on `research/lab-audit-m0`,
  the LAB_PASS head). No merges, no prior research modified, no bulk data in git.
- Data: validated Dukascopy EURUSD BID/ASK tick store
  (E:/ResearchData/botTrading/ticks/parquet, 2017 partitions only).
- Discovery window: 2017-01-01..2017-06-30. Confirmation window:
  2017-07-01..2017-12-31, accessed ONLY after FROZEN_CANDIDATES.md was
  committed (git history enforces the ordering).
- Execution: real BID/ASK sides, 5s baseline entry latency, tick-accurate
  stop/target/time resolution, stop-priority on ties, data-gap invalidation
  (validated rule). Stress = 30s latency + 0.50 pip adverse slippage per side.
  Engine primitives mirror the validated mtf_lib (LAB_AUDIT_M0 control G/H/I);
  12-trade independent scalar spot-audit reproduced the replay.

## EXPERIMENTS_TOTAL = 271 (ledger rows E001..E271, incl. 4 confirmation rows)
## FAMILIES_TOTAL = 15 mechanism families screened
(F01 impulse continuation, F02 impulse reversion, F03 hour-of-day drift,
F05 session range breakout/false-breakout, F06 climactic-spike fade,
F07 H1-trend × impulse, F08 weekend gap, F10 tick-activity intensity,
F11 24h-extreme stretch, F12 4h momentum, F14 volatility compression,
F15 daily-VWAP reversion, F07d/F12d deepening, tick-replay F07t/F12t)

Dead families (killed fast, ledger kept): F01/F02 flat alone, F05 design
produced no events (killed, not rescued), F08 killed (0 usable weekends),
F10/F11/F15 sub-cost, F06 sub-cost. Only F07/F12 showed material evidence
and were deepened.

## BEST_CANDIDATE = C2 — "4-hour momentum continuation" (family F12)

### RULES (complete, frozen in FROZEN_CANDIDATES.md)
- Context: EURUSD, 24/5, no session filter, one position at a time.
- Signal at any M1 bar close: MID return over the last 4 completed H4 closes.
  > +10 pips → LONG; < −10 pips → SHORT.
- Entry: first tick ≥ decision + 5s on execution side (ASK for long,
  BID for short).
- Stop: 15 pips. Target: 15 pips. Time exit: 120 minutes after entry fill.
  First event wins, stop priority on ties.
- Fixed normalized risk (1R = 15 pips). No martingale/pyramid/sizing tricks.

### DISCOVERY (2017H1, tick-exact baseline)
N=1194 (592 L + 602 S) | TRADES_PER_MONTH=199
MEAN_NET_PIPS=+2.42 | PF=1.70 | EXPECTANCY_R=+0.161
STRESS_R=+1.97 (mean of L +1.53 / S +2.41 under 30s+0.5p)
REMOVE_BEST_1PCT=+2.28 — positive all 6 months, both sides

### CONFIRMATION (2017H2, frozen rules, tick-exact baseline)
N=1195 (645 L + 550 S) | TRADES_PER_MONTH=199
MEAN_NET_PIPS=+2.53 | PF=1.77 | EXPECTANCY_R=+0.169
STRESS_R=+1.94 (L +1.80 / S +2.07)
REMOVE_BEST_1PCT=+2.39 — positive all 6 months, both sides

### PARAMETER_PLATEAU (M1-sim stage, 16 configs, all profitable)
thr {10,15} × SL/TP {15/15, 20/20, 15/30} × T {120,180,240}: PF 1.62–3.08,
expR 0.135–0.355. No razor optimum. Long AND short profitable in every
monthly cell of both halves.

## SECOND CANDIDATE = C1 — "H1-trend impulse continuation" (family F07)
Rules: H1 close vs EMA20(H1) regime; 15-min impulse > +4p (up regime) → LONG,
< −4p (down regime) → SHORT; SL/TP 12p; time exit 60 min.
DISCOVERY: N=1989, mean +1.19p, PF 1.39, expR +0.099, stress L +0.39 / S +1.11,
positive all 6 months. CONFIRMATION: N=1996, mean +1.22p, PF 1.40,
expR +0.101, stress L +0.29 / S +1.41, positive all 6 months.
Plateau: x {3..6} × SL/TP {10..20} × T {30..120} all profitable (24 configs).
C1 passes §17 but is weaker and more cost-sensitive than C2 (stress L is
marginal: +0.29/+0.39).

## WHY_EDGE_MAY_EXIST
Short-horizon momentum persistence in FX is a documented, economically
grounded effect (time-series momentum across currency futures; intraday
momentum/order-flow continuation). Mechanism: institutional order flow is
executed in slices over hours (client rolls, hedging flows, central-bank
operations), which creates positive short-horizon return autocorrelation
conditional on an impulse; the 4h trigger harvests the middle of these
episodes while the symmetric 15-pip bracket bounds the mean-reversion tail.
Both sides and both halves of 2017 worked, including H2's trend reversal
(EUR topped in September), which is the opposite of a single-direction
trend-beta artifact.

## OVERFIT_RISK = LOW
- 2 of 15 families won; winners were selected after ONE deepening pass each.
- Rules are 4 numbers (thr 10p, SL 15p, TP 15p, T 120m) on a raw return.
- Broad plateaus both families; honest decay at extreme parameters (F07 x=8).
- No session/market/metric filters were added to rescue anything.
- Confirmation was run once, frozen, and passed with HIGHER PF than discovery
  (1.77 vs 1.70) — the opposite of a discovery-window artifact.
- Caveats (for human review): 6+6 months is a short total span (one year,
  one macro regime); 2017 had an unusually clean EUR trend for 9+ months.
  The candidate must still pass full 2010–2018 frozen validation.

## NEXT STEP (human decision)
Run the frozen full-history validation (2010–2018) for C2 (and optionally C1)
in a separate mission. DO NOT tune parameters under any circumstances.
