# OPR_CANONICAL_SPEC — NQ OPR MODERN M1

Frozen BEFORE any NQ strategy PnL was computed or inspected.
No post-PnL reinterpretation permitted.

SOURCE_COMMIT=3122f1ea64aafb2c8952cc01189f9af63ff62f63
SOURCE_FILE=research/phenomena_discovery_v1/video_strategy_spec.md
SOURCE_IMPL=research/phenomena_discovery_v1/p000_lib.py (canonical executable semantics)
SOURCE_RUNNER=research/phenomena_discovery_v1/run_p000.py
SOURCE_TRANSCRIPT=research/phenomena_discovery_v1/video_source/ (YouTube transcript, PBInvesting video)

HISTORICAL_MARKET=US stocks (illustrated); historically TESTED on Dukascopy index CFD
proxies (USA500IDXUSD primary, USATECHIDXUSD replication).
HISTORICAL_VERDICT_ON_CFD=VIDEO_STRATEGY_NET_EDGE=NO / ROBUST=NO / NOT_REPLICATED_USATECH.
THIS CAMPAIGN DOES NOT INHERIT THAT VERDICT: the data-generating process changes
(real CME NQ futures, ohlcv-1m, 2020-2025). The SIGNAL DEFINITION below is frozen.

TIMEZONE=America/New_York with real DST handling (no fixed UTC offset).
TIMEFRAME=5-minute bars (built deterministically from acquired 1m bars).
SESSION=RTH [09:30, 16:00) ET. Only RTH bars are eligible for confirmation/retest/entry.
PREMARKET_DEFINITION=
  Window [04:00, 09:30) ET.
  PMH = max(high) of 5m bars in window; PML = min(low) of 5m bars in window.
  Day skipped unless >= MIN_PM_BARS=12 premarket 5m bars exist and PMH > PML.
  (NQ trades Globex through this window; no CFD-proxy gap issue.)
BREAKOUT_DEFINITION=
  First 5m bar of the RTH session whose CLOSE is strictly ABOVE PMH (long bias)
  or strictly BELOW PML (short bias). No trade if no such close (chop day).
  Wick penetration alone is NOT a breakout. Confirmation bar timestamp = its
  bucket START; the close is usable only at bucket START + 5min.
RETEST_DEFINITION=
  After confirmation: tap = 5m bar whose LOW touches the broken level (long) or
  whose HIGH touches it (short). If, before any tap, a 5m CLOSE crosses back
  through the level, the day's setup is invalidated (no trade).
ENTRY_DEFINITION=
  After the tap, a stop order is placed at the tap-bar extreme (tap-bar HIGH for
  long, tap-bar LOW for short). Fill = that price; if a later bar gaps through,
  fill = that bar's OPEN (worse price, mechanical, as p000_lib).
  If a 5m CLOSE crosses back through the level before the stop triggers, the
  setup is invalidated. Maximum ONE trade per day; first valid setup only;
  one position at a time; no pyramiding, no averaging, no adding.
STOP_DEFINITION=
  Untrimmed position: exit at 5m CLOSE back through the broken level
  (close-based invalidation per video: "stop loss if it closes under it";
  a wick alone never stops out).
  After first trim: breakeven floor on the remaining size, gap-aware
  (exit at OPEN if open breaches BE; else at BE if close breaches BE).
PROFIT_MANAGEMENT=
  50% trim (limit fill) at first NEW running day extreme (running high for long /
  running low for short, computed from same-ET-day bars strictly BEFORE the
  current bar — causal shifted cummax/cummin); stop then moves to breakeven.
  Runner exits on 5m CLOSE through EMA8 (span=8, adjust=False, computed on the
  continuous 5m close series exactly as p000_lib).
SESSION_END=
  Flatten remaining position at the last RTH bar of the ET day (fill at that
  bar's CLOSE). Early-close holiday sessions handled mechanically: the last
  available RTH bar IS the session end; such days are flagged in the data
  manifest, never treated as anomalies requiring rule changes.
VWAP_VARIANT_P000B_SECONDARY=
  Canonical secondary variant from the same frozen spec: retest of RTH-anchored
  session VWAP instead of PMH/PML, traded ONLY when VWAP has already moved
  beyond the broken premarket level at confirmation; VWAP is a dynamic level
  updated every bar. Volume-weighted (real NQ 1m volume exists — an improvement
  over the historical TWAP fallback, which the frozen spec explicitly allows:
  "reconstruit en volume-pondere si volumes disponibles"). Same retest / entry /
  stop / trim / EMA8 machinery. P000A (LEVEL) remains the PRIMARY result.
NQ_SPECIFIC_FROZEN_RESOLUTIONS=
  1) Continuous contract: Databento NQ.v.0 (stype_in=continuous), NOT
     back-adjusted. Strategy is day-local; rolls cannot affect intraday logic,
     but a roll manifest is built and any session straddling two contracts is
     documented.
  2) DST/holidays/early closes: tz database America/New_York; early closes
     mechanically shorter sessions (flagged); no rule change.
  3) EMA8 is computed over the continuous 5m series across days (mechanical
     fidelity to frozen p000_lib).
  4) Costs preregistered NOW (all round-trip, 1 contract, 1 NQ point = 5.00 USD):
     LOW=0.75 pt ($3.75) = tight-spread crossing only, near-zero fees.
     NORMAL=1.50 pt ($7.50) = ~1 tick spread crossing (0.50 pt) + retail
     all-in commissions/fees (~0.50-0.70 pt) + 1 tick slippage RT (0.50 pt).
     STRESS=3.00 pt ($15.00) = double friction + degraded fills.
     MODELED_EXECUTION label: OHLCV-1m cannot prove tick-exact fills; no
     tick-exact claims will be made.
     For the raw event study (no costs): forward returns measured from the
     mechanical stop-entry fill to future bar OPENS at h=1,3,6,12,24 bars
     (5m/15m/30m/60m/120m) — identical to frozen run_p000 horizons.
  5) MIN_PM_BARS=12 kept unchanged.
AMBIGUITIES=
  (all resolved in the historical spec and FROZEN; none left open)
  AMBIGUOUS_RULE=PM_WINDOW -> 04:00-09:30 ET (TradingView default, most literal).
  AMBIGUOUS_RULE=RETEST_TRIGGER -> stop-entry at tap-bar extreme, momentum =
  price resuming through that extreme after the tap.
  AMBIGUOUS_RULE=STOP_WICK_VS_CLOSE -> CLOSE-based (literal video wording).
  AMBIGUOUS_RULE=TRIM_SIZE -> 50% at first new day extreme (most conservative
  reading of "trim... sold most"), stop to breakeven.
  AMBIGUOUS_RULE=VWAP_ANCHOR -> RTH start 09:30 ET (TradingView default).
  AMBIGUOUS_RULE=ONE_TRADE_PER_DAY -> max 1 entry/day/market, 1 position at a
  time, one side per day (the breakout side).
  AMBIGUOUS_RULE=ENTRY_TIME_WINDOW -> no artificial hour cutoff; the
  confirm->retest->entry sequence must simply occur within the same RTH session.
FROZEN_AT=2026-09-16, before any NQ data download, 5m build, event study, or PnL.
