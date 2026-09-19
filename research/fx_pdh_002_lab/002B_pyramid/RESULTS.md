# FX_PDH_002B — PYRAMIDING RESULTS (8 pre-registered cells)

Reference FX_PDH_001 (base alone): 639 trades, +4.90 pips/trade, PF 1.379,
rb1 +2.54, stress +3.82, EUR500 -> 943 (dd 15.0%), 2022 = 61.2% of profit,
year sums (pips): 2020 -16 | 2021 +318 | 2022 +1192 | 2023 +365 | 2024 -136
| 2025 +180.

Invariant: BASE layer trade set == frozen 001 trade-for-trade (tested).
Sizing: every layer targets 0.5% of FIXED EUR 500 (floor 0.01 lots); adds
truncated to remaining capacity; cap = policy % of CURRENT equity at the
add decision close. One add per bar max; base must still be open; stops
never widened.

## Cells (NORMAL costs; group = base entry + its adds)

| cell | adds fired | net pips | pips/grp | PF | rb1 | stress pips/grp | EUR500 | dd% | 2022% | verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| B1_P075 | 258 / 183 | +5285 | +8.27 | 1.478 | +2.65 | +6.25 | 1273 | 10.6 | 59.7 | PASS |
| B1_P100 | 260 / 184 | +5309 | +8.31 | 1.475 | +2.68 | +6.42 | 1300 | 10.7 | 59.4 | PASS |
| B2_P075 | 272 / 233 | +5642 | +8.83 | 1.465 | +3.26 | +6.13 | 1323 | 13.2 | 62.7 | PASS |
| B2_P100 | 275 / 240 | +5323 | +8.33 | 1.427 | +2.74 | +5.76 | 1316 | 14.1 | 64.1 | PASS |
| B3_P075 | 212 / 143 | +4792 | +7.50 | 1.444 | +3.23 | +5.02 | 1205 | 11.6 | 52.6 | PASS |
| B3_P100 | 213 / 149 | +4640 | +7.26 | 1.423 | +2.99 | +5.08 | 1217 | 11.9 | 52.3 | PASS |
| B4_P075 | 159 / 43  | +2750 | +4.30 | 1.314 | +0.66 | +2.91 (rb1 -0.69) | 896 | 13.2 | 74.0 | FAIL |
| B4_P100 | 159 / 44  | +2579 | +4.04 | 1.295 | +0.39 | +2.69 (rb1 -0.92) | 880 | 13.4 | 74.0 | FAIL |

STRESS runs (0.5 pip/side) re-simulate the whole engine per the frozen
convention (643 groups, marginal fills/stops differ); every cell stays
positive and PF > 1.18 except B4 whose stress rb1 is NEGATIVE.

3_OF_8_VARIANTS_CLEANLY_SURVIVED (B1, B2, B3 under both caps); B4 failed
(its adds lose money standalone: ADD1 -156 pips / ADD2 -224 pips in B4_P075
and the whole cell leans 103% on 2022).

## Incremental contribution (NORMAL, P075)

| arch | BASE pips | ADD1 pips | ADD2 pips | adds EUR |
|---|---|---|---|---|
| B1 | +3130 | +1874 | +280 | +330 |
| B2 | +3130 | +1957 | +555 | +380 |
| B3 | +3130 | +1262 | +400 | +262 |
| B4 | +3130 | -156  | -224 | -47   |

Both add levels are positive for B1/B2/B3 — the adds carry their own edge
(they are independent STRICT positions taken only in confirmed runs), they
do not just re-leverage the base.

## By-year group sums (pips, NORMAL P075)

| year | 001 base | B1 | B2 | B3 | B4 |
|---|---|---|---|---|---|
| 2020 | -16 | +22 | -87 | +221 | -235 |
| 2021 | +318 | +835 | +848 | +753 | +260 |
| 2022 | +1192 | +3154 | +3539 | +2520 | +2034 |
| 2023 | +365 | +353 | +592 | +1034 | +694 |
| 2024 | -136 | +173 | -401 | -75 | +171 |
| 2025 | +180 | +747 | +1152 | +338 | -174 |

Protocol section 19 focus years: B1 turns ALL THREE weak years positive
(2020 +22, 2024 +173, 2025 +747) — the only architecture with every year
positive. B3 improves 2020/2023 strongly but keeps 2024 slightly negative.
B2 amplifies 2022 most (the failure mode section 19 warns about).

## Risk behaviour

* Worst-case open risk is capped AT EVERY ADD DECISION: risk-after <=
  policy% of CURRENT marked equity (verified per add: max 8.10 EUR at
  equity ~1100+ for P075). Because the policy is on current equity, the
  same decision allows more absolute EUR later (anti-martingale
  compounding); vs the FIXED initial 500 the peak decision-time risk is
  ~1.6%.
* Peak open risk AFTER decisions drifts slightly higher (B1_P075: 8.64 EUR
  = 1.7% of initial 500) because ATR expansion can pull an existing trailed
  stop back to its initial level between decisions. This is inherent to
  trailing-stop accounting, not a cap breach.
* Peak notional 9,000 units (0.09 lots) -> ~6x leverage on grown equity,
  margin at 1:30 well under equity. No veto/warn gates tripped anywhere.
* Worst group loss -8.1 EUR (B1_P075), worst calendar day -10.2 EUR.

## Verdict (pre-registered rule)

Pyramiding ACCEPTED as a component: B1/B2/B3 improve return AND
risk-adjusted quality (PF 1.42-1.48 vs 1.379, rb1 up, stress expectancy up,
dd DOWN 10.6-13.2% vs 15.0%, EUR500 ending equity 1205-1323 vs 943).

Validated pyramid architecture for any composite: **B1_P075** — chosen on
the protocol's own multi-dimensional criteria (only all-years-positive
cell, lowest max DD 10.6%, best stress pips/grp 6.25, first-registered
architecture; no post-hoc threshold search). B3_P075 is the runner-up
(lowest 2022 dependence, 52.6%). B4 is DEAD.
