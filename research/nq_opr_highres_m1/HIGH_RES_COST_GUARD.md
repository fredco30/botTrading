# HIGH_RES_COST_GUARD — NQ P000 HIGH-RES EXECUTION VALIDATION M1 (2026-09-16)

STATUS=DATA_PURCHASE_AUTH_REQUIRED (no purchase executed; estimation only)

## Frozen signal identity (mission section 6)

TRADE_IDENTITY_COUNT=420
EXPECTED=420
TRADE_IDENTITY_MATCH=YES
POOLED_NET_CHECK=+2.9937 pts/trade (frozen committed +2.994)
LONG/SHORT=224/196 | TRIMMED=345 | 2020-01-03..2025-12-24
FROZEN_TRADE_LIST.csv sha256=e04d1c5cd685edcfd1acdaf742c50371ab1605f3734d744b97929576f47489c4
ACTUAL_CONTRACTS=from existing roll_audit manifest (raw symbols, e.g. NQH0/NQH2/NQM5)
ROLL_CROSS_WINDOWS=0 (every execution window sits inside one ET day / one contract)
Execution semantics frozen pre-PnL: EXECUTION_SEMANTICS_FROZEN.md

## Schema availability (queried, not assumed — record counts per year)

bbo-1s: AVAILABLE 2020-2025 (17.6M/17.9M/19.0M/17.9M/18.2M/18.8M records/yr)
mbp-1 : AVAILABLE 2020-2025 (0.84B/1.20B/1.61B/1.47B/1.57B/2.08B records/yr)
tbbo  : AVAILABLE 2020-2025 (89.6M/82.0M/110.4M/96.1M/95.3M/93.9M records/yr)
trades: AVAILABLE 2020-2025 (identical counts to tbbo, as expected)

## Execution windows (deterministic, mission section 8)

START = min(breakout_ts, order_activation_ts) - 10min, END = exit_ts + 10min,
rounded outward to 10-minute boundaries, merged per DATE+CONTRACT:
  BBO1S_WINDOWS=420   BBO1S_TOTAL_HOURS=581.67
(raw per-trade windows: execution_windows_raw.csv)

## COST ESTIMATES (raw metadata.get_cost values, USD — NEVER divided)

BBO1S_ESTIMATED_COST_USD=3.128      (420 windows, 0 errors)
MBP1_FULL_ESTIMATED_COST_USD=69.6472 (all 420 windows, 0 errors)
MBP1_PILOT_ESTIMATED_COST_USD=4.3787 (100 x 10min deterministic even sample,
chronological, PnL-independent, both directions present)

## CHECKPOINT (mission section 11)

BBO_1S_AVAILABLE=YES
BBO1S_ESTIMATED_COST_USD=3.128
MBP1_AVAILABLE=YES
MBP1_FULL_ESTIMATED_COST_USD=69.6472
MBP1_PILOT_ESTIMATED_COST_USD=4.3787
TBBO_AVAILABLE=YES
RECOMMENDED_FIRST_PURCHASE=bbo-1s over the 420 merged windows (USD 3.13)

Every recommended purchase has a NON-ZERO cost.

FINAL_STATUS=DATA_PURCHASE_AUTH_REQUIRED
STOP.

This prompt did NOT authorize any purchase (mission sections 3/12). Replay,
tests and verdict phases (14-30) execute ONLY after the human user explicitly
approves a stated dollar ceiling. Per SPENDING_GUARD.md: any excess over the
exact authorized ceiling => STOP; no self-authorized ceilings.
