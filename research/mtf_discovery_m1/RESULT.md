# MULTITIMEFRAME_DISCOVERY_M1 — FINAL REPORT (terminal)

FINAL_STATUS = **NO_CONFIRMED_MULTITIMEFRAME_EDGE** → STOP (mission 25/23)

- Branch: research/multitimeframe-discovery-m1 (base b417d19 = M2 tip, preserved & pushed).
- M3_EXPERIMENTS = 31 (ledger M3_E001..E031; budget 80 — never approached).
- M3_FAMILIES = 12/12 (F01..F12; family cap reached, no family #13 exists).
- **2018H2_ACCESSED = NO.** No candidate reached the freeze bar (§16/§19), so
  the sole sealed confirmation window was never opened. 2018H1 also never
  loaded. 2019_PLUS_ACCESSED = NO. PROTECTED_OOS_ACCESSED = NO.
- Signals: M15 (9 families) and H4 (2 families) completed bars; ticks used
  ONLY for execution (5 s latency entry, real BID/ASK sides, gap-through
  stops, capped targets, stop priority, 30 s + 0.5 pip/side stress).
- Data: Dukascopy EURUSD ticks 2010-2017 (LAB_AUDIT_M0 LAB_PASS layer,
  infra_lib.load_year), bars rebuilt causally (close-time-labelled completed
  M1/M5/M15/H1/H4 bars; bucket id = (close_time−1)//tf).
- Execution engine: m3lib.mtf_replay — vectorized exit scan proven
  byte-identical to the audited m2lib.m2_replay on 4 SL/TP/T/latency cells
  (tests/test_replay_equivalence.py, including 3-day holds and stress).

## What was tested (all new vs M1/M2 tick campaigns; bar-level M5-H4 signals)

| Family | Mechanism (signal TF) | Screen gross | Tick-exact net verdict |
|---|---|---|---|
| F01 | H4 z-band fade, SMA50, \|z\|≥2 (H4) | **+8.20p** (h24, 261 sig, L +4.9/S +8.3) | +2.74p, PF 1.069, expR −0.006R, remove-best −1.23 → near-miss |
| F01b | F01 + ADX<20 regime filter (H4) | +9.35p (N=130) | +1.98p, PF 1.086, 5/8 yr → REJECT |
| F01w | F01 wide stop 4σ, no TP (drift capture) | — | +2.97p, PF 1.067, remove-best −2.0 → REJECT |
| F02 | Donchian 30/60 break (H4) | −0.21 / +2.00 | ~0, L/S split → REJECT |
| F03 | London break of Asia range (M15) | +0.25 / +0.44 / −0.34 | ~0, sides split → REJECT |
| F04 | Prev-day H/L break / fade (M15) | −0.02 / **+3.08** (both sides) | fade: +0.39p, PF 1.04 → REJECT |
| F05 | Failed break of H4 Donchian (M15) | +2.02 (S +3.3, L −0.1) | one-side → REJECT |
| F06 | H4 trend + H1 pullback + M15 cross | −0.84 | negative → REJECT |
| F07 | M15 squeeze + H4-direction break | −0.35 | negative → REJECT |
| F08 | Asia→London state transfer (M15) | +3.90 (S +8.0, L +0.3) | one-side regime beta → REJECT |
| F09 | H4 momentum accel + M15 thrust | −0.64 | negative → REJECT |
| F10 | Prev-week H/L break / fade (M15) | +2.38 / **+3.38** (both sides) | fade: **+1.10p, PF 1.093, expR +0.044R** → best near-miss |
| F11 | Sunday-gap fade / continuation (M15) | +0.65 / +5.57 (S-only) / −0.41 | tiny N, one-side → REJECT |
| F12 | N-day break + M15 retest | +0.32 / −0.79 / +2.29 | below bar → REJECT |

All F01/F04/F10/F05-family signals passed the T1/T2/T3 causality gate on
2010 (24 firing-bar traces each: max input ts ≤ decision ts, truncation
identity, future-mutation identity; traces in cache/gate_trace_*.json).

## TOP_NEAR_MISSES

### 1. F10b — previous-week high/low fade (M15 trigger, Mon-Thu)

M15 close re-enters the prior week's range after poking beyond it; SHORT
after upside poke, LONG after downside poke; SL 25 / TP 40 pips / T 480 min,
5 s latency, one position at a time. Discovery 2010-2017, tick-exact:

- N = 290, 3.09 trades/month, mean **+1.095 pips**, median −6.05, total +317.5
- PF **1.093**, expectancy **+0.0438 R**, win 46.2 %
- 5/8 positive years, 46/94 positive months; L +0.046 R / S +0.041 R
- remove-best-1 % **+0.688 p** (>0), stress-common **+0.62 p** (>0)
- max DD 22.2 R, worst year −9.0 R, worst rolling-12m −10.8 R
- Survival (500 EUR, 0.5 %/trade): final **530.50**, max DD **10.64 %**,
  worst year −4.45 %, worst rolling-12m −5.29 %, lowest 456.69 — no veto.
- Per-year (pips): 2010 +113.5, 2011 −200.6, 2012 −225.5, 2013 −7.1,
  2014 +95.7, 2015 +52.9, 2016 +94.7, **2017 +393.9**.
- Why not frozen: PF 1.093 ≪ 1.20 target and the R profile is
  regime-concentrated (2017 = +15.8 R of +23.1 R total; 2011-2012 lose
  −8/−9 R in trend years) — precisely the §12 regime-fragility flag. A
  marginal-freeze here would have spent the one sealed window on a
  likely-regression candidate.

### 2. F01a — H4 z-band fade (SMA50/std50, |z| ≥ 2)

SHORT at z ≥ +2, LONG at z ≤ −2; TP = mid-band frozen at decision, SL = 2σ
(1:1 band geometry), T 5760 min. Discovery 2010-2017, tick-exact:

- N = 403, 4.2/month, mean **+2.736 pips** (clears the +2.0 preference),
  total +1102.7, PF **1.069**, expectancy −0.006 R, win 49.9 %
- 5/8 positive years; L −0.046 R / S +0.030 R
- remove-best-1 % **−1.233 p** (≤0 — the top 1 % of trades carry the edge),
  stress-common +1.73 p (corrected; E020 value invalid, see governance)
- max DD 10.2 R, worst year −4.5 R, worst rolling-12m −7.7 R; survival
  final 491.80, max DD 5.05 %, lowest 486.72 — no veto.
- Per-year (pips): 2010 +706.7, 2011 +145.4, 2012 +673.2, 2013 −386.3,
  2014 +303.8, 2015 −186.1, 2016 −281.2, 2017 +127.3.
- Why not frozen: the gross drift is real (screen +8.2 p/trade at fixed
  24-H4-bar horizon, both sides, 8-year stable) but net expectancy is ~0:
  ~1.2 p round-trip cost ≈ 45 % of the achievable net mean, PF stuck at
  1.07 across three structural exit variants (mid-band TP, ADX regime
  filter, wide-stop drift capture). Same structural wall as M2-F17b.

## REASONS_FOR_REJECTION (campaign level)

Across 12 causally-gated families and 31 experiments, no M5/M15/H1/H4
signal family produced a conditional drift large enough to clear ~1.0-1.2 p
of real execution cost with PF ≥ 1.20 and expectancy ≥ +0.05 R. Fade-type
edges (H4 band, weekly/daily S/R re-entry, PDH/PDL) exist gross at +2-8
pips but net out at PF 1.04-1.09. Breakout/trend families (Donchian,
London break, squeeze break, trend-pullback, acceleration, break-retest)
show ≈ 0 gross on EURUSD 2010-2017 at these scales. The only ≥3-pip gross
survivors that failed the both-side/mechanism sanity (F08a short-only,
F11b short-only, F05 short-side) were rejected without tick replay per §12
(one direction = all profit, regime-beta explanation).

## GOVERNANCE

- Budget: 31/80 experiments, 12/12 families, max 7 configs in any family
  (F01). Hard stops never approached. Ledger: RESEARCH_LEDGER_M3.csv.
- E031 is an EVIDENCE_CORRECTION: E020's stress-common was computed with
  m2lib.common_sample keyed on per-year index j (collides across years when
  trade lists are pooled); stress_common was re-keyed on decision_ts
  (m3lib.stress_common) and F01a re-reported (+1.73 p, common N=402).
  E021-E024 already used the corrected function.
- Incident: an accidental `import run_screens` resolved to M1's
  run_screens.py (sys.path shadowing) and appended 3 rows to M1's ledger.
  Both files were restored to HEAD (git checkout) — M1/M2 campaign dirs are
  byte-identical to commit b417d19 again; legacy dirs are now APPENDED to
  sys.path so this cannot recur.
- The sealed window (2018-07-01..2018-12-31) was never read, extracted, or
  computed on. No parameter was tuned against 2018. No candidate was frozen
  (MULTITIMEFRAME_M1_FROZEN_SPEC.md intentionally does not exist).

MULTITIMEFRAME_DISCOVERY_M1

EXPERIMENTS=31
FAMILIES=12

TOP_NEAR_MISSES=F10b prev-week-H/L fade (net +1.10p PF 1.093 expR +0.044R,
remove-best +0.69, stress-common +0.62, 5/8 yr, survival PASS — fails PF
≥1.20/expR ≥0.05, R regime-concentrated in 2017); F01a H4 z-band fade (net
+2.74p PF 1.069 expR −0.006R, remove-best −1.23, stress-common +1.73,
survival PASS — gross +8.2p drift does not survive 1:1 band exits + costs)

2018H2_ACCESSED=NO

REASONS_FOR_REJECTION=no M5/M15/H1/H4 mechanism cleared PF 1.20 AND
expR +0.05R on 2010-2017 tick-exact replay: fade edges gross +2-8p collapse
to PF 1.04-1.09 after ~1.2p execution cost; breakout/trend families ≈ 0
gross; one-side survivors rejected for direction concentration (§12)

2019_PLUS_ACCESSED=NO
PROTECTED_OOS_ACCESSED=NO

FINAL_STATUS=NO_CONFIRMED_MULTITIMEFRAME_EDGE

STOP.
