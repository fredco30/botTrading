# FX_MACRO_RATES_SWING_M1 — FINAL REPORT

Branch `research/fx-macro-rates-swing-m1` (cut from
`7e3bd46baea6dcd6ec4e5bf763e8d3c6eda1233b`, previous branch untouched,
unmerged). Frozen spec commit: `708cfab`.

```
FX_MACRO_RATES_SWING_M1

AUDIT:
DATA_SUFFICIENT=YES
DATA_CAUSALITY_PROVEN=YES
RATES_INSTRUMENTS=ZT(2Y), ZF(5Y), ZN(10Y) US Treasury futures 1m OHLCV (Databento GLBX.MDP3, validated RATES-DATA-M0 store, 2010-06-07..2018-12-31, roll_map, unadjusted continuous)
MACRO_DATA=NFP/CPI/FOMC event table 2010-2018 w/ exact release timestamps + ALFRED real-time vintages (rejected at screen; frozen rule uses no event data)
DISCOVERY_PERIOD=2010-06-07 .. 2017-12-31 (UTC)

EXPERIMENTS=27
FAMILIES=9 (A,B,C,D,E,G,H,I,K; 10th not opened — budget is a maximum)

CANDIDATE=B — RATE/FX DIVERGENCE (multi-hour catch-up), frozen config = MR_E017
MECHANISM=24h ZN futures impulse |z24|>=2.5 (vol-normalized, roll-safe) while
  EURUSD/GBPUSD has NOT followed (fx24 * usd_dir <= 0, ATR units) -> trade the
  rates-implied USD direction at the H4 close; stop=target=2.5xATR(H4,14);
  max hold 48h; one position at a time
TIMEFRAMES=H4 decisions (5m execution); rates features on 1m grid (24h horizon,
  30d trailing vol)

DISCOVERY (EURUSD+GBPUSD pooled, MODELED_EXECUTION):
N=177
MEAN_PIPS=+12.87
PF=1.465
EXPECTANCY_R=+0.1388
POSITIVE_YEARS=5/8 (negatives small: 2010 -162p, 2012 -90p, 2016 -168p)
REMOVE_BEST=+10.99R
STRESS=+12.05 pips (+0.5 pip/side; 30s latency immaterial at H4 scale)
MAX_DD_R=6.99

PAIR_BREAKDOWN=EURUSD N=93 +9.63p PF 1.372 expR +0.131R 5/8 pos-yr remove-best +8.01R |
               GBPUSD N=84 +16.45p PF 1.556 expR +0.147R 6/8 pos-yr remove-best +14.43R
TICK_EXACT (EURUSD 2010-2017, real BID/ASK, 5s latency): N=80 +6.75p PF 1.232
  expR +0.0966R | stress (30s + 0.5pip/side) +5.90p PF 1.20 — MODELED pairs
  (GBPUSD, USDJPY) use validated 5m bar layer + conservative spread model.

SURVIVAL_500EUR (0.5%/trade diagnostic, not optimized):
FINAL_CAPITAL=564.62 EUR
MAX_DD_PERCENT=3.45
WORST_YEAR_PERCENT=-0.58
WORST_ROLLING_12M_PERCENT=-0.73
LOWEST_EQUITY=497.11 EUR
LONGEST_DRAWDOWN=405 days

PLATEAU_RESULT=PASS — thr 1.5/2.0/2.5 monotone (PF 1.114/1.172/1.465); hold
  24h 1.704 / 48h 1.465 / 120h 1.083 (decays, expected for multi-hour effect);
  cap -0.5/0.0 1.551/1.465; stop 2.0/2.5xATR 1.392/1.465; both pairs
  participate at the frozen threshold. Candidate fixed BEFORE neighbors ran
  (E017 before E025-E027).

CAUSALITY=FX T1/T2/T3 PASS 24/24 traces per pair (5m truncation + future
  mutation); rates T1r/T2r/T3r PASS 24/24 per pair (timestamp trace +
  truncation + post-T mutation). Any-leakage rule satisfied pre-PnL.

FROZEN_SPEC_COMMIT=708cfab

USDJPY_REPLICATION (Stage A, first access AFTER freeze, frozen rule):
N=23
MEAN_PIPS=+24.82
PF=2.242
EXPECTANCY_R=+0.3334
STRESS=+24.08
(6/7 pos years, remove-best +16.69R, both directions +, max DD 1.8R, PASS)

EURUSD_2018H2_CONFIRMATION (Stage B, only after Stage A, frozen rule):
N=5 (12 signals, overlapping ones skipped by the one-position rule)
MEAN_PIPS=+25.47
PF=7.464
EXPECTANCY_R=+0.3881
STRESS=+24.67
(total +127.35 pips, remove-best +15.1R, months 3/3 positive -> PASS §30)

INDEPENDENT_AUDIT=PASS — separate scalar implementation (no shared feature/
  replay code) reproduced 93/93 EURUSD discovery trades exactly: side, entry
  timestamp, stop/target distances, exit reason, pips, R; rates input
  timestamps all <= decision timestamps; 0 content mismatches.

2019_PLUS_ACCESSED=NO
PROTECTED_OOS_ACCESSED=NO (sentinel-gated: USDJPY unlocked only at Stage A
  after freeze; EURUSD 2018H2 only at Stage B after Stage A PASS)

TOP_NEAR_MISS=C curve-regime steepener (D1, 5d hold, thr1.5: N=97 +23.6p
  PF 1.546 expR +0.118 stress +22.7) — NOT frozen: N small, 2012-heavy,
  next plateau cell deliberately left untested (one-candidate rule).

FINAL_STATUS=CONFIRMED_MACRO_RATES_SWING_CANDIDATE

STOP.
```

## Verdict summary

The 2010-2017 sample supports a real, causal, economically meaningful
multi-hour mechanism: large 24h moves in 10Y Treasury futures that FX has
not yet reflected are followed by 10-25 pip FX moves in the rates-implied
direction within 48h, robust across two discovery pairs, replicating on the
sealed USDJPY holdout and on the sealed EURUSD 2018H2 window, surviving
tick-exact execution, stress costs, plateau and an independent recompute.
Event-minute / surprise-direction territory remains dead (families G/H
rejected), consistent with RATES-MACRO-M1; the edge here lives at the
multi-hour regime timescale the mission targeted.
