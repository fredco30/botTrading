#!/usr/bin/env python3
"""PHASE C — FX_PDH_002C entry-quality variants (exits = original STRICT V1).

C0 reference (first-touch) vs C1 close-confirm, C2 close-retest,
C3 strong-break (close location >= 0.70). Pre-registered in
RESEARCH_PROTOCOL.md section 4C. No exit changes.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E


def main():
    D = E.prepare()
    out_dir = os.path.join(HERE, "002C_entry")
    os.makedirs(out_dir, exist_ok=True)
    res = {}
    rows = []
    for kind in ("long_touch", "C1", "C2", "C3"):
        sig = E.signals(D, kind)
        entry = {"long_touch": "C0", "C1": "C1", "C2": "C2", "C3": "C3"}[kind]
        res[entry] = {"n_signals": int(len(sig))}
        for slip, tag in ((0.0, "NORMAL"), (E.SLIP_STRESS, "STRESS")):
            tr = E.replay(D, sig, slip=slip)
            s = E.summarize(D, tr, slip=slip, label=f"002{entry}_{tag}")
            s["eur500"], s["gates"], _ = E.eur500_sim(D, tr, slip=slip)
            res[entry][tag] = s
            if tag == "NORMAL":
                tr.to_csv(os.path.join(out_dir, f"trades_{entry}.csv"),
                          index=False)
            rows.append({
                "variant": entry, "tag": tag, "signals": len(sig),
                "n": s["n"], "tpw": round(s["trades_per_week"], 2),
                "net": round(s["net_pips_per_trade"], 2),
                "PF": round(s["pf"], 3),
                "expR": round(s["expectancy_r"], 3),
                "t": round(s["t_stat"], 2),
                "rb1": round(s["remove_best_1pct"], 2),
                "stress_net": None,
                "eq500": round(s["eur500"]["ending_equity"], 0),
                "dd%": round(s["eur500"]["max_dd_percent"], 1),
                "2022%": round(s["y2022_profit_share_pct"], 1),
                "VETO": s["gates"]["VETO"], "WARN": s["gates"]["WARN"],
            })
    # stress net per variant onto the NORMAL rows
    for row in rows:
        if row["tag"] == "NORMAL":
            row["stress_net"] = res[row["variant"]]["STRESS"]["net_pips_per_trade"]
            row["stress_net"] = round(row["stress_net"], 2)
    # how many original 001 trades does each variant remove?
    base_entries = set(E.replay(D, E.signals(D, "long_touch"))["entry_i"]
                       .tolist())
    for v in ("C1", "C2", "C3"):
        tr = E.replay(D, E.signals(D, v))
        ent = set(tr["entry_i"].tolist())
        res[v]["removed_vs_001"] = len(base_entries - ent)
        res[v]["added_vs_001"] = len(ent - base_entries)
    import pandas as pd
    tbl = pd.DataFrame(rows)
    tbl.to_csv(os.path.join(out_dir, "CELLS.csv"), index=False)
    with open(os.path.join(out_dir, "RESULTS.json"), "w") as f:
        json.dump(res, f, indent=1, default=float)
    print(tbl.to_string(index=False))
    for v in ("C1", "C2", "C3"):
        print(f"{v}: removed {res[v]['removed_vs_001']} of 001 entries, "
              f"added {res[v]['added_vs_001']}")


if __name__ == "__main__":
    main()
