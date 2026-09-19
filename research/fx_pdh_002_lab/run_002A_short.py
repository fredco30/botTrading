#!/usr/bin/env python3
"""PHASE A — FX_PDH_002A: exact SHORT mirror of STRICT V1 (no tuning).

PDL first-touch -> SHORT at next H1 open, stop +1 ATR, trail 3 ATR, 48h.
Question: is the long-only asymmetry real? Decisively negative => DEAD.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E


def main():
    D = E.prepare()
    sig = E.signals(D, "short_touch")
    out_dir = os.path.join(HERE, "002A_short")
    os.makedirs(out_dir, exist_ok=True)
    res = {"spec": "002A exact SHORT mirror of STRICT V1 (PDL break, stop 1.0 "
                   "ATR, trail 3.0 ATR, 48h, one spread + stress 2x0.5 slip)"}
    for tag, slip in (("NORMAL", 0.0), ("STRESS", E.SLIP_STRESS)):
        tr = E.replay(D, sig, side=-1, slip=slip)
        s = E.summarize(D, tr, slip=slip, label=f"002A_{tag}")
        s["eur500"], s["gates"], _ = E.eur500_sim(D, tr, slip=slip)
        res[tag] = s
        tr.to_csv(os.path.join(out_dir, f"trades_{tag.lower()}.csv"),
                  index=False)
        print(f"{tag}: N={s['n']} PF={s['pf']:.3f} "
              f"net={s['net_pips_per_trade']:+.2f} t={s['t_stat']:+.2f} "
              f"rb1={s['remove_best_1pct']:+.2f} "
              f"eq500={s['eur500']['ending_equity']:.0f} "
              f"dd={s['eur500']['max_dd_percent']:.1f}%")
    # the frozen LONG reference for direct comparison
    trl = E.replay(D, E.signals(D, "long_touch"))
    res["LONG_reference"] = E.summarize(D, trl, label="001_LONG_reference")
    dead = (res["STRESS"]["net_pips_per_trade"] < 0
            and res["NORMAL"]["net_pips_per_trade"] < 0)
    res["status"] = "DEAD" if dead else "REVIEW"
    with open(os.path.join(out_dir, "RESULTS.json"), "w") as f:
        json.dump(res, f, indent=1, default=float)
    with open(os.path.join(out_dir, "RESULTS.md"), "w") as f:
        f.write("# FX_PDH_002A — exact SHORT mirror\n\n")
        for tag in ("NORMAL", "STRESS"):
            s = res[tag]
            f.write(f"- {tag}: N={s['n']} ({s['trades_per_week']:.2f}/wk) "
                    f"PF={s['pf']:.3f} net={s['net_pips_per_trade']:+.2f} "
                    f"t={s['t_stat']:+.2f} rb1={s['remove_best_1pct']:+.2f} "
                    f"eq500={s['eur500']['ending_equity']:.0f} "
                    f"dd={s['eur500']['max_dd_percent']:.1f}%\n")
        f.write(f"\nLONG 001 reference: N={res['LONG_reference']['n']} "
                f"PF={res['LONG_reference']['pf']:.3f} "
                f"net={res['LONG_reference']['net_pips_per_trade']:+.2f}\n")
        f.write(f"\nSTATUS = {res['status']}\n")
    print("status:", res["status"])


if __name__ == "__main__":
    main()
