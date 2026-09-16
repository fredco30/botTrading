# FX_CURRENCY_NETWORK_M1 — FINAL REPORT

Autonomous multi-currency relative-strength / lead-lag discovery.
Branch: `research/fx-currency-network-m1` (from terminal commit of
FX_CROSS_ASSET_RELATIVE_VALUE_M1, `dbd636fb77d1b32a67a326303b693cd00895cfc0`,
verified present on origin before branching).

## FINAL STATUS: NO_USEFUL_CURRENCY_NETWORK_CANDIDATE

No candidate cleared the discovery gate (mission 16). The nearest miss,
CN_E035, passes every economic gate and fails only the hard frequency gate
(1.86 trades/week vs >= 2.0 required). Per mission 22 the near-miss was NOT
rescued and the campaign STOPPED. Validation (2015-2016) and replication
(2017-2018) folds were never evaluated (fold access must be earned by a
discovery pass). 2019+ was never accessed.

## 0 — CLOSE PREVIOUS TERRITORY

- Remote verification: `refs/heads/research/fx-macro-rates-swing-m1` =
  `dbd636f...` on origin. VERIFIED.
- Previous conclusion respected: no rates->FX research continued, no
  MR_E017 / A-cont / D-partial-adjustment rescue attempted, no ZN purchase.

## DATA AUDIT (mission 2)

Local, validated, zero-cost. No data purchased, no API called.

| Pair   | Store                          | Coverage local | Accessed    |
|--------|--------------------------------|----------------|-------------|
| EURUSD | Dukascopy BID 5m parquet       | 2010-01..2026-04 | 2010-2018 only |
| GBPUSD | same                           | same           | same        |
| USDJPY | same                           | same           | same        |
| EURJPY | same                           | same           | same        |
| GBPJPY | same                           | same           | same        |
| EURGBP | same                           | same           | same        |

- The 6 pairs form a COMPLETE K4 network over currencies EUR, GBP, USD, JPY
  (every currency in exactly 3 pairs).
- Crosses verified REAL quotes, not leg-derived (deviation from leg-implied
  ~1 pip at 5m), so lead-lag/residual families had genuine signal space.
- Execution: MODELED_EXECUTION (bid layer + per-side spread crossing,
  semantics identical to the engine audited 121/121 exact in
  fx_macro_rates_swing_m1). Pre-registered spreads (pips/round trip):
  EURUSD 0.6, GBPUSD 1.0, USDJPY 0.9, EURJPY 1.2, GBPJPY 2.0, EURGBP 0.8.
  Stress: +0.5 pip adverse per side. TICK_EXACT EURUSD BID/ASK ticks
  (2010-2018, E: store) reserved for a final survivor audit — never needed.

## CAUSALITY (mission 4)

`run_causality.py` on the H4 grid, 12 sampled decisions, ALL features used
by any family (strength z-scores, differentials, cross-vs-leg residual z,
network regression residual z, factor-idio z, spread z, dispersion
percentile):

- T1 MAX_INPUT <= DECISION: PASS (close-time-labelled bars; asserted).
- T2 TRUNCATION identity: PASS (features recomputed on data truncated at T
  are identical to 1e-10).
- T3 FUTURE MUTATION identity: PASS (mutating all post-T bars changes
  nothing).
- No full-sample normalization anywhere; all rolling windows trailing.

## FAMILIES AND EXPERIMENTS (missions 6, 12)

10 families registered, 45 experiments logged (CN_E001..CN_E045; 41
distinct — E010-E013 duplicate the aborted-run C-family rows of an earlier
crashed invocation; ledger kept intact, duplicates not counted).
Budget limit 60 never approached. Dead families killed after one screen.

| Family | Mechanism | Result (DISCOVERY) |
|--------|-----------|--------------------|
| CN-A strength continuation (H4, trend exit) | z(strength) extreme pair | FAIL: PF 0.90-0.98 at 1.7-5.2 tpw; longer lookbacks (72h/96h) flip negative |
| CN-B strength reversal (fade extreme, conv exit) | fade stretched pair | +17.4 pips PF 1.614 ONLY at thr 2.5 -> 0.34 tpw (useless frequency); thr 2.0 PF 0.65. Same sparse-tail decay the previous campaign found |
| CN-C major/cross lead-lag (cross-overshoot convergence + legs catch-up) | resid vs legs | FAIL: PF 0.82-0.94 at 20-23 tpw |
| CN-D network residual (5-factor rolling regression, cont + conv) | resid z | FAIL: PF 0.78-0.88 at 7-13 tpw |
| CN-E factor idio (strength-model idio, cont + conv) | idio z | FAIL: PF 0.88-0.97 |
| CN-F cross-sectional rank momentum (always extreme pair) | rank trend | FAIL: PF 0.92-0.995 at 6.7-12.4 tpw |
| CN-G corr-break reconvergence (EURUSD/GBPUSD spread -> EURGBP) | spread z | FAIL: PF 0.98-0.99 |
| CN-H session transfer (Asia -> London/NY) | session strength z | FAIL: PF 0.88-0.98 at 1.42 tpw |
| CN-I dispersion regime (expansion -> trend continuation) | disp percentile crossing | **BEST: E035 PF 1.210 +5.96 pips at 1.86 tpw — fails only frequency gate** |
| CN-J JPY-shock spillover (invented) | USDJPY shock -> JPY crosses | FAIL: PF 0.872 |

## TOP CANDIDATE (documented, NOT frozen): CN_E035

Mechanism: cross-sectional dispersion of 24h currency strengths suddenly
entering its top quintile (percentile >= 0.8, crossing trigger) marks the
onset of a trending network regime. Trade the single extreme
strongest-vs-weakest currency pair in the differential direction.
Exit architecture (pre-registered from the mechanism BEFORE PnL): TREND —
2xATR(H4,14) initial stop, 3xATR chandelier trail (5m-updated, effective
next bar), strength-differential sign-flip signal exit, 48h max hold.
Decision: H4 bar close, entry next 5m open. 1R = initial stop distance.

DISCOVERY 2010-2014:
- N=484, TRADES_PER_WEEK=1.86  **(GATE: >= 2.0 — FAIL)**
- MEAN_PIPS=+5.96  (PASS)
- PF=1.210  (PASS, >= 1.20)
- EXPECTANCY_R=+0.0889  (PASS, >= +0.05)
- REMOVE_BEST(1%)=+2.71  (PASS, > 0)
- STRESS(+0.5pip/side)=+5.03  (PASS, > 0)
- win_rate 0.475, max_dd 9.2R, pos_months 32/59, pos_years 4/5
- yearly pips: 2010 +262, 2011 +1426, 2012 -41, 2013 +307, 2014 +930

VALIDATION 2015-2016: NOT_ACCESSED (discovery gate failed).
REPLICATION 2017-2018: NOT_ACCESSED.

EXIT_DIAGNOSTICS (discovery):
- exits: TIME 277, SIGNAL_EXIT 82, STOP 74, TRAIL 51
- winners (n=230): avg +72.3, median +52.9, max +394.5 pips, dur 36.7h
- losers (n=254): avg -54.2, median -42.6, max -209.0 pips, dur 22.5h
- trailing lets trends run: 51 TRAIL exits captured multi-ATR moves
  (avg winner 72 pips vs 9.2R max-dd scale)

PLATEAU (coarse neighbors, all DISCOVERY):
- trigger percentile: 0.7 -> +1.27 pips PF 1.046 (2.43 tpw); 0.8 -> +5.96
  PF 1.210 (1.86 tpw); 0.9 -> -2.26 PF 0.930 (1.16 tpw). Edge peaks AT the
  pre-registered 0.8 and decays on both sides — not a fragile spike, but
  the 0.8 value was chosen before PnL and survived.
- strength lookback (at pct 0.8): 24h -> +2.37 PF 1.084; 48h -> +5.96 PF
  1.210. 72h+ untested in this family (A-family long lookbacks negative).
- max hold: 48h -> +5.96; 24h -> +2.37 (same trigger, n=24h lookback).
- state-based entry (any bar in regime vs onset-crossing): NEGATIVE
  (-2.53 pips, PF 0.926). Hysteresis re-arm: PF 0.999. The edge is
  specifically in regime ONSET, not regime persistence — re-entries inside
  the regime destroy it.

SURVIVAL 500EUR (discovery-only, 0.5% equity risk/trade, not optimized):
FINAL_CAPITAL=617.06, MAX_DD_PERCENT=4.55, LOWEST_EQUITY=500.00,
WORST_CALENDAR_YEAR=+1.66%, WORST_ROLLING_12M=-3.44%.

PAIR_BREAKDOWN (E035 discovery pips): EURUSD +1305.8, USDJPY +1136.6,
EURJPY +537.1, GBPJPY +180.2, GBPUSD +42.9, EURGBP -318.9. Edge
concentrated in the USD majors; EURGBP (widest relative spread vs move
size) is negative.

## WHY THE CAMPAIGN FAILED (honest mechanism reading)

Across 10 families and 41 distinct configurations the pattern of the
previous campaign replicated EXACTLY in the network information set:

1. Every continuous mechanism (residual, lead-lag, idio, corr-break,
   rank momentum, session transfer) has ZERO-to-negative net expectancy at
   useful frequency after 0.6-2.0 pip modeled costs.
2. Positive expectancy exists ONLY in selective tails — extreme strength
   reversal at thr 2.5 (+17 pips, 0.34 tpw), dispersion-expansion onset
   (+5.96 pips, 1.86 tpw) — and decays monotonically as triggers loosen
   toward the 2+/wk requirement.
3. Frequency is the binding constraint, exactly as in
   FX_CROSS_ASSET_RELATIVE_VALUE_M1. The currency network at M15-H4
   resolution does not overcome spread costs at high turnover.

## HANDOFF NOTES FOR A FUTURE MISSION

- CN_E035 is the natural starting point if the frequency gate is ever
  relaxed (1.5/wk) OR if a second disjoint pair is pre-registered as an
  allowed concurrent candidate (mission 15 widening) BEFORE any PnL is
  seen. Both avenues were deliberately left untested here (mission 22).
- Its edge lives in regime ONSET; do not convert to always-in variants.
- EURGBP leg is negative; a pair-selection rule excluding it is a candidate
  improvement to pre-register (not tested here).
- INFRASTRUCTURE WARNING: `research/autonomous_edge_discovery_m2/m2lib.py`
  line 23 does `sys.path.insert(0, M1DIR)` — any process that imports m2lib
  and THEN imports a module name that also exists in
  `autonomous_edge_discovery_m1` (e.g. `run_screens`) executes the LEGACY
  campaign's script at import time and mutates its ledger. Load local
  modules by explicit file path (importlib) — see run_screens_phase2.py.
  Two accidental foreign executions occurred; both times the foreign
  campaign's counter/ledger were restored to HEAD before any commit.

## COMPLIANCE

- 2019_PLUS_ACCESSED=NO (loader hard-guard at 2019-01-01).
- Validation/replication folds never evaluated (no qualified candidate).
- No data purchase, no billable API. Costs modeled conservatively and
  pre-registered; stress +0.5 pip/side.
- Exit architectures chosen per mechanism before PnL; one trailing method
  (3xATR chandelier) for trend families; convergence families exit on the
  phenomenon returning to neutral; no 3-exit bake-off.
- Experiment budget: 45/60 logged, 41 distinct. Families: 10/10.

FINAL_STATUS=NO_USEFUL_CURRENCY_NETWORK_CANDIDATE
