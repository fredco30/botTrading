# HIGH-RES COST GUARD — H02_TREND_DAY_EARLY / O01_ON_TRANSFER (2026-09-16)

STATUS=DATA_PURCHASE_AUTH_REQUIRED (estimation only — NO purchase executed,
none authorized by the prompt)

## Frozen trade identity (mission section 2)

H02_IDENTITY_COUNT=226      EXPECTED 226  MATCH=YES
  avg net +15.0697 pts (frozen +15.07) | LONG/SHORT per ledger
  sha256(H02_FROZEN_TRADE_LIST.csv)=fc41abc6a346d028bd9cbbcf6815e0f1... (full in meta json)
O01_IDENTITY_COUNT=133      EXPECTED 133  MATCH=YES
  avg net +14.3083 pts (frozen +14.31)
  sha256(O01_FROZEN_TRADE_LIST.csv)=b366b704ba7e0bca...
ROLL_CROSS_WINDOWS=0 (H02) / 0 (O01) — every window inside one ET day of one
actual contract from the existing roll manifest (raw symbols, no continuous).

## Execution semantics

EXECUTION_SEMANTICS_FROZEN.md — all-executable candidates (no passive orders):
entry market-at-next-open (LONG at ASK / SHORT at BID), hard-touch stops on
the opposite-side quote, chandelier-close exits and EOD as market orders at
frozen decision instants, no quote before activation may fill, no backward
interpolation, 2026 hard guard.

## Windows + BBO-1s estimates (raw metadata.get_cost USD — never divided)

H02_BBO1S_WINDOWS=226   H02_BBO1S_TOTAL_HOURS=1141.08   H02_BBO1S_ESTIMATED_COST_USD=5.7018
O01_BBO1S_WINDOWS=133   O01_BBO1S_TOTAL_HOURS=312.00    O01_BBO1S_ESTIMATED_COST_USD=1.5685
COMBINED_BBO1S_WINDOWS=337  COMBINED_BBO1S_TOTAL_HOURS=1419.42  COMBINED_BBO1S_ESTIMATED_COST_USD=7.0884
(COMBINED uses a true interval union: 22 overlapping H02/O01 windows merged,
hence 7.0884 < 5.7018 + 1.5685 = 7.2703.)

## Priority assessment (frozen properties ONLY — no new PnL exists)

O01: PF 1.515 > H02 1.284; years positive 5/6 > 4/6; amplitude +14.31 vs
+15.07 (comparable); frequency 0.43 tpw vs 0.73 tpw; N=133 vs 226; cost
$1.57 vs $5.70 (3.6x cheaper). The P000 high-res mission measured a ~1.8
pt/trade execution decay for a similar morning-entry style; both candidates'
amplitudes (~14-15 pts) would absorb it ~8x better than P000's 3 pts.

RECOMMENDED_VALIDATION_ORDER=1) O01_ON_TRANSFER (better PF, more robust years,
3.6x cheaper — fastest decisive read per dollar) 2) H02_TREND_DAY_EARLY
(larger sample, more statistically binding; costs 3.6x more).

## CHECKPOINT

Every estimated purchase is non-zero =>
FINAL_STATUS=DATA_PURCHASE_AUTH_REQUIRED
STOP. Only the human user may authorize a ceiling (SPENDING_GUARD.md).
2026_REQUESTED=NO / 2026_ACCESSED=NO / NEW_DATA_PURCHASED=NO
