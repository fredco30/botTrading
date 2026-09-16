
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

---

# BLOCKING FIXES (2026-09-17, reconciliation mission)

MODE GUARD (engine.py):
  MODE=REFERENCE_REGRESSION -> any ts >= 2026-01-01Z refused (research seal).
  MODE=PROSPECTIVE_PAPER    -> any ts < ACTIVATION_TIMESTAMP
  (2026-09-16T22:01:40Z) refused; ts >= activation allowed.

DATA WINDOW per session D (pilot_eod.py):
  ohlcv-1m : [D-1 09:30 ET -> D 16:00 ET]  (prior RTH close for on_ret,
             overnight [D-1 18:00 -> D 09:30) for on_high/on_low, premarket
             [04:00,09:30), RTH bars)
  bbo-1s   : [D 09:30 -> D 16:05 ET] on the day's ACTUAL contract
  Overnight/premarket payload attached to every bar; no synthetic fills in
  PROSPECTIVE mode: unproven stop/trail/EOD = DATA_GAP journal event, day
  carried or flat per frozen rules, never a fabricated price.

WARM-UP (exact):
  ON_RET_Z_LOOKBACK = 20 prior session returns -> first record at session 2
  (needs prior session close) -> decision needs >=20 -> session 22.
  ATR_LOOKBACK = 14 prior TRs -> session 15 (non-binding).
  FIRST_SIGNAL_ELIGIBLE_SESSION = 22nd prospective session = 2026-10-16
  (22nd US weekday from 2026-09-17; no US equity holiday in that span —
  NQ trades normal RTH on Columbus Day).

BUDGET (metadata.get_cost on 2025 equivalent-length session — no 2026 access):
  1m context 28.5h = $0.0064 | BBO 6.6h = $0.0322 | session = $0.0385
  22 sessions to first signal = $0.847 | 30 sessions = $1.155
  => the $0.50 ceiling covers only ~13 sessions (ceiling < signal eligibility).
