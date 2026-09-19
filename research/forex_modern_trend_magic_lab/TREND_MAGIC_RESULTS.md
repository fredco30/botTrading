# TREND MAGIC ENHANCED [AlgoAlpha] — LAB VERDICT

```
CAMPAIGN          = FOREX_MODERN_STRATEGY_LAB_M1
BRANCH            = research/forex-modern-trend-magic-lab-m1
IMPLEMENTATION_SHA= cd221b1 (frozen before any PnL inspection)
PINE_SOURCE_SHA256= 82de45d028e0c8793115ef07f4c7d6f3de7d4f844ea96bb58a10b4f4bc1c2e21
PERIOD            = 2020-01-01 .. 2025-12-31
2026_ACCESSED     = NO (hard seal in tmlab.load_5m; tested)
LIVE_TRADING      = NO
```

## VERDICT: DEAD — ARCHIVED (no candidate)

FAMILY = Trend Magic Enhanced state changes AND H1-state-filtered entries.
B1-B5 entry families NOT run: gated by Experiment B0 + control, which show the
state carries no conditional directional information (details below). Per
protocol sections 25/35 the family stops here.

## Evidence chain

### 1. Source fidelity (pre-PnL, tests/test_trend_magic.py — 30/30 PASS)
Exact Pine v5 source recovered (pine-facade, scriptAccess=open_no_auth).
Confirmed: VOL = SMA(TR,5) (not Wilder), CCI(20)-steered ratchet, direction
from Low/High crossing the line (not CCI sign), nz(0)-anchor quirks.
PYTHON == ORIGINAL by construction (hand-calculated bars, truncation
invariance, online==batch, warm-up semantics).

### 2. EXPERIMENT A — state-change event study (EVENT_STUDY_RESULTS.json)
9 series (3 pairs x M5/M15/H1) x 5 horizons = 45 cells, 2020-2025.

  - ZERO cells show significant positive drift.
  - 6 cells significant NEGATIVE (GBPUSD M5 +15m/+30m/+120m/+240m, M15 +30m/+60m;
    means -0.14..-0.67 pips, t up to -3.2): flips carry mildly contrarian
    information — the opposite of an entry signal.
  - MFE ~= |MAE| everywhere (no directional asymmetry).
  - By-year means flip sign; remove-best-1% makes every cell worse.
  - Isolated positive cell (USDJPY_H1 +8h, +2.0 pips, t=1.6) has no
    neighbouring support ( +4h t=0.9, +16h t=0.8 ), fails by-year stability
    (2023 negative) => noise.

### 3. EXPERIMENT B0 — H1-state conditional drift screen (STATE_DRIFT_RESULTS.json)
Per-bar drift in state direction (pips/bar):

```
            H1 bull   H1 bear   M15 bull  M15 bear     round-trip cost
EURUSD       +0.028    +0.009    -0.021    -0.026       ~0.6 + slip
GBPUSD       +0.038    +0.044    -0.030    -0.030       ~1.0 + slip
USDJPY       +0.218    +0.001    +0.064    +0.008       ~0.9 + slip
```

EURUSD/GBPUSD: drift ~ 30x smaller than cost at H1 holding horizons; negative
at M15. USDJPY bull looks alive per-bar (+0.22/bar, positive all 6 years).

### 4. CONTROL — is USDJPY bull drift Trend Magic information? (run_state_drift_control.py)
24h-holding drift, pips/day:

```
USDJPY  ALL  +2.84     (2020:-2.2 2021:+4.6 2022:+5.7 2023:+3.6 2024:+5.9 2025:-0.5)
USDJPY  bull +2.77     <- BELOW unconditional baseline
USDJPY  bear +2.99     <- ABOVE the bull state itself
```

The bear state out-drifts the bull state. The state filter adds NO marginal
information over "just be long USDJPY 2020-2025" (carry era baseline). The
per-bar bull drift is baseline regime drift, not indicator skill.
EURUSD/GBPUSD controls show the same null (in-state ~= baseline).

## Consequence

A continuation entry (B1-B5) can only sample time inside the state; its
expected gross drift per holding period is bounded by the conditional drift
minus baseline, which measures ~0 (EURUSD/GBPUSD, both signs) or negative
(USDJPY bear vs bull). With round-trip costs 0.9-1.5 pips there is no
mechanism for net expectancy > 0. Running B1-B5 would burn budget against a
measured null (protocol sections 25 + 35). Trend Magic Enhanced:
STATUS=ARCHIVED_DEAD_FAMILY.
