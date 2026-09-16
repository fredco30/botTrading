#!/usr/bin/env python3
"""Freeze the exact P000 trade ledger for high-res execution validation.

Reproduces the frozen NQ_OPR_MODERN_M1 (P000A LEVEL, NORMAL cost) pooled
2020-2025 trade list with the frozen engine (nq_lib, untouched), then augments
each trade with roll-manifest contract mapping and execution-window data.
Identity requirements: exactly 420 trades, per-trade fields identical to the
engine, pooled net identical to the committed frozen result (+2.994 pts avg).
Writes FROZEN_TRADE_LIST.csv + sha256, and execution_windows.csv.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
import nq_lib as N  # noqa: E402

HERE = Path(__file__).parent
MANIFEST_DIR = Path(r"E:\ResearchData\botTrading\nq\databento\manifest")
ET = N.ET
NS_MIN = 60 * 10 ** 9


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    df = N.load_5m()
    events = [e for e in N.detect_us_events(df, variant="LEVEL")
              if N.FOLDS["DISCOVERY"][0] <= e.entry_ts < N.FOLDS["REPLICATION"][1]]
    trades = N.trades_frame(N.simulate_strategy(df, events, N.NQ_COSTS["NORMAL"],
                                                N.ET, 1600))
    trades = trades.sort_values("entry_ts").reset_index(drop=True)
    assert len(trades) == 420, f"IDENTITY FAIL: {len(trades)} != 420"
    frozen_avg = 2.994  # committed frozen pooled NET_POINTS_PER_TRADE (NORMAL)
    assert abs(trades["net"].mean() - frozen_avg) < 0.001, "pooled net mismatch"

    # context arrays for trim-level detection
    run_hi, run_lo = N.running_day_extremes(df, ET)
    run_hi, run_lo = run_hi.to_numpy(), run_lo.to_numpy()
    closes = df["close"].to_numpy()
    pos_of = {ts: k for k, ts in enumerate(df.index)}
    levels = N.premarket_levels(df)
    roll = pd.read_csv(MANIFEST_DIR / "roll_audit.csv", parse_dates=["date"])

    rows = []
    win_rows = []
    for tid, t in trades.iterrows():
        day = t["day"]
        i0, i1 = pos_of[t["entry_ts"]], pos_of[t["exit_ts"]]
        side = int(t["side"])
        pmh, pml, _ = levels[day]
        # trim level = running extreme known at entry (tgt = fill if NaN)
        tgt = run_hi[i0] if side == 1 else run_lo[i0]
        if np.isnan(tgt):
            tgt = float(t["fill"])
        trimmed = False
        for k in range(i0, i1 + 1):
            if (side == 1 and df["high"].iloc[k] >= tgt) or \
               (side == -1 and df["low"].iloc[k] <= tgt):
                trimmed = True
                break
        exit_px = float(closes[i1])
        contract_row = roll[roll["date"] == pd.Timestamp(day)]
        contract = contract_row["raw_symbols"].iloc[0] if len(contract_row) else "UNKNOWN"
        breakout_ts = pd.Timestamp(t["entry_ts"])  # placeholder replaced below
        ev = [e for e in events if e.entry_ts == t["entry_ts"] and e.side == side]
        e = ev[0]
        order_active = e.tap_ts + pd.Timedelta(5, "min")   # tap bar completion
        w_start = min(e.confirm_ts, order_active) - pd.Timedelta(10, "min")
        w_end = pd.Timestamp(t["exit_ts"]) + pd.Timedelta(10, "min")
        assert w_end < pd.Timestamp("2026-01-01", tz="UTC"), "2026 seal"
        roll_cross = (w_start.date() != pd.Timestamp(str(day)).date()) or \
                     (w_end.date() != pd.Timestamp(str(day)).date())
        rows.append({
            "TRADE_ID": f"P000-{tid:04d}",
            "DATE": str(day),
            "ACTUAL_FUTURES_CONTRACT": contract,
            "SIDE": "LONG" if side == 1 else "SHORT",
            "PREMARKET_HIGH": round(pmh, 2),
            "PREMARKET_LOW": round(pml, 2),
            "BREAKOUT_TIMESTAMP": str(e.confirm_ts),
            "RETEST_TIMESTAMP": str(e.tap_ts),
            "ORDER_ACTIVATION_TIMESTAMP": str(order_active),
            "MODELED_ENTRY": round(float(t["fill"]), 2),
            "INITIAL_STOP": round(float(t["level"]), 2),
            "TRIM_LEVEL": round(float(tgt), 2),
            "TRIM_TRIGGERED": bool(trimmed),
            "EMA8_MANAGEMENT_STATE": "ARMED" if trimmed else "NOT_ARMED",
            "MODELED_FINAL_EXIT_TIMESTAMP": str(t["exit_ts"]),
            "MODELED_FINAL_EXIT": round(exit_px, 2),
            "MODELED_GROSS_POINTS": round(float(t["gross"]), 4),
            "MODELED_NET_POINTS": round(float(t["net"]), 4),
            "MODELED_EXIT_REASON": t["exit_reason"],
            "WINDOW_START_UTC": str(w_start),
            "WINDOW_END_UTC": str(w_end),
            "ROLL_CROSS": bool(roll_cross),
        })
        win_rows.append({"DATE": str(day), "CONTRACT": contract,
                         "START_UTC": str(w_start), "END_UTC": str(w_end)})
    f = pd.DataFrame(rows)
    out = HERE / "FROZEN_TRADE_LIST.csv"
    f.to_csv(out, index=False)
    w = pd.DataFrame(win_rows)
    w.to_csv(HERE / "execution_windows_raw.csv", index=False)
    digest = sha256_file(out)
    meta = {
        "TRADE_IDENTITY_COUNT": int(len(f)),
        "EXPECTED": 420,
        "TRADE_IDENTITY_MATCH": bool(len(f) == 420),
        "POOLED_NET_POINTS_SUM": round(float(trades["net"].sum()), 4),
        "POOLED_NET_POINTS_AVG": round(float(trades["net"].mean()), 4),
        "FROZEN_AVG_CHECK": frozen_avg,
        "ROLL_CROSS_WINDOWS": int(f["ROLL_CROSS"].sum()),
        "TRIMMED_TRADES": int(f["TRIM_TRIGGERED"].sum()),
        "SHA256_FROZEN_TRADE_LIST": digest,
        "LONG": int((f["SIDE"] == "LONG").sum()),
        "SHORT": int((f["SIDE"] == "SHORT").sum()),
        "DATE_MIN": f["DATE"].min(), "DATE_MAX": f["DATE"].max(),
    }
    (HERE / "frozen_trade_list_meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
