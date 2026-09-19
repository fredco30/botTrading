#!/usr/bin/env python3
"""PHASE B — FX_PDH_002B pyramid cells: 4 architectures x 2 risk caps,
NORMAL + STRESS. Pre-registered in RESEARCH_PROTOCOL.md section 4B.

Invariant tested: the BASE layer trade set is IDENTICAL to frozen 001.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E
import pyramid as P


def run_cell(D, arch, cap_pct, slip):
    ldf, info = P.run_pyramid(D, arch, cap_pct, slip=slip)
    gs, grp = P.group_stats(D, ldf)
    lc = P.layer_contribution(ldf)
    if gs:
        r = grp["net_pips"].to_numpy()
        se = np.std(r, ddof=1) / np.sqrt(len(r))
        gs["t_stat_group"] = float(np.mean(r) / se) if se > 0 else np.nan
        gs["trades_per_week"] = float(gs["n_groups"] / E.N_WEEKS)
        gs["expectancy_r_group"] = float(grp["base_r"].mean())
    gs.update({k2: v for k2, v in info.items() if k2 != "add_log"})
    gate = {"VETO": bool(gs and (gs["max_dd_percent"] >= 50
                                 or gs["ending_equity"] <= 250)),
            "WARN": bool(gs and gs["max_dd_percent"] >= 30)}
    return {"summary": gs, "layers": ldf, "contribution": lc, "gate": gate}


def main():
    D = E.prepare()
    out_dir = os.path.join(HERE, "002B_pyramid")
    os.makedirs(out_dir, exist_ok=True)

    # identity invariant: BASE rows == frozen 001 trades (NORMAL)
    ref = E.replay(D, E.signals(D, "long_touch"))
    ldf0, _ = P.run_pyramid(D, "B1", 0.01, slip=0.0)
    b = ldf0[ldf0["kind"] == "BASE"].reset_index(drop=True)
    assert len(b) == len(ref) == 639, (len(b), len(ref))
    assert (b["entry_i"].to_numpy() == ref["entry_i"].to_numpy()).all()
    assert (b["exit_i"].to_numpy() == ref["exit_i"].to_numpy()).all()
    assert np.allclose(b["net_pips"].to_numpy(),
                       ref["net_pips"].to_numpy(), atol=1e-9)
    print("base-layer identity with frozen 001: OK (639 trades)")

    results = {}
    rows = []
    for arch in ("B1", "B2", "B3", "B4"):
        for cap_pct, cap_tag in ((0.0075, "P075"), (0.01, "P100")):
            for slip, tag in ((0.0, "NORMAL"), (E.SLIP_STRESS, "STRESS")):
                cell = run_cell(D, arch, cap_pct, slip)
                key = f"{arch}_{cap_tag}_{tag}"
                s = cell["summary"]
                s.pop("add_log", None)
                results[key] = {"summary": s, "contribution": cell["contribution"],
                                "gate": cell["gate"]}
                if tag == "NORMAL":
                    cell["layers"].to_csv(
                        os.path.join(out_dir, f"layers_{arch}_{cap_tag}.csv"),
                        index=False)
                if s:
                    rows.append({
                        "cell": key, "arch": arch, "cap": cap_tag, "tag": tag,
                        "groups": s["n_groups"], "add1": cell["summary"]["n_add1"],
                        "add2": cell["summary"]["n_add2"],
                        "net_pips": round(s["net_pips"], 1),
                        "pips_per_group": round(s["net_pips_per_group"], 3),
                        "PF": round(s["pf_group"], 3),
                        "expR_base": round(s["expectancy_r_group"], 3),
                        "t": round(s["t_stat_group"], 2),
                        "rb1": round(s["remove_best_1pct_pips"], 2),
                        "eq500": round(s["ending_equity"], 0),
                        "dd%": round(s["max_dd_percent"], 1),
                        "peak_risk_eur": round(s["max_open_risk_eur"], 2),
                        "2022%": round(100 * s["by_year_group_pips"].get(2022, 0)
                                       / s["net_pips"], 1) if s["net_pips"] else None,
                        "VETO": cell["gate"]["VETO"], "WARN": cell["gate"]["WARN"],
                    })
                    print(f"{key}: groups={s['n_groups']} "
                          f"adds={s['n_add1']}/{s['n_add2']} "
                          f"net={s['net_pips']:+.0f} pips "
                          f"({s['net_pips_per_group']:+.2f}/grp) "
                          f"PF={s['pf_group']:.3f} eq={s['ending_equity']:.0f} "
                          f"dd={s['max_dd_percent']:.1f}% "
                          f"peak_risk={s['max_open_risk_eur']:.2f} EUR")

    tbl = pd.DataFrame(rows)
    tbl.to_csv(os.path.join(out_dir, "CELLS.csv"), index=False)
    with open(os.path.join(out_dir, "RESULTS.json"), "w") as f:
        json.dump(results, f, indent=1, default=float)
    print("\n", tbl.to_string(index=False))


if __name__ == "__main__":
    main()
