# FX_PDH_002 LAB — RESULTS SUMMARY

FINAL_STATUS = **FX_PDH_002_FROZEN_CANDIDATE**
FX_PDH_002_FREEZE_SHA = `dc7322b4d2154b267a2b852657c408c35ff43aed`
Branch `research/fx-pdh-002-lab` (from authoritative state `617f9b1`).
2026_ACCESSED = NO (every load through the tmlab hard seal).

## Baseline

FX_PDH_001 STRICT V1 (vault, untouched, git-diff-tested): N=639, 2.04
trades/week, PF 1.379, +4.90 pips/trade, stress +3.82, rb1 +2.54, t +2.52,
EUR500 -> 943 (dd 15.0%), 2022 = 61.2% of profit.

## Phase 0 — diagnostic (no filtering)

Runners (top net-R decile) are made by MULTI-DAY CONTEXT, not bar shape:
prior-1d return rho +0.41 (median +98 vs +30 pips), narrower prior-day
range, and in 2022 specifically a high-volatility trending regime (ATR
percentile 0.82 vs 0.56; +237-pip 5d context). Runners exist in every year
(7-17 per year). Lifecycle: winners' median MAE -0.48R vs losers -1.31R;
49% of trades touch +1R; the 3-ATR trail is what converts ~9R MFEs into
profit. => the edge is trend-run capture: exit and pyramiding research
attack the mechanism; entry timing barely matters.

## Phase A — 002A exact SHORT mirror: DEAD

N=563, NORMAL net -0.24 pips/trade (PF 0.984, rb1 NEGATIVE -3.78), stress
-1.70 (PF 0.889), EUR500 537 (dd 23.7%). The long-only asymmetry is real;
no rescue attempted (pre-registered).

## Phase B — 002B pyramiding: 3_OF_8 cells survived

B1 (R-momentum adds), B2 (H1-continuation adds), B3 (pullback-reclaim adds)
pass under both risk caps; B4 (day-persistence adds) FAILS outright (its
adds lose money standalone; stress rb1 negative; 103% of profit from 2022).
Best trade-off: B1_P075 — PF 1.478, +8.27 pips/group, dd 10.6%, the ONLY
cell positive in all six years, adds contribute +2154 pips of their own
edge. Validated as a component; NOT folded into the frozen composite
(layer exits were only validated under strict trails).

## Phase C — 002C entry quality: 1_OF_3 survived

C1 close-confirm (first H1 CLOSE above PDH): PF 1.424, +5.47 pips/trade,
dd 10.3%, 2022 share 48.6% at ~equal total profit — a quality improvement.
C2 close-retest and C3 strong-break(>=0.70) FAIL (weaker t/rb1/stress,
frequency collapse).

## Phase D — 002D exit architecture: 2_OF_3 survived

D2 daily chandelier: PF 1.517, +7.66 pips/trade, t 3.11, rb1 4.98, stress
6.52, dd 12.7%, 2022 41.1%. D1 slower trail (4.5 ATR): PF 1.464, t 2.89.
D3 5-bar structure exit: DEAD (PF 1.078, stress -0.09 — chops the runners).

## Composite (ONE pre-registered run) — FX_PDH_002 FROZEN

C1 entry + D2 exit (pyramid deliberately excluded):

| metric | 001 | 002 |
|---|---|---|
| N / trades-per-week | 639 / 2.04 | 517 / 1.65 |
| net pips/trade | +4.90 | **+8.43** |
| expectancy R | 0.367 | **0.619** |
| PF | 1.379 | **1.573** |
| t-stat | +2.52 | **+3.13** |
| remove-best-1% | +2.54 | **+5.59** |
| STRESS pips/trade | +3.82 | **+6.63** |
| EUR500 @0.5% | 943 | **1145** |
| max DD | 15.0% | **6.7%** |
| 2022 profit share | 61.2% | **30.5%** |
| years negative | 2020, 2024 | **none** |

EUR500 gates: no VETO, no WARN (worst year +5.3%, worst rolling 12m -4.2%,
max losing streak 23, peak leverage 13.5x on the fixed-0.5% sizing
convention, margin @1:30 max 224 EUR).

## Honesty / multiple testing

16 meaningful cells were run in total (1 mirror, 8 pyramid, 3 entry,
3 exit) plus 1 composite. The frozen candidate descends from the surviving
branch: 1_OF_1 mirror DEAD, 3_OF_8 pyramid, 1_OF_3 entry, 2_OF_3 exit,
1_OF_1 composite PASS. FX_PDH_002 is INTERNAL research — its edge estimate
carries selection bias; only the sealed 2026 comparison against FX_PDH_001
on the same untouched period is decisive.

Caveats carried forward: (i) pyramid caps bound decision-time risk; ATR
expansion can drift open risk higher between decisions (peak 8.64 EUR on
B1_P075, ~1.7% of initial capital); (ii) stress runs re-simulate the whole
engine (643/524 marginal fills differ from NORMAL by the frozen
convention); (iii) group-level rb1 is not directly comparable to
trade-level rb1 across cost scenarios.

## Artifacts

`RESEARCH_PROTOCOL.md` (pre-registrations) ·
`FX_PDH_001_DIAGNOSTICS.md` · `EXPERIMENT_LEDGER.csv` ·
`002A_short/ 002B_pyramid/ 002C_entry/ 002D_exit/` (JSON + CSVs) ·
`FX_PDH_002_COMPOSITE_PREREG.md` ·
`candidates/FX_PDH_002/` (FROZEN_SPEC.md, RESULTS.json, RESULTS.md, code,
tests — `pytest candidates/FX_PDH_002/tests` green; lab engine tests green).
No market data committed.
