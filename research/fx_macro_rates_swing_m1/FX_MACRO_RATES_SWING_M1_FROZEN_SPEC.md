# FX_MACRO_RATES_SWING_M1 — FROZEN SPEC (commit BEFORE any holdout access)

Frozen candidate: **B — RATE/FX DIVERGENCE (multi-hour catch-up)**, config
`z>=2.5 / H4 / hold 48h / cap 0.0 / stop 2.5xATR` = experiment MR_E017.
Written and committed before first access to USDJPY or EURUSD 2018H2.

## 1. Data sources (exact)

| layer | source | file/range |
|---|---|---|
| rates | Databento GLBX.MDP3 ohlcv-1m, `ZN.v.0` continuous (volume-ranked prev-day rule, UNADJUSTED), RATES-DATA-M0 store | `E:/ResearchData/botTrading/rates/databento/parquet/ZN.parquet`, 2010-06-07..2018-12-31 UTC, `ts_event`-labelled 1m bars |
| roll map | RATES-DATA-M0 `roll_map.csv` (raw contract per date interval) | `research/fx_macro_rates_swing_m1/roll_map.csv` |
| FX | Dukascopy 5m BID OHLCV parquet (close-time-labelled causal bars, cross-validated vs LAB_PASS tick store) | `data_raw/parquet/{EURUSD,GBPUSD}_5m.parquet`, discovery access [2010-01-04, 2018-01-01) |
| EURUSD execution | validated BID/ASK tick store | `E:/ResearchData/botTrading/ticks/parquet/EURUSD/year=*`, 2010..2018 |

## 2. Timestamp semantics / causality proof

* Decision times = H4 bar CLOSE times (ns UTC), bars built from completed 5m
  BID candles with `bucket=(close_time-1)//tf` (m3lib idiom).
* Rates feature at T reads only ZN 1m bars with `close_time = ts_event+60s
  <= T`; the 30-day vol window is trailing (ends at that bar).
* FX features at T read only H4 bars closing <= T.
* Proofs (24 sampled decisions per pair, pooled 2010-2017):
  - FX T1/T2/T3 (swing_lib.causality_gate): PASS — feature bars close <= T;
    5m-truncated rebuild reproduces the side; +1% mutation of all 5m bars
    closing after T does not change the side.
  - Rates T1r/T2r/T3r (mrlib.rates_gate): PASS — max rates input close <= T;
    rates grids truncated at T reproduce the side; +10% mutation of all
    post-T rates z values cannot change the side.
* Macro events: NOT used by the frozen rule (event families G/H rejected at
  screen).

## 3. Feature formulas (exact)

* Back-adjustment: additive; at each roll boundary `shift += close_prev -
  close_new`; `adj = raw + shift` (roll-safe log-returns; max genuine roll
  gap 1.56 ZN points preserved as shift, never filled).
* `ret24(T)` = sum of 1m log-returns of `adj(ZN)` over bars with
  `T-24h < close_time <= T` (cumsum diff on the 1m grid).
* `z24(T)` = `ret24(T) / std30d(T)`, `std30d` = trailing 30-day (=43200
  grid bars) rolling std of the same 24h-return series on the ZN grid.
* `fx24(T)` = `ln(close_H4[T]/close_H4[T-6]) / (ATR_H4_14[T] * pip)` —
  24h FX move in ATR units (6 H4 bars).
* `pip` = 1e-4 (EURUSD, GBPUSD), 1e-2 (USDJPY, Stage A).

## 4. Rule (entry/exit/execution/costs)

* Universe: EURUSD + GBPUSD (discovery). USDJPY = Stage A holdout only.
* `usd_dir(T)` = `-1` if `z24 >= +2.5`; `+1` if `z24 <= -2.5`; else 0.
  Convention: ZN futures PRICE surge = yields-down impulse; empirically the
  USD-positive direction (flight-to-quality asymmetry; short side expR
  +0.192R vs long +0.096R). This mapping is frozen exactly as screened.
* Trade `side(T) = usd_dir(T)` iff `fx24(T) * usd_dir(T) <= cap (0.0)` —
  i.e. FX has NOT followed the rates-implied direction (flat or opposing).
* Entry: next 5m bar open after T (MODELED_EXECUTION: BID layer, long entry
  crosses full spread 0.6 pip EURUSD / 1.0 pip GBPUSD; short exit crosses
  it back). TICK_EXACT check: EURUSD 2010-2017 real BID/ASK, 5s latency
  (m3lib.mtf_replay, stop/target levels frozen from next-5m-open basis).
* Stop distance = target distance = 2.5 x ATR(H4,14) at T (1R = 2.5 ATR).
* Max hold 48h (time exit at 5m close granularity). One position at a time
  (overlapping decisions skipped).

## 5. Discovery results 2010-06-07..2017-12-31 (pooled, MODELED_EXECUTION)

N=177 | trades/mo 1.85 | mean +12.87 pips | median +8.90 | PF 1.465 |
expR +0.1388R | win 54.9% | long +0.096R short +0.192R | total +2277 pips |
remove_best_1pct +10.99R | max DD 6.99R | worst year -1.14R | worst rolling
12m -1.41R | exits 29 STOP / 55 TARGET / 93 TIME | stress +12.05 pips
(+0.5 pip/side; latency immaterial at H4 scale).

| pair | N | mean | PF | expR | pos years | remove-best |
|---|---|---|---|---|---|---|
| EURUSD | 93 | +9.63 | 1.372 | +0.131 | 5/8 | +8.01 |
| GBPUSD | 84 | +16.45 | 1.556 | +0.147 | 6/8 | +14.43 |

Yearly pips: 2010 -162.5 | 2011 +747.8 | 2012 -90.1 | 2013 +940.5 |
2014 +260.6 | 2015 +557.7 | 2016 -168.2 | 2017 +191.4 (5/8 positive).

TICK_EXACT EURUSD 2010-2017 (real BID/ASK, 5s latency): N=80, mean
+6.75 pips, PF 1.232, expR +0.0966R; stress (30s latency + 0.5 pip/side)
N=80, mean +5.90, PF 1.20, expR +0.0865R. TICK_EXACT < bar-model (fewer
fills, real spread) but decisively positive under stress.

Survival (500 EUR, 0.5%/trade, diagnostic): FINAL 564.62 | MAX_DD 3.45% |
worst year -0.58% | worst rolling 12m -0.73% | LOWEST_EQUITY 497.11 |
longest DD 405 days. No veto condition approached (limits: DD>=50%,
equity<=250, year<=-40%).

## 6. Plateau (§25 — all neighbors tested, no cliff)

| axis | cells (PF, mean pips) |
|---|---|
| thr | 1.5 (1.114, +3.4) -> 2.0 (1.172, +5.4) -> **2.5 (1.465, +12.9)** — monotone |
| hold | 24h (1.704, +14.3) / **48h (1.465, +12.9)** / 120h (1.083, +3.5 decays) |
| cap | -0.5 (1.551, +14.5) / **0.0 (1.465, +12.9)** |
| stop | 2.0xATR (1.392, +10.4) / **2.5xATR (1.465, +12.9)** / 3.0xATR@2.0 (1.119, +4.1) |
| pair split @2.5 | EURUSD PF 1.372 / GBPUSD PF 1.556 — both participate (concentration at 2.0 dissolves at 2.5) |

Selection was NOT the best cell: z2.5/h48/cap0/stop2.5 was fixed as the
candidate BEFORE its neighbors were run (E017 before E025-E027); every
neighbor clears PF>=1.15 and stress>0.

## 7. Dead territory confirmed (screened, rejected — see RESEARCH_LEDGER_MR.csv)

A impulse-underreaction (2 cfg, weak); C curve-regime (near-miss: steep
variant thr1.5 PF 1.546 but N=97, 2012-heavy, single-pair-weighted — NOT
frozen, next cell thr2.0 deliberately untested); D trend-pullback (2);
E vol-regime (1); G event follow/fade (2); H surprise 24h/120h (2, NEGATIVE);
I cross-maturity (2); K regime breakout (2). E021 ledger row is a flagged
duplicate of E004 (signal_fn ignored rates_sym; not ZF evidence).

Budget: 27 experiments / 9 families of 10. Seals: USDJPY and EURUSD 2018H2
first accessed ONLY in the validation stages that follow this commit;
2019+ never accessed.

Stage A pass condition (registered pre-access): USDJPY NOT clearly
negative = net mean pips > 0 AND PF > 1.0 AND expR > 0 (frozen rule, no
adaptation). Stage B success bar (§30): mean>0, PF>=1.10, expR>0,
remove-best>0, stress>=0.
