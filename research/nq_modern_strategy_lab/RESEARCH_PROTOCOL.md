# RESEARCH_PROTOCOL — NQ MODERN STRATEGY LAB

SCOPE=autonomous multi-strategy search on real CME NQ ohlcv-1m 2020-2025.
2026_ACCESSED=NO (sealed, external OOS for a later date).
CONTAMINATION_RULE=2020-2021 discovery / 2022-2023 internal validation /
2024-2025 internal replication are INTERNAL RESEARCH SAMPLES. Only 2026 is
pristine. Families are evaluated sequentially on the same sample; reported
blocks are temporal robustness blocks, not external OOS.

## Budget
FAMILIES_MAX=15 (A..O) | EXPERIMENTS_MAX=100 (materially distinct cells only)
DEAD_FAMILY_RULE=decisively negative/unstable/sub-cost/regime-fragile family =>
close it, log in REJECTED_FAMILIES.md, never tune it again.
NEAR_MISS_RULE=max ONE broad mechanism-consistent robustness wave, else archive.
CANDIDATE_RULE=on a pass, freeze (never retune), register, CONTINUE searching.

## Mechanism-first
Every experiment declares, BEFORE PnL: mechanism (why the edge should exist),
entry trigger, exit architecture (mechanism-matched), stop, cost tier.
No blind indicator grids. Cells are coarse and few (1-3 per mechanism).

## Exit architectures (preregistered per family)
TREND/CONTINUATION: initial stop (hard touch or close-based) + trailing
  (EMA or chandelier kxATR-at-entry, close-cross exit) + EOD flatten. No tiny TP.
MEAN_REVERSION: initial stop + target at causal equilibrium level + time stop
  + EOD flatten. Pessimistic same-bar rule: if stop and target both touched in
  one bar, STOP is counted first.
ENTRY FILL MODEL: market-at-signal => fill at NEXT bar OPEN (no same-bar
  look-ahead); stop/retest entries fill at the stop level (worse open on gap).
COSTS=preregistered NQ frictions: LOW 0.75 / NORMAL 1.5 / STRESS 3.0 pts RT
  (1 pt = $5.00). MODELED_EXECUTION. Never lowered to rescue a strategy.

## Candidate gate (all required, evaluated on 2020-2025 pooled)
NET_POINTS_PER_TRADE > 0 at NORMAL and at STRESS
PF >= 1.15 at NORMAL
REMOVE_BEST_1_PERCENT > 0 at NORMAL
TRADES >= 40 over 6y (frequency honesty; rare mechanisms are noted, not primary)
YEARS_POSITIVE >= 4 of 6 at NORMAL, and no single year contributes > 60% of
  total net points
FOLD_SANITY: 2022-2023 block net > 0 at NORMAL OR (block ~flat and both other
  blocks clearly positive) — the middle block is the hardest regime.
Frequency 0.5-5 trades/week preferred (daily-session mechanisms naturally
  lower; nothing below ~0.4/wk is a primary candidate).

## Diagnostics on survivors (no retuning)
daily/weekly PnL correlation, trade overlap, drawdown overlap, by-year and
by-fold tables, regime table correlation (diagnostic only).

## Ledger
EXPERIMENT_LEDGER.csv: one row per experiment (id, family, mechanism, entry,
exit, trades, tpw, net/pf/stress/remove-best, by-fold, verdict).
Experiment counter is authoritative: hard stop before experiment 101.
