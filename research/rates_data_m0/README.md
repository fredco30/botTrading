# RATES-DATA-M0 — Databento ZT/ZF/ZN 1-minute acquisition

Data acquisition and validation only. No strategy, no PnL, no forex outcome analysis.

## What was done

- Dataset `GLBX.MDP3`, schema `ohlcv-1m`, symbols `ZT.v.0`, `ZF.v.0`, `ZN.v.0`
  (continuous, volume-ranked, previous-day-volume rule, unadjusted prices).
- Range 2010-06-06T00:00:00Z → 2019-01-01T00:00:00Z (exclusive).
- Databento batch job `GLBX-20260913-PJ387FJNFC` (DBN + Zstd, monthly split).
- Estimated cost 24.28 USD, actual charged 24.28 USD (under the 30 USD cap).
- Bulk data stored OUTSIDE git at `E:\ResearchData\botTrading\rates\databento\`
  (`raw/`, `parquet/`, `metadata/`, `manifests/`).

## Scripts

| script | purpose |
|---|---|
| `estimate_cost.py` | cost estimate + budget gate |
| `download.py` | poll batch job, cost gate, download once |
| `build_roll_map.py` | symbology resolve → `roll_map.csv` (continuous → raw contract per interval) |
| `run_validation.py` | parquet conversion + validation + roll audit + gap classification |
| `validation.py` | pure validation functions (tested) |
| `make_manifest.py` | provenance manifest with SHA-256 hashes (no secrets) |
| `tests/` | synthetic tests: OHLC validity, duplicates, ordering, roll transitions, roll-gap reporting, 2019 cutoff, alignment logic |

## Results (see `reports/validation_summary.json`)

| | ZT | ZF | ZN |
|---|---|---|---|
| records | 1,591,842 | 2,407,981 | 2,649,934 |
| range | 2010-06-07 → 2018-12-31 | same | same |
| raw contracts | 35 | 35 | 35 |
| rolls | 34 | 36 | 34 |
| duplicates / non-monotonic / OHLC-invalid / NaN | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |
| unexpected gaps (>10 min, active session) | 427 | 68 | 71 |
| EURUSD M1 alignment | 47.31% | 71.56% | 78.73% |

Total records 6,649,757 = exactly the job's billed record count.

## Notes on gap classification

1-minute bars only exist when trades occur. Gaps >10 min are classified in
`reports/{zt,zf,zn}_gaps.json` as:

- `EXPECTED_MARKET_CLOSED` — daily 16:00–17:00 CT maintenance, weekends, and
  holiday closures (incl. multi-day Christmas/New Year closures).
- `EXPECTED_NO_TRADES` — thin overnight session (22:00–12:00 UTC) where rates
  futures trade but rarely print, especially ZT.
- `UNEXPECTED_DATA_GAP` — anything else. Remaining counts are small thin-print
  lulls concentrated in ZT (the least liquid contract); none indicate corrupt
  or missing delivery. No repair, no back-adjustment applied.

Roll price gaps in `reports/roll_audit.csv` are genuine contract-switch
discontinuities (max |gap| ≈ 1.56 points in ZT), intentionally not adjusted.

`2019_PLUS_ACCESSED=NO`. `PROTECTED_OOS_ACCESSED=NO`.
