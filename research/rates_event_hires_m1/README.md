# RATES-EVENT-HIRES-M1

TBBO event-window acquisition + validation for the validated macro event universe
(102 NFP + 103 CPI = 205 events, 2010-06-07 .. 2019-01-01).

Parent: `research/rates-data-m0` (commit `7c63937`). NOT a child of the failed
RATES-MACRO strategy code.

- Dataset: `GLBX.MDP3`, schema `tbbo`, `stype_in=continuous` (`ZF.v.0`, `ZN.v.0`)
- Window: `[T0 - 5m, T0 + 10m)` per event, per instrument
- Bulk data: `E:\ResearchData\botTrading\rates\databento_event_tbbo\`
  (`raw\` original `.dbn.zst`, `parquet\` convenience, `metadata\`, `manifests\`)
- Cost cap: 15.00 USD (pre-flight gate in `download_tbbo.py --plan`)
- Idempotency: per event/instrument manifest key `EVENT_ID:SYMBOL`; a validated
  raw file (sha256 recorded) is never re-downloaded. No API key in any manifest.

## 2014-10-03 diagnosis (NFP, T0=12:30:00Z)

Classification: **CONFIRMED_DATA_GAP** (upstream Databento gap covering the
entire Friday 2014-10-03 session).

Evidence (free metadata + local M0 data only):
- Local M0 ohlcv-1m parquet: 0 bars for ZF and ZN for the entire day 2014-10-03
  (2014-10-02 is fully populated; the M0 gap audit had mislabeled the gap
  `2014-10-02 21:00 -> 2014-10-05 22:00` as EXPECTED_MARKET_CLOSED — it was a
  normal NFP trading day).
- Databento symbology resolves normally on 2014-10-03:
  `ZF.v.0 -> 116721 (ZFZ4)`, `ZN.v.0 -> 354456 (ZNZ4)`.
- TBBO metadata for 2014-10-03 12:25-12:40Z: record_count = billable_size =
  cost = 0 for continuous symbols AND for raw contracts ZFZ4/ZNZ4 AND by
  instrument_id. Whole-day TBBO counts are 0 as well.
- Sanity: identical window on 2014-09-05 NFP returns 104,034 TBBO records.

Since raw-contract TBBO is also zero, the CONTINUOUS_METADATA_RESOLUTION_ISSUE
fallback does not apply. The event is excluded; nothing fabricated.

## Good Friday 2017-04-14 (CPI)

CME Globex closed all of Good Friday -> EXPECTED_MARKET_CLOSED, excluded
(`EXPECTED_CLOSED_DATES` in `tbbo_lib.py`).

## Files

- `tbbo_lib.py` — windows, classification, roll guard, validation (pure)
- `download_tbbo.py` — idempotent downloader + cost gate
- `validate_tbbo.py` — per-event validation, coverage funnel, micro-timing stats
- `test_tbbo_lib.py` — synthetic tests (no network)
