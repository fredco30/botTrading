# RATES_MACRO_M1_FROZEN_SPEC

Mission: RATES-MACRO-M1 — cross-market event-driven discovery.
NFP/CPI → US Treasury futures repricing → delayed EURUSD adjustment.

This spec is FROZEN and committed BEFORE any EURUSD outcome is computed.
Every threshold, rule and definition below is fixed. No optimizer, no
parameter grid, no ML, no threshold rescue, no post-hoc reversal of any
mapping after seeing results.

- Parent branch/head: `research/rates-data-m0` @ `7c63937670e30a5cfb41362455700b233917d43b` (PR #35, DO NOT MERGE)
- Working branch: `research/rates-macro-m1`
- Discovery window: **2010-06-07 inclusive → 2019-01-01 exclusive. 2019+ FORBIDDEN.**
- Protected OOS FORBIDDEN. V1 must NOT be opened.
- Exactly THREE frozen strategies (A/B/C). No variants.

## 0 — Signal source

The signal source is NOT EURUSD itself. Information chain:

```
NFP/CPI release → Treasury futures repricing → possible delayed EURUSD adjustment
```

Primary Treasury instruments: `ZF.v.0`, `ZN.v.0`.
`ZT.v.0` is DIAGNOSTIC ONLY (its M1 alignment is materially lower; the primary
sample must never require ZT).

## 1 — Macro event source (validated artifact, not rebuilt)

Use ONLY the validated MACRO-TICK-M0 event database artifact:

- Source commit: `f968f4ae353e79fef80311e646987dc3add38b2b`
- File: `research/macro_tick_m0/data/macro_events_2010_2018_aligned.csv`
- Copied verbatim onto this branch at
  `research/rates_macro_m1/data/macro_events_2010_2018_aligned.csv`
- Source blob SHA-256:
  `f89623096e36a12a98f3aaa23f1217dc245bfa9745cc46d4a6c1b6b4e3a2e418`

The macro calendar is NOT rebuilt or reinterpreted. FOMC rows are excluded.
Market consensus forecasts, revised macro values and any future macro
information are NOT used. ALFRED actual values remain metadata only and MUST
NOT determine direction.

Event universe: `family ∈ {NFP, CPI}` with official
`release_timestamp_utc` inside the discovery window.

## 2 — Data

- Treasury futures: Databento `GLBX.MDP3`, schema `ohlcv-1m`, continuous
  symbols `ZT.v.0 / ZF.v.0 / ZN.v.0`, UNADJUSTED prices (RATES-DATA-M0,
  commit `7c63937`). Stored at `E:\ResearchData\botTrading\rates\databento\`.
- EURUSD: validated tick store (BID/ASK/MID), month partitions
  `year=YYYY/month=MM` 2010-01..2018-12 at `E:\ResearchData\botTrading\ticks\`.
- Roll identity: `metadata/roll_map.csv` + exact transition instants from
  `metadata/roll_audit.csv` (RATES-DATA-M0 validated artifacts).
- Rate gap classification: `metadata/{zt,zf,zn}_gaps_full.json`
  (`EXPECTED_MARKET_CLOSED | EXPECTED_NO_TRADES | UNEXPECTED_DATA_GAP`).

## 3 — Treasury bar causality

A 1-minute rate bar is usable only after that minute is COMPLETED. High/low/
close/volume of a still-forming bar are never used. For an event at T0 exactly
on a minute boundary the EVENT_RATE_BAR = [T0, T0+1min); its CLOSE becomes
known at T0+1min. The rate-signal decision cannot occur before T0+1min.

## 4 — Roll guard

Continuous prices are intentionally NOT back-adjusted, so no event may use a
Treasury return crossing a contract roll. For ZF and ZN independently, the raw
underlying contract identity must remain unchanged over
**[T0 − 60 min, T0 + 1 min]**. Operational rule (frozen): using the exact
transition instants of `roll_audit.csv` (old contract last print
`old_last_ts`, new contract first print `new_first_ts`), an event is
`ROLL_WINDOW_INVALID` for an instrument iff a transition satisfies
`old_last_ts >= T0−60min AND new_first_ts <= T0+1min`. If either primary
instrument is roll-invalid the event is excluded. Do not repair, do not
back-adjust, do not bridge the price jump.

## 5 — Rate data gap guard (validated RATES-DATA-M0 logic)

A missing 1-minute trade bar is not automatically corruption (bars exist only
when trades print). For the event shock itself, the event bar [T0, T0+1min)
must EXIST for both ZF and ZN. The pre-event baseline uses only valid
consecutive rate returns (below). Rate prices are never forward-filled across
unexpected gaps; bars are never fabricated. Frozen addition (conservative,
causal): the shock move of an instrument must not cross an
`UNEXPECTED_DATA_GAP`; specifically no unexpected gap may intersect
`(start of the PRE_CLOSE bar, T0]` for that instrument — otherwise the event
is `RATE_WINDOW_INVALID` for that instrument (excluded).

## 6 — Pre-event rate noise (baseline)

For each event and each primary instrument (ZF, ZN), use ONLY completed
1-minute bars with start time `s ∈ [T0−60min, T0−5min)`. The bar starting at
T0−5min and everything inside [T0−5min, T0) is EXCLUDED. Returns are
close-to-close changes between CONSECUTIVE existing bars in this window
(`close_k − close_{k−1}`, bar starts exactly 60 s apart); a return is skipped
if either bar is missing, if it would cross a raw-contract roll, or if it
would cross an unexpected data gap. For each instrument:

```
RATE_Q95 = 95th percentile of |valid 1-minute price changes|
```

Require `N_BASELINE_RETURNS >= 30`, else `BASELINE_INVALID` (event excluded).

## 7 — One-minute rate shock

For each instrument:

```
PRE_CLOSE   = last completed close known strictly before T0 (any age)
POST1_CLOSE = close of the completed event minute [T0, T0+1min)
RATE_MOVE   = POST1_CLOSE − PRE_CLOSE
RATE_SCORE  = |RATE_MOVE| / RATE_Q95
```

`PRIMARY_RATE_SHOCK = TRUE` iff ALL:

- ZF RATE_MOVE and ZN RATE_MOVE have the SAME NON-ZERO sign
- ZF RATE_SCORE >= 2.0
- ZN RATE_SCORE >= 2.0

Thresholds 2.0/2.0 are FROZEN. No alternative (1.5, 2.5, 3.0), no sweep.

## 8 — Economic direction (FROZEN, never reversed after seeing outcomes)

- Treasury futures price DOWN ⇒ US yields repriced UP ⇒ USD bullish ⇒ **EURUSD SHORT**
- Treasury futures price UP ⇒ US yields repriced DOWN ⇒ USD bearish ⇒ **EURUSD LONG**

Therefore ZF/ZN UP → EURUSD LONG; ZF/ZN DOWN → EURUSD SHORT.

## 9 — ZT diagnostic only

If a valid ZT event-minute bar exists (event bar exists + ZT baseline valid by
the identical §5/§6 rules), compute its move and score identically and report
`ZT_AVAILABLE`, `ZT_CONFIRMS_PRIMARY_DIRECTION` (ZT move sign equals the
primary rate-implied direction). ZT MUST NOT decide eligibility, direction, or
trade selection. Diagnostic only.

## 10 — EURUSD event references

Real EURUSD BID/ASK ticks only.

```
FX_P0           = MID of last valid tick strictly before T0
FX_P1           = MID of first valid tick at or after T0 + 1 minute
FX_MOVE_1M_PIPS = (FX_P1 − FX_P0) in pips, signed (directional raw 1-minute move)
```

A tick must exist in [T0−60min, T0) and FX_P1 must exist within
[T0+1min, T0+2min), else the event is `FX_REF_INVALID` (excluded).
Pre-event FX noise: window [T0−60min, T0−5min); non-overlapping 1-minute MID
changes — for each minute bucket in that window take the LAST tick MID in the
bucket ("bucket-close mid"); changes are differences of CONSECUTIVE non-empty
buckets' close mids; a change spanning an empty bucket is skipped.

```
FX_Q95 = 95th percentile of |changes| in pips
```

Require `>= 30` valid changes, else `FX_BASELINE_INVALID` (excluded). All causal.

## 11 — Real EURUSD execution

Frozen latency: **250 ms**. At the decision timestamp:

- LONG: first ASK tick >= decision + 250 ms
- SHORT: first BID tick >= decision + 250 ms
- LONG exits at BID; SHORT exits at ASK (real historical spread naturally
  charged; no synthetic spread subtraction)
- No executable quote within **60 seconds** of decision+250 ms ⇒ `NO_FILL`

## 12 — Strategy A — `RATES_A_1M_REPRICING_CONTINUATION`

HYPOTHESIS: a large, cross-curve-confirmed Treasury repricing contains
fundamental information that EURUSD may continue to absorb after the first
minute.

- Eligibility: `PRIMARY_RATE_SHOCK = TRUE`
- Decision: T0 + 1 minute; direction per §8; entry per §11
- Structural stop: opposite extreme of EURUSD MID observed during
  [T0, T0+1min) — LONG: stop = first-minute LOW of MID; SHORT: stop =
  first-minute HIGH of MID
- If no tick exists in [T0, T0+1min): `NO_TRADE_FIRST_MINUTE_NO_TICKS`
- Stop invalid relative to executable entry (LONG stop >= entry / SHORT
  stop <= entry): `NO_TRADE_INVALID_STOP`
- Risk < 1.0 pip: `NO_TRADE_RISK_TOO_SMALL` (R = |entry − stop|)
- TARGET = 2.0R; TIME EXIT = 60 minutes after entry
- One trade maximum per event

## 13 — Strategy B — `RATES_B_FX_LAG`

HYPOTHESIS: the strongest opportunity is when rates reprice strongly but
EURUSD has NOT yet made an unusually large first-minute move.

- Eligibility: `PRIMARY_RATE_SHOCK = TRUE` AND `|FX_MOVE_1M_PIPS| <= FX_Q95`
  (frozen definition of "FX has not yet made an abnormal move"; no
  alternative threshold)
- Otherwise identical to A (decision T0+1min, §8 direction, §11 entry,
  first-minute structural stop, 1.0 pip minimum risk, 2.0R target,
  60-minute time exit)
- Separately pre-registered; NOT a post-hoc rescue of A

## 14 — Strategy C — `RATES_C_FX_DISAGREEMENT_REVERSION`

HYPOTHESIS: if Treasury futures strongly reprice in one fundamental direction
while EURUSD initially moves meaningfully in the OPPOSITE direction, the FX
move may be a temporary mispricing.

- Eligibility: `PRIMARY_RATE_SHOCK = TRUE`
  AND EURUSD first-minute move has the OPPOSITE sign to the rate-implied
  EURUSD direction AND `|FX_MOVE_1M_PIPS| >= 0.50 * FX_Q95` (0.50 frozen)
- Decision T0+1min; direction = rate-implied; entry per §11
- STOP = adverse first-minute EURUSD MID extreme (LONG: first-minute LOW;
  SHORT: first-minute HIGH); invalid stop or risk < 1 pip ⇒ NO_TRADE
- TARGET = FX_P0 (pre-release MID); if already crossed at executable entry
  (LONG entry <= FX_P0 / SHORT entry >= FX_P0):
  `NO_TRADE_TARGET_ALREADY_CROSSED`
- TIME EXIT = 30 minutes. One trade maximum per event

## 15 — Stop / target execution (tick-accurate)

- LONG STOP: trigger when BID <= stop; fill at actual BID (overshoot is real)
- LONG TARGET: trigger when BID >= target; fill capped at target
- SHORT STOP: trigger when ASK >= stop; fill at actual ASK
- SHORT TARGET: trigger when ASK <= target; fill capped at target
- First event wins: STOP → TARGET → TIME EXIT → DATA_GAP_INVALID

## 16 — EURUSD data gaps

Reuse the validated EURUSD gap rule (inter-tick delta whose non-weekend
portion exceeds 1 hour). If a true data gap intersects an open trade ⇒
`DATA_GAP_INVALID` (excluded from main metrics). Regular weekend closure is
not a data error. No invented path.

## 17 — Execution stress

Baseline = real historical BID/ASK execution. Additionally report adverse
slippage PER SIDE: `STRESS_025` = +0.25 pip/side, `STRESS_050` = +0.50/side,
`STRESS_100` = +1.00/side (round trip = 2 sides ⇒ mean net −0.50 / −1.00 /
−2.00 pips). Primary gate uses STRESS_050.

## 18 — No money-management rescue

Forbidden: pyramid, martingale, averaging down, reverse-on-stop, partials,
trailing, breakeven, dynamic sizing. Evaluation in pips and R only.

## 19 — Exactly three strategies

A, B, C exactly as above. No 2-minute shock, no 5-minute shock, no different
Q95, no different rate-score threshold, no different TP/stop/lag threshold.
No optimizer. No variants.

## 20 — Family breakdown

Primary verdict: NFP + CPI POOLED. Diagnostics reported separately for NFP and
CPI (N, mean net, PF) per strategy. A pooled strategy cannot PASS if
NFP mean <= 0 OR CPI mean <= 0. No family is selected after observing results.

## 21 — Year stability

Report 2010..2018 separately (2010 partial: Treasury data begin June).
POSITIVE_YEARS denominator = number of calendar years with >= 3 trades for
that strategy (`YEARS_ELIGIBLE`), reported explicitly; never silently forced
to 9.

## 22 — Metrics (per strategy A/B/C)

EVENTS_AVAILABLE, RATE_SHOCKS_QUALIFYING, N_TRADES, NFP_N, CPI_N,
NET_MEAN_PIPS, MEDIAN_NET_PIPS, WIN_RATE, AVG_WIN, AVG_LOSS, PROFIT_FACTOR,
EXPECTANCY_R (mean net/R), TOTAL_NET_PIPS, MAX_DRAWDOWN_PIPS (chronological),
MAX_CONSECUTIVE_LOSSES, POSITIVE_YEARS, YEARS_ELIGIBLE,
REMOVE_BEST_1_PERCENT_NET_MEAN (drop top 1% of trades, mean of the rest),
STRESS_025/050/100_MEAN, NFP_MEAN, NFP_PF, CPI_MEAN, CPI_PF.
Bootstrap mean CI: 2000 resamples, seed 42, percentile CI95_MEAN_NET.
Diagnostics: mean ZF rate score, mean ZN rate score, fraction ZT available,
fraction ZT confirming.

## 23 — Economic pass gate (ALL required)

```
N_TRADES                        >= 40
NET_MEAN_PIPS                   >= +3.0
PROFIT_FACTOR                   >= 1.25
EXPECTANCY_R                    >= +0.10
POSITIVE_YEARS / YEARS_ELIGIBLE >= 0.67
REMOVE_BEST_1_PERCENT_NET_MEAN  >  0
STRESS_050_MEAN                 >  0
TOTAL_NET_PIPS                  >  0
NFP_MEAN                        >  0
CPI_MEAN                        >  0
```

CI95 reported; `CI_POSITIVE=YES` iff lower bound > 0 (robustness flag only,
not mandatory for Discovery PASS).

## 24 — Fail fast / credit discipline

Run all three frozen strategies. For each: if `NET_MEAN <= 0` OR `PF <= 1.0`
OR `REMOVE_BEST <= 0` ⇒ **REJECT** (no rescue analysis). Otherwise, if the
full §23 gate is not met ⇒ **FAIL_GATE**. Once A/B/C have verdicts: STOP.
Do not optimize. Do not open V1 unless a strategy passes the complete gate.

## 25 — Tests

Synthetic tests required for: macro event timestamp use; rate bar unavailable
until completed; no forming-rate-bar lookahead; PRE_CLOSE causal;
event-minute POST1_CLOSE causal; roll-window exclusion; rate unexpected-gap
exclusion; baseline excludes T0−5m; RATE_Q95; rate-score calculation;
ZF/ZN same-sign requirement; futures-UP → EURUSD-LONG mapping; futures-DOWN →
EURUSD-SHORT mapping; ZT diagnostic cannot change signal; FX P0/P1 causality;
FX_Q95; A rules; B lag rule; C disagreement rule; 250 ms latency; LONG ASK
entry; SHORT BID entry; LONG BID exit; SHORT ASK exit; stop overshoot;
target cap; stress arithmetic; 2019 hard cutoff; protected-OOS guard.
Also run locally: RATES-DATA-M0 (13 tests), MTF-M1, TICK-M1, TICK-M0 suites.
Wire the RATES-DATA-M0 and RATES-MACRO-M1 synthetic suites into the existing
`research-engine-tests` workflow if practical; never claim CI covers what it
does not.

## 26 — Independent real-data audit

Before the final verdict, independently verify (separate implementation path)
at least 10 A trades, 10 B trades, 10 C trades (or all if fewer): official
event T0, ZF/ZN raw contracts, PRE_CLOSE, POST1_CLOSE, rate moves/scores,
direction, FX P0/P1, entry timestamp/side/price, stop, target, exit
timestamp/price, net PnL. Minimum 30 exact checks if available.

## 27 — Performance

Never load all 208M EURUSD ticks at once — event windows only. Rate data
(~6.65M rows) may be loaded whole. No new paid Databento download; no
additional data purchase.

## 28 — Git

PR kept NON-MERGED, base `research/rates-data-m0`. No bulk data in git.
Commits: frozen spec → code → tests → small results → report.
