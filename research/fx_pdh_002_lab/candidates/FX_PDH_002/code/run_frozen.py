#!/usr/bin/env python3
"""FX_PDH_002 — frozen candidate runner (C1 entry + D2 daily-chandelier).

Deterministic reproduction of RESULTS.json from sealed local data.
No tuning parameters; every number is computed by this script.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import engine as E


def run():
    D = E.prepare()
    sig = E.signals(D, "C1")
    out = {"spec": "FX_PDH_002 V1 = C1 close-confirm entry + D2 daily "
                   "chandelier exit (see FROZEN_SPEC.md)"}
    for slip, tag in ((0.0, "NORMAL"), (E.SLIP_STRESS, "STRESS")):
        tr = E.replay(D, sig, slip=slip, exit_arch="daily_chand")
        s = E.summarize(D, tr, slip=slip, label=f"FX_PDH_002_{tag}")
        s["eur500"], s["gates"], _ = E.eur500_sim(D, tr, slip=slip)
        out[tag] = s
    out["no_2026"] = bool(D["no_2026"]
                          and out["NORMAL"]["no_2026"]
                          and out["STRESS"]["no_2026"])
    return out


if __name__ == "__main__":
    res = run()
    with open(os.path.join(HERE, "..", "RESULTS.json"), "w") as f:
        json.dump(res, f, indent=1, default=float)
    print(json.dumps({k: v for k, v in res.items() if k != "spec"},
                     indent=1, default=float))
