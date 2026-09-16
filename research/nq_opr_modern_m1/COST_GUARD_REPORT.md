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
