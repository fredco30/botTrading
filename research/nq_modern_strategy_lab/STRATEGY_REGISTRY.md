# STRATEGY_REGISTRY — NQ MODERN STRATEGY LAB (durable memory)

Campaign: real CME NQ ohlcv-1m 2020-2025 (Databento GLBX.MDP3, NQ.v.0).
2026 SEALED (external OOS, untouched). 2022-2025 = internal temporal blocks.
Cost model: LOW 0.75 / NORMAL 1.5 / STRESS 3.0 INDEX POINTS RT
(1 pt = $20; 1 tick = 0.25 pt = $5). UNIT AUDIT 2026-09-16: simulation always
ran in index points; earlier USD labels used $5/pt (tick value) by mistake and
were 4x understated — corrected below (SPENDING_GUARD + NQ_UNIT_AUDIT).
Gate: N>=40, NET>0 & STRESS>0, PF>=1.15, remove-best>0, >=4/6 positive years,
year concentration <=60%, fold sanity. Frozen candidates are NEVER retuned.

## FROZEN CANDIDATES (3)

### #1 NQ_OPR_MODERN_M1 — premarket breakout-retest continuation (canonical P000)
FROZEN_SPEC=candidates/NQ_OPR_MODERN_M1/NQ_OPR_MODERN_M1_FROZEN_SPEC.md
MECHANISM=premarket range break confirmed by 5m close, retest with momentum
  continuation; trim at new extreme + BE + EMA8 runner (video-canonical rules)
TRADES=420 | TPW=1.33 | NET=+2.99 pts (+$59.88) | PF=1.366 | EXP_R=+0.244
STRESS=+1.49 pts (+$29.88, PF 1.164) | REMOVE_BEST=+1.74 | MAXDD_USD_1NQ=-4845
BY_YEAR=2020 +1.02 / 2021 +4.10 / 2022 +1.01 / 2023 +2.05 / 2024 +3.72 / 2025 +5.98
  (6/6 positive — the only candidate positive every single year)
FOLDS=D +2.52 / V +1.56 / R +4.72 | boot95 [+0.72, +5.44] p=0.012
CORRELATION=daily vs H02 +0.27, vs O01 -0.13

### #2 H02_TREND_DAY_EARLY — opening efficiency trend-day detection
FROZEN_SPEC=candidates/H02_TREND_DAY_EARLY/FROZEN_SPEC.md
MECHANISM=first-30m directional efficiency >=0.6 with range expansion >=0.5
  ATR identifies trend sessions; ride with chandelier 1.0 ATR, no target
TRADES=226 | TPW=0.73 | NET=+15.07 pts (+$301.39) | PF=1.284 | EXP_R=+0.069
STRESS=+13.57 (+$271.39, PF 1.252) | REMOVE_BEST=+4.31 | MAXDD_USD_1NQ=-26505
BY_YEAR=2020 -17.74 / 2021 +12.12 / 2022 +40.57 / 2023 +15.04 / 2024 -4.76 /
  2025 +38.02 (4/6 positive)
FOLDS=D +0.36 / V +27.98 / R +15.40
CORRELATION=daily vs OPR +0.27, vs O01 +0.16

### #3 O01_ON_TRANSFER — overnight drift transfer (narrow premarket)
FROZEN_SPEC=candidates/O01_ON_TRANSFER/FROZEN_SPEC.md
MECHANISM=extreme overnight return (|z|>=1.0) with narrow premarket
  (<=0.5x ON range) persists into RTH; chandelier 1.0 ATR, no target
TRADES=133 | TPW=0.43 | NET=+14.31 pts (+$286.17) | PF=1.515 | EXP_R=+0.063
STRESS=+12.81 (+$256.17, PF 1.443) | REMOVE_BEST=+12.06 | MAXDD_USD_1NQ=-12250
BY_YEAR=2020 -13.07 / 2021 +28.96 / 2022 +43.32 / 2023 +9.91 / 2024 +23.00 /
  2025 +5.41 (5/6 positive)
FOLDS=D +6.87 / V +28.70 / R +13.79
CORRELATION=daily vs OPR -0.13, vs H02 +0.16

## SURVIVOR CORRELATIONS (diagnostic only, no portfolio built)
daily PnL corr: OPR-H02 +0.267 | OPR-O01 -0.125 | H02-O01 +0.161
weekly PnL corr: OPR-H02 +0.014 | OPR-O01 +0.000 | H02-O01 +0.159
trade-day overlap: H02&O01 22 days | H02&OPR 69 | O01&OPR 25
=> three economically distinct, low-correlation continuation mechanisms.

## NEXT (outside this campaign)
All three face the SAME untouched 2026 as final external validation.
HIGH_RES_VALIDATION_RECOMMENDED=YES for all three (BBO-1s replay on signal
days) — requires explicit human authorization; NOT purchased in this campaign.
MNQ deployment study is a separate mission.
