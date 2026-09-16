# HISTORICAL_SIGNAL_EXIT_AUDIT_M1 — FINAL REPORT (terminal)

QUESTION AUDITED: did we reject any sufficiently-frequent old signal because
its EXIT architecture was wrong? Answer after full audit: **NO.** One signal
(G10) genuinely improves with a mechanism-matched exit but remains below the
usefulness bar; the other two do not improve at all.

- Branch: research/historical-signal-exit-audit-m1 (base 0a4eb55, preserved).
- New exits pre-registered in EXIT_PREREGISTRATION.md BEFORE any PnL.
- No entry change of any kind; event sets reconstructed from source commits
  and verified against historical artifacts (ENTRY_IDENTITY.md, all PASS).
- New-exit causality suite: 66/66 PASS (run_causality.py: post-exit mutation
  invariance, truncation at trail updates, frozen ATR0/midpoint, tighten-only).
- Infra hazard avoided: NO sys.path imports — all historical code copied
  verbatim (provenance-tagged) into audit_lib.py; no historical ledger,
  counter or cache mutated. F04b control reproduces the cached historical
  trades BYTE-EXACT (145/145 on 2010; deployable N=1183 mean +0.388 PF 1.04
  == ledger M3_E023).
- Period: 2010-01-04 .. 2017-12-31 only (the historical signal identity
  window). 2018 and 2019+ never accessed. Stability blocks are HISTORICAL
  blocks, not pristine OOS.

## LOW_FREQUENCY_SKIPPED (FREQUENCY_IMMUTABLE_FAIL — documented, not replayed)

- G08= path-efficiency: best registered deploy SW_E038 N=106 trades / 8y
  = 0.25/wk (233 raw events ~= 0.56/wk); plateau SW_E042 0.9/wk. Immutable.
- G11= vol-regime transition: SW_E035 N=56 / 8y = 0.13/wk (variants 40-56).
  Immutable.
- F10B= prev-week fade: M3_E024 tick replay N=290 / 8y = 0.70/wk. Immutable.
- MR_E017= archived candidate's frozen validation sets 93/23/5 trades (<1/wk);
  its high-frequency family form M2_E017 already economics-dead (N=5503,
  mean -0.127, PF 0.983). Not replayed per mission.
- CN_E035 excluded by charter (exit already mechanism-matched; fail was
  frequency only at 1.86/wk).

## SIGNAL_A: MTF F08 — Asia->London continuation (EURUSD, tick-exact)

NAME=MTF F08 | ENTRY_IDENTITY=PASS (EVENT_HASH 87d603bb8089b19b..., N=1257
raw events = historical screen N exactly; screen gross +3.9016 replicated)
EVENTS_PER_WEEK=3.017 | ORIGINAL_EXIT=generic fixed horizon: time exit 960
min (64 M15 bars), no stop/target | NEW_EXIT=2.0xATR(H1,14) initial stop +
3.0xATR(H1,14) Chandelier trail (tighten-only, completed H1 bars) + 24h max
hold (single pre-registered architecture)

COMMON_SAMPLE_ORIGINAL (event-level, N=1255 after 2 no-fills):
  N=1255  MEAN_PIPS=+3.119  PF=1.123  EXPECTANCY_R=+0.075  STRESS=+2.159p
  (PF 1.084)
COMMON_SAMPLE_NEW (event-level, same events):
  N=1255  MEAN_PIPS=+2.271  PF=1.133  EXPECTANCY_R=+0.054  STRESS=+1.051p
  (PF 1.059)
DEPLOYABLE_NEW: N=1169  TRADES_PER_WEEK=2.807  MEAN_PIPS=+2.862  PF=1.170
EXPECTANCY_R=+0.068 | stress +1.598p (PF 1.092) | common-deployable
(n=1169): control +3.49 vs new +2.86
EXIT_DIAGNOSTICS=TRAIL 47.0% / STOP_INIT 36.2% / TIME 16.8%; win 34.0%;
median -15.2p; MFE +45.4 vs control +54.3; blocks: 2010-2014 +3.88p PF 1.21,
2015-2016 +1.66p PF 1.11, 2017 -0.45p PF 0.96 (degrading)
VERDICT=NOT_REHABILITATED. Gate FAIL (mean +2.86 < +3.0) AND the
mechanism-matched exit is WORSE than the original generic exit on the common
event set (mean, expR, remove-best all degrade; only PF moves 1.123->1.133).
Trail clips the right tail (max winner 273p vs 384p). Side concentration
that historically killed F08 persists under the new exit (short expR
+0.144, long +0.001): the entry was always one-side regime beta. The exit
was never the problem. STOP.

## SIGNAL_B: SWING G10 — D1 EMA20/50 x H4 Donchian20 (EURUSD+GBPUSD, 5m)

NAME=SWING G10 | ENTRY_IDENTITY=PASS (EVENT_HASH f1b6385668e8a86c..., 3038
raw events; historical scan cell SW_E029 replicated: N=1057, +1.7871p,
PF 1.0644)
EVENTS_PER_WEEK=7.30 raw (non-overlapping deployable far lower) |
ORIGINAL_EXIT=generic fixed horizon: 24h time exit, no stop/target (the
registered scan cell; gross +1.79p, never cost-replayed) | NEW_EXIT=2.0
xATR(H4,14) initial stop + 3.0xATR(H4,14) Chandelier trail + D1-trend
regime exit + 240h max hold

COMMON_SAMPLE_ORIGINAL (event-level, N=3038):
  N=3038  MEAN_PIPS=+0.761  PF=1.029  EXPECTANCY_R=+0.016  STRESS=-0.239p
  (PF 0.991)
COMMON_SAMPLE_NEW (event-level, same events):
  N=3038  MEAN_PIPS=+1.515  PF=1.038  EXPECTANCY_R=+0.062  STRESS=+0.432p
  (PF 1.011)
DEPLOYABLE_NEW: N=602  TRADES_PER_WEEK=1.448  MEAN_PIPS=+1.891  PF=1.047
EXPECTANCY_R=+0.059 | stress +0.620p (PF 1.015) | common-deployable
(n=576): control -0.36 vs new -0.585 (BOTH NEGATIVE), new remove-best
-5.67
EXIT_DIAGNOSTICS=TRAIL 66.3% / STOP_INIT 27.9% / TIME 5.3% / REGIME 0.5%;
avg winner 112p vs control 53p (trail lets trends run); median -36.3p;
remove-best -3.688 (tail-dependent); blocks: 2010-2014 +3.8p PF 1.09,
2015-2016 +6.6p PF 1.16, 2017 -15.2p PF 0.58 (collapse)
VERDICT=EXIT_IMPROVED_BUT_NOT_USEFUL (mission §18). The trail exit doubles
event-level mean (+0.76 -> +1.52) — the exit WAS suboptimal — but the
signal still fails every usefulness gate: 1.45 trades/wk < 2.0, mean +1.89
< +3.0, PF 1.047 < 1.10, remove-best < 0, 2017 collapse, and the
common-deployable sample is NEGATIVE — much of the native improvement is
occupancy/sample composition (the §7 trap), not economics. Documented and
STOPPED. No rescue.

## SIGNAL_C: MTF F04b — previous-day H/L fade (EURUSD, tick-exact)

NAME=MTF F04b | ENTRY_IDENTITY=PASS (EVENT_HASH c19c33252846a8a0..., 1232
raw events; all 1183 cached historical trades an exact subset; control
replay byte-identical to cached M3_E023: 145/145 trades on 2010)
EVENTS_PER_WEEK=2.961 | ORIGINAL_EXIT=SL20 / TP30 / T240 (audit: time exit =
first tick strictly after entry_ts+240min; verified byte-exact) |
NEW_EXIT=SL20 kept + TP=frozen previous-day midpoint (PDH+PDL)/2 + T240
kept, no trail

COMMON_SAMPLE_ORIGINAL (event-level, N=1230):
  N=1230  MEAN_PIPS=+0.420  PF=1.043  EXPECTANCY_R=+0.021  STRESS=-1.128p
  (PF 0.893)
COMMON_SAMPLE_NEW (event-level, same events):
  N=1230  MEAN_PIPS=-0.228  PF=0.975  EXPECTANCY_R=-0.011  STRESS=-1.560p
  (PF 0.842)
DEPLOYABLE_NEW: N=1230  TRADES_PER_WEEK=2.956  MEAN_PIPS=-0.228  PF=0.975
EXPECTANCY_R=-0.011 | common-deployable (n=1183): control +0.388 PF 1.04
== historical ledger | new -0.249 PF 0.973
EXIT_DIAGNOSTICS=STOP 40.6% / TARGET(midpoint) 35.7% / TIME 23.7%; median
winner 13.9p vs control 30.0p — the phenomenon target is CLOSER than TP30
and caps winners below cost coverage; every block negative-to-flat
VERDICT=NOT_REHABILITATED. The mechanism-matched midpoint target is WORSE
than the "arbitrary" TP30 (mean -0.23 vs +0.42; stress -1.56 vs -1.13).
The original generic exit was already near the mechanism's ceiling; the
mechanism itself nets ~+0.4p after costs. Gate FAIL on all economics.
STOP.

## BEST_SIGNAL=NONE

No signal cleared the §17 usefulness gate, so per §19 no survival run is
applicable and per §20 no freeze spec is created.

SURVIVAL_500EUR: not applicable (no gate passer)
2019_PLUS_ACCESSED=NO
ENTRY_RULES_CHANGED=NO
EXIT_OPTIMIZATION=NO (one pre-registered architecture per signal; control
rerun once; zero parameter sweeps)

FINAL_STATUS=NO_HISTORICAL_SIGNAL_REHABILITATED
STOP.

## ANSWER TO THE MISSION QUESTION

The old rejections were NOT exit-architecture artifacts:
- F08: rejected for one-side regime beta — confirmed again under a
  trend-matched trailing exit (short carries everything, long is zero).
- G10: the generic 24h exit WAS suboptimal (a trail exit doubles the mean),
  but the signal is frequency- and robustness-limited regardless of exit —
  EXIT_IMPROVED_BUT_NOT_USEFUL.
- F04b: the arbitrary TP30 was already better than the mechanism-derived
  midpoint target; the mechanism is too thin after realistic costs.

## ARTIFACTS

- EXIT_PREREGISTRATION.md (written before PnL)
- ENTRY_IDENTITY.md (+ identity_results.json)
- audit_lib.py (verbatim historical code + pre-registered new exits)
- run_identity.py / run_causality.py (66/66 PASS) / run_audit.py
- audit_A.json / audit_B.json / audit_C.json (full §15/§16 metric blocks)
