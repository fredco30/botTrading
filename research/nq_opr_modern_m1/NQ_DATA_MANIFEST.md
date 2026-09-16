# NQ_DATA_MANIFEST — NQ OPR MODERN M1 (mission sections 3-10)

SOURCE=Databento Historical (batch), dataset GLBX.MDP3
SYMBOL=NQ.v.0 (stype_in=continuous, volume-based lead contract, NOT back-adjusted)
SCHEMA=ohlcv-1m
PERIOD=2020-01-01T00:00Z -> 2026-01-01T00:00Z exclusive
2026_ACCESSED=NO (never requested; hard end-date guard in download.py)
DATA_COST_USD=7.73 actual (6 yearly jobs: 1.2766 + 1.2902 + 1.2928 + 1.2900 + 1.2959 + 1.2869)
DATA_ROWS=2,117,998 rows 1m (349672+353393+354112+353358+354954+352509)
DATA_SIZE=~40 MB dbn.zst raw (1,567 daily files, per-file SHA256 in manifests)
STORAGE=E:\ResearchData\botTrading\nq\databento\{raw,parquet,manifest}\ — OUTSIDE git
JOB_IDS=GLBX-20260916-YCRF9W9FWK(2020), R5N8YXT47R(2021), + batch_job_<year>.json

## Integrity by year (full JSON: manifest/integrity_by_year.json)

YEAR | ROWS_1M  | FIRST_TS(UTC)      | LAST_TS(UTC)       | RTH_DAYS | DUP | NONMONO | BAD_PX | OFFGRID | MISSING_MIN
2020 | 349,672  | 2020-01-01 23:00   | 2020-12-31 21:59   | 259      | 0   | 0       | 0      | 0       | 1465
2021 | 353,393  | 2021-01-03 23:00   | 2021-12-31 21:59   | 258      | 0   | 0       | 0      | 0       | 1245
2022 | 354,112  | 2022-01-02 23:00   | 2022-12-30 21:59   | 258      | 0   | 0       | 0      | 0       | 1425
2023 | 353,358  | 2023-01-02 23:00   | 2023-12-29 21:59   | 257      | 0   | 0       | 0      | 0       | 1590
2024 | 354,954  | 2024-01-01 23:00   | 2024-12-31 21:59   | 259      | 0   | 0       | 0      | 0       | 1755
2025 | 352,509  | 2025-01-01 23:00   | 2025-12-31 21:59   | 257      | 0   | 0       | 0      | 0       | 1755

MISSING_SESSION_MINUTES are dominated by early-close holiday sessions
(210/225-minute days, flagged individually in the manifest); full RTH days
have 389-390 minutes with ~zero missing minutes.
SHORT_RTH_DAYS includes 4 circuit-breaker sessions in March 2020
(2020-03-09/12/16/18, 376-377 minutes) — treated mechanically (shorter
sessions), never patched.

## Rolls / continuous contract integrity

ROLLS=25 intervals over 2020-2025 (quarterly H/M/U/Z) — manifest/roll_map.csv
ROLL_AUDIT=manifest/roll_audit.csv: per ET trading day, which actual contract
supplied the RTH bars (from instrument_id in the data itself).
SESSION_STRADDLE_DAYS=0 — no RTH session ever mixes two contracts, therefore
the day-local OPR strategy is unaffected by roll gaps. No back-adjustment
applied or needed (documented in OPR_CANONICAL_SPEC.md).

## 5m bars (mission section 10)

5M_ROWS=423,892 (parquet/nq_5m_2020_2025.parquet)
BUCKET LABEL=5-minute bucket START (UTC ns) — frozen p000 convention.
AGGREGATION=open=first, high=max, low=min, close=last, volume=sum (no
forward-fill, no fabrication); n_min = contributing 1m bars, n_instr =
distinct contracts per bucket.
CAUSALITY TESTS=test_causality.py — 9/9 PASS (levels exclusive of session
window; shifted running extremes; no same-bar confirm+entry; close-based
level stop ignores wicks; gap-aware BE; EMA8 runner exit; EOD flatten;
forward returns strictly post-entry; split guard).

DATA_INTEGRITY=PASS — strategy work may proceed.
