# RATES-MACRO-M1 — Cross-Market Discovery Report

NFP/CPI → US Treasury futures (ZF/ZN) 1-minute repricing → delayed EURUSD
adjustment. Discovery window 2010-06-07 → 2019-01-01 (2019+ never accessed;
protected OOS never accessed; V1 never opened).

## Provenance

| item | value |
|---|---|
| BASE_HEAD | `7c63937670e30a5cfb41362455700b233917d43b` (research/rates-data-m0) |
| MACRO_SOURCE_SHA | `f89623096e36a12a98f3aaa23f1217dc245bfa9745cc46d4a6c1b6b4e3a2e418` (blob from commit `f968f4a`, copied verbatim) |
| FROZEN_SPEC_COMMIT | `ab05ff3` — committed BEFORE any outcome computation |
| Rate data | Databento `GLBX.MDP3` ohlcv-1m ZT/ZF/ZN, unadjusted (RATES-DATA-M0) |
| FX data | EURUSD BID/ASK ticks, month partitions 2010-01..2018-12 |

## Event funnel

205 NFP/CPI events (102 NFP / 103 CPI; FOMC excluded; all EXACT_SCHEDULE_PAGE
+ ALIGNED + minute-aligned) → 192 events pass all validity gates (roll guard,
rate window/gap guards, baselines, FX refs) → **142 qualifying
PRIMARY_RATE_SHOCKs** (ZF/ZN same non-zero sign, both RATE_SCORE ≥ 2.0).
Mean qualifying scores: ZF 12.9, ZN 11.2. ZT diagnostic: available 77.5% of
shocks, confirmed the primary direction 71.1% (diagnostic only — never gates
anything).

## Verdicts (pooled NFP+CPI)

| metric | A 1M_REPRICING_CONT | B FX_LAG | C DISAGREEMENT_REV |
|---|---|---|---|
| N_TRADES | 135 | 13 | 0 |
| NET_MEAN_PIPS | +0.10 | −0.68 | n/a |
| PROFIT_FACTOR | 1.01 | 0.83 | n/a |
| EXPECTANCY_R | +0.026 | −0.156 | n/a |
| POSITIVE_YEARS / ELIGIBLE | 4 / 9 | 2 / 3 | n/a |
| REMOVE_BEST_1PCT | −0.99 | −2.15 | n/a |
| STRESS_050_MEAN | −0.90 | −1.68 | n/a |
| NFP_MEAN (PF) | −1.58 (0.88) | +1.39 (1.43) | n/a |
| CPI_MEAN (PF) | +2.48 (1.39) | −4.00 (0.25) | n/a |
| CI95_MEAN_NET | [−4.39, +4.47] | [−4.83, +4.31] | n/a |
| **VERDICT** | **REJECT** | **REJECT** | **REJECT** |

- A: `REMOVE_BEST_1_PERCENT = −0.99 ≤ 0` ⇒ fail-fast REJECT (independence
  fails: the entire pooled edge is the single best trade). Additionally
  NFP mean ≤ 0 (−1.58) while CPI mean > 0 — a pooled PASS is impossible by
  §20, and the CI straddles zero.
- B: NET_MEAN ≤ 0 and PF ≤ 1.0 ⇒ REJECT. Eligibility collapsed: in 127 of
  142 shocks EURUSD's first-minute move already exceeded the pre-release
  FX_Q95 — "FX has not yet moved abnormally" almost never happens at NFP/CPI.
- C: zero trades. In 123 of 142 shocks EURUSD moved WITH the rate-implied
  direction (no disagreement); 3 disagreements were too small; the 10 real
  opposite-direction disagreements all died at NO_TRADE_TARGET_ALREADY_
  CROSSED / stop-validity checks. The FX market has already digested the
  rates signal by the end of the first minute.

## Exit / robustness detail (A)

66 STOP / 27 TARGET / 42 TIME; win rate 41.5%; avg win +25.0 vs avg loss
−17.5 pips; max DD 243 pips; max 5 consecutive losses. Under +0.25 pip/side
slippage the mean is already negative — no execution stress level rescues it.

## Tests

- New synthetic suite `test_rates_macro_m1.py`: **84/84 green** (causality,
  roll/gap guards, Q95 baselines, mappings, A/B/C rules, latency, sides,
  overshoot/cap, stress arithmetic, 2019 cut, OOS guard, gates).
- Existing suites re-run locally: RATES-DATA-M0 **13/13** (pytest),
  MTF-M1 **39/39**, TICK-M1 **22/22**, TICK-M0 **18/18**.
- CI: `research-engine-tests` workflow extended with RATES-DATA-M0 (pytest)
  and RATES-MACRO-M1 steps — both suites now actually run in CI.

## Independent real-data audit (§26)

`audit_rates_macro_m1.py` — a separate pandas implementation that imports
nothing from the engine library — re-derived official T0, ZF/ZN raw
contracts (via roll_map date intervals), PRE_CLOSE/POST1_CLOSE, rate
moves/scores, direction, FX_P0/P1, entry timestamp/side/price, stop, target,
exit timestamp/reason/price and net pips for **12 A trades and all 13 B
trades** (C has no trades): **500 exact checks, 500 passed, 0 failed**
(`rates_macro_m1_audit.json`, AUDIT_PASS).

## Conclusion

**NO_RATES_MACRO_CANDIDATE — STOP.**

Under the frozen 2010-2018 discovery sample, the immediate ZF/ZN repricing
after NFP/CPI does NOT contain exploitable delayed information for EURUSD:
by the time the event minute completes (the earliest causal decision time),
EURUSD has already moved in the rate-implied direction and by an
above-normal amount in ~90% of qualifying shocks. Per §24 there is no rescue
analysis, no optimization, no variant; V1 is not opened.

DO NOT MERGE this PR.
