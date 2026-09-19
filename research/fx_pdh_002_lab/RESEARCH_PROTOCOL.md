# FX_PDH_002 LAB — RESEARCH PROTOCOL

Mission: controlled improvement of FX_PDH_001 (USDJPY prior-day-high
continuation, STRICT V1) under the EUR 500 constraint.
Mode: AUTONOMOUS SCIENTIFIC RESEARCH. Local data only, 2020-2025.
ABSOLUTE: `2026_ACCESSED=NO` — every data access goes through
`forex_modern_trend_magic_lab/tmlab.py::load_5m`, which hard-seals at
2025-12-31 23:59:59 UTC.

## 0. VAULT RULE

FX_PDH_001 STRICT V1 (commit `033f6f0`, replication `617f9b1`) is FROZEN.
Nothing in this lab modifies it, its spec, its results, or its history.
Every experiment here belongs to FX_PDH_002A/B/C/D. Improvements become NEW
candidates; they never retroactively change 001.

## 1. BASELINE (reference numbers, frozen)

Engine `../../forex_modern_trend_magic_lab/audit/replay_strict.py`, NORMAL
costs unless stated: N=639, trades/week 2.04, PF 1.379, net +4.90 pips/trade,
stress +3.82, remove-best-1% +2.54, t=+2.52, EUR500@0.5% -> EUR 943.01,
maxDD 15.0%, 2022 = 61.2% of profit. By year (pips/trade):
2020 -0.17 | 2021 +5.01 | 2022 +18.78 | 2023 +5.75 | 2024 -1.14 | 2025 +1.78.

## 2. EXECUTION CONVENTIONS (inherited from STRICT V1, unchanged)

* H1 = left-labelled causal resample of sealed 5m BID bars (tmlab).
* One spread round-trip only: long buys at open+spread, exits at bid;
  `net_pips = gross - spread - slip` (stress slip = 0.5 pip/side, so
  stress total = spread + 2x0.5).
* Initial stop active from the entry fill; the entry bar CAN stop out.
  Fill = min(open, stop) - slip (conservative).
* Trailing level for bar i uses only information completed at the close of
  bar i-1 (ATR14(i-1), highs through i-1). A bar never sets its own stop.
* A bar that exits a position cannot trigger a new entry in the same bar.
* One position at a time (one group at a time in 002B); one first-break
  signal per UTC day; days with < 4 completed H1 bars are skipped (holidays),
  identical to the frozen engine.
* ATR14 = Wilder RMA of true range on H1, exactly as the frozen engine.
* Period 2020-01-01 .. 2025-12-31 23:59. No downloads. No new data sources.

## 3. SEARCH BUDGET (pre-registered, hard caps)

| Phase | Budget |
|---|---|
| 0 Diagnostic | 1 pass over the frozen 001 trades (no filtering) |
| A Short mirror | exactly 1 (no tuning, no rescue) |
| B Pyramiding | max 4 architectures x max 2 risk-cap policies = 8 cells |
| C Entry | reference + max 3 alternatives |
| D Exit | reference + max 3 alternatives |
| Composite | max 1, only if >= 2 phases independently improve (section 8) |

No fine parameter grids. No indicator filters (Trend Magic stays
DEAD_AND_CLOSED; no RSI/MACD/etc).

## 4. PRE-REGISTRATION — made BEFORE any 002 PnL was computed

The sub-sections below were written and committed before the first
FX_PDH_002 experiment was run. Coarse constants are fixed here; they are NOT
to be adjusted after seeing results.

### 4A. FX_PDH_002A — exact short mirror (no free parameters)

SIGNAL: first H1 bar of the UTC day with `low < PDL` (PDL = previous
COMPLETED UTC day's low). SIDE: SHORT. ENTRY: next H1 open, fill =
open - spread - slip. STOP: fill + 1.0 x ATR14(signal bar), active from the
fill; entry bar can stop out (fill = max(open, stop) + slip). TRAIL:
min(low since entry .. i-1) + 3.0 x ATR14(i-1). MAX HOLD 48 bars, exit at
close + slip. One position, no same-bar re-entry, same < 4-bar day skip.
If SHORT is decisively negative: `FX_PDH_002A_STATUS=DEAD`. No rescue.

### 4B. FX_PDH_002B — pyramiding (anti-martingale only)

Principles: no averaging down, no adds on losing positions, never widen a
stop to make room, total worst-case open risk capped, base = exact STRICT V1
trade (entry, stop, trail, 48h — untouched by adds).

**Layer management (pre-registered):** every layer (BASE, ADD1, ADD2) is
managed as an independent STRICT V1 position: own initial stop
1.0 x ATR14(own trigger bar), own trail `extreme-since-own-entry -/+ 3.0 x
ATR14(i-1)`, own 48h max hold, own conservative fills. Adding never touches
an existing layer's stop. Layers exit independently.

**Lifecycle:** ADD triggers are evaluated at H1 bar CLOSE only; an add fills
at the NEXT H1 open (+ costs). A new add requires the BASE layer to still be
open and its condition newly true. Max ONE add per bar per group; if two
levels qualify on the same bar, the lower level (ADD1) fills first. Max 2
adds per group. Once the BASE layer has exited, no new adds; already-open
adds keep their own management.

**Add architectures (exactly 4, chosen now):**

* B1 R-MOMENTUM: ADD1 at the first H1 close where base open PnL >= +1.0 R
  (R = 1.0 x ATR14(base signal bar)); ADD2 at the first H1 close where base
  PnL >= +2.0 R.
* B2 H1-CONTINUATION: ADD1 at the first H1 close where the bar's high is a
  new high above every H1 high since the base entry (bar itself excluded)
  AND base PnL >= +0.5 R; ADD2 at the next H1 close satisfying the same
  condition with the extreme re-anchored at the ADD1 trigger bar.
* B3 PULLBACK-RECLAIM: after base PnL has reached >= +0.5 R once, ADD1 at
  the first H1 close with `low <= PDH(and-current-day) and close > that
  PDH` (a successful retest-reclaim of the broken prior-day high); ADD2 at
  the SECOND such distinct reclaim bar. (PDH reference updates to the
  current trading day's own prior-day high; only bars above the entry-day
  regime count — i.e. the reclaim bar must close above the PDH in force.)
* B4 DAY-PERSISTENCE: ADD1 at the first H1 close that falls on a LATER UTC
  calendar day than the base entry while base PnL >= +0.5 R (the run
  survived a day boundary); ADD2 at the first H1 close on a third UTC day
  while base PnL >= +0.5 R.

**Risk-cap policies (exactly 2, chosen now):** total worst-case open risk
across all open layers must stay <= 0.75% (P075) or <= 1.0% (P100) of
current equity. Worst-case layer risk at a decision close =
max(0, entry_fill - currently-effective stop) x pip-EUR x lots
(short mirrored), with the effective stop computed from information through
that close (hh through i, ATR14(i)). Sizing: every layer targets 0.5% of the
FIXED EUR 500 initial capital (floor-rounded lots, step 0.01, min 0.01 —
identical formula to 001); an add is then TRUNCATED to the remaining
capacity `cap_eur - total_open_risk_eur`; if the remaining capacity cannot
carry 0.01 lots, the add is SKIPPED (never exceeds the cap). pip-EUR per
layer evaluated causally at the layer's entry time.

**Accounting:** equity for caps = 500 + realized PnL of closed layers +
marked unrealized PnL of open layers at the current close (both net of
costs). Every add records risk-before / risk-after / total worst-case EUR.

**Verdict rule (pre-registered):** pyramiding is accepted only if it
improves return AND does not substantially degrade risk-adjusted quality:
group-level expectancy_R, PF, remove-best-1%, stress, maxDD% and EUR500
gates are all reported; if profit rises but DD% rises proportionally more
and stress/RB1 fall materially, REJECT.

### 4C. FX_PDH_002C — entry quality (exits = original STRICT V1 exits)

* C0 REFERENCE: original first-touch break (high > PDH).
* C1 CLOSE-CONFIRM: signal = first H1 bar of the day with `close > PDH`.
* C2 CLOSE-RETEST: the day must first arm (first H1 close > PDH); the signal
  is the first LATER H1 bar IN THE SAME UTC DAY with `low <= PDH and
  close > PDH`. No retest by day end = no trade that day.
* C3 STRONG-BREAK: signal = first H1 touch of PDH, but only if that bar's
  close location `(close-low)/(high-low) >= 0.70` (degenerate zero-range bar
  -> rejected). If the first break bar fails the test, the day is skipped.

### 4D. FX_PDH_002D — exit architecture (entry = original STRICT V1 entry)

* D0 REFERENCE: stop 1.0 x ATR14(sig), trail 3.0 x ATR14(i-1), 48h.
* D1 SLOWER TRAIL: identical, but trail multiplier 4.5 instead of 3.0.
* D2 DAILY-CHANDELIER: initial stop unchanged; from the first H1 bar AFTER
  the first completed UTC day boundary following entry, trail =
  max(DAILY high of completed days since entry) - 3.0 x daily ATR14(last
  completed day). (Daily ATR14 = Wilder RMA on completed UTC days, causal.)
  Until that boundary only the initial stop is active. 48h unchanged.
* D3 STRUCTURE-EXIT: no trailing. Initial stop unchanged; exit at H1 CLOSE
  when the bar closes below the minimum low of the previous 5 completed H1
  bars (long; mirrored for any future short use). 48h unchanged.

### 4E. Composite (only if triggered)

Allowed ONLY if >= 2 of {B, C, D} independently improve 001 on the primary
criteria. ONE composite spec written to `FX_PDH_002_COMPOSITE_PREREG.md`,
then run ONCE. No second composite rescue.

## 5. REPORTING (every variant, no exceptions)

N, trades/week (N / 313.2), net pips/trade, PF, expectancy R, win rate,
t-stat, remove-best-1%, STRESS (0.5 pip/side), by-year mean pips/trade,
2022 profit share, max DD (R-space), EUR500@0.5% ending equity / maxDD% /
maxDD EUR. EUR500 gates for every candidate: VETO if maxDD >= 50%, ending
equity <= 250 EUR, any single-year loss >= 40%, or rolling-12m loss >= 40%;
WARN if maxDD >= 30% or worst year <= -25%. Margin scenario reported as
peak notional leverage (0.01 lot = 1,000 units of base).

Multiple-testing honesty: ALL variants are reported. The best of M variants
is labelled `k_OF_M_VARIANTS_SURVIVED`, never as externally preregistered.
2026 stays sealed and remains the final external test for BOTH candidates.

## 6. DIAGNOSTIC (phase 0) — description only

Pre-entry causal features (ATR, ATR percentile from prior history only,
prior-day range, day distance travelled, close vs PDH, body/close-location,
session, gap, 1d/3d/5d returns, 24-bar H1 efficiency, consecutive
higher-high days, EMA20 distance, bars-into-day) and lifecycle variables
(MFE/MAE in R, time-to-0.5R/1R/2R, max R, exit reason) computed on the
FROZEN 001 trades. Lifecycle variables are NEVER used as entry filters.
Output: `FX_PDH_001_DIAGNOSTICS.md` + `diagnostics/` CSVs.

## 7. FREEZE RULE

If a variant materially improves 001, create
`candidates/FX_PDH_002/` (FROZEN_SPEC.md, RESULTS.json, RESULTS.md, code,
tests), commit on `research/fx-pdh-002-lab`. Never replace 001; both stay
in the vault. Allowed final statuses: `NO_IMPROVEMENT_OVER_FX_PDH_001`,
`FX_PDH_002_COMPONENT_FOUND`, `FX_PDH_002_FROZEN_CANDIDATE`, or STOP.
