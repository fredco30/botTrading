# LIVE DATA OPTIONS — O01 paper engine (mission 18; NO purchase made)

Engine is provider-agnostic: any adapter emitting 5m BAR events + top-of-book
QUOTE events (UTC, ts-ordered) can drive it. Required feed properties:
  GLBX.MDP3 NQ top-of-book bid/ask, ~1s or better resolution, RTH hours,
  reliable UTC timestamps, low startup cost.

Checked locally (no secrets revealed):
  - Databento HISTORICAL key present (~/.databento/config) — pay-per-GB,
    per-mission authorization required for every pull (SPENDING_GUARD.md).
  - No broker credentials, no live market-data subscriptions configured.

Options:
1. DATABENTO LIVE (real-time GLBX.MDP3, bbo-1s equivalent)
   provider=Databento Live; schema=bbo-1s (live); latency ~real-time;
   top-of-book bid/ask = YES; entitlement = CME real-time data subscription
   (exchange fees apply — CME real-time non-pro market data is NOT free).
   Cost: subscription + usage — NOT estimated from free APIs; requires
   account console review. NOT purchased.
2. DELAYED EOD PAPER via existing Databento HISTORICAL API (recommended first)
   Each evening after the RTH close, pull ONLY that day's execution window
   (09:30-16:05 ET, bbo-1s + 1m bars, ~19h of 1s data + 390 bars).
   Observed equivalent pricing from this account's actual history:
   O01 full-day window ~= $1.57/133 days ~= $0.012 per day ~= $3.0/year.
   Latency = end-of-day (signals observed next morning); the engine replays
   the session exactly as the validated BBO replay did. This is a PAID API
   usage => requires explicit per-mission authorization (estimate above).
3. FREE simulated feed
   Synthetic/test fixtures only (tests already use them). Not market data.

RECOMMENDED_FEED=option 2 (delayed EOD paper via existing historical API,
~$0.012/day) as the first prospective observation phase, upgrading to option 1
(real-time) only if a live subscription is separately authorized.

NEW_PAID_DATA_PURCHASED=NO
