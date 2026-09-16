# NQ_CONTRACT_SPEC — derived + verified (mission section 7)

PRODUCT=CME E-mini Nasdaq-100 futures (NQ)
EXCHANGE=CME (dataset GLBX.MDP3)
CURRENCY=USD
TICK_SIZE=0.25 index points
  DERIVATION=empirical: minimum positive price increment across 2,117,998
  acquired 1m bars = 0.25 exactly (see manifest/tick_derivation.json; all
  increments are integer multiples of 0.25; OFFGRID_PRICES=0 across all years).
TICK_VALUE_USD=5.00  (= 0.25 pt x $20/pt)
CONTRACT_MULTIPLIER=20 USD per index point (CME-published contract specification)
NOTIONAL_CONTEXT=at NQ ~20,000-25,000 pts (2024-2025 range in this dataset:
  see PRICE range in manifest), 1 contract controls ~$0.4-0.5M notional.
  CME initial margin is SPAN-based and varies; order of magnitude ~$25-35K per
  contract in 2024-2025. CONTEXT ONLY — no sizing claims made in this mission.
TRADING_HOURS (America/New_York, verified against acquired data):
  Globex: Sun 18:00 -> Fri 17:00, daily halt 17:00-18:00.
  RTH (cash-equity hours, strategy session): 09:30-16:00, continuous.
  Dataset confirms: first bar Sunday 23:00 UTC (18:00 ET), RTH minutes
  09:30-16:00 present on all full days.
HALTS/EARLY_CLOSES (observed, all flagged in manifest):
  Holiday early closes (13:00 ET, 210 RTH minutes) ~8-9/year;
  pre-holiday 13:15 ET closes (225 minutes);
  2020-03-09..2020-03-18 circuit-breaker halts (376-377 minute days).
MNQ (Micro E-mini Nasdaq-100, $2/pt) exists; per mission section 26 it is NOT
  researched here — NQ is the price-discovery instrument.
SYMBOL_MAP=Databento continuous NQ.v.0 -> actual contracts per roll_map.csv
  (25 intervals 2020-2025, quarterly H/M/U/Z, volume-ranked roll rule).
