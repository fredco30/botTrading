#!/usr/bin/env python3
"""Manual traces: 3 LONG + 3 SHORT trades from raw BBO records to final PnL."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
import bbo_replay as B  # noqa: E402
import nq_lib as N  # noqa: E402

HERE = Path(__file__).parent


def trace(t, df, w):
    side = t["SIDE"]
    trig = float((df["high"].iloc[df.index == pd.Timestamp(t["RETEST_TIMESTAMP"])]).iloc[0]) \
        if side == "LONG" else \
        float((df["low"].iloc[df.index == pd.Timestamp(t["RETEST_TIMESTAMP"])]).iloc[0])
    print("=" * 78)
    print(f"{t['TRADE_ID']} {t['DATE']} {side} contract={t['ACTUAL_FUTURES_CONTRACT']}")
    print(f"  PMH={t['PREMARKET_HIGH']} PML={t['PREMARKET_LOW']} "
          f"breakout={t['BREAKOUT_TIMESTAMP']} tap={t['RETEST_TIMESTAMP']}")
    print(f"  order activation={t['ORDER_ACTIVATION_TIMESTAMP']} "
          f"trigger(tap extreme)={trig}")
    act = pd.Timestamp(t["ORDER_ACTIVATION_TIMESTAMP"])
    k0 = w.first_idx_after(act, inclusive=False)
    print(f"  first eligible quote after activation: ts={w.ts[k0]} "
          f"bid={w.bid[k0]} ask={w.ask[k0]}")
    k = k0
    trig_ts = None
    while k is not None and k < len(w.ts):
        px = w.ask[k] if side == "LONG" else w.bid[k]
        ok = px >= trig if side == "LONG" else px <= trig
        if ok:
            trig_ts = k
            break
        k += 1
    print(f"  entry trigger first marketable at: "
          f"{w.ts[trig_ts] if trig_ts is not None else 'NEVER'} "
          f"exec={'ask' if side == 'LONG' else 'bid'}="
          f"{(w.ask[trig_ts] if side == 'LONG' else w.bid[trig_ts]) if trig_ts is not None else '-'}")
    print(f"  frozen stop={t['INITIAL_STOP']} trim_level={t['TRIM_LEVEL']} "
          f"trimmed(frozen)={t['TRIM_TRIGGERED']} exit_reason={t['MODELED_EXIT_REASON']}")
    print(f"  frozen exit ts={t['MODELED_FINAL_EXIT_TIMESTAMP']} "
          f"frozen exit px={t['MODELED_FINAL_EXIT']}")
    for scen, tier in (("L1_BASE", "NORMAL"), ("L1_CONSERVATIVE", "NORMAL"),
                       ("L1_STRESS", "STRESS")):
        r = B.replay_trade(dict(t), df, w, scen, tier)
        print(f"  [{scen}] entry={r['entry_exec']} exit={r['exit_exec']} "
              f"trim={r['trim_exec']} gross={round(r['gross'], 3)} "
              f"fees={r['fees']} slip={round(r['slippage'], 3)} "
              f"NET={round(r['net'], 3)} flag={r['flag']}")


def main() -> int:
    df = N.load_5m()
    trades = pd.read_csv(HERE / "FROZEN_TRADE_LIST.csv")
    picks = []
    longs = trades[trades["SIDE"] == "LONG"].head(3)
    shorts = trades[trades["SIDE"] == "SHORT"].head(3)
    picks = list(longs.iterrows()) + list(shorts.iterrows())
    for _, t in picks:
        wid = f"{t['DATE']}_{t['ACTUAL_FUTURES_CONTRACT']}"
        f = B.BBO_DIR / f"{wid}.dbn.zst"
        w = B.BboWindow(f)
        trace(t, df, w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
