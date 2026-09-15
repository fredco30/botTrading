# FX_MULTIPAIR_SWING_DISCOVERY_M1 — FINAL REPORT (terminal)

FINAL_STATUS = **NO_MULTIPAIR_SWING_CANDIDATE** → STOP (mission 29/31)

- Branch: `research/fx-multipair-swing-discovery-m1` (base `29dfb7b` =
  `research/multitimeframe-discovery-m1` terminal commit, verified on
  `origin/research/multitimeframe-discovery-m1`, preserved untouched).
- SW_EXPERIMENTS = **49** (ledger `SW_E001..E049`; budget 80 — never approached).
- SW_FAMILIES = **12/12** (G01..G12; family cap reached, no family #13).
- **USDJPY_ACCESSED = NO** (cross-pair holdout never loaded; no
  `STAGE_A_UNLOCKED` sentinel exists; `DATA_ACCESS_LOG.md` records only
  EURUSD + GBPUSD discovery windows).
- **EURUSD_2018H2_ACCESSED = NO** (temporal holdout never loaded; no
  `STAGE_B_UNLOCKED` sentinel exists).
- **2019_PLUS_ACCESSED = NO. PROTECTED_OOS_ACCESSED = NO** (hard-refused in
  `swing_lib.load_5m`; tested in `tests/test_swing_lib.py::test_window_guards`).

## Why this verdict

No strategy completed the discovery-phase requirements (missions 17–21) on
the EURUSD + GBPUSD 2010–2017 discovery set. Two novel mechanisms cleared
every *performance* bar (mission 17/18: PF ≥ 1.20, expR ≥ +0.05R, mean net
≥ +2 pips, remove-best > 0, stress-common > 0, both pairs positive) but
**both failed the parameter-plateau requirement** (mission 21: broad coarse
plateaus, no razor-thin winners). Per mission 29, no freeze was made,
USDJPY was never touched, and EURUSD 2018H2 stays sealed.

## Data layer (new in this campaign, validated)

- Source: Dukascopy **BID 1-min candles → 5m OHLCV parquet**
  (`data_raw/parquet/{EURUSD,GBPUSD}_5m.parquet`, built by
  `phenomena_discovery_v1/build_5m.py`), strict window 2010-01-04..2017-12-31 UTC.
- **Cross-validation**: 5m-parquet-derived H1 BID closes match the
  LAB_AUDIT_M0 LAB_PASS tick store (E:) **exactly (max diff 0.0 pips)** on
  EURUSD 2015-03-02 (all 24 hours).
- H1/H4/D1 bars built close-time-labelled from completed 5m bars
  (`bars_from_5m`, same bucket idiom as the audited `m3lib.bars_from_m1`).
  EURUSD: 49,944 H1 / 12,486 H4 / 2,081 D1; GBPUSD: 49,920 / 12,480 / 2,080.
- Execution: 5m-bar replay with per-side spread model (long entry crosses
  ask side; short exit crosses it back). EURUSD spread measured from
  validated ticks: median 1.0 pip (2010) → 0.3 pips (2013-17); model 0.6
  pooled (conservative). GBPUSD 1.0 / USDJPY 0.9 modeled (no local ticks).
  Stress = +0.5 pip/side. Fills mirror m3lib semantics (stop priority,
  gap-through via bar open, capped targets, time exit at 5m close).
- Tests: `tests/test_swing_lib.py` — synthetic aggregation/fill/non-overlap
  tests, window-guard tests, real-data coverage tests. **ALL PASS.**
- Causality gate T1/T2/T3 ported to 5m-based multi-TF bars (fire indices
  pooled across years for D1-scale signal rates; ≥20 traces/pair).
  **G08 and G11: PASS on all 4 pair-gates (24/24 traces each).**

## What was tested (49 experiments; gross screens pooled EURUSD+GBPUSD gross BID, then net 5m replay)

| Family | Mechanism (signal TF) | Verdict |
|---|---|---|
| G01 | Donchian multi-day breakout N=10/20/40 (D1) | REJECT — gross ≤ 0 at all horizons (confirms prior F2 on independent data) |
| G02 | Time-series momentum k=10/20/60 (D1) | REJECT — gross ≈ 0, all t < 1 |
| G03 | H4 trend + H1 pullback re-cross (H1) | REJECT — net negative (h=8 t = −3.0) |
| G04 | Conditional MR at N-day z-extremes (D1) | REJECT — gross ≈ 0 / negative |
| G05 | PDH/PDL acceptance break (H1) | REJECT — +0.66p gross @h=8, N=2509: far below costs |
| G06 | Compression → expansion break (D1) | REJECT — one pair carries (GBPUSD −21.5p net), PF 1.03 |
| G07 | Unusual H4 displacement continuation | REJECT — +0.96p net pooled, GBPUSD negative |
| G08 | **Path efficiency at fresh 20d extremes (D1)** | **NEAR MISS — REJECT on plateau** (below) |
| G09 | Cross-pair common-USD regime (D1, EURUSD+GBPUSD sync) | REJECT — negative short-horizon, +13-18p only @10d ≈ weak TSMOM |
| G10 | D1 trend × H4 Donchian state machine | REJECT — gross ≈ 0 |
| G11 | **Vol-regime transition, ATR14 252d-percentile cross (D1)** | **NEAR MISS — REJECT on plateau** (below) |
| G12 | Monday-range → week-direction break (H1) | REJECT — +2.1p gross @8h, below swing-scale economics |

## TOP_NEAR_MISSES

### 1. G11 — volatility-regime transition continuation (D1)

Rule: D1 ATR14 rolling-252d percentile **crosses above 0.80** → follow the
SMA20 direction (long above / short below); entry next 5m bar; stop
2.5×ATR14; no target; time exit 5 days; one position per pair.

Discovery 2010-2017 net (5m replay, spread model):

- Pooled: N = 56, mean **+22.66p**, median +33.5p, **PF 1.452**,
  **expR +0.106R**, win 58.9%, remove-best **+16.6p**, stress-common **+15.6p**
- Per-pair: EURUSD N=27 +33.1p PF 1.792 | GBPUSD N=29 +13.0p PF 1.224 (both positive ✓)
- Years: 3/6 positive (no 2010 trades — 252d lookback), maxDD 3.27R
- Survival (500 EUR, 0.5%/trade): final 515.00, maxDD 1.62%, lowest 496.64

**Why rejected**: plateau failure. Stop axis is a genuine plateau
(stop 2.0/2.5/3.0 → +26.6/+22.7/+26.9p), but the **threshold axis is a
spike**: hi=0.90 → **−31.0p, PF 0.618, negative on BOTH pairs** (a real
vol-regime mechanism must degrade gracefully, not flip sign), and the
**hold axis collapses**: 10d hold → +2.6p, PF 1.035. Also side-skewed
(L −0.005R / S +0.168R) and 3/6 positive years. A razor-thin winner
(mission 21) — parameter rescue (e.g. hunting hi=0.75) explicitly forbidden.

### 2. G08 — path-efficiency continuation at fresh extremes (D1)

Rule: 20-day path efficiency |c−c₋₂₀|/Σ|Δc| ≥ 0.45 AND D1 close breaks the
prior 20-day high/low → follow; stop 2.5×ATR14; time exit 5 days.

- Pooled: N = 106, mean **+17.07p**, **PF 1.344**, **expR +0.096R**, win 55.7%,
  **6/8 positive years**, remove-best +9.5p, stress-common +18.3p
- Per-pair: EURUSD +14.7p PF 1.342 | GBPUSD +19.9p PF 1.346 (balanced ✓)
- Survival: final 525.86, maxDD 2.07%, worst year −1.75%

**Why rejected**: plateau failure. k axis: k=10 → +2.8p (PF 1.05),
k=30 → **−5.0p** (PF 0.90). Threshold axis: eff 0.50 → **−9.4p** (PF 0.87)
while eff 0.40 → +10.8p — non-monotone spike at 0.45. Hold axis: 72h →
+1.0p (PF 1.02). The frozen point was the only strongly positive cell.

## Honest-campaign notes

- Budget integrity: 49/80 experiments; two families (G08, G11) reached
  their 8-config caps; the G08 hold=168h plateau cell was **blocked by the
  family cap** and never run (logged here instead).
- The gate-year adaptation (pooling 2011-2017 for G11; 2010-2012 for G08)
  exists because D1-scale strategies cannot yield 20 firing bars inside
  one calendar year; every individual T1/T2/T3 trace passed everywhere —
  no causality failure was ever observed on any sampled decision.
- EURUSD tick-exact replay (m3lib.mtf_replay) was prepared but not run:
  mission 14 applies to frozen serious candidates; no candidate froze.
- Independent confirmation of prior campaigns: classical swing families
  (trend/breakout/MR/pullback) are gross-flat on 2010-2017 majors at
  swing horizons — consistent with `autonomous_h1_h4_2026_09` (F1-F8 on
  MT4 data, different windows/costs) and `mtf_discovery_m1` (M15/H4
  EURUSD). The failure to find a plateau-robust multi-pair swing edge is
  not for lack of mechanisms tried: 12 families spanning classical + novel
  (cross-pair USD regime, path efficiency, vol-regime transitions,
  displacement, weekday structure).

STOP.
