# AUTONOMOUS_EDGE_DISCOVERY_M2 — FINAL REPORT (terminal)

FINAL_STATUS = **NO_CONFIRMED_EDGE_FOUND** → STOP (mission 28)

- Branch: research/autonomous-edge-discovery-m2 (base 22473fb, F08 longitudinal tip).
- M2_EXPERIMENTS = 22 (ledger + disk counter; E001..E022, no silent discards).
- GLOBAL_EXPERIMENTS = 103 (= 81 M1 + 22 M2).
- M2_FAMILIES = 7 (F14..F20; GLOBAL_FAMILIES = 20).
- Budget respected: no experiment #23.. was needed; #70/#8 hard stops never approached.
- **2018H2_ACCESSED = NO.** No candidate reached the freeze bar, so the sole
  confirmation window was never opened (mission 19 gate held).
- 2019_PLUS_ACCESSED = NO. PROTECTED_OOS_ACCESSED = NO.
- Causality gate (T1/T2/T3 + 24 firing-bar traces each) ran on 2010 BEFORE
  any screening for every family; all 7 families PASS. Traces:
  cache/gate_trace_F14..F20.json.

## What was tested (all mechanisms new vs M1; tick-microstructure priority)

| Family | Mechanism (gated feature) | Verdict |
|---|---|---|
| F14 | spread-state transitions (close-spread vs 24h q10/q90 + move) | gross ~0, L/S sign splits — REJECT |
| F15 | displacement-per-tick thin-fade / grind-continue | thin-fade negative; grind N too small, unstable — REJECT |
| F16 | tick-flow imbalance continuation (sum(up−dn)15) | tick-exact 2010-17 −1.27p, 0/8 years — REJECT |
| F17 | post-spike reaction asymmetry (retrace fraction of range-expansion spike) | **best family — see below**; dead after costs — REJECT |
| F18 | inefficient-path extreme fade (er60 q10 + 60-bar extreme) | gross ~0 — REJECT |
| F19 | vol-crush state transition (rv30/rv1440 q10 after ≥8p move) | h240 BOTH sides negative — REJECT |
| F20 | time-since-extreme acceptance (age ≥ 20 bars at 90% position) | gross ~0 — REJECT |

## TOP_NEAR_MISS

**F17b — post-spike deep-retrace fade** (spike: range ≥ 3× mean30 range, body
≥ 0.6×range; next 3 bars retrace ≥ 2/3 of spike range; fade the spike).
- Gross multi-year screen 2010-2017, h=240: meanYR **+1.05 pips/trade**,
  **7/8 positive years**, both sides positive (L +1.86 / S +0.19), N=4733,
  worst year only −0.36. The mirror condition (F17a shallow-retrace
  continuation) is negative at every horizon — the reaction-shape discriminator
  is economically coherent, not noise.
- Tick-exact replay 2010-2017 (5s latency, real BID/ASK, SL15/TP15/T240):
  **−0.23 pips, PF 0.964, 2/8 positive years; stress-common −1.29, 0/8 years.**
  Plateau across thresholds 0.60/0.67/0.75, T120/T240, SL/TP 10/20 all
  negative (best cell −0.13, PF 0.983). Long horizon h=960 gross +1.90 but
  max year +17.7 vs min −4.4 (single-year concentration, §10) and L≫S.
- Cause of death: ~1.2 pips/trade execution cost ≈ 100%+ of the gross edge.
  Same wall as M1-F10; M2 confirms it is structural at 240-960min horizons
  for ~1-2 pip gross microstructure edges.

## REASONS_FOR_REJECTION (campaign level)

Across 7 causally-verified tick-microstructure families on 2010-2017, no
mechanism produced a gross conditional drift large enough to survive real
BID/ASK market execution with 5s latency (~1.2 pips round trip at these
horizons). The single robust gross effect found (F17b, multi-year stable,
direction-symmetric, plateaued in its threshold) is exactly cost-sized.
Screens with gross ≲ 1 pip were rejected without tick-exact replay; the two
screen survivors (F17b, F16a) died at tick-exact replay in BOTH baseline and
stress, across their whole coarse grids — no razor-thin winner to rescue
(and none was rescued, per mission 8/10/17).

## GOVERNANCE

- No candidate frozen → no 2018H2 access → confirmation window remains
  SEALED for a future campaign (the valuable asset of this cycle).
- No rule changes after any gate; no parameter rescue; no fine grids
  (≤ 8 meaningful configurations per family; F17 used 8 of 10).
- Ledger: RESEARCH_LEDGER_M2.csv; counters on disk; bulk tick caches stay
  local (cache/ gitignored).
- Reusable M2 infrastructure committed: validated data layer reuse +
  parameterized tick-exact replay + multi-year evidence/survival tooling
  (m2lib.py), 7 gated family feature definitions (families_m2.py).

STOP.
