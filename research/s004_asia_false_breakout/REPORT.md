# S004 — EURUSD Asia False Breakout → Range Reversion — Discovery Report

Verdict: **S004_DISCOVERY_REJECT** (fail fast — no tuning, no variants).

## Result summary
- 2064 Asian-range breakouts (08:00–11:00 London), 58.0% failed (reentry
  within 60 min) — the false-breakout phenomenon is real and frequent.
- 1180 trades over 9 years (~131/year). Gross edge: **+0.22 pip/trade** —
  essentially zero before costs. Win rate 46.5%, PF 0.74.
- The 2-pip RT cost turns it into **−1.78 pips/trade net normal**
  (−3.78 stress). CI95 bootstrap [−2.62, −0.96]: no scenario near breakeven.
- Negative in all 9 years (POSITIVE_YEARS 0/9), REMOVE_BEST_1% still −2.25.

Fail-fast triggers: NET_NORMAL_MEAN ≤ 0 (−1.78), PF ≤ 1.0 (0.74),
REMOVE_BEST ≤ 0 (−2.25). Per spec: REJECT, STOP. None of the forbidden
variants (other pairs, 30/90/120-min reentry, alternate targets/stops,
filters) were tested.

## Bugs found & fixed during build (bug policy: verdict-changing only)
1. tgt_ok orientation inverted vs trade direction.
2. Stop used the wrong extreme of the breakout→reentry sequence
   (lowest low instead of highest high for the SHORT trade).
Both were caught by inspecting individual trades against raw 5m bars;
final engine verified by 11 passing spec tests (test_s004.py):
GMT/BST handling, range bounds, close-only signals, entry at next-bar open,
stop side, target = midpoint, stop-first, adverse/favorable gap fills,
12:00 time exit, 2/4 costs, hard 2019 data cut.

## Files
- S004_FROZEN_SPEC.md — frozen before execution (commit 1)
- s004_strategy.py — deterministic engine (discovery window only)
- test_s004.py — minimal spec tests
- s004_trades.csv, s004_results.json — full outputs
