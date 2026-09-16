# FX_CROSS_ASSET_RELATIVE_VALUE_M1 — FINAL REPORT

Branch research/fx-macro-rates-swing-m1. MR_E017 archived untouched (no
validation continued, no 2019+ ZN purchased, no parameter variants).
All 2010-2018 data treated as research data in sequential folds
(DISCOVERY 2010-06..2014-12, VALIDATION 2015-16, REPLICATION 2017-18).
Budget: 25 experiments / 8 families (of 10/60). 2019+ never accessed.

## Result

**NO_USEFUL_CROSS_ASSET_FX_CANDIDATE.**

No continuous mechanism reached the pre-registered usefulness bar
(>= 2 trades/week pooled WITH positive net expectancy after costs).
The two families with genuine economic edge are frequency-bound:

| mechanism (discovery fold, 3 pairs pooled, modeled exec) | N | /wk | mean | PF | expR | stress |
|---|---|---|---|---|---|---|
| A residual CONTINUATION z>=1.5, H4/24h | 184 | 0.77 | +5.38 | 1.323 | +0.047 | +4.48 |
| A residual continuation z>=1.0 | 348 | 1.46 | -0.35 | 0.983 | -0.006 | -1.44 |
| A residual continuation z>=0.75 | 457 | 1.92 | -2.83 | 0.875 | -0.026 | -3.83 |
| A continuation z>=1.5, H1/8h | 369 | 1.55 | -1.30 | 0.902 | -0.004 | -2.22 |
| A residual FADE z>=1.5 (MR_E017-direction, continuous) | 184 | 0.77 | -7.59 | 0.67 | -0.072 | -8.70 |
| D partial adjustment 1.0 sigma, H4/24h | 109 | 0.46 | +9.35 | 1.465 | +0.089 | +8.50 |
| D relaxed 0.75 sigma / phi 0.6 | 165 | 0.69 | +6.87 | 1.350 | +0.065 | +6.00 |
| D partial adjustment, H1/8h (1.0 / 0.75) | 235/354 | 0.99/1.48 | -0.39/-0.83 | 0.97/0.94 | neg | neg |

Rejected at screen (frequent but negative after costs): B curve slope/level
(3 cells, PF 0.90-0.99 at 4.5-6.8/wk), C common-USD lag (PF 0.87 at 3.0/wk),
E dynamic-beta regime (0.85), H response speed (0.90 at 7.6/wk),
F slope+pullback (0.90), G cross-pair residual ranking (0.74).

## Interpretation

The monotone decay is the key scientific finding: rates/FX residual and
partial-adjustment information EXISTS on 2010-2018 (H4, selective cells are
solidly positive and stress-positive) but it is concentrated in the sparse
tail of the signal distribution. Diluting selectivity to reach the required
2-5 trades/week consumes the edge entirely; at H4-scale costs (0.6-1.0 pip
spread, +0.5 pip stress) the continuous core of the distribution is flat to
negative on every family tested. This is consistent with the earlier
multipair and MR_E017 results: US rates information reaches FX quickly
enough that only genuinely selective configurations retain net value.

No parameter rescue was attempted on A-cont/D (their low-frequency cells
are NOT MR_E017 variants and still fail the frequency gate; their
high-frequency cells fail economics). No internal validation/replication
folds were consumed because no screen survivor existed to advance.

```
FX_CROSS_ASSET_RELATIVE_VALUE_M1

EXPERIMENTS=25
FAMILIES=8 (A,B,C,D,E,F,G,H; I/J not opened)

TOP_CANDIDATE=none
MECHANISM=A-residual-continuation / D-partial-adjustment: economically
  positive only at 0.46-0.77 trades/week pooled (below the >=2/wk gate);
  monotone decay to ~0/negative as threshold relaxes toward the gate

DISCOVERY_2010_2014: best cells as table above (none pass frequency gate)
VALIDATION_2015_2016: not consumed (no survivor)
REPLICATION_2017_2018: not consumed (no survivor)
PAIR_BREAKDOWN: negative families negative across pairs; no pair-specific
  artifact involved in the verdict
PLATEAU=threshold axes decay monotonically (A-cont: PF 1.323 -> 0.983 ->
  0.875; D: 1.465 -> 1.350 -> H1 0.97) — no plateau at useful frequency
SURVIVAL_500EUR: not applicable (no candidate)
2019_PLUS_ACCESSED=NO
MR_E017_RESCUED=NO

FINAL_STATUS=NO_USEFUL_CROSS_ASSET_FX_CANDIDATE
STOP.
```
