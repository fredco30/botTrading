# MR_E017 LONGITUDINAL OOS 2019-2025 — PHASE A DATA AUDIT

Head verified: `9ac9c776fbaeca8ef459e792aafd0b1461d40c5a` (local = remote).
Frozen spec `708cfab`, audit PASS artifacts verified on branch.
No 2019-2025 strategy results were computed. No purchases, no billable API
calls, no keys used.

## Local availability

| dataset | required | local | verdict |
|---|---|---|---|
| ZN 1m (Databento GLBX.MDP3, ohlcv-1m, continuous vol-ranked, unadjusted) | 2019-01-01..2025-12-31 (+2018 warmup) | E:\ResearchData\botTrading\rates\databento: **2010-06-07 .. 2018-12-31 21:59 UTC only** | **MISSING 2019-2025** |
| EURUSD 5m BID | 2019-01-01..2025-12-31 | 524,160 rows, full | OK |
| GBPUSD 5m BID | 2019-01-01..2025-12-31 | 525,888 rows, full | OK |
| USDJPY 5m BID | 2019-01-01..2025-12-31 | 523,584 rows, full | OK |
| warmup history pre-2019 | rates 30d vol (available: full 2010-2018 ZN), FX ATR/fx24 (available) | OK | OK |

Also checked: no other local ZN/10Y source covers 2019-2025 (raw dir ends
2010-06..2018-12 monthly dbn.zst; FRED DGS2 exists but is NOT the frozen
rates series and must not be substituted). 2026 FX rows exist locally but
2026 is FORBIDDEN and was not touched.

## Required acquisition (NOT executed — awaiting authorization)

```
ZN_LOCAL_END_DATE=2018-12-31 21:59:00 UTC
MISSING_PERIOD=2019-01-01T00:00:00Z .. 2025-12-31T23:59:59Z
REQUIRED_SCHEMA=ohlcv-1m
REQUIRED_DATASET=GLBX.MDP3
REQUIRED_SYMBOL_OR_CONTINUOUS_METHOD=ZN.v.0 continuous (volume-ranked,
  previous-day-volume rule, UNADJUSTED) — identical to RATES-DATA-M0 /
  frozen spec 708cfab; roll_map regenerated for 2019-2025 intervals via the
  same symbology-resolve method
ESTIMATED_DOWNLOAD_SIZE=~20-25 MB compressed (dbn+zstd, monthly split;
  scaled from 63 MB for 6.65M records in the 2010-2018 job at ~40% ZN share)
ESTIMATED_COST=~USD 8 (scaled from documented actual: GLBX-20260913-PJ387FJNFC
  charged 24.28 USD for 6,649,757 records ≈ 3.65 USD/M; ~2.2M records expected)
```

Compatibility pre-check: acquisition must replicate dataset, schema,
timestamp semantics (ts_event, UTC), bar labeling, and unadjusted
continuous construction of the frozen series; else INCOMPATIBLE_OOS_DATA.

FINAL_STATUS=DATA_ACQUISITION_REQUIRED — waiting for explicit human
authorization.
