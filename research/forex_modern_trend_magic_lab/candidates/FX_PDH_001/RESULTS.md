# FX_PDH_001 — RESULTS (frozen candidate)

```
STRATEGY_ID   = FX_PDH_001
MECHANISM     = prior-day-high upside continuation, USDJPY
TIMEFRAME     = H1 signals + H1 bar replay (5m BID resample, causal)
SESSION       = none
PERIOD        = 2020-2025, 2026_ACCESSED=NO
BRANCH        = research/forex-modern-trend-magic-lab-m1
FROZEN_AT     = commit of candidates/FX_PDH_001/ (see git log)
STATUS        = FROZEN_CANDIDATE
```

## Trades and economics (NORMAL costs: 0.9 pip spread, no extra slippage)

```
TRADES              = 615  (1.96/week)
NET_PIPS_PER_TRADE  = +5.22
EXPECTANCY_R        = +0.30R (median stop 17.2 pips)
PF                  = 1.37
WIN_RATE            = 0.293 (trend shape: few big winners, many small stop-outs)
T_STAT              = +2.47
REMOVE_BEST_1%      = +2.79 net pips/trade (still positive)
STRESS (0.9+0.5x2)  = +3.59 net pips/trade, PF 1.24, t=+1.72 — POSITIVE
MAX DD (equity sim) = 14.3% at 0.5% risk / 26.3% at 1.0% risk
```

## EUR 500 compatibility (sections 18/19/20)

```
MIN_LOT=0.01, LOT_STEP=0.01
median stop            = 17.2 pips (p10 8.8, p90 31.2)
pip value at 0.01 lot  = ~EUR 0.079
RISK at min lot        = EUR 1.40 = 0.28% of capital (p90 0.48%) -> SAFE,
                         min lot UNDER-shoots the 0.5% target (no
                         excessive-risk trap, section 20 satisfied)
lot for 0.5% risk      = 0.018 -> rounded 0.01 (actual risk 0.28%)
lot for 1.0% risk      = 0.036 -> rounded 0.03 (actual risk ~0.84%)
margin at 0.03 lots    = ~$3,000 notional: ~EUR 128 at 1:20, ~EUR 85 at 1:30
                         (SCENARIO - NOT BROKER VERIFIED)
REALISTIC_WITH_500_EUR = YES
```

## Equity simulation from EUR 500 (rounded real lots, compounding risk)

```
0.5% risk/trade: EUR 500 -> 913  | maxDD 14.3% | worst year +0.3% | veto=NO warn=NO
1.0% risk/trade: EUR 500 -> 1470 | maxDD 26.3% | worst year +3.9% | veto=NO warn=NO
max losing streak 28 (win rate 0.293)
```

## Year-by-year (net pips/trade, NORMAL)

```
2020 +0.4   2021 +4.3   2022 +18.8   2023 +5.3   2024 +1.1   2025 +1.7
DISCOVERY_2020_2021 = +4.3 net/trade blended (2020 flat, 2021 strong)
VALIDATION_2022_2023 = +12.1 blended (best regime)
REPLICATION_2024_2025 = +1.4 blended (DECAY — see warnings)
No losing year at NORMAL costs; stress-cost years 2020/2024/2025 ~flat-negative.
```

## Warnings (honest limitations)

1. SINGLE-PAIR, SINGLE-SIDE: mechanism only measured alive on USDJPY longs.
   The asymmetry (PDL shorts dead) is economically coherent (carry + upside
   liquidity runs incl. 2022/2024 MoF/BoJ intervention days among top events)
   but makes the candidate a regime-aware long-USDJPY continuation, not a
   universal breakout law.
2. YEAR CONCENTRATION: 2022 contributes ~60% of total net pips at the frozen
   default exit (1.0 ATR stop / 3.0 ATR trail / 48h hold).
3. EXIT SENSITIVITY (plateau pass, pre-registered): performance rises
   monotonically with wider stops (best neighbour 1.5/4.5: +8.28 net,
   PF 1.42, all years positive, stress +6.74). The DEFAULT remains primary
   per protocol 24 (no best-cell selection). The gradient direction is
   mechanistically consistent with the MAE structure (median MAE -33 pips).
4. 2025 decay: +1.7 net/trade gross-of-nothing special: barely > costs.
   2026 sealed test remains the real confirmation gate.
5. Win rate 0.293 -> long losing streaks are normal (max 28); sizing must
   assume them (risk does not create edge, section 33).

## Provenance

- Screen -> deep pass -> frozen spec -> backtest -> plateau -> sizing:
  all artefacts in this directory; data = data_raw/parquet/USDJPY_5m.parquet
  (Dukascopy BID, 2010-2026, hard-sealed at 2025-12-31 23:59 UTC by tmlab).
- Causality: decision at event-bar close, entry at next bar open, stops are
  bid-side triggers, worst-case intrabar sequencing (stop before time exit).
