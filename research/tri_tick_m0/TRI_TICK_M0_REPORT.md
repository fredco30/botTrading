# TRI_TICK_M0 — Triangular Microstructure Feasibility Report

**Mission:** determine whether synchronized Dukascopy tick data for EURUSD / GBPUSD / EURGBP is complete, timestamp-compatible and economically coherent enough to justify a full 2010–2018 triangular / cross-pair microstructure research campaign.

**Scope:** DATA FEASIBILITY ONLY. No strategy, no PnL, no trading signal, no optimization, no 2019+ access, no protected OOS access.

- BASE_HEAD: `def3a943dfdd9ee0c59249080e5c1318815b11ae` (= `research/mtf-m1-tick-execution`)
- Sample range (UTC): 2018-06-04 00:00:00 → 2018-06-09 00:00:00 exclusive (validated TICK-M0 reference week)
- Data root: `E:\ResearchData\botTrading\ticks` (external, configurable; nothing bulk committed)
- Pipeline: reuse of the validated TICK-M1 Dukascopy hourly downloader (idempotent / resumable / retry-safe) and TICK-M0 20-byte big-endian decoder, extended per-symbol.

## FINAL_STATUS = TRI_TICK_DATA_NOT_SUITABLE — STOP

The three feeds decode perfectly and are economically coherent (the triangular identity holds to ~0.35 pips at 95%), **but the Dukascopy historical feed cadence is too coarse for 250 ms-class triangular synchronization**: on the 250 ms grid, only **18.3%** of snapshots have all three quote ages ≤ 500 ms (gate requires ≥ 50%). Median max quote age is **~2.1 s**. This is an intrinsic property of the feed (EURUSD median inter-tick interval ≈ 511 ms), NOT a parsing bug (verified below). Per mission section 15, we STOP: no full-history download.

---

## 1 — Individual feed quality

All three symbols empirically confirmed: 20-byte big-endian records, ms-offset-from-hour timestamps, point scaling **1e5** (proven by candidate scan, not assumed), ASK ≥ BID everywhere, monotone timestamps, hour bounds respected.

| Metric | EURUSD | GBPUSD | EURGBP |
|---|---|---|---|
| N_TICKS | 474,506 | 424,422 | 406,180 |
| FIRST_TICK (UTC) | 06-04T00:00:00.485 | 06-04T00:00:00.092 | 06-04T00:00:00.275 |
| LAST_TICK (UTC) | 06-08T20:59:56.794 | 06-08T20:59:49.177 | 06-08T20:59:55.580 |
| HOURLY_FILES_EXPECTED / PRESENT | 120 / 120 | 120 / 120 | 120 / 120 |
| EMPTY_MARKERS | 3 | 3 | 3 |
| MISSING / CORRUPT | 0 / 0 | 0 / 0 | 0 / 0 |
| MEDIAN_SPREAD_PIPS | 0.30 | 0.80 | 0.80 |
| P95_SPREAD_PIPS | 0.50 | 1.10 | 1.20 |
| P99_SPREAD_PIPS | 1.00 | 2.40 | 2.40 |
| MAX_SPREAD_PIPS | 5.60 | 14.50 | 11.00 |
| MEDIAN_TICKS_PER_MIN | 64 | 52 | 54 |
| P95_TICKS_PER_MIN | 134 | 137 | 120 |
| ASK_LT_BID / NON_MONO_TS / NEG_VOL / INVALID_PX | 0/0/0/0 | 0/0/0/0 | 0/0/0/0 |

The 3 empty markers per pair are the identical low-activity Friday-hours hours (consistent with synchronized market close ~21:00 UTC Friday) — identical across all three feeds, further confirming timestamp compatibility. Feed-level verdict: **PASS for all three.**

## 2 — Synchronization (causal, fixed UTC grids, no future quotes)

Snapshots use the latest quote with `quote_ts <= grid_ts` per pair (`searchsorted` right−1); quote ages recorded per pair. 100% of grid points inside the week have all three prior quotes except the first instants of Monday 00:00 (dropped).

| Grid | N_SNAPSHOTS | P50 max age (ms) | P95 (ms) | P99 (ms) | all ≤100ms | all ≤250ms | all ≤500ms | all ≤1000ms |
|---|---|---|---|---|---|---|---|---|
| 100 ms | 4,319,995 | 2,099 | 25,627 | 6,490,729 | 1.0% | 5.6% | 18.3% | 32.7% |
| 250 ms | 1,727,998 | 2,099 | 25,632 | — | 1.0% | 5.6% | **18.3%** | 32.7% |
| 500 ms | 863,999 | 2,099 | 25,640 | — | 1.0% | 5.6% | 18.3% | 32.7% |
| 1000 ms | 431,999 | 2,099 | 25,660 | — | 1.0% | 5.5% | 17.9% | 32.6% |

Per-pair 250 ms-grid quote ages: EURUSD P50 674 ms / 42.9% ≤500 ms; GBPUSD P50 1,037 ms / 35.4%; EURGBP P50 856 ms / 38.5%.

Restricting to **in-session** snapshots (max age ≤ 60 s; 97.4% of grid) barely helps: 18.8% ≤ 500 ms, 33.6% ≤ 1000 ms. The 25.6 s P95 comes from ordinary thin periods (early Asian hours, late Friday); the extreme P99 tail (~1.8 h) is rare multi-hour lulls in the cross feed. There is no hour-long daily maintenance break in this feed (largest EURUSD intra-week gap: 75 s).

**Root cause (verified, not a bug):** EURUSD median inter-tick interval in an active London hour (Jun 4, 14h UTC) = **511 ms**; hourly tick-count profile is sane (London/NY 5–7k ticks/h vs Asian/late 1–3k); sub-second ms offsets are genuinely sub-second (only 0.14% of offsets are exact seconds). The Dukascopy historical "tick" feed averages ~1–2 quotes/s per pair; three legs combined ⇒ max-age ≤ 500 ms occurs ~18% of the time. **No grid choice fixes this — it is feed cadence.**

## 3 — Triangular mid residual (DIAGNOSTIC ONLY)

`SYNTH_EURUSD_MID = EURGBP_MID × GBPUSD_MID`; residual in pips (1 pip = 1e-4). 250 ms grid:

| Slice | N | mean | median | std | P01 | P99 | mean_abs | P95_abs | max |
|---|---|---|---|---|---|---|---|---|---|
| ALL | 1,727,998 | −0.013 | −0.002 | 0.240 | −0.527 | +0.515 | 0.146 | 0.475 | +7.23 |
| age ≤ 100 ms | 97,284* | −0.002 | −0.002 | 0.209 | −0.511 | +0.507 | 0.142 | 0.378 | +7.23 |
| age ≤ 250 ms | 97,284 | −0.002 | −0.002 | 0.209 | −0.511 | +0.507 | 0.142 | **0.379** | +7.23 |
| age ≤ 500 ms | 316,394 | −0.003 | −0.002 | 0.213 | −0.514 | +0.512 | 0.134 | 0.350 | +7.23 |
| age ≤ 1000 ms | 565,354 | −0.005 | −0.002 | 0.223 | −0.523 | +0.514 | 0.128 | 0.331 | +7.23 |

(*on the 250 ms grid, age ≤ 100 ms and ≤ 250 ms select the same snapshots.)

**The identity is economically coherent:** median residual ≈ −0.002 pips, P95 ≈ 0.4 pips, and restricting to fresher quotes shrinks the tail modestly (0.475 → 0.379 pips at 250 ms). Large residuals (max 7.2 pips) are rare and occur at genuine quote-transition moments (see §5 event inspection) — not parse artifacts.

## 4 — Executable cycle bounds (FEASIBILITY DIAGNOSTICS, not profits)

Quotes: EURUSD = USD/EUR, GBPUSD = USD/EURGBP-leg = USD/GBP, EURGBP = GBP/EUR. Buy base ⇒ ASK; sell base ⇒ BID.

- **Cycle A** (USD → GBP → EUR → USD): `A = BID(EURUSD) / (ASK(GBPUSD) × ASK(EURGBP))`
- **Cycle B** (USD → EUR → GBP → USD): `B = BID(EURGBP) × BID(GBPUSD) / ASK(EURUSD)`

Both directions proven by unit tests, including the synthetic properties: internally-consistent zero-spread triangle ⇒ A = B = 1 exactly; consistent triangle with realistic spreads ⇒ A ≤ 1 and B ≤ 1. Measured (250 ms grid):

| Slice | mean A (bp) | median A | max A | A > 0 count | mean B (bp) | max B | B > 0 count |
|---|---|---|---|---|---|---|---|
| ALL | −1.17 | −0.96 | +4.73 | 341 / 1,727,998 | −1.15 | +2.90 | 300 |
| age ≤ 250 ms | −0.90 | −0.89 | +4.73 | 124 / 97,284 | −0.90 | +1.49 | 117 |

The ~−1 bp mean is the natural round-trip cost of three half-spreads; positive excursions are rare (0.02% of snapshots), tiny (max 4.7 bp), and isolated (100 ms-grid positive episodes: 430 total, median duration 100 ms, P95 400 ms, max 5.2 s; 250 ms grid: max 16.25 s). **Coherent — no scale/formula pathology.**

## 5 — Event-level sanity examples (top-10 |resid|, age ≤ 250 ms, ≥ 60 s apart)

Largest residual: 2018-06-05T16:00:43.250 UTC — EURUSD 1.16787/1.16790, GBPUSD 1.33589/1.33594, EURGBP 0.87358/0.87378, ages 17/0/144 ms, residual +7.23 pips, cycle A 1.000473, cycle B 0.999235. Bid/ask levels are mutually consistent across pairs at that instant (EURGBP ≈ EURUSD/GBPUSD to the tick), confirming this is a real quote-transition skew, not a decode error. Full 10-event table in `tri_tick_m0_results.json` (`events_top10_abs_resid`).

## 6 — Lead/lag (DESCRIPTIVE ONLY, frozen lag table)

100 ms grid, MID-change series, `corr(ΔLEG1[t], ΔLEG2[t+lag])` (lag > 0 ⇒ LEG1 leads). ΔEURUSD vs Δ(EURGBP×GBPUSD):

| lag (ms) | −2000 | −1000 | −500 | −250 | −100 | 0 | +100 | +250 | +500 | +1000 | +2000 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| vs dSYNTH | −0.001 | 0.001 | 0.007 | 0.044 | 0.159 | **0.282** | 0.167 | 0.097 | 0.018 | 0.002 | −0.000 |
| vs dGBPUSD | −0.001 | 0.001 | 0.006 | 0.034 | 0.115 | 0.192 | 0.122 | 0.074 | 0.010 | 0.000 | 0.000 |
| vs dEURGBP | −0.000 | 0.001 | 0.003 | 0.021 | 0.083 | 0.160 | 0.086 | 0.048 | 0.013 | 0.003 | −0.000 |

ΔGBPUSD vs ΔEURGBP peaks at lag 0 (−0.216; sign negative because EURGBP ≈ EURUSD/GBPUSD).

**Interpretation:** correlation is maximal at lag 0 and nearly symmetric around it (|+100| 0.167 vs |−100| 0.159). No leg systematically updates ≥ 100 ms before the others in this feed — consistent with all three series being derived from the same upstream quote-engine snapshots at this granularity. NOTE: DESCRIPTIVE_ONLY_NO_SELECTION.

## 7 — Feasibility gate (section 14)

| Criterion | Result | Pass |
|---|---|---|
| GBPUSD decode/validation | 0 corrupt, 0 invalid | ✅ |
| EURGBP decode/validation | 0 corrupt, 0 invalid | ✅ |
| missing/corrupt trading-hour data ≤ 1% | 0% (0/120 both) | ✅ |
| 250 ms grid: ≥ 50% snapshots max age ≤ 500 ms | **18.3%** (in-session: 18.8%) | ❌ |
| residual shrinks ALL→age≤250ms (or naturally tight) | 0.475 → 0.379 pips | ✅ |
| executable cycles coherent | mean ≈ −1 bp = spread cost; no impossible arbitrage | ✅ |

**TRI_TICK_M0_PASS = FALSE.**

## 8 — Conclusion

The data is *complete, correctly decoded, timestamp-compatible and economically coherent* — every quality and identity check passes, and the triangular residual is tight (~0.4 pips P95). The disqualifying failure is **synchronization granularity**: the Dukascopy historical feed's ~0.5–2 s effective quote cadence per pair means causal three-way snapshots at 250 ms are stale >500 ms in 82% of cases. Any triangular lead/lag or delayed-transmission research at 100–500 ms horizons would be dominated by quote staleness, not by market microstructure.

Per the stop rule: FINAL_STATUS=**TRI_TICK_DATA_NOT_SUITABLE**, STOP. No 2010–2018 history downloaded; no 2019+ accessed; no protected OOS accessed.

## 9 — Artifacts

- `tri_lib.py` — decode / causal sync / residual / cycle / lead-lag library
- `run_feasibility.py` — deterministic full run (CLI: `BOTTRADING_TICK_DATA_ROOT=... python run_feasibility.py`)
- `test_tri_tick_m0.py` — 23 synthetic tests (decode, scaling, hour semantics, causal sync + no-future-quote, identity, all 6 conversion sides, cycle A/B formulas, spread-consistency bounds, lead/lag sign convention)
- `tri_tick_m0_results.json` — machine-readable results (no bulk dataframes committed)
- Raw/parquet tick data live only under the external data root (`raw/GBPUSD`, `raw/EURGBP`, `parquet` untouched for EURUSD).
