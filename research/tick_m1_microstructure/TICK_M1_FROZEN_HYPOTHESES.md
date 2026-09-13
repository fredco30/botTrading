# TICK_M1 — FROZEN HYPOTHESES (pre-registered)

**Commit order guarantee:** this file is committed BEFORE any Discovery-window
(2010-01-01 .. 2019-01-01 exclusive) tick data is downloaded, decoded, or
inspected on this machine. All numeric thresholds are chosen from the only tick
data ever seen so far: the committed TICK-M0 validation sample
(`research/tick_m0/TICK_M0_REPORT.md`: EURUSD 2018-06-04..08, median spread
0.30 pips, P05/P95 0.10/0.50, median 64 ticks/min, rollover widening at
21:00 UTC). No Discovery outcome has been observed. No thresholds may be
changed after this commit. No rescue variants, no H7+.

Scope: Discovery screen only. EURUSD, 2010-01-01 inclusive to 2019-01-01
exclusive. No 2019+ read. Protected OOS untouched.

---

## 0. Shared frozen definitions

All conventions below are part of the freeze and apply to every hypothesis.

### 0.1 Data and timestamps
- Source: Dukascopy hourly `.bi5` tick files (format validated in TICK-M0).
- `t` = tick timestamp (ms resolution, UTC). `timestamp_utc`.
- Columns per tick: `bid`, `ask`, `mid = (bid+ask)/2`, `spread_pips =
  (ask-bid)/1e-4`, `bid_volume`, `ask_volume`.
- VOLUMES ARE DUKASCOPY FEED QUOTE VOLUMES (median ≈ 1.87 in the M0 sample).
  They are NOT global FX volume and NOT traded volume at our broker. Any
  volume-based hypothesis is a statement about this specific feed only.

### 0.2 Causal feature primitives (computed at decision tick with timestamp t)
Window = closed interval of tick timestamps [a, b] (inclusive). `last(a)` =
the last tick with timestamp <= a (searchsorted-right minus 1).

- `F1 rate_now(t)` = number of ticks in [t-10s, t].
- `F2 rate_base(t)` = number of ticks in [t-600s, t-10s) divided by 59
  (mean ticks per 10s over the trailing 10 minutes, excluding the current
  10s window).
- `F3 rate_ratio(t)` = F1 / F2 (undefined if F2 == 0 -> no event).
- `F4 r10(t)` = mid(t) - mid(t-10s), in pips, where mid(t-10s) is mid of
  `last(t-10s)`; undefined if no tick <= t-10s -> no event.
- `F5 spread_base(t)` = median of the per-minute median `spread_pips` over the
  10 COMPLETE minutes immediately before the minute containing t
  (minutes [floor_min(t)-10, floor_min(t)-1]); undefined if any of those
  minutes has no ticks -> that minute's median is skipped; undefined if <8 of
  the 10 minute-medians exist -> no event.
- `F6 spread_ratio(t)` = spread_pips(t) / F5.
- `F7 imb30(t)` = (BV - AV) / (BV + AV) where BV, AV = sums of `bid_volume`,
  `ask_volume` over ticks in [t-30s, t]. Undefined if BV+AV == 0.
- `F8 qdir30(t)` = over all consecutive tick pairs whose LATER tick lies in
  [t-30s, t]: n_up = #(bid_i > bid_{i-1}) + #(ask_i > ask_{i-1});
  n_dn = #(bid_i < bid_{i-1}) + #(ask_i < ask_{i-1});
  qdir = (n_up - n_dn) / (n_up + n_dn). Undefined if n_up + n_dn == 0.

### 0.3 Event validity filters (frozen, identical for all hypotheses)
A candidate decision tick t is an EVENT only if ALL hold:
- 2010-01-01 00:00:00 UTC <= t < 2019-01-01 00:00:00 UTC (hard discovery cut).
- gap to previous tick <= 60s (kills weekend-open / feed-gap artifacts: no
  event may fire on data that only just resumed after a hole).
- t NOT in the daily rollover exclusion window [21:00:00, 21:05:00) UTC
  (rollover spread widening is a documented feed artifact from TICK-M0, not an
  information event; this exclusion is uniform, not outcome-derived).
- Hypothesis-specific feature definitions are defined (no NaN/undefined).

### 0.4 Execution (frozen)
- Decision at t uses only ticks <= t. Entry uses the decision tick's own quote.
- LONG: entry at ask(t), exit at bid(last tick with ts <= t+H).
- SHORT: entry at bid(t), exit at ask(last tick with ts <= t+H).
- `net_pips(LONG) = (bid_exit - ask_entry)/1e-4`; `net_pips(SHORT) =
  (ask_exit - bid_entry)/1e-4`. Real historical spread is charged by
  construction; NO additional synthetic spread is subtracted.
- Exit tick must be strictly after the decision tick; if no tick exists in
  (t, t+H] within the loaded discovery data, the event is SKIPPED (not a loss,
  not a win; counted in `n_skipped_no_exit`).
- `gross_mid_pips = direction * (mid_exit - mid(t))/1e-4` (report only).
- Stress: `net_stress(x) = net - 2x` with x = 0.10 and x = 0.25 pip/side
  (adverse only; no favorable fills anywhere).

### 0.5 Overlap suppression (frozen)
- Candidates processed in chronological order (greedy). After an accepted
  event at t with horizon H, the next accepted event must have decision
  timestamp > t + H (per hypothesis+configuration).
- RAW_EVENTS = candidate events before suppression; NON_OVERLAPPING_EVENTS =
  after. ALL headline inference uses NON_OVERLAPPING_EVENTS.

### 0.6 Metrics (frozen, per configuration)
N_EVENTS (raw), N_NON_OVERLAP, mean net pips, median net, win rate,
gross mid mean, positive years (of 9: 2010..2018, mean net > 0), year-by-year
mean net, remove-best-1% mean (drop the top ceil(1%) most profitable events,
mean of the rest), 95% bootstrap CI of mean net (2000 resamples, percentile,
numpy default_rng(42); if N > 200000, a deterministic stride subsample with
stride = ceil(N/200000) first), stress nets (+0.10, +0.25 per side),
direction balance (% LONG), time-of-day distribution (6 buckets of 4h UTC).

### 0.7 Economic gate (frozen) — MICROSTRUCTURE_PROMISING requires ALL of:
1. mean net (executable) >= +0.30 pip/event
2. positive years >= 6/9
3. remove-best-1% mean > 0
4. stress net at +0.10 pip/side > 0
5. N_NON_OVERLAP >= 500
(no rarity exception is pre-registered; if a hypothesis produces < 500 events
over 9 years it fails the gate as-is and that fact is documented).

### 0.8 Multiple testing sanity check (frozen)
- ALL configurations are reported, no cherry-picking.
- Ranking by frozen primary metric: mean net pips (non-overlapping).
- One-sided p per config = 1 - Phi(mean/SE), SE = std/sqrt(N) (normal
  approximation). Benjamini-Hochberg FDR at q = 0.10 across all tested
  configurations as a SANITY CHECK ONLY: a strong economic effect is not
  rejected solely for imperfect p, and a single lucky config is not claimed
  as robust.

### 0.9 Two-stage rule (frozen)
- STAGE A = this Discovery screen. If ZERO configs pass the gate:
  FINAL_STATUS = NO_MICROSTRUCTURE_CANDIDATE. STOP. No rescue variants.
- If >= 1 passes: at most TWO candidates selected (highest mean net,
  tie-break by positive years then N), exact candidate specs written, NO V1
  access, STOP for human review.

### 0.10 Parameter budget (frozen)
- Feature windows: 10s, 30s, 600s (as defined above). Prediction horizons:
  10s, 30s, 60s only. Total primary configurations across all hypotheses:
  13 (<= 24 budget). No optimizer, no ML, no additional grids, no post-hoc
  threshold changes.

---

## H1 — TICK-RATE BURST CONTINUATION
- Mechanism: an extreme local acceleration of quote arrivals proxies
  information arrival / aggressive order flow; price drift observed during the
  burst continues briefly.
- Causal observable: F3 = rate_ratio (burst vs trailing 10-min baseline);
  F4 = r10 (drift direction during burst).
- Trigger: F3 >= 3.0 AND F1 >= 10.
- Direction: sign(F4); LONG if F4 > 0, SHORT if F4 < 0; requires |F4| >= 0.20
  pip (else no event).
- Entry timestamp: t (decision tick).
- Prediction horizon H: primary family {10s, 30s, 60s} -> configurations
  H1a/H1b/H1c.
- Expected direction: continuation of sign(F4).
- Execution price: per 0.4 (bid/ask, real spread).
- Cost treatment: real spread by construction; stress per 0.4.
- Rejection criterion: fails 0.7 gate on non-overlapping events.

## H2 — SPREAD COMPRESSION + ACTIVITY BURST
- Mechanism: unusually tight quotes co-occurring with elevated flow =
  liquidity replenishment while informed flow trades; short continuation.
- Causal observable: F6 <= 0.8 (spread now at most 80% of trailing-10min
  median) AND F3 >= 2.0.
- Trigger: F6 <= 0.8 AND F3 >= 2.0.
- Direction: sign(F4), |F4| >= 0.20 pip required.
- Entry timestamp: t.
- Prediction horizon H: {30s, 60s} -> H2a/H2b.
- Expected direction: continuation of sign(F4).
- Execution/cost/rejection: per 0.4/0.7.

## H3 — SPREAD SHOCK / LIQUIDITY WITHDRAWAL REVERSAL
- Mechanism: a sudden strong spread widening (liquidity withdrawal) often
  accompanies a quote overreaction; after the shock, quotes partially revert.
- Causal observable: F6 >= 2.0 AND spread_pips(t) >= 1.0 pip (absolute floor
  so the "shock" is economically meaningful in all years).
- Trigger: F6 >= 2.0 AND spread_pips(t) >= 1.0 (rollover window already
  excluded by 0.3).
- Direction: REVERSAL of the last-10s mid drift: SHORT if F4 > 0, LONG if
  F4 < 0; requires |F4| >= 0.20 pip.
- Entry timestamp: t.
- Prediction horizon H: {30s, 60s} -> H3a/H3b.
- Expected direction: partial reversion of sign(F4).
- Execution/cost/rejection: per 0.4/0.7.

## H4 — BID/ASK FEED-VOLUME IMBALANCE
- Mechanism: within the Dukascopy feed, relative quoting volume on the bid vs
  ask side proxies resting/absorbing interest asymmetry; sustained imbalance
  predicts short-term drift toward the heavy side. THIS IS FEED VOLUME, NOT
  GLOBAL FX VOLUME (0.1).
- Causal observable: F7 = imb30.
- Trigger: F7 >= +0.30 (LONG) or F7 <= -0.30 (SHORT); requires >= 5 ticks in
  [t-30s, t] and BV+AV > 0.
- Direction: sign(F7).
- Entry timestamp: t.
- Prediction horizon H: {30s, 60s} -> H4a/H4b.
- Expected direction: drift toward the volume-heavy side.
- Execution/cost/rejection: per 0.4/0.7.

## H5 — QUOTE MOVE IMBALANCE
- Mechanism: counting bid-side vs ask-side quote improvements over a short
  causal window measures which side of the book is being walked / repriced
  more aggressively; asymmetry predicts short-horizon drift.
- Causal observable: F8 = qdir30.
- Trigger: F8 >= +0.30 (LONG) or F8 <= -0.30 (SHORT); requires n_up + n_dn >= 8
  pairs in the window.
- Direction: sign(F8).
- Entry timestamp: t.
- Prediction horizon H: {30s, 60s} -> H5a/H5b.
- Expected direction: drift toward the side with more upward quote moves.
- Execution/cost/rejection: per 0.4/0.7.

## H6 — COMBINED ACTIVITY + QUOTE DIRECTION (single conjunction)
- Mechanism: burst-level flow (H1 mechanism) is most credible when the feed
  volume imbalance agrees with the observed drift; one conjunction, both
  primitives mechanistically motivated, no new thresholds invented.
- Causal observable: F3 >= 3.0 AND F1 >= 10 (H1 burst) AND sign(F7) ==
  sign(F4) with |F7| >= 0.10 (weaker imbalance than H4, as agreement filter).
- Trigger: the conjunction above; |F4| >= 0.20 pip required.
- Direction: sign(F4).
- Entry timestamp: t.
- Prediction horizon H: {30s, 60s} -> H6a/H6b.
- Expected direction: continuation of sign(F4).
- Execution/cost/rejection: per 0.4/0.7.

---

## Configuration inventory (13 total — the complete and only set)

| config | hyp | horizon | trigger summary | direction |
|---|---|---|---|---|
| H1a | H1 | 10s | rate_ratio>=3, F1>=10, r10>=0.2p | sign(r10) |
| H1b | H1 | 30s | rate_ratio>=3, F1>=10, r10>=0.2p | sign(r10) |
| H1c | H1 | 60s | rate_ratio>=3, F1>=10, r10>=0.2p | sign(r10) |
| H2a | H2 | 30s | spread_ratio<=0.8, rate_ratio>=2, r10>=0.2p | sign(r10) |
| H2b | H2 | 60s | spread_ratio<=0.8, rate_ratio>=2, r10>=0.2p | sign(r10) |
| H3a | H3 | 30s | spread_ratio>=2, spread>=1.0p, r10>=0.2p | -sign(r10) |
| H3b | H3 | 60s | spread_ratio>=2, spread>=1.0p, r10>=0.2p | -sign(r10) |
| H4a | H4 | 30s | imb30 >= +0.30 / <= -0.30 | sign(imb30) |
| H4b | H4 | 60s | imb30 >= +0.30 / <= -0.30 | sign(imb30) |
| H5a | H5 | 30s | qdir30 >= +0.30 / <= -0.30 | sign(qdir30) |
| H5b | H5 | 60s | qdir30 >= +0.30 / <= -0.30 | sign(qdir30) |
| H6a | H6 | 30s | H1 burst AND sign(imb30)=sign(r10), imb>=0.10 | sign(r10) |
| H6b | H6 | 60s | H1 burst AND sign(imb30)=sign(r10), imb>=0.10 | sign(r10) |

There are no other configurations. There is no H7. Any result table that
contains more or different rows than this inventory means the freeze was
violated.

## Verdict vocabulary
- Config passes 0.7 -> MICROSTRUCTURE_PROMISING.
- Zero configs pass -> FINAL_STATUS = NO_MICROSTRUCTURE_CANDIDATE; STOP.
- >= 1 passes -> write candidate specs for at most two configs;
  FINAL_STATUS = STOP_FOR_HUMAN_REVIEW. No V1 work.

## Infrastructure constraints (binding for implementation)
- Data root configurable via env `BOTTRADING_TICK_DATA_ROOT` and/or CLI
  `--data-root`; code must not hardcode machine paths. This run uses
  `E:\ResearchData\botTrading\ticks`. Only code/manifests/reports go to Git.
- Free-space report on C: and E: before download; abort if the run would
  materially consume C:.
- Processing: partitioned parquet (year/month), chunked by month with
  <=15-min context padding on each side; 32 GB RAM cap; no O(N^2).
- Bugs fixed automatically only if they affect timestamps, tick decode,
  causal windows, execution side, spread, volume interpretation, overlap,
  discovery boundary, or the reported verdict. Once the verdict is decisive,
  STOP.
