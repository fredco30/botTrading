# S003_FROZEN_SPEC — EURUSD Volatility Compression → Confirmed Breakout

Frozen before any S003 computation. One version, no optimization, fail fast.

## Provenance — P034 definition (REUSED EXACTLY)

Source: `research/phenomena_discovery_v1/phase2_lib.py::p034_compression`
(verified against `phase2_correction_report.md` and `phase2_results.json`).

P034 operates on **5-minute EURUSD bars** (`load_5m`, bucket-START timestamps,
bar known only at ts+5min), Discovery window 2010-01-01..2019-01-01 UTC:

- `hi12 = rolling(144).max(high) − rolling(144).min(low)` — trailing 12h range
  of 5m bars (144 × 5min).
- `med  = hi12.rolling(30 × 288, min_periods=5000).median()` — 30-day rolling
  median of that range (backward-looking).
- `comp = hi12 / med` — the ONLY normalization used by P034.
- Compression condition: `comp < 0.60` (event threshold, see below).
- Event = first bar of a compression run (`comp[i] < 0.60` AND
  `comp[i−1] >= 0.60`), after a 5000-bar warmup.

**P034_PARAMETERS_CHANGED = NO** — same window (144 5m bars), same
normalization (30-day rolling median), same event/run-start rule, same
Discovery frontier. The 5000-bar warmup is inherited unchanged.

### Frozen threshold: COMP < 0.60

P034 tested two frozen thresholds, 0.60 and 0.70. S003 freezes **0.60**
(stricter compression; P034's corrected EURUSD expansion was strongest there:
ratio 1.128, N=1799, vs 1.120, N=2166). Chosen a priori from P034's corrected
results, before any S003 run. No other threshold will be tested.

### Documented discrepancy (does not change the frozen definition)

The mission brief cites expansion "1.24–1.29x". That figure is the
pre-correction P034 result, invalidated by the forward-range implementation
bug (measured a single bar 12h later; baseline 4.2 pips instead of 62.5).
The corrected P034 shows EURUSD ratio ≈ 1.13 and was logged
`SECOND_ORDER_CANDIDATE=NO`. The definition itself is unaffected; S003
reuses it exactly and lets the fail-fast gate decide.

### Mapping to H1 (causal)

- The P034 compression condition is evaluated at each **completed H1 close T**
  using only 5m bars whose close time ≤ T (the P034 series truncated at T).
- An H1-sampled COMPRESSION_EVENT fires when `comp < 0.60` holds at T and did
  not hold at the previous H1 close (run-start at H1 sampling), after warmup.
- At that H1 close, freeze:
  `COMPRESSION_HIGH = max(high of the 144 trailing 5m bars)` and
  `COMPRESSION_LOW = min(low of the same 144 5m bars)`.
- H1 bars are built causally from the 5m series; an H1 bar is usable only
  once fully closed.

## Strategy (frozen)

- Instrument: EURUSD only. Pip = 0.0001.
- Breakout search: H1 bars after the compression close, max 12 hours.
  LONG signal: first H1 close > COMPRESSION_HIGH. SHORT: first H1 close
  < COMPRESSION_LOW. First confirmed break wins; none in 12h → NO TRADE.
- ENTRY = OPEN of the H1 bar after the signal bar (never the signal close).
  Next open unavailable → NO TRADE.
- LONG stop = COMPRESSION_LOW; SHORT stop = COMPRESSION_HIGH.
  RISK_PIPS = |ENTRY − STOP|; ≤ 0 → invalid.
- TARGET = 1.5R. No trailing / BE / partial / pyramid.
- TIME EXIT: if neither stop nor target hit, exit at the OPEN of the first
  H1 bar ≥ 12h after ENTRY.
- Execution: causal OHLC; stop/target via HIGH/LOW; both touched in the same
  bar → STOP-FIRST; adverse gap beyond stop → fill at real OPEN; favorable
  gap beyond target → credit capped at TARGET.
- One position at a time; compression events during an open position are
  ignored; a fresh P034 event is required after each exit.
- Costs: NORMAL 2 pips round-trip, STRESS 4 pips. Decision criteria on NORMAL.
- Window: 2010-01-01 inclusive → 2019-01-01 exclusive. 2019+ and protected
  OOS: never accessed.

## Discovery gate

S003_DISCOVERY_PROMISING iff ALL of:
NET_NORMAL_MEAN_PIPS > +2.0; PROFIT_FACTOR_NORMAL ≥ 1.20;
EXPECTANCY_R_NORMAL > +0.10R; POSITIVE_YEARS ≥ 6/9;
REMOVE_BEST_1_PERCENT_NET_MEAN > 0; TOTAL_NET_PIPS > 0.
CI95 (2000 bootstrap, seed 42) informative only.

Fail fast → S003_DISCOVERY_REJECT if NET_NORMAL_MEAN ≤ 0 OR
PROFIT_FACTOR_NORMAL ≤ 1.0 OR REMOVE_BEST_1_PERCENT_NET_MEAN ≤ 0.
No re-tuning of any parameter after the verdict.

## Addendum — FINAL P034 5M IDENTITY FIX (mandated, post-verdict)

After the first reject, the event detection was corrected to the EXACT P034
5m rule: run-start = comp[i] < 0.60 AND comp[i-1] >= 0.60 on the 5m series
(144-bar rolling range, 30*288 median, warmup 5000, Discovery frontier).
EVENT_KNOWN_TIME = event bar ts + 5min; HIGH/LOW frozen over the same
trailing 144 5m bars; the H1 strategy then starts at the first H1 bar fully
closed after EVENT_KNOWN_TIME. Raw event count = 1799, exactly equal to the
published P034 COMP<0.60 N (phase2_results.json) → P034_5M_EVENT_IDENTITY=PASS.
No other rule changed. Verdict recomputed once: still S003_DISCOVERY_REJECT.
Note: P034's original fwd-range tail exclusion (last 144 bars) applied to its
forward measurement only; S003 does not measure forward ranges, so no tail
exclusion is applied — this affects only events in the final hours of
Discovery and no raw event count was excluded (1799 = 1799).
