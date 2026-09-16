# COST GUARD REPORT — NQ OPR MODERN M1 (mission section 4)

Checked BEFORE any download. 2026-09-16.

REQUEST=
  DATASET=GLBX.MDP3
  SYMBOL=NQ.v.0 (stype_in=continuous)
  SCHEMA=ohlcv-1m
  PERIOD=2020-01-01T00:00:00 -> 2026-01-01T00:00:00 (end EXCLUSIVE; 2026 SEALED)

API=response of databento Historical metadata (key read from
~/.databento/config, never printed; billing mode pay-per-GB — confirmed by
RATES-DATA-M0 batch job GLBX-20260913-PJ387FJNFC, actual $24.28 billed).

ESTIMATED_COST_USD=0.08
ESTIMATED_RECORDS=2117998
ESTIMATED_BYTES=118607888   (~113 MB billable / decoded-size basis)

LOCAL_AVAILABILITY_CHECK=no existing NQ data found anywhere under
E:\ResearchData\botTrading (only rates ZN/ZF/ZT) — so the ZERO-cost local
exemption does not apply. get_cost returned a strictly positive charge, so the
ZERO-cost subscription/credit exemption does not apply either.

DECISION=COST_NONZERO_STOP_BEFORE_PURCHASE
STATUS=DATA_PURCHASE_AUTH_REQUIRED

No download was executed. No money was spent.

HOW TO AUTHORIZE (one line, then the campaign resumes autonomously):
  create the gate file  research/nq_opr_modern_m1/DATA_PURCHASE_AUTHORIZED
  (or reply "authorized"). download.py refuses to run while the gate file is
  absent. Expected actual cost within +/-20% of the estimate (historical
  variance: estimate vs actual on RATES-DATA-M0 differed by <$0.01).

---

# CORRECTION (2026-09-16, post-first-download)

UNIT BUG FOUND. The original ESTIMATED_COST_USD=0.08 was WRONG: estimate_cost.py
divided get_cost() output by 100 (inherited from the rates-data-m0 script), but
the SDK documents get_cost as returning **US dollars** directly.

Evidence (3 independent):
  1. SDK docstring: "Request the cost in US dollars".
  2. metadata.get_cost(2020 only) == 1.276577115059 — numerically identical to
     the ACTUAL batch job GLBX-20260916-YCRF9W9FWK cost_usd = 1.2765771150589.
  3. Pricing sanity: billed_size 19,581,632 B (~18.7 MB) x ~$65/GB = ~$1.21.

CORRECTED COSTS:
  FULL RANGE 2020-01-01 -> 2026-01-01 EXCL: ESTIMATED_COST_USD=7.73
  SPENT SO FAR (2020 job, done+downloaded): cost_usd=1.2766 (billed_size 19.6 MB,
  349,672 records, 312 daily DBN files under raw/2020/)
  REMAINING 2021..2025 (5 yearly jobs): ~6.45 USD estimated

The user authorization received was for "approximately USD 0.08". Actual cost is
~100x that figure. Remaining downloads are HELD pending explicit
re-authorization of the corrected amount. 2026 remains sealed (never requested).
