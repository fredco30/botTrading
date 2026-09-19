# COST ASSUMPTIONS — pre-registered BEFORE any cross-pair PnL (2026-09-19)

MODELED_EXECUTION. For 2020-2025 the local stores are BID-side 5m bars only;
there is no contemporaneous full BID/ASK store for these pairs, so all costs
are modeled, conservative, and taken from already-validated prior botTrading
research — NOT derived from strategy results.

Source: `research/fx_currency_network_m1/netlib.py` (SPREAD table,
pre-registered in that campaign BEFORE its own PnL; conventions identical:
one-spread round trip, buy at modeled ASK = BID + spread, sell at BID,
adverse per-side slippage in stress only). EURUSD/GBPUSD/USDJPY values were
also carried by `research/fx_multipair_swing_m1/swing_lib.py` (EURUSD =
measured Dukascopy tick median; GBPUSD/USDJPY conservative majors estimates).

| PAIR   | NORMAL_SPREAD_PIPS | STRESS_SPREAD_PIPS     | NORMAL_SLIPPAGE | STRESS_SLIPPAGE | PIP SIZE |
|--------|--------------------|------------------------|-----------------|-----------------|----------|
| EURUSD | 0.6                | 0.6 (1.6 total w/slip) | 0.0             | 0.5 per side    | 1e-4     |
| GBPUSD | 1.0                | 1.0 (2.0 total)        | 0.0             | 0.5 per side    | 1e-4     |
| USDJPY | 0.9                | 0.9 (1.9 total)        | 0.0             | 0.5 per side    | 1e-2     |
| EURJPY | 1.2                | 1.2 (2.2 total)        | 0.0             | 0.5 per side    | 1e-2     |
| GBPJPY | 2.0                | 2.0 (3.0 total)        | 0.0             | 0.5 per side    | 1e-2     |
| EURGBP | 0.8                | 0.8 (1.8 total)        | 0.0             | 0.5 per side    | 1e-4     |

SOURCE_OF_COST_ASSUMPTION = fx_currency_network_m1/netlib.py SPREAD table
(prior validated research); STRESS = spread + 2 x 0.5 pip per-side adverse
slippage. No pair uses another pair's spread. No cost was chosen or adjusted
after seeing any replication result.
