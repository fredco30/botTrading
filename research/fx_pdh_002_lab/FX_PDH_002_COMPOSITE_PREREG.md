# FX_PDH_002 COMPOSITE — PRE-REGISTRATION (written BEFORE the composite run)

Trigger check (protocol section 23): at least TWO components independently
provide meaningful improvements over FX_PDH_001 without obvious overfit:

* B (pyramiding): 3 of 8 pre-registered cells pass; B1_P075 validated
  (PF 1.478, dd 10.6%, all years positive; adds carry standalone edge).
* C (entry): 1 of 3 alternatives passes — C1 close-confirm (PF 1.424,
  +5.47 pips/trade, dd 10.3%, 2022 share 48.6% at equal total profit).
* D (exit): 2 of 3 alternatives pass — D1 slower trail and D2 daily
  chandelier (PF 1.464 / 1.517, t 2.89 / 3.11, rb1 4.08 / 4.98,
  stress 5.44 / 6.52, dd 13.6% / 12.7%).

=> COMPOSITE TRIGGERED. ONE composite will be run ONCE.

## The composite (exact specification)

FX_PDH_002 = C1 entry + D2 exit:

* SIGNAL: first H1 bar of the UTC day whose CLOSE is above the prior
  completed UTC day's high (C1, close-confirm).
* ENTRY: next H1 bar open, fill = open + 0.9 pip spread (+ stress slip
  0.5 pip per side).
* INITIAL STOP: fill - 1.0 x ATR14(signal bar), active from the fill;
  the entry bar can stop out (conservative fills).
* TRAIL: D2 daily chandelier — until the first completed UTC day boundary
  after entry only the initial stop is active; from the first bar of the
  next completed day, trail = max(daily high of completed days since
  entry) - 3.0 x daily ATR14(last completed day), never below the initial
  stop; ATR14 = Wilder RMA on completed UTC days.
* MAX HOLD: 48 H1 bars, time exit at bar close.
* One position at a time, no same-bar re-entry, days with < 4 H1 bars
  skipped. Costs: one spread round-trip (stress: + 0.5 pip/side).

## Why NOT include the pyramid (B1_P075)

The pyramid was validated with STRICT V1 layer exits (1 ATR stop / 3 ATR
trail per layer). Combining it with the D2 exit would require re-specifying
layer management (a rule that was never tested) — the composite must be the
direct product of independently validated components. Pyramiding remains a
validated standalone component (FX_PDH_002B, kept in the vault as research),
NOT part of the frozen composite.

## Commitment

This composite is run ONCE. If it fails to improve FX_PDH_001 on the
primary criteria (section 20), the lab reports the component findings only
(FX_PDH_002_COMPONENT_FOUND) and freezes nothing. No second composite, no
rescue, no parameter adjustments after seeing the composite PnL.
