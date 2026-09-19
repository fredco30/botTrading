# FX_PDH_001 — INDEPENDENT STRICT AUDIT + CAUSAL FREEZE RECORD

```
AUDIT DATE     = 2026-09-19 (UTC)
BRANCH         = research/forex-modern-trend-magic-lab-m1
BASE           = 01bb65ec75fae58a02c57b7b30653f076910c05d (campaign final, untouched)
FREEZE         = 5a758824442ff0eec9731af4f091a30db7e4acc5 (original candidate, untouched)
SCOPE          = read-only audit of candidates/FX_PDH_001; independent re-derivation
                 from data_raw/parquet; STRICT V1 causal correction + re-freeze
2026_ACCESSED  = NO
MODE           = reproduction, NOT research. No parameters changed.
```

## 1. Defects found in the original frozen replay

| id | defect | consequence | fix in STRICT V1 |
|----|--------|-------------|------------------|
| D1 | entry H1 bar never exit-checked (96%-stop architecture started checks one bar after fill) | 20.2% of trades had their initial stop touchable on the entry bar; those stops were never simulated | entry-bar stop check active (test: `test_entry_bar_stopout`) |
| D2 | trailing level used the CURRENT bar's ATR14 — a bar's own range set its own stop (intra-bar lookahead) | stop levels marginally contaminated by future-within-bar info | trail for bar i uses ATR14(bar i-1) (test: `test_trail_uses_prior_bar_atr`) |
| D3 | net_pips formula charged the spread TWICE (spread inside the entry price AND subtracted again in the net adjustment): NORMAL cost 1.8 pips, STRESS 3.8 | ALL pre-strict reported numbers (original +4.87/+3.59 style figures AND the first audit pass +4.00/+2.42) were computed on the over-charged cost model | one-spread round trip (buy at ask, sell at bid) + per-side slip: 0.9 NORMAL / 1.9 STRESS (test: `test_cost_model`) |

## 2. Reproduction (STRICT V1, frozen parameters, 2020-2025)

Committed machine-readable result: `FX_PDH_001_STRICT_RESULTS.json`.
Reproduction tests: `test_replay_strict.py` — 17/17 PASS, including
trade-exact regeneration of the committed JSON from raw parquet.

```
N                      = 639          TRADES_PER_WEEK = 2.04
PF                     = 1.379        WIN_RATE = 0.283
NET_PIPS_PER_TRADE     = +4.90        EXPECTANCY_R = +0.37
T_STAT                 = +2.52
REMOVE_BEST_1_PERCENT  = +2.54
STRESS_PIPS_PER_TRADE  = +3.82        (STRESS PF 1.29, rb1 +1.48)
EXITS                  = 619 stop / 20 time
LAST EXIT              = 2025-12-26 01:00 UTC       no_2026 = true

BY_YEAR (net pips/trade, NORMAL):
2020 = -0.17    2021 = +5.01    2022 = +18.78
2023 = +5.75    2024 = -1.14    2025 = +1.78

2022_PROFIT_SHARE = 61.2% of total net pips (16% of trades)

EUR500_0_5_PERCENT:
ENDING_EQUITY  = EUR 943
MAX_DD_PERCENT = 15.0%  (max EUR 108)
```

Gate status under STRICT V1: NET>0 PASS, PF>=1.15 PASS, EXPECTANCY_R>0 PASS,
STRESS>0 PASS, REMOVE_BEST_1%>0 PASS, t>=2 PASS, EUR-500 sizing PASS
(min-lot risk 0.28% median, margin ~EUR 85-128 at 1:20-1:30, scenario).
Year-robustness WARNING stands: 2020 and 2024 marginally negative
(-0.17 / -1.14 net per trade, i.e. cost-level noise, not edge), 2022 carries
61% of profits, 2025 +1.78 thin. These warnings move forward with the freeze.

## 3. Comparison to previously reported versions

```
                         original frozen     first strict audit      STRICT V1 (canonical)
cost model               spread x2 (D3)      spread x2 (D3)          spread x1 (correct)
entry-bar stop           skipped (D1)        checked                 checked
trail ATR                current bar (D2)    prior bar               prior bar
N                        615                 639                     639
NET pips/trade           +5.22               +4.00                   +4.90
STRESS                   +3.59               +2.42                   +3.82
PF                       1.37                1.295                   1.379
t                        2.47                2.06                    2.52
rb1                      +2.79               +1.64                   +2.54
losing years (NORMAL)    none                2020,2024               2020,2024
2022 share               58%                 71%                     61%
```

The pre-strict numbers are retained as historical records (commits 5a75882,
01bb65e are never rewritten). STRICT V1 supersedes them as the ONLY
2026-eligible version.

## 4. Integrity verification performed

- V0-faithful replay reproduced the frozen CSV trade-for-trade
  (615/615, identical entry/exit bars and net pips) BEFORE corrections,
  proving no double counting / no overlap / no event-entry shift in the
  frozen artifact; entries always = signal bar + 1 at open + spread.
- Independent signal re-derivation: 798 first-break events, matched.
- H1 bars are causal left-labelled resamples of completed 5m bars; PDH uses
  the prior COMPLETED UTC day only; ATR14(signal) known strictly before the
  entry bar opens (documented in FROZEN_SPEC_STRICT_V1.md rule 3).
- USDJPY pip = 0.01 JPY; 0.01 lot = 1,000 USD notional; EUR conversion via
  EURUSD close at entry time; lot floor-rounding to 0.01 with 0.01 minimum.
- 2026 hard seal asserted on every load; last exit 2025-12-26 01:00 UTC.

## 5. Trend Magic — permanent closure

Interaction test (A/B on FX_PDH_001 base, identical strict engine): the H1
bullish-state filter changed expectancy by +0.07 pips/trade on a 12% trade
reduction; PF +0.01; remove-best-1% worse; equity identical. No material
incremental value, consistent with the baseline-control null.

```
TREND_MAGIC_FINAL_STATUS = DEAD_AND_CLOSED   (no further experiments)
```

## 6. Provenance

- Engine: `audit/replay_strict.py` — tests: `audit/test_replay_strict.py`
  (17/17 PASS) — results: `audit/FX_PDH_001_STRICT_RESULTS.json`
- Spec: `candidates/FX_PDH_001/FROZEN_SPEC_STRICT_V1.md`
- Research/paper only. No live trading. 2026 sealed until the protected test.
