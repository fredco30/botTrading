#!/usr/bin/env python3
"""PHASE D — FX_PDH_002D exit architectures (entry = original STRICT V1).

D0 reference (1 ATR stop / 3 ATR trail / 48h) vs D1 slower trail (4.5),
D2 daily chandelier (3x daily ATR14 after first day boundary), D3
5-bar structure close-exit. Pre-registered in RESEARCH_PROTOCOL.md 4D.
"""
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E

ARCHS = {"D0": dict(exit_arch="orig", trail_mult=3.0),
         "D1": dict(exit_arch="orig", trail_mult=4.5),
         "D2": dict(exit_arch="daily_chand", trail_mult=3.0),
         "D3": dict(exit_arch="struct5", trail_mult=3.0)}


def main():
    D = E.prepare()
    sig = E.signals(D, "long_touch")
    out_dir = os.path.join(HERE, "002D_exit")
    os.makedirs(out_dir, exist_ok=True)
    res, rows = {}, []
    for label, kw in ARCHS.items():
        res[label] = {}
        for slip, tag in ((0.0, "NORMAL"), (E.SLIP_STRESS, "STRESS")):
            tr = E.replay(D, sig, slip=slip, **kw)
            s = E.summarize(D, tr, slip=slip, label=f"002{label}_{tag}")
            s["eur500"], s["gates"], _ = E.eur500_sim(D, tr, slip=slip)
            res[label][tag] = s
            if tag == "NORMAL":
                tr.to_csv(os.path.join(out_dir, f"trades_{label}.csv"),
                          index=False)
            rows.append({
                "variant": label, "tag": tag, "n": s["n"],
                "tpw": round(s["trades_per_week"], 2),
                "net": round(s["net_pips_per_trade"], 2),
                "PF": round(s["pf"], 3), "expR": round(s["expectancy_r"], 3),
                "t": round(s["t_stat"], 2),
                "rb1": round(s["remove_best_1pct"], 2),
                "eq500": round(s["eur500"]["ending_equity"], 0),
                "dd%": round(s["eur500"]["max_dd_percent"], 1),
                "2022%": round(s["y2022_profit_share_pct"], 1),
                "exits": s["exits"], "VETO": s["gates"]["VETO"],
                "WARN": s["gates"]["WARN"],
            })
    tbl = pd.DataFrame(rows)
    tbl.to_csv(os.path.join(out_dir, "CELLS.csv"), index=False)
    with open(os.path.join(out_dir, "RESULTS.json"), "w") as f:
        json.dump(res, f, indent=1, default=float)
    print(tbl.to_string(index=False))


if __name__ == "__main__":
    main()
