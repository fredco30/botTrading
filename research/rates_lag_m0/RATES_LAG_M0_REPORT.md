# RATES-LAG-M0 — REPORT

Generated: 2026-09-14. Branch `research/rates-lag-m0`, parent `968a0e4`
(`research/rates-event-hires-m1`). Spec: `RATES_LAG_M0_FROZEN_SPEC.md` (committed
before any outcome was computed).

## Question

Does the Treasury-futures reaction to NFP/CPI leave an economically meaningful
EURUSD move that is still exploitable at realistic non-HFT delays
(decision at T0+10s / +30s / +60s, entry decision+1s or +5s, 120s frozen exit)?

## Funnel

| Stage | Count |
|---|---|
| M1 manifest events (NFP+CPI) | 205 |
| ZF ok AND ZN ok (universe) | **200** (100 NFP, 100 CPI) |
| excluded | Good Friday 2017 (EXPECTED_MARKET_CLOSED), 2014-10-03 NFP (CONFIRMED_DATA_GAP), 3 ZN-only zero_records |
| H10 rate signals / trades / no-fill | 175 / 174 / 1 |
| H30 rate signals / trades | 182 / 182 |
| H60 rate signals / trades | 183 / 183 |

Rate signal = ZF and ZN mid move (ts_recv causal windows, PRE strictly before T0,
LAST obs in [T0, T0+H]) in the SAME direction with |move| >= 1 definition tick each
(ZF 0.0078125 = 1/128, ZN 0.015625 = 1/64, resolved from Databento instrument
definitions for all 70 raw contracts, cached in `instrument_tick_sizes.json`).
Cross-check: data-derived min |Δmid| is half the definition tick (ZF 1/256) because
the mid of a 1-tick-wide spread lands on the half-grid — consistent with the
definitions, and the guard correctly uses the full definition tick.

## Results (baseline = decision+1s entry, real historical spread, +120s exit)

| Metric | H10 | H30 | H60 |
|---|---|---|---|
| RATE_SIGNALS | 175 | 182 | 183 |
| N_TRADES | 174 | 182 | 182 |
| NET_MEAN_PIPS | +0.319 | **+1.584** | +0.798 |
| MEDIAN_NET_PIPS | +1.55 | +1.05 | +0.70 |
| TOTAL_NET_PIPS | +55.5 | +288.3 | +146.1 |
| WIN_RATE | 0.563 | 0.538 | 0.535 |
| PROFIT_FACTOR | 1.056 | **1.324** | 1.176 |
| POSITIVE_YEARS / ELIGIBLE | 5/9 | 6/9 | 5/9 |
| REMOVE_BEST_1PCT_MEAN | −0.223 | +0.864 | +0.171 |
| LATENCY_5S_MEAN | −0.072 | **+1.156** | +0.867 |
| SLIPPAGE_050_MEAN | −0.681 | +0.584 | −0.202 |
| SLIPPAGE_100_MEAN | −1.681 | −0.416 | −1.202 |
| REALISTIC_STRESS_MEAN | −1.072 | **+0.156** | −0.133 |
| NFP_MEAN / PF | −0.685 / 0.92 | +2.059 / 1.31 | +1.397 / 1.24 |
| CPI_MEAN / PF | +1.527 / 1.56 | +1.066 / 1.37 | +0.166 / 1.05 |
| BOOTSTRAP_CI95_MEAN | [−2.15, +2.66] | [−0.74, +4.11] | [−1.17, +2.84] |
| MTM +30s / +60s / +300s (diag) | −0.01 / +0.29 / +1.82 | +0.27 / +1.83 / +1.62 | +1.07 / +1.11 / +1.43 |

## Economic gate (section 14)

- **H10: FAIL** — mean < 2.0, PF < 1.20, year ratio 0.556, remove-best < 0,
  latency-5s < 0, realistic stress < 0, NFP mean < 0. Seven of ten criteria fail.
- **H30: FAIL (materially close)** — meets N_TRADES (182), PF (1.324), TOTAL
  (+288.3), year ratio fails marginally (6/9 = 0.6667 < 0.67), remove-best
  (+0.864), latency-5s (+1.156), realistic stress (+0.156), NFP (+2.059) and CPI
  (+1.066) all positive; fails NET_MEAN_PIPS (+1.584 < +2.0). Two of ten
  criteria fail, both narrowly. CI95 includes 0 (diagnostic, not mandatory).
- **H60: FAIL** — mean < 2.0, PF < 1.20, year ratio 0.556, realistic stress < 0.

## Signal stability (diagnostic only)

H10→H30 same direction 94.0% (167 common), H30→H60 97.1% (171), H10→H60 93.3%
(165). The Treasury signal is directionally persistent across horizons; what
decays is the exploitable EURUSD residual, which the frozen 120s exit captures
as ~+1.6 pips mean at H30 — real but below the +2.0 promotion threshold, and
almost entirely consumed (+0.16) by 0.5 pip/side adverse slippage on the slow
path.

## Independent audit (section 19, triggered by H30 proximity)

`audit_rates_lag_m0.py` re-derived 40 H30 trades (evenly spaced over the sample)
with a deliberately different implementation (pure Python, no shared library
code, linear scans, independent timestamp parsing and parquet reads). Fields
re-derived: rate direction, PRE/H horizon mids and timestamps, EURUSD entry
side/time/price, exit side/time/price, net pips. Result: **40/40 exact → PASS**
(`rates_lag_m0_audit.json`). The H30 near-miss is a property of the market data,
not an implementation error.

## Feasibility rule (section 15)

No horizon is an ECONOMIC_CANDIDATE. H30/H60 do not pass; H10 does not pass
either (and would be rejected by the retail-feasibility rule regardless).

**RETAIL_FEASIBLE_CANDIDATE = NO**
**FINAL_STATUS = NO_RETAIL_RATES_LAG_CANDIDATE**

Per governance: no V1 opened, no faster-entry variants attempted, no
money-management rescue, PR not merged.

## Data hygiene

2019+ never accessed (hard `assert_discovery_range` guards on every Treasury and
FX read; tested). Protected OOS never accessed. No bulk TBBO/EURUSD data in git;
only tiny artifacts (results/trades/audit JSONs, tick-size map).
