# FX_PDH_001 — FROZEN SPEC (pre-backtest)

```
STRATEGY_ID   = FX_PDH_001
MECHANISM     = prior-day-high upside continuation (Family G)
PAIR          = USDJPY only (EURUSD/GBPUSD PDH marginals measured dead;
                PDL short side measured dead on all pairs)
TIMEFRAME     = H1 signals, H1 bar replay
SESSION       = none (24h)
PERIOD        = 2020-01-01 .. 2025-12-31 (2026 sealed)
```

## Entry (causal)
- PDH = highest HIGH of the previous COMPLETED UTC calendar day with H1 data.
- Event: first H1 bar of the current day whose HIGH > PDH (no earlier
  close-through tracking needed for the long side — break is touch-based).
- Order: market LONG at the NEXT H1 bar open (decision at event-bar close;
  bar-close causality, section 9).
- One position at a time; signals while in position are ignored
  (no pyramiding, section 16). Max one entry per day (first break only).

## Exit architecture (section 15 — ONE consistent family, pre-registered)
- Initial protective stop: entry - 1.0 * ATR(14, H1) computed at entry bar
  close (Wilder RMA on H1 bars, causal).
- Volatility trailing stop: highest HIGH since entry - 3.0 * ATR(14, H1)
  (recomputed each bar close; stop ratchets up only).
- Maximum hold: 48 H1 bars (48h). Time exit at bar close.
- No fixed TP. Intrabar sequencing conservative: if both the initial/trail
  stop and the time exit are touchable in the same bar, the STOP is assumed
  filled first (worst case).

## Costs (section 17)
- LONG entry crosses the spread: fill = bid_open(next bar) + SPREAD + slip.
- LONG exit at bid: stop fills at stop level (bid trigger), time exit at
  bid close; exit slip adverse.
- NORMAL: SPREAD=0.9 pip, slip=0.0 per side. STRESS: SPREAD=0.9, slip=0.5
  per side. All results reported after costs.

## Money management (sections 16/18)
- One base position. Sizing: risk 0.5% of current equity (EUR) at the
  initial stop distance, lot rounded DOWN to 0.01; min lot 0.01 always
  traded if target >= 0.01 (risk then equals min-lot risk, reported).
- No martingale/grid/averaging.

## Research questions this backtest answers
1. Does the mechanism survive realistic entry/exit vs the idealised 24h
   screen (+9.09 gross)?
2. Gate check (section 21) + stress + remove-best-1% + by-year.
3. EUR 500 sizing compatibility (section 18/19/20) and equity path
   simulation (section 33, veto rules).
4. If pass: one plateau pass around (stop ATR mult in {0.75, 1.5},
   trail mult in {2.25, 4.5}, hold in {24, 72}) — 6 coarse neighbours,
   default remains primary (section 24/30).
