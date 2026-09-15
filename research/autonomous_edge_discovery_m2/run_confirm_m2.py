#!/usr/bin/env python3
"""AUTONOMOUS_EDGE_DISCOVERY_M2 — phase 4: SEALED 2018H2 confirmation.

Runs ONLY after FROZEN_SPEC_COMMIT (mission 19/20). Reads the frozen
candidate parameters from frozen_candidate.json (committed artifact) —
never from editable strategy code. No tuning, no added filters.

Data: 2018-07-01..2018-12-31 via validated monthly tick store (2018 only;
2019+ partitions are hard-guarded by validated_mtf_lib).
"""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

import m2lib as M
import validated_mtf_lib as mtf

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_ROOT = "E:/ResearchData/botTrading/ticks/parquet"


def load_2018h2():
    f = os.path.join(M.CACHE, "ticks_2018_m07-12.npz")
    if os.path.exists(f):
        z = np.load(f)
        return z["ts"], z["bid"], z["ask"]
    parts = []
    for m in range(7, 13):
        mtf.assert_month_in_discovery(2018, m)
        df = mtf.read_month_ticks(DATA_ROOT, "EURUSD", 2018, m)
        if df is not None:
            parts.append((df["timestamp_utc"].astype("int64").to_numpy(),
                          df["bid"].to_numpy(np.float64),
                          df["ask"].to_numpy(np.float64)))
        print(f"  loaded 2018-{m:02d}")
    ts = np.concatenate([p[0] for p in parts])
    bid = np.concatenate([p[1] for p in parts])
    ask = np.concatenate([p[2] for p in parts])
    np.savez_compressed(f, ts=ts, bid=bid, ask=ask)
    return ts, bid, ask


def main():
    frozen = json.load(open(os.path.join(HERE, "frozen_candidate.json")))
    fam = frozen["family"]
    assert fam == "F17b", f"unexpected frozen family {fam}"
    thr, sl, tp, tmin = (frozen["retrace_thr"], frozen["sl_pips"],
                         frozen["tp_pips"], frozen["t_exit_min"])

    ts, bid, ask = load_2018h2()
    bars = M.add_n_ticks(ts, M.I.m1_bars(ts, bid, ask))
    ex = M.rolling_extras(M.extras_from_ticks(ts, bid, ask), 2018)

    import families_m2 as F
    n = len(ex["close"])
    sig = np.zeros(n, np.int8)
    t0 = time.time()
    for j in range(31, n):
        f = F.f17_feat(None, ex, j)
        if f is None:
            continue
        if f["aux"] == 1 and f["value"] >= thr:
            sig[j] = -1
        elif f["aux"] == -1 and f["value"] >= thr:
            sig[j] = 1
    print(f"signals: {int((sig != 0).sum())} ({time.time()-t0:.0f}s)")

    base, _ = M.m2_replay(ts, bid, ask, bars, sig, sl, tp, tmin,
                          latency_ns=5 * M.NS, slip_pips=0.0)
    stress, _ = M.m2_replay(ts, bid, ask, bars, sig, sl, tp, tmin,
                            latency_ns=30 * M.NS, slip_pips=0.50)
    bc, sc = M.common_sample(base, stress)
    out = {
        "base": M.agg_metrics(base, "2018H2 BASE"),
        "stress": M.agg_metrics(stress, "2018H2 STRESS"),
        "base_common": M.agg_metrics(bc, "2018H2 BASE-COMMON"),
        "stress_common": M.agg_metrics(sc, "2018H2 STRESS-COMMON"),
        "years_table": M.year_table(base),
        "months": {},
        "survival_base": M.survival_veto(base),
        "n_signals": int((sig != 0).sum()),
    }
    mon = pd.to_datetime([t["entry_ts"] for t in base], unit="ns", utc=True)
    for t, m in zip(base, mon):
        k = str(m.to_period("M"))
        d = out["months"].setdefault(k, {"N": 0, "pips": 0.0, "r": 0.0})
        d["N"] += 1; d["pips"] = round(d["pips"] + t["net_pips"], 2)
        d["r"] = round(d["r"] + t["r"], 3)
    json.dump(out, open("confirm_2018h2.json", "w"), indent=1, default=str)

    b = out["base"]; s = out["stress_common"]
    print(f"\n==== 2018H2 CONFIRMATION {fam} thr={thr} SL{sl}/TP{tp}/T{tmin} ====")
    print(f"BASE   : N={b['N']} mean={b['mean_pips']}p med={b['median_pips']} "
          f"PF={b['PF']} expR={b['expectancy_r']} tot={b['total_pips']}p "
          f"L={b['long_r']}R S={b['short_r']}R remove_best={b['remove_best']}p "
          f"maxDD={b['max_dd_r']}R posMON={b['pos_months']}/{b['n_months']}")
    print(f"         exits={b['exits']} months={out['months']}")
    print(f"STRESSC: N={s['N']} mean={s['mean_pips']}p PF={s['PF']} "
          f"expR={s['expectancy_r']} remove_best={s['remove_best']}p")
    print("BASE_N={} STRESS_N={} INTERSECTION_N={}".format(
        out["base"]["N"], out["stress"]["N"], out["stress_common"]["N"]))
    print("CONFIRM_2018H2_DONE")


if __name__ == "__main__":
    main()
