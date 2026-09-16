#!/usr/bin/env python3
"""Replay all 420 frozen P000 trades on BBO-1s and produce the final report."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
import bbo_replay as B  # noqa: E402
import nq_lib as N  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "results"
POINT_USD = 20.0
TICK = 0.25
SCENARIOS = [("L1_BASE", "NORMAL"), ("L1_CONSERVATIVE", "NORMAL"),
             ("L1_STRESS", "STRESS")]


def main() -> int:
    df = N.load_5m()
    trades = pd.read_csv(HERE / "FROZEN_TRADE_LIST.csv")
    rows = []
    win_cache = {}
    for k, t in trades.iterrows():
        wid = f"{t['DATE']}_{t['ACTUAL_FUTURES_CONTRACT']}"
        f = B.BBO_DIR / f"{wid}.dbn.zst"
        if not f.exists():
            print("MISSING WINDOW", wid)
            continue
        if wid not in win_cache:
            win_cache[wid] = B.BboWindow(f)
        w = win_cache[wid]
        rec = {"TRADE_ID": t["TRADE_ID"], "DATE": t["DATE"],
               "SIDE": t["SIDE"], "R0": abs(t["MODELED_ENTRY"] - t["INITIAL_STOP"])}
        for scen, tier in SCENARIOS:
            try:
                r = B.replay_trade(dict(t), df, w, scen, tier)
            except Exception as e:  # noqa: BLE001
                r = {"flag": f"ERROR:{type(e).__name__}:{e}", "net": np.nan}
            rec[f"{scen}_NET"] = r.get("net", np.nan)
            rec[f"{scen}_GROSS"] = r.get("gross", np.nan)
            if scen == "L1_BASE":
                rec.update({
                    "ENTRY_BID": r.get("entry_bid"), "ENTRY_ASK": r.get("entry_ask"),
                    "ENTRY_SPREAD": r.get("entry_spread"),
                    "EXIT_SPREAD": r.get("exit_spread"),
                    "BBO_ENTRY_EXEC": r.get("entry_exec"),
                    "BBO_EXIT_EXEC": r.get("exit_exec"),
                    "FLAG": r.get("flag", ""),
                    "AMBIGUITY": r.get("ambiguity", ""),
                    "ENTRY_DELTA": (abs(r["entry_exec"] - t["MODELED_ENTRY"])
                                    if r.get("entry_exec") == r["entry_exec"] else np.nan),
                    "EXIT_DELTA": (abs(r["exit_exec"] - t["MODELED_FINAL_EXIT"])
                                   if r.get("exit_exec") == r["exit_exec"] else np.nan),
                })
        rows.append(rec)
        if (k + 1) % 50 == 0:
            print(f"{k + 1}/420", flush=True)
    r = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    r.to_csv(OUT / "bbo_replay_trades.csv", index=False)

    def agg(col):
        v = r[col].to_numpy(float)
        v = v[~np.isnan(v)]
        pos_, neg_ = v[v > 0].sum(), -v[v < 0].sum()
        sr = np.sort(v)[::-1]
        top = max(1, int(round(0.01 * len(v))))
        eq = np.cumsum(v)
        peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))
        dd = float((np.concatenate([[0.0], eq]) - peak).min())
        yrs = pd.DatetimeIndex(pd.to_datetime(r["DATE"])).year
        return {"N": int(len(v)),
                "NET_POINTS": round(float(v.mean()), 4),
                "NET_USD": round(float(v.mean()) * POINT_USD, 2),
                "PF": round(float(pos_ / neg_), 4) if neg_ > 0 else None,
                "WR": round(float((v > 0).mean()), 4),
                "REMOVE_BEST": round(float(sr[top:].mean()), 4),
                "MAX_DD_USD": round(dd * POINT_USD, 2),
                "BY_YEAR": {int(y): round(float(v[np.asarray(yrs) == y].mean()), 3)
                            for y in sorted(set(yrs))}}

    summary = {name: agg(f"{name}_NET") for name, _ in SCENARIOS}
    spreads = np.concatenate([r["ENTRY_SPREAD"].dropna().to_numpy(),
                              r["EXIT_SPREAD"].dropna().to_numpy()])
    sp = {"SPREAD_MEDIAN": round(float(np.median(spreads)), 4),
          "SPREAD_P90": round(float(np.percentile(spreads, 90)), 4),
          "SPREAD_P95": round(float(np.percentile(spreads, 95)), 4),
          "SPREAD_P99": round(float(np.percentile(spreads, 99)), 4)}
    amb = r[r["FLAG"].str.startswith(("AMBIGUOUS", "ERROR"))]
    resolved = r[~r["FLAG"].str.startswith(("AMBIGUOUS", "ERROR"))]
    summary["SPREADS"] = sp
    summary["BBO_RESOLVED_TRADES"] = int(len(resolved))
    summary["BBO_AMBIGUOUS_TRADES"] = int(len(amb))
    summary["AMBIGUOUS_FRACTION"] = round(len(amb) / max(len(r), 1), 4)
    summary["ENTRY_DELTA_MEDIAN"] = round(float(r["ENTRY_DELTA"].median()), 4)
    summary["ENTRY_DELTA_P95"] = round(float(r["ENTRY_DELTA"].quantile(0.95)), 4)
    summary["EXIT_DELTA_MEDIAN"] = round(float(r["EXIT_DELTA"].median()), 4)
    summary["EXIT_DELTA_P95"] = round(float(r["EXIT_DELTA"].quantile(0.95)), 4)
    (OUT / "bbo_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
