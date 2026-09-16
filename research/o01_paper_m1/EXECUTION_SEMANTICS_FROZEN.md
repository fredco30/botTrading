
---

# EXECUTION MODES (reconciliation audit 2026-09-16)

MODE 1 REFERENCE_REGRESSION (NEVER deployable):
  = the validated high-res replay code (nq_h02_o01_highres_m1/o01_replay.py)
  exactly: stops priced inside the FROZEN exit bar only; missing/late quotes
  fall back to frozen 1m prices. Reproduces N=133 / +13.3853 / PF 1.467.

MODE 2 PROSPECTIVE_PAPER (deployable):
  S1_BAR_SEMANTIC trigger (completed 5m bar touch) + quote-window pricing:
  stop executes at the first executable opposite-side quote inside the
  triggering bar; missing quotes = DATA_GAP (day stays flat), NEVER a
  synthetic fallback price. No fill before activation.

## STOP SEMANTICS TRUTH TABLE (code evidence)

LAYER                 | TRIGGER                      | EXECUTION PRICE
lab_lib.py:187-189    | S1 bar touch (l<=stop /      | stop price or worse 1m
(frozen strategy)     | h>=stop), every completed bar| bar open
o01_replay.py:65-68   | frozen-timeline (exit bar    | first BBO quote >= exit
(validated replay)    | inherited from lab), scanned | bar start, executable
                      | from exit-bar start only     | side
paper engine          | S1 bar touch (same as lab)   | first executable quote
                      |                              | inside the touch bar
ORIGINAL_STRATEGY_IMPLIES=S1_BAR_SEMANTIC (lab_lib is the canonical frozen
implementation; its trigger is the completed-bar touch, not a quote-level
monitor). DEPLOYABLE_STOP_SEMANTICS=S1_BAR_SEMANTIC with quote-window pricing.

The validated replay's stop timing (pricing only inside the frozen exit bar)
was an execution-resolution artifact: it exits stops LATER than a real resting
stop order would (paper stops earlier, cutting losses faster). Both are S1;
the paper engine does NOT introduce S2 quote-touch triggering (its trigger
remains the completed-bar touch; quotes only price it).
