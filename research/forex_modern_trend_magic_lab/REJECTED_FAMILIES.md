# REJECTED_FAMILIES — FOREX_MODERN_STRATEGY_LAB_M1

| family id | mechanism | evidence | verdict |
|-----------|-----------|----------|---------|
| F01 | Trend Magic Enhanced state-change entries (any tf) | EVENT_STUDY_RESULTS.json: 45 cells, 0 significant positive, 6 significant negative (GBPUSD); MFE~=MAE | DEAD |
| F02 | Trend Magic H1 state as directional filter for continuation entries (B1-B5 family) | STATE_DRIFT_RESULTS.json + control: conditional drift ~= unconditional baseline on all pairs; USDJPY bear-state 24h drift (+2.99) > bull-state (+2.77); no marginal information, cannot clear costs | DEAD (gated pre-backtest) |

Historical (this repo, prior campaigns — not re-tested here):
S001 GBPUSD London breakout (-3.32 pips/trade), S003 EURUSD compression
breakout (-1.39), S004 EURUSD Asia false breakout (-1.78),
fx_multipair_swing_m1 (12 families, no plateau), fx_currency_network_m1
(no candidate), fx_cross_asset_rv_m1 / fx_macro_rates_swing_m1 (terminal,
no candidate).
