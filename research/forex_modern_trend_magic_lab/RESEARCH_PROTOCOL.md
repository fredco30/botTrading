# FOREX MODERN STRATEGY LAB M1 — RESEARCH PROTOCOL

Campaign: find multiple genuinely robust Forex strategies tradable with
EUR 500 capital. Modern market only (2020-2025). 2026 sealed.

## Non-negotiables
1. CAPITAL_EUR = 500; MIN_LOT = 0.01; target risk 0.5%/trade (EUR 2.50),
   max reference 1.0% (EUR 5.00). Strategies whose minimum-lot risk is
   materially excessive are NOT usable regardless of backtest.
2. PERIOD: discovery 2020-2021, validation 2022-2023, replication 2024-2025.
   2026_ACCESSED=NO enforced by hard seal in tmlab.load_5m (asserted by test).
3. CAUSALITY: bars are 5m BID OHLCV (Dukascopy parquet), left-labelled,
   close-time decisions; features read bars closing <= T; forward returns
   start at event-bar close. Resamples are causal (label=left).
4. SOURCE FIDELITY before PnL for any imported indicator: recover exact
   source, freeze spec, port, test (hand-calculated bars, truncation
   invariance, online==batch, warm-up semantics).
5. COSTS: spread (measured Dukascopy medians EURUSD 0.6 / GBPUSD 1.0 /
   USDJPY 0.9 pip) + adverse slippage; NORMAL and STRESS (+0.5 pip/side)
   scenarios; all results reported after costs.
6. GATES (section 21): NET>0, PF>=~1.15, EXPECTANCY_R>0, STRESS>0,
   REMOVE_BEST_1%>0, no single-year dependence, usable EUR 500 sizing.
   Plus the BASELINE CONTROL gate (added by this campaign, see below).
7. BASELINE CONTROL GATE (added after Trend Magic post-mortem): a filter
   or entry is only considered to carry information if its conditional
   forward drift beats the UNCONDITIONAL same-horizon baseline drift by a
   margin relevant vs costs. A signal that merely re-labels regime beta
   (e.g. "long USDJPY was right in 2020-2025") is not an edge.
8. BUDGET: MAX_DISTINCT_FAMILIES=15, MAX_MEANINGFUL_EXPERIMENTS=100.
   Dead family => archive, never retune (OLD != OBSOLETE). Near miss =>
   at most one broad mechanism-consistent robustness pass, then archive.
9. Frozen candidates: FROZEN_SPEC.md + RESULTS.json/md + code + tests,
   committed, STRATEGY_ID assigned, never modified afterwards.
10. RESEARCH/PAPER ONLY. No broker API, no live orders.

## Methodology standard for screens (this campaign)
Drift screens BEFORE backtests: conditional forward drift must clear
(baseline + costs) or the entry family is not run at all. This converts
the protocol's dead-strategy rule into a cheap pre-gate and conserves
budget for mechanisms with measured economic potential.

## Prior-knowledge ledger (families measured dead in THIS repo)
- Trend Magic Enhanced [AlgoAlpha]: state flips + state filter (this lab).
- GBPUSD London breakout (S001): net -3.32 pips/trade.
- EURUSD compression -> confirmed breakout (S003): net -1.39 pips/trade.
- EURUSD Asia false breakout -> reversion (S004): net -1.78 pips/trade.
- FX multipair swing discovery, 12 families 2010-2018: no plateau-passing
  candidate (fx_multipair_swing_m1; modern re-tests need explicit
  justification and must use the baseline control gate).
- FX currency network / relative strength lead-lag: no candidate
  (fx_currency_network_m1).
