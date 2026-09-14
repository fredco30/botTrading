# LEGACY_REVERSE_M1 — REPORT

Spec: `LEGACY_REVERSE_M1_FROZEN_SPEC.md` (frozen + committed BEFORE any outcome).
Data: Dukascopy EURUSD ticks 2010-2018 only (108 SHA256-verified partitions,
209,682,628 ticks). 2019_PLUS_ACCESSED=NO · PROTECTED_OOS_ACCESSED=NO ·
OPTIMIZATION_EXECUTED=NO.

## 0. Canonical source signal verification (mission §2)

`m1_engine.py` reused unmodified. Regenerated streams match the frozen prior
CSVs row-by-row: baseline 428 trades, pyramid 428, BASE_SIGNAL_IDENTITY PASS,
TRADE_STREAM_MATCH PASS, TRADE_ACCOUNTING PASS. Prior result re-confirmed:
historical PF 0.8726, E[R] −0.0525R; realistic PF 0.7475, E[R] −0.1345R.

## 1. Forensic recovery (mission §1)

- **Test01** = initial revision `294001e` (blob `e63df9e`): reverse on EVERY L0
  stop close with pnl<=0; no consec-loss gate, no hour block, no SL filter,
  RevLotMult=1.0, swing SL ±2 pips (3 M15 bars), TP=2.5R, BE 1.5R live.
  Fingerprints from `...Test01_16ans.txt` (811 trades = claim; 199 same-tick
  reverses at hours 02-21) prove the unfiltered revision.
- **Test04** = UNCOMMITTED intermediate between `fcf0e1a` and `69b736d`
  (closest committed ancestor `fcf0e1a`, blob `b182909`): fingerprints prove
  `RevMinConsecLosses=3` active (first L0 reverse exactly at 3rd consecutive
  loss) AND toxic-hour block absent (reverses at 13h, 14h, 17-21h) AND L2
  reverses unconditional AND RevLotMult=2.0 (2% risk arithmetic). No committed
  revision has this combination — documented honestly.
- Historical claims (Test01 REV PF 1.33 / Test04 REV PF 1.59, 811/802 trades)
  reproduced as claims in the markdown `EMA_Pullback_pyramid_v2_ANALYSIS.md`
  @ `9f11ec8`; trade counts 811/802 match the logs exactly.

## 2. H1 — REVERSE_AFTER_STOP_RAW (Test01 mechanics, tick-realistic)

| Metric | Value |
|---|---|
| ORIGINAL_STOPPED_L0_N | 276 (of 428 baseline trades; 51 BE-positive stops excluded by the EA win rule) |
| N_TRADES | 207 (75.0% of stops reversed; 48 daily-limit skips, 12 invalid swing levels, 9 overlap skips) |
| TRADES_PER_MONTH / YEAR | 1.92 / 23.0 |
| WIN_RATE | 43.96% |
| MEAN_NET_PIPS | **−0.96** · MEDIAN −4.8 · TOTAL **−199.3** |
| PROFIT_FACTOR | **0.914** |
| EXPECTANCY_R | +0.157 · AVG_WIN_R +1.641 · AVG_LOSS_R −1.008 |
| MAX_DRAWDOWN_R / MAX_CONSEC_LOSSES | 26.1R / 9 |
| POSITIVE_YEARS | 5/9 (0.556) |
| REMOVE_BEST_1%_E[R] | +0.122 |
| LONG_E[R] / SHORT_E[R] | +0.162 / +0.150 |
| LATENCY_30S_E[R] | +0.068 (N=209) |
| REALISTIC_STRESS_E[R] | **−0.103** (PF 0.852, WR 25.8%) |
| BOOTSTRAP_CI95_E[R] | [−0.046, +0.352] — includes 0 |
| TIME_STOP_TO_REVERSE_FILL_MEDIAN | 5.38 s (baseline) |
| STOP_TICK_FALLBACK_N | 96/207 (MT4-bar stop not tick-confirmed → bar-end fallback, spec §6) |
| GATE | FAIL: PF<1.20, TOTAL_PIPS<0, POS_YEARS<0.67, STRESS<0 |
| VERDICT | **NO CANDIDATE — GATE_FAIL** |

**Mechanism reading.** The positive E[R] is a risk-denominator artifact, not an
edge: the mean trade LOSES 0.96 pips. Reverses whose swing stop lands close to
entry (small R denominator) produce large +R on tiny pip wins (BE locks at
+1 pip = up to +0.2R on a 4-5 pip risk). In pip space — the space money is
denominated in — the raw reverse has PF 0.91 and loses 199 pips over 9 years.
Under the frozen stress scenario it is negative in both pips and R
(−0.103R, SHORT −0.303R). The 30s-latency pass already halves E[R] to +0.068.

## 3. H2 — DIRECT_SIGNAL_INVERSION

| Metric | Value |
|---|---|
| TRIGGERS / N_TRADES | 428 / 427 (1 NO_FILL) |
| TRADES_PER_MONTH | 3.95 |
| WIN_RATE | 21.31% |
| MEAN_NET_PIPS | **−5.42** · TOTAL **−2313.6** |
| PROFIT_FACTOR | **0.643** |
| EXPECTANCY_R | **−0.264** (CI95 [−0.402, −0.124]) |
| POSITIVE_YEARS | 1/9 |
| REMOVE_BEST_1%_E[R] | −0.297 |
| LONG_E[R] / SHORT_E[R] | −0.274 / −0.254 |
| LATENCY_30S / STRESS_E[R] | −0.282 / −0.330 |
| ORIGINAL vs INVERTED E[R] | −0.0525 vs −0.2642 |
| CORRELATION_ORIG_VS_INV | Pearson −0.341 · Spearman −0.282 (n=427) |
| GATE | FAIL (9 of 10 criteria) |
| VERDICT | **NO CANDIDATE — GATE_FAIL** |

## 4. TEST04_LEGACY (historical benchmark ONLY — contaminated, not eligible)

Reconstructed config: L0 reverse gated at consecLosses>=3 + unconditional L2
reverse + RevMaxSL=25 + RevLotMult=2.0, on the canonical pyramid stream.

| Metric | Value |
|---|---|
| N_TRADES | 93 (70 L0 + 23 L2; 26 RevMaxSL skips, 34 daily skips) |
| WIN_RATE | 53.76% |
| MEAN/TOTAL_NET_PIPS | +2.19 / +203.9 |
| PROFIT_FACTOR | **1.319** (tick-realistic, spread-inclusive) |
| EXPECTANCY_R | +0.427 · CI95 [+0.102, +0.738] |
| POSITIVE_YEARS | 6/9 (0.667) |
| REALISTIC_STRESS | E[R] **+0.197**, PF 1.532 (N=92) |
| HISTORICAL_CLAIM_REPRODUCED | **PARTIAL**: directional PF>1 confirmed, but the claimed 1.59 (bid-only MT4, 2010-2026, 127 L0 reverses) degrades to 1.32 under 2010-2018 tick-realistic execution with ~30% fewer reverses. The survival under stress (+0.20R) is consistent with the historical claim being partly real but flattered by execution assumptions and window selection. Contaminated by prior optimization → cannot prove an edge. |

## 5. IS_THE_EMA_SIGNAL_ANTI_PREDICTIVE = **NO**

1. **Direct test:** if the signal contained negative predictive information,
   flipping it would print money. It does the opposite: inverted E[R] = −0.264
   vs original −0.0525 — five times WORSE, CI95 entirely negative, 1 positive
   year in 9, WR collapses 35.5% → 21.3%.
2. **Breakeven arithmetic:** at 2.5R payout the breakeven WR is 28.6%. The
   original sits at 35.5% gross-of-costs (its losses come from costs, asymmetric
   BE management and gap fills), the inverse at 21.3%. Neither side of the coin
   is predictive — the signal is close to uninformative, not informative-inverted.
3. **Geometry, not information:** original entries follow a pullback-rejection
   bar WITH the H1 trend, stop behind the swing. The inverted trade opens the
   opposite position at the same price with the mirrored stop — which places the
   stop INSIDE the direction of prevailing momentum. Its 78.7% stop rate is a
   structural property of that geometry, not evidence of anti-prediction.
4. **Correlation confirms partial asymmetry:** original-vs-inverted outcome
   correlation is only −0.34 (Pearson). Perfect anti-prediction would approach
   −1 with inverted E[R] ≈ +2.5R-breakeven-adjusted positive. It is nowhere close.
5. **H1 is the §19 cautionary tale in vivo:** PF/E[R] asymmetries manufactured by
   stop-distance heterogeneity (E[R] +0.16 with negative mean pips) look like
   information and are not: latency halves them and stress flips them negative.

## 6. Tests & CI

- `test_legacy_reverse_m1.py`: 29 synthetic checks PASS (trigger rules, EA win
  rule, T4 gates, 5s/30s delays, LONG-ASK/SHORT-BID, exit sides, gap-through,
  target cap, BE live/lock/gap, slippage, inversion mirrors, swing construction
  incl. forming-bar roll, no-cascade, daily limit, 2019+/pre-2010/partition
  guards, prior EMA replication suite).
- Wired into `.github/workflows/research-engine-tests.yml` (unittest discovery,
  2 tests collected). CI link to be confirmed on GitHub after push (below).

## 7. Audit (mission §20)

`audit_legacy_reverse_m1.py` — independent scalar reimplementation reading the
FROZEN prior CSVs (not the engine) and per-tick loops (not vectorized):
**H1 40/40 exact · H2 40/40 exact · T4 20/20 exact** (timestamps, sides, fills,
stops, targets, exits, pips, R). Two audit-side bugs were found and fixed during
reconciliation (tuple unpack order; rounded-CSV tolerances); no engine defect
surfaced.

## 8. Verdict

**NO_REVERSE_EDGE** — neither H1 nor H2 passes the frozen economic gate.
Test04 remains a contaminated benchmark (PF 1.32 realistic vs 1.59 claimed).
The historical "reverse is a real edge" claim does not survive: the raw
mechanism loses pips, degrades under latency and turns negative under realistic
stress; the direct inversion is strongly negative. Per mission §22: STOP — no
H3, no optimization, no V1.
