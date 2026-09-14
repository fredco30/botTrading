# LEGACY_REVERSE_M1 — FROZEN SPEC (pre-registration)

Status: FROZEN before any reverse/inversion outcome was computed.
Date frozen: 2026-09-14. Base HEAD: `b51b9f6141dabe89dd029a34cf3a88b81ae7b4e4`.
Scope: strict replication / mechanism study of the two reverse mechanisms of
`EMA_Pullback_pyramid_v2` on the validated 2010-2018 EURUSD Dukascopy tick store.
This is NOT fresh validation; the historical 2010-2026 analysis is contaminated
(previously observed) and is used only as a replication target for Test04.

---

## 1. Exact historical source (forensic recovery)

| Item | Value |
|---|---|
| TEST01_SOURCE_COMMIT | `294001e` — "feat: EMA_Pullback_pyramid_v2 — reverse trade on L0 stop loss" (first committed v2 revision) |
| TEST01_SOURCE_FILE | `EMA_Pullback_pyramid_v2.mq4` |
| TEST01_SOURCE_BLOB | `e63df9e244f76fccc9aec29cd8d4f8e04eec13f5` |
| TEST04_SOURCE_COMMIT | **no committed revision matches exactly** — Test04 was produced by an *uncommitted intermediate* between `fcf0e1a` ("replace UseReverseOnL1 with UseReverseOnL2", blob `b1829097dc8385dc5dd060c05c52ffef5587aa42`) and `69b736d` ("champion — reverse L0+L2 with rolling WR"). Closest committed ancestor: `fcf0e1a`. |
| TEST04_RECONSTRUCTION_EVIDENCE | behavioral fingerprints of `EMA_Pullback_pyramid_v2Test04_16ans.txt` (802 trades = claimed 802): (a) first L0 reverse fires exactly at the 3rd consecutive loss, never at the 2nd → `RevMinConsecLosses=3` gate present; (b) reverses executed at hours 13, 14 and 17-21 (e.g. 2010-12-27 19:01) → toxic-hour block ABSENT (that block exists only in `69b736d`); (c) L2 reverses exist (178 same-tick entries after s/l = 127 L0 + 51 L2 per analysis decomposition); (d) reverse lots = 2% risk → `RevLotMult=2.0`, `UseRevLotFromLevel` absent/not used. |
| Historical claims file | `EMA_Pullback_pyramid_v2_ANALYSIS.md` @ `9f11ec807f8b91440b2c86854920ebaa666bce79` |
| Test01 log | `EMA_Pullback_pyramid_v2Test01_16ans.txt` — 811 trades, 199 same-tick reverse entries after s/l, hours 13-21 present → matches initial revision (reverse on EVERY L0 loss, no hour block, no SL filter, no consec gate). Independently re-derived from the log, not from the markdown. |

### Reverse mechanics confirmed in source (all revisions)

From `ExecuteReverseTrade()` / `CheckPyramidClose()` / `ExecuteTradeReverse()`:

- **Trigger**: a NORMAL trade closes with `pnl <= 0` (EA: `if(pnl>0)` win, else loss branch)
  at pyramid level L0 (Test01: every such loss; Test04: only when `consecLosses >= 3`).
  A close with `pnl > 0` (including a BE stop-out in profit) is a WIN → NO reverse.
  A reverse trade NEVER triggers another reverse (`wasReverse` early-return). Reverse
  closes do not touch the streak, `consecLosses` or the rolling-WR buffer.
- **Direction**: original BUY stopped → open SELL; original SELL stopped → open BUY.
- **Entry timing**: same tick as the stop-out close (market order). MT4 sell enters at BID,
  buy enters at ASK. (This study wraps the entry with a causal delay — §5.)
- **Stop**: Test01/initial revision has NO Min/Max SL filter for reverses.
  SELL reverse: `sl = max(iHigh(M15, 1..SL_SwingBars)) + 2 pips`.
  BUY reverse: `sl = min(iLow(M15, 1..SL_SwingBars)) - 2 pips`.
  `SL_SwingBars = 3`; bars 1..3 = last three CLOSED M15 bars at the reverse moment
  (forming bar excluded). M15 series is BID OHLC (broker chart series).
- **Target**: `TP = entry - MinRR * slDist` (sell) / `entry + MinRR * slDist` (buy),
  `MinRR = 2.5`. `slDist = sl - bid` (sell) / `ask - sl` (buy) at the reverse tick;
  skip if `slDist <= 0`.
- **Breakeven**: LIVE in code and applies to reverse trades (`ManageOpenTrades` normal
  branch): when unrealized move >= `BE_Trigger_R * riskDist` (`BE_Trigger_R = 1.5`),
  SL moves to `openPrice + 1 pip` (buy) / `openPrice - 1 pip` (sell). Replicated.
- **Daily limit**: reverse counts toward `g_dailyTrades`; skipped if the day already
  has `MaxTradesPerDay = 2` trades. Skipped if another trade is open.
- **Risk sizing**: risk-based lots (`RiskPercent = 1.0%`), reverse multiplied by
  `RevLotMult` (Test01: 1.0) or Thursday multiplier x0.5 on Thursdays. Lot size affects
  $ metrics only; all verdict metrics are R- / pip-normalized.
- **L2 reverse** (Test04 only): in the recovered build L2 stop-losses reverse
  unconditionally (the rolling-WR "cold" condition does not exist before `69b736d`).

### TEST01_PARAMETERS (frozen)

```
UseReverseTrade=true  reverse on EVERY L0 stop-loss close (pnl<=0)
UseReverseOnL2=false  RevMinConsecLosses=NONE (feature absent)  RevMaxSL_Pips=NONE
RevLotMult=1.0        RiskPercent=1.0      MaxTradesPerDay=2    MinRR=2.5
SL_SwingBars=3        swing buffer=2 pips  BE_Trigger_R=1.5 (live, applies to reverses)
Toxic-hour skip: ABSENT. Rolling-WR cold filter: ABSENT.
```

### TEST04_PARAMETERS (frozen, reconstructed)

```
UseReverseTrade=true  reverse on L0 stop close (pnl<=0) AND consecLosses>=3
reverse on L2 stop close (pnl<=0), unconditional (no rolling-WR filter)
RevMaxSL_Pips=25.0 (skip reverse if slDist > 25 pips)
RevLotMult=2.0        RiskPercent=1.0      MaxTradesPerDay=2    MinRR=2.5
SL_SwingBars=3        swing buffer=2 pips  BE_Trigger_R=1.5
Toxic-hour skip: ABSENT (fingerprint-proven).
```

Test04 is a HISTORICAL BENCHMARK ONLY (contaminated by prior optimization). It cannot
trigger candidate status and no parameter of H1/H2 is chosen from it.

---

## 2. Canonical source signal (reused, not reimplemented)

- Engine: `research/legacy_bots_m1/m1_engine.py`
  SHA256 `d1da65c4abdbd2b8a591bd6bd6a4e2da938fd04aee82dafc4941f51d3a4083f7` (frozen, unmodified).
- Prior frozen results (re-verified in this session before freezing):
  historical baseline 428 trades, WR 35.51%, PF 0.8726, E[R] -0.0525, SUM_R -22.46;
  realistic 430 trades, PF 0.7475, E[R] -0.1345. BASE_SIGNAL_IDENTITY / TRADE_STREAM_MATCH
  / TRADE_ACCOUNTING all PASS. Expected order of magnitude confirmed (~428-430).
- Canonical stream used by this study = HISTORICAL baseline pass
  (`results_baseline.csv` mode=historical, SHA256
  `f84cef65035aed58b9dcd417569df7faa664830acc0d634ee28a3e7d1d871567`),
  regenerated in-session and diffed against the frozen CSV (must be identical).
- H1 trigger universe: baseline trades with `reason=='sl'` AND `pnl<=0` (EA loss
  semantics). Pre-freeze count from the FROZEN prior stream: 276 triggers
  (51 BE-positive stops excluded per EA win rule; 100 tp + 1 eod excluded).
- Test04 trigger universe: `results_pyramid_safe.csv` mode=historical with level tags:
  L0 stops (pnl<=0) = 182, gated by consecLosses>=3; L2 stops (pnl<=0) = 40.

## 3. Data (frozen)

- Ticks: `E:\ResearchData\botTrading\ticks\parquet\EURUSD\year={Y}\month={MM}\ticks.parquet`,
  108 partitions, 209,682,628 rows, real BID/ASK, UTC ns timestamps.
  Manifest: `research/legacy_reverse_m1/data_manifest.json` (copy of the frozen po3
  manifest, SHA256 `e29806efd95b05ab25a9fdf44bbe0fb56563e20223e28ba3de86af1f0e4a44c0`);
  every partition SHA256-verified at load. Partition guard: year 2010..2018 only.
- Hard UTC guard: all tick access inside [2010-01-01T00:00:00Z, 2019-01-01T00:00:00Z).
  2019+ FORBIDDEN. Protected OOS FORBIDDEN. No new data download.
- M15 bars (signal + swing-stop construction): `research/legacy_bots_m1/data/EURUSD15_2010_2018.csv`,
  SHA256 `a8276a959269b2cae9c45bd26370f51ff96c932c7cbea71a1ebd8b82b59b9bd0`,
  222,613 bars, server time. Server timezone = Europe/Helsinki (EET/EEST, documented
  assumption carried from the prior replication). Server<->UTC conversion via IANA tz.

## 4. H1 — REVERSE_AFTER_STOP_RAW (primary)

- ID: `REVERSE_AFTER_STOP_RAW`. Configuration = Test01 exactly (§1): reverse after an
  original L0 baseline trade exits by STOP with pnl<=0. No L2 reverse, no RevMaxSL
  filter, no consec-loss gate, no hour filter, no new filter of any kind.
- Trigger timestamp: the stop becomes causally known at the first tick at/after the
  canonical exit-bar open where the original trade's stop condition actually holds
  (long: BID <= SL_at_exit; short: ASK >= SL_at_exit; SL_at_exit = original sl0, or the
  BE level entry±1 pip when the prior pass flagged be_moved). That tick is T_stop.
  No future bar knowledge.
- Direction: original long -> reverse SHORT; original short -> reverse LONG.
- Execution baseline: entry ref = T_stop + 5 s; first tick with ts >= ref fills;
  if none within 30 s -> NO_FILL (no trade). LONG reverse fills at ASK, SHORT at BID.
- Stop/target: exact historical construction (§1): swing M15 bars 1..3 (bars of the
  server-time M15 calendar, forming bar = bar containing T_stop excluded), +/- 2 pip
  buffer; slDist from the actual fill price; skip if slDist <= 0; TP = 2.5 x slDist.
- Breakeven: live EA rule replicated (move SL to entry +/- 1 pip when the exit-side
  price reaches 1.5 x initial risk favorably).
- Anti-cascade: a reverse never triggers a reverse (by construction).
- Daily limit (EA-faithful): reverse skipped if baseline trades opened that server day
  + reverses already taken that server day >= 2.
- Overlap guard (EA-faithful idealization): a reverse is skipped if a previous reverse
  is still open at T_stop. Documented idealization: the canonical baseline stream is
  NOT displaced by reverse trades (overlay study on the frozen source signal;
  in the real EA a reverse would delay the next baseline entry).
- Window end: a reverse still open at the last tick <= 2018-12-31 23:59:59.999999 UTC
  is closed at that tick (exit_reason EOD_WINDOW), documented.
- Lot simulation: EA risk-based sizing (1%, Thursday x0.5, RevLotMult=1.0) is carried
  for $ accounting but ALL verdict metrics are R/pip-normalized so lot size cannot
  manufacture the verdict.

## 5. H2 — DIRECT_SIGNAL_INVERSION (secondary)

- ID: `DIRECT_SIGNAL_INVERSION`. Universe: every executed canonical baseline trade
  (428). Same decision timestamp as the original signal (M15 bar open, server time).
- Rule: flip direction immediately. Original LONG signal -> direct SHORT; original
  SHORT -> direct LONG. No waiting for a loss.
- Risk mirror: `R0 = |entry_ref - S|` from the ORIGINAL event geometry (entry_ref =
  bid at decision bar open; S = original SL). Inverted LONG: entry = ASK fill,
  stop = entry - R0, target = entry + 2.5 x R0. Inverted SHORT: entry = BID fill,
  stop = entry + R0, target = entry - 2.5 x R0. ORIGINAL_RR = 2.5 (EA MinRR, frozen).
  The old stop PRICE is never reused; the RISK DISTANCE is mirrored.
- No breakeven for H2 (mission defines the full construction as entry/stop/target;
  BE is not part of it). Frozen explicitly: H2 trades run to stop/target/window-end.
- Execution baseline: entry ref = decision + 5 s, 30 s fill bound, LONG at ASK /
  SHORT at BID, tick-accurate stop/target resolution. Window-end close as H1.

## 6. Execution conventions (all hypotheses, frozen)

- LONG: entry ASK, all exits on BID. SHORT: entry BID, all exits on ASK (MT4 semantics,
  identical to prior engine and po3 executor).
- STOP exit fills at the actual exit-side tick price (gap-through preserved — realistic,
  conservative). TARGET exit fills at the target price exactly (favorable overshoot
  capped). Same-tick stop&target: STOP wins (pessimistic; exit-side conditions are
  mutually exclusive at one tick anyway).
- Costs baseline: real historical spread via side-accurate fills. No commission
  (mission §8/§13 defines baseline as delay + real spread; documented). No slippage.
- LATENCY_30S scenario: entry delay 30 s, everything else identical.
- REALISTIC_STRESS scenario: entry delay 30 s + 0.50 pip adverse slippage per side
  (entry fills 0.5 pip worse; STOP and window-end exits 0.5 pip worse on the exit
  side; TARGET fills remain exact limit fills). Stop/target LEVELS unchanged.
- NO_FILL trades are excluded from N_TRADES; TRIGGERS counts them.

## 7. Metrics (frozen definitions)

N_TRADES = executed trades. TRADES_PER_MONTH = N/108. TRADES_PER_YEAR = N/9.
WIN_RATE = share of trades with net_pips > 0. R = favorable-adverse move in price /
INITIAL risk distance (entry->initial SL; BE-moved exits keep the INITIAL distance).
PROFIT_FACTOR = sum(wins)/|sum(losses)| on net pips (cap 999).
EXPECTANCY_R = mean(R). MAX_DRAWDOWN_R on cumsum(R). MAX_CONSECUTIVE_LOSSES on net<0.
POSITIVE_YEARS = years (of the years present) with total net pips > 0; YEARS_ELIGIBLE = 9.
REMOVE_BEST_1_PERCENT_EXPECTANCY_R = mean(R) after removing max(1, ceil(0.01*N))
highest-R trades. BOOTSTRAP_CI95: 2000 resamples, seed 42, percentile 2.5/97.5.
H1 extras: ORIGINAL_STOPPED_L0_N, PCT_OF_STOPPED_L0_REVERSED (executed / triggers),
TIME_STOP_TO_REVERSE_FILL_MEDIAN_SEC. H2 extras: ORIGINAL_SIGNAL_EXPECTANCY_R (frozen
prior stream, -0.0525R), INVERTED_SIGNAL_EXPECTANCY_R, paired Pearson+Spearman
correlation of original vs inverted R.

## 8. Verdict gates (frozen, mechanical)

CANDIDATE gate (all must hold): N>=100; EXPECTANCY_R>=+0.10; PF>=1.20;
TOTAL_NET_PIPS>0; POSITIVE_YEARS/YEARS_ELIGIBLE>=0.67; REMOVE_BEST_1PCT_E[R]>0;
LATENCY_30S_E[R]>0; REALISTIC_STRESS_E[R]>0; LONG_E[R]>0; SHORT_E[R]>0. CI95 reported.
Outcomes: H1 pass -> REVERSE_AFTER_STOP_CANDIDATE; H2 pass -> DIRECT_INVERSION_CANDIDATE;
both -> BOTH_REVERSE_MECHANISMS_CANDIDATE; neither -> NO_REVERSE_EDGE.
IS_THE_EMA_SIGNAL_ANTI_PREDICTIVE = YES iff H2 satisfies the candidate gate, else NO
(mechanism explanation mandatory either way, see report §anti-predictive).
"Materially close" for §20 audit = EXPECTANCY_R>0 AND PF>1.0 on the baseline scenario.

## 9. Forbidden (frozen)

No RevMaxSL sweep, no RR/swing-bars/hours/EMA/session/latency/stop/target search, no new
filters, no optimizer, no ML, no money-management rescue. Exactly: H1 RAW, H2 direct
inversion, Test04 historical benchmark. 2019+ and protected OOS are never accessed.

## 10. Provenance hashes (frozen)

```
BASE_HEAD            b51b9f6141dabe89dd029a34cf3a88b81ae7b4e4
m1_engine.py         d1da65c4abdbd2b8a591bd6bd6a4e2da938fd04aee82dafc4941f51d3a4083f7
results_baseline.csv f84cef65035aed58b9dcd417569df7faa664830acc0d634ee28a3e7d1d871567
results_pyramid.csv  a3448784f0c001699ac486bcfc6516cb716329ea0447188b64c22fb5f2fdbeb9
M15 slice            a8276a959269b2cae9c45bd26370f51ff96c932c7cbea71a1ebd8b82b59b9bd0
data_manifest.json   e29806efd95b05ab25a9fdf44bbe0fb56563e20223e28ba3de86af1f0e4a44c0
v2 EA (worktree)     dfbef35bdd11844b31139b6525ee6f1d3d4de152693f0e72d19b7babde1dc854
```
