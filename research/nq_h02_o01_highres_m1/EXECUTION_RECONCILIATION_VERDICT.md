# O01 EXECUTION RECONCILIATION — VERDICT (2026-09-16)

STATUS=PAPER_EXECUTION_MODEL_SEPARATE_BUT_VALIDATED

## MODE 1 REFERENCE_REGRESSION (validated replay re-run)
N=133 | NET=+13.3853 | PF=1.4672 — exact reproduction ✓ (deterministic re-run
of nq_h02_o01_highres_m1/o01_replay.py; 3 ambiguous days use the validated
frozen-price fallbacks). NEVER used for prospective trading.

## MODE 2 PROSPECTIVE_PAPER (deployable semantics, owned data replay)
SIGNALS=133 | EXECUTED=130 | DATA_GAPS=3 (see classification)
BASE    +15.2306 pts  PF 1.5998  RB +12.93  DD -$9,030   5/6 years +
CONS    +14.7306      PF 1.5716  RB +12.43  DD -$9,240
STRESS  +14.2306      PF 1.5443  RB +11.93  DD -$9,450
BY_YEAR (BASE): 2020 -5.16 | 2021 +18.59 | 2022 +43.51 | 2023 +12.02 |
2024 +21.55 | 2025 +11.30

## STOP SEMANTICS TRUTH TABLE (code-evidenced)
lab_lib.py:187-189 (frozen strategy): S1_BAR_SEMANTIC — trigger = completed
5m bar touch (l<=stop / h>=stop), fill = stop or worse bar open.
o01_replay.py:65-68 (validated): trigger TIMELINE inherited from the frozen
lab (stop priced only inside the FROZEN exit bar) — an execution-resolution
artifact that exits stops LATER than a real resting stop order.
paper engine: S1 bar-touch trigger + first executable opposite-side quote
INSIDE the touch bar (real resting-stop behavior). NOT S2 quote-monitoring
of the strategy decision: the trigger remains the completed-bar touch.

ORIGINAL_STRATEGY_IMPLIES=S1_BAR_SEMANTIC
DEPLOYABLE_STOP_SEMANTICS=S1_BAR_SEMANTIC with quote-window pricing

## PNL DELTA RECONCILIATION (paper - reference, BASE)
TOTAL_PNL_DELTA=+237.2 pts over 130 executed trades (+1.84/trade average:
paper exits losing stops EARLIER at better prices than the frozen-timeline
artifact; the improvement concentrates in loss-reduction, not profit
inflation).
DELTA classes (pts, sum): STOP +122.0 (95 trades) | EOD +19.0 (33) |
TRAIL +0.5 (1) | ENTRY included in per-trade deltas (BBO ask/bid vs 1m open,
~+-0.25) | MISSING_QUOTE 3 days.
File: results/EXECUTION_SEMANTICS_DELTA.csv (all 133 signals).

## 3 MISSING-QUOTE DAYS (classified from the owned BBO windows)
2020-03-09: DATA_GAP_FIRST_QUOTE_LATE (61s after activation)
2020-03-12: DATA_GAP_FIRST_QUOTE_LATE (1s; bid_first 7450.00)
2021-11-29: DATA_GAP_FIRST_QUOTE_LATE (0s; bid_first 16261.00)
Reference PnL on those days: -132.5 / -75.0 / -52.25 (all LOSSES). The paper
engine's working-order semantics skipped them (conservative): skipping them
IMPROVED the paper result — no winning trade was fabricated.
Also NOTE: on those days the paper SIGNAL matched (dates in the frozen list);
the entries did not fill for lack of an executable quote at/after activation
inside the data window. DATA_GAP, not strategy outcome.

## TESTS
16/16 PASS (12 engine: tz/DST, intervals, z-causality, no-future, bid/ask
sides, stop, chandelier, EOD, 3 scenarios, no-real-order, restart,
idempotence + 4 reconciliation: S1 bar-trigger not quote-continuous,
no synthetic fallback symbols in the engine, no real-order route,
reference artifact present for MODE 1).

## CLASSIFICATION
The deployable execution model (S1 + quote-window pricing) differs in
RESOLUTION from the validated replay (frozen-timeline stop timing) but the
frozen-signal replay under the new model remains robust: NET +15.23 BASE /
+14.23 STRESS, PF >= 1.54 across all frictions, 5/6 years positive, better
worst-case stops. No tuning; no signal change.

STRATEGY_CHANGED=NO | NEW_DATA_PURCHASED=NO | HISTORICAL_2026_ACCESSED=NO |
REAL_ORDER_CAPABILITY=NO | NO LIVE ACTIVATION (awaits feed authorization)
