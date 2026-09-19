# REJECTED_FAMILIES — FOREX_MODERN_STRATEGY_LAB_M1

| family id | mechanism | evidence | verdict |
|-----------|-----------|----------|---------|
| F01 | Trend Magic Enhanced state-change entries (any tf) | EVENT_STUDY_RESULTS.json: 45 cells, 0 significant positive, 6 significant negative (GBPUSD); MFE~=MAE | DEAD |
| F02 | Trend Magic H1 state as directional filter for continuation entries (B1-B5 family) | STATE_DRIFT_RESULTS.json + control: conditional drift ~= unconditional baseline on all pairs; USDJPY bear-state 24h drift (+2.99) > bull-state (+2.77); no marginal information, cannot clear costs | DEAD (gated pre-backtest) |

| F03 | Multi-timeframe momentum (H1 1d/3d/1w + D1 5/10/20d lookbacks) | run_momentum_screen*.py: EURUSD/GBPUSD null or reversal-shaped; USDJPY momentum = carry regime (-16..-20 pips/day in 2020) | DEAD |
| F04 | Prior-day level rejection (touch + close-back-inside fades) | run_pdh_pdl_screen.py: n=2-13 events total, unstable | DEAD |
| F05 | London session momentum continuation (07-12 UTC -> 8h) | run_session_screens.py: negative marginals all pairs | DEAD |
| F06 | London false breakout of Asia range (fade) | run_session_screens.py: best marginal +0.43 < cost | DEAD |

Historical (this repo, prior campaigns — not re-tested here):
S001 GBPUSD London breakout (-3.32 pips/trade), S003 EURUSD compression
breakout (-1.39), S004 EURUSD Asia false breakout (-1.78),
fx_multipair_swing_m1 (12 families, no plateau), fx_currency_network_m1
(no candidate), fx_cross_asset_rv_m1 / fx_macro_rates_swing_m1 (terminal,
no candidate).
