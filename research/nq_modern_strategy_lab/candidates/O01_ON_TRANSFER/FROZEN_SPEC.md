# FROZEN_SPEC — O01_ON_TRANSFER (STATUS=FROZEN_CANDIDATE)

STRATEGY_ID=O01_ON_TRANSFER
DATE_FROZEN=2026-09-16
2026_ACCESSED=NO
MECHANISM=Overnight-to-RTH transfer. When the overnight session carries an
extreme directional return AND the premarket offers no reversal structure
(narrow premarket range), the overnight positioning persists into the RTH
morning: there is no premarket counter-flow to absorb it, so the open continues
the drift as the cash session re-prices to the futures lead.
TIMEFRAME=5m (bucket-START labels), real CME NQ (GLBX.MDP3 NQ.v.0, unadjusted)
SESSION=RTH [09:30, 16:00) America/New_York (real DST)
ENTRY=
  Overnight return = open_09:30 / prior_RTH_close - 1.
  ON z = (on_ret - mean20)/std20 of the trailing 20 RTH days (causal, shifted).
  Premarket range = [04:00, 09:30) ET high-low.
  Decision at the CLOSE of the 09:35 bar:
    IF |ON z| >= 1.0 AND pm_range <= 0.5 x ON range:
       side = sign(ON z); fill = NEXT bar open (market-at-signal)
  One trade/day, one base position, no pyramiding/averaging.
STOP=hard stop at the opposite extreme of 09:30-09:35 (long: min low; short:
  max high); intrabar touch fills at the stop, worse open on gap.
EXIT=chandelier trail: extreme since entry -/+ 1.0 x ATR14, exit on 5m CLOSE
  crossing; mandatory EOD flatten. No profit target (continuation mechanism).
PARAMETERS=z_thr=1.0; pm/on ratio 0.5; trail_k=1.0
COST_MODEL=MODELED_EXECUTION, RT per contract: LOW 0.75 / NORMAL 1.5 /
  STRESS 3.0 pts ($3.75/$7.50/$15.00). 1 pt = $5. 2020-2025 internal sample.
DISCOVERY_METRICS(2020-2021)=+6.87 pts/trade (2020 negative -13.1, 2021 +29.0)
2022_2023_METRICS=+28.70 pts/trade | 2024_2025_METRICS=+13.79 pts/trade
POOLED_2020_2025(NORMAL)=N=133, 0.43 tpw, +14.31 pts/trade ($71.54), PF 1.515,
  WR 25.6%, EXP_R +0.063, remove-best1% +12.06, STRESS +12.81 (PF 1.443),
  LOW +15.06
BY_YEAR=2020 -13.07 | 2021 +28.96 | 2022 +43.32 | 2023 +9.91 | 2024 +23.00 |
  2025 +5.41 (5/6 positive; concentration 44%)
MAX_DD=-3062 USD (1 contract, NORMAL, trade-sequence peak-to-trough)
FREQUENCY=0.43 trades/week (133 trades / 6y) — low; event-driven mechanism
CORRELATION_WITH_OTHER_CANDIDATES=daily PnL corr: OPR -0.13, H02 +0.16;
  weekly ~0.00-0.16 (independent mechanisms)
SOURCE=../families.py O01 (entry), ../lab_lib.py (engine, causality-tested),
  ../results_lab.json + candidates/O01_res.json (results)
LIMITS=internal temporal blocks, NOT pristine OOS (only 2026 is sealed); low
  frequency; win rate 26% (trend-shaped PnL, tail-dependent); modeled execution
  (OHLCV-1m); 2020 negative year.
