# RATES-EVENT-HIRES-M1 — SUMMARY REPORT

Generated: 2026-09-13. Branch: `research/rates-event-hires-m1` (parent `7c63937` rates-data-m0).

## Funnel

| Metric | Value |
|---|---|
| EVENTS_TOTAL | 205 (102 NFP, 103 CPI) |
| EXPECTED_CLOSED | 1 (Good Friday 2017-04-14 CPI) |
| DATA_GAPS | 4 |
| ROLL_INVALID | 0 |
| VALID_ZF | 200 |
| VALID_ZN | 200 |
| VALID_BOTH | 200 |

## Records (valid events)

| | ZF | ZN |
|---|---|---|
| total records | 1,844,091 | 2,920,078 |
| median / event | 6,208.5 | 9,762.0 |
| P05 / event | 1,697 | 2,291 |
| P95 / event | 29,387 | 47,182 |

TOTAL_RECORDS = 4,764,169.

## Micro-timing feasibility (% valid events with >=1 obs in [T0, T0+H])

| H | ZF | ZN |
|---|---|---|
| 1s | 79.0% | 89.5% |
| 2s | 98.5% | 98.5% |
| 5s | 99.5% | 100.0% |
| 10s | 99.5% | 100.0% |
| 30s | 99.5% | 100.0% |

Feasible at >=2s horizons. At T0+1s coverage is 79-89.5% (many events have no
print inside the first second — NFP/CPI releases often have a silent first
second). Any future design must not assume a 1s observation exists.

## Data gaps (excluded, no fabrication)

- 2014-10-03 NFP (ZF+ZN): entire Friday session absent from Databento
  GLBX.MDP3 (tbbo AND ohlcv-1m; continuous AND raw contracts ZFZ4=116721 /
  ZNZ4=354456; symbology resolves normally). CONFIRMED_DATA_GAP.
- 2015-01-09 NFP (ZN only): ZN nearly full-day gap (6 bars all day in M0
  ohlcv-1m); ZF valid.
- 2015-03-24 CPI (ZN only): ZN data halt 12:19:00 -> 22:00 UTC, 11 min before
  T0; window empty. ZF valid.
- 2015-05-22 CPI (ZN only): same 12:19 halt pattern. ZF valid.

## Good Friday 2017-04-14 (CPI)

EXPECTED_MARKET_CLOSED — CME Globex closed all session. Excluded.

## Container-semantics exception (documented, not a leak)

7 post-2017 windows (CPI-201804, CPI-201805, CPI-201806, NFP-201805, NFP-201807)
contain 1-7 records timestamped in the last part of the second preceding
window_start (12:24:59.xxx). Databento timeseries delivery is second-batch
aligned. Flagged `boundary_batch_records`; future research should filter
`ts_event >= window_start`.

## Timestamp fields present (TBBO)

`ts_recv`, `ts_event`, `ts_in_delta`, `sequence`, plus identity
(`rtype`, `publisher_id`, `instrument_id`), trade (`action`, `side`, `depth`,
`price`, `size`, `flags`) and top-of-book (`bid_px_00/ask_px_00/bid_sz_00/
ask_sz_00/bid_ct_00/ask_ct_00`).

Semantics (per Databento documentation, confirmed empirically):
- `ts_recv`: capture timestamp at Databento's gateway, UTC, int ns. Primary
  timestamp; present on all records.
- `ts_event`: exchange capture timestamp per Databento docs. **Pre-2017
  GLBX history: ts_event == ts_recv exactly and millisecond precision
  (sub-ms part zero in 100% of sampled rows); `ts_in_delta` == 0.** The
  exchange timestamp carries no independent information in this era.
- 2017+ (sampled 2018): `ts_event` differs from `ts_recv`, true nanosecond
  precision, `ts_in_delta` populated (gateway-in latency).
- Do not manufacture sub-millisecond precision for pre-2017 events; use
  `ts_recv` as the working timestamp there.

Exact full-row duplicates exist in the source (trade-summary style repeats,
same ms/px/size/book, sometimes same `sequence`): 1,182,566 of 4,764,169 rows
(~25%). They are genuine source records, reported per event
(`duplicate_exact_records`), not silently dropped.

## Cost

- Pre-flight estimate: 11.5743 USD (get_cost sum over all windows)
- Actual: 11.5743 USD (sum of per-window get_cost at download time)
- Out-of-pocket: 0.00 USD (paid from existing dashboard credit; no
  subscription, no payment method added). Cap 15.00 USD respected.

## Data location

`E:\ResearchData\botTrading\rates\databento_event_tbbo\`
`raw\` (403 .dbn.zst originals, untouched) + `parquet\` + `metadata\`
(validation_report.json) + `manifests\manifest.json` (no API key).

## Idempotency

`download_tbbo.py` keys manifest entries by `EVENT_ID:SYMBOL`; validated raw
files (sha256) are never re-downloaded; re-running the downloader is a no-op.
