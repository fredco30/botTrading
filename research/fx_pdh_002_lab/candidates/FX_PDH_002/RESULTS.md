# FX_PDH_002 — RESULTS (frozen, 2020-2025, 2026 sealed)

Candidate: C1 close-confirm entry + D2 daily-chandelier exit on USDJPY H1.
One pre-registered composite run (see `../FX_PDH_002_COMPOSITE_PREREG.md`).

## Headline vs the frozen baseline FX_PDH_001 STRICT V1

| metric (NORMAL) | FX_PDH_001 | FX_PDH_002 | delta |
|---|---|---|---|
| N trades | 639 | 517 | -19% |
| trades/week | 2.04 | 1.65 | credible |
| net pips/trade | +4.90 | **+8.43** | +72% |
| expectancy (R) | 0.367 | **0.619** | +69% |
| profit factor | 1.379 | **1.573** | +14% |
| win rate | 28.3% | 23.2% | fewer, much bigger winners |
| t-stat | +2.52 | **+3.13** | +24% |
| remove-best-1% (pips/trade) | +2.54 | **+5.59** | half the tail dependence |
| STRESS net pips/trade | +3.82 | **+6.63** | +74% |
| STRESS PF | 1.285 | **1.433** | |
| STRESS rb1 | +1.48 | **+3.81** | |
| 2022 share of profit | 61.2% | **30.5%** | regime dependence halved |
| EUR500@0.5% ending equity | 943 | **1145** | |
| max drawdown | 15.0% | **6.7%** | -56% |
| max DD (R) | 47.4 | 27.9 | -41% |

## By year (net pips/trade, NORMAL — every year positive)

| year | 001 | 002 |
|---|---|---|
| 2020 | -0.17 | **+4.48** |
| 2021 | +5.01 | **+9.39** |
| 2022 | +18.78 | **+14.46** |
| 2023 | +5.75 | **+12.75** |
| 2024 | -1.14 | **+5.14** |
| 2025 | +1.78 | **+3.65** |

STRESS by-year is positive in all six years as well
(2020 +3.10, 2021 +8.74, 2022 +13.82, 2023 +8.89, 2024 +2.72, 2025 +2.24).

## EUR 500 survival gates (NORMAL; STRESS in parentheses)

| gate | value | limit | status |
|---|---|---|---|
| ending equity | 1144.6 EUR (1032.0) | > 250 | PASS |
| max DD | 6.68% (8.25%) / 61.9 EUR | < 30% warn, < 50% veto | PASS |
| worst single year | +5.3% (+4.3%) | > -40% veto | PASS |
| worst rolling 12m | -4.2% (-7.0%) | > -40% veto | PASS |
| max losing streak | 23 (30) trades | informational | - |
| peak leverage | 13.5x (tight-stop trade early, fixed 0.5% sizing, same convention as 001) | informational | - |
| peak margin @1:30 | 224 EUR | < equity | PASS |

VETO: none. WARN: none. The 23-trade losing streak (23.2% win rate) is the
price of the 9R+ runner capture profile; its EUR damage is capped by the
1-ATR stops (max DD 6.7%).

## Honesty record

* Internal research only. Across the lab, 16 meaningful variants/cells were
  run (1 mirror, 8 pyramid cells, 3 entry, 3 exit) plus this single
  composite; the frozen candidate descends from the surviving branch
  (B: 3/8, C: 1/3, D: 2/3). Selection effects exist and only the sealed
  2026 test is decisive.
* 2026_ACCESSED = NO. The final external evaluation must compare frozen
  FX_PDH_001 and FX_PDH_002 on the same untouched 2026 period.
* FX_PDH_001 remains in the vault unchanged (git-diff-tested).
