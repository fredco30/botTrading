# TICK_M0 — DUKASCOPY TICK DATA FEASIBILITY REPORT

Data-infrastructure mission only. No strategy research was performed or permitted.

## Verdict: TICK_M0_PASS

## Source & download method

- SOURCE: Dukascopy public datafeed (no key, no third party):
  `https://datafeed.dukascopy.com/datafeed/EURUSD/{Y}/{MM-1}/{DD}/{HH}h_ticks.bi5`
  (month is 0-indexed on the wire, same convention as the existing M1 pipeline).
- DOWNLOAD_METHOD: direct HTTP GET of hourly LZMA .bi5 files, sequential,
  retry/backoff on 429/503/5xx, 404 = no-data distinct from real errors,
  idempotent (existing files skipped), raw stored under `data_raw/tick_m0/`
  (gitignored). Script: `dukascopy_tick_probe.py`.
- Edge case found and handled: hours with no ticks return a **200 with an
  empty body** (not 404) — e.g. Friday 2018-06-08 21:00–23:00 UTC after the FX
  weekly close. Stored as empty-file markers. Also observed transient 503 HTML
  bodies served in place of .bi5; retried until clean data.

## Format validation (experimental, not assumed)

The 20-byte big-endian hypothesis was validated on real data:
`u32 ms-from-hour-start | u32 ask | u32 bid | f32 ask_volume | f32 bid_volume`,
prices scaled by point = 1e5 for EURUSD. Evidence:

- every decompressed hour file length divisible exactly by 20;
- 1e5 scaling yields EURUSD prices 1.166–1.185 during June 2018 (correct era);
- ASK >= BID on 100% of 474,506 ticks; timestamps monotone and inside hour
  bounds; tick files are hourly (ms offset resets each hour), not daily.

Note: tick timestamps are **ms from the hour start**, unlike candle files.

## Sample

SAMPLE_DATES = 2018-06-04 … 2018-06-08 (Mon–Fri), EURUSD only, 120 hourly
files. No 2019+ data, no protected OOS touched.

## Spread & activity (data validation only, not trading criteria)

| metric | value |
|---|---|
| N_TICKS | 474,506 |
| MEDIAN_SPREAD_PIPS | 0.30 |
| P05 / P95 / P99 | 0.10 / 0.50 / 1.00 |
| MAX_SPREAD_PIPS | 5.60 |
| MEDIAN_TICKS_PER_MINUTE | 64 |
| P95_TICKS_PER_MINUTE | 134 |

Activity structure is plausible FX: quiet Asian hours (~2–3k ticks/h),
London/NY overlap peak (h06–h16 UTC, 5–7k ticks/h), spread widening at the
daily 21:00 UTC rollover (median 0.9 pips vs 0.3 intraday).

## Volumes (as provided by Dukascopy — NOT global FX volume)

ASK_VOLUME >= 0 and BID_VOLUME >= 0 everywhere; 0% zero volumes; median
bid/ask volume ≈ 1.87 (millions, Dukascopy convention). Documented only.

## Storage

| metric | value |
|---|---|
| RAW_COMPRESSED_BYTES (sample, 5 days) | 2,830,898 |
| PARQUET_BYTES (sample, zstd) | 5,889,189 |
| ESTIMATED_1_YEAR_PARQUET_GB | ≈ 0.30 |
| ESTIMATED_2010_2018_PARQUET_GB | ≈ 2.67 |

Estimates extrapolate the sample over 252 trading days/year; actual tick
density varies by year (pre-2016 FX was less active, so these are upper-ish).
No large tick files will be committed.

## Consistency with existing EURUSD_5m feed

Tick BID aggregated to 5m bars ([t, t+5m), left-labeled) and compared with
`data_raw/parquet/EURUSD_5m.parquet` over the same 5 days: **1404 bars
matched, max absolute difference = 0.0 pips on OPEN/HIGH/LOW/CLOSE.** The two
feeds are the same underlying BID series; the tick pipeline is a superset.

## Tests

`python research/tick_m0/test_tick_m0.py` → 18/18 PASS: record decode,
timestamp offset, bid/ask scaling, volumes, spread pips, corrupt-record
rejection, ASK<BID detection, monotonicity detection, hour-bounds rejection,
negative-volume detection, causally-correct 5m aggregation.

## Layout

- `research/tick_m0/dukascopy_tick_probe.py` — download (idempotent, retry)
- `research/tick_m0/decode_ticks.py` — decode/validate/stats/parquet/5m-agg
- `research/tick_m0/analyze_sample.py` — sample report driver
- `research/tick_m0/test_tick_m0.py` — synthetic tests
- `research/tick_m0/tick_stats.json` — machine-readable stats manifest
- raw + parquet stay under `data_raw/tick_m0/` (gitignored)

## Constraints honoured

- No modification of the existing M1 pipeline (`research/phenomena_discovery_v1/`).
- 2019_PLUS_ACCESSED = NO; PROTECTED_OOS_ACCESSED = NO.
- No signal, backtest, or strategy analysis of any kind.
