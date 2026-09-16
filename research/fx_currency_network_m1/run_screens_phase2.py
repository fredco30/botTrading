#!/usr/bin/env python3
"""Phase 2 screens: families C D E G H I J (experiments CN_E010..CN_E028).
Run as a script (python run_screens_phase2.py) - never imported by path
ambiguity. Same pre-registered parameters as run_screens.py main()."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
assert os.path.samefile(sys.path[0], HERE)

import numpy as np

import netlib as N
# NOTE: m2lib (imported transitively by netlib) does sys.path.insert(0, M1DIR)
# for a LEGACY campaign; a plain `import run_screens` therefore resolves to
# autonomous_edge_discovery_m1/run_screens.py and EXECUTES it. Always load
# our screens by explicit file path.
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "cn_screens", os.path.join(HERE, "run_screens.py"))
R = importlib.util.module_from_spec(_spec)
sys.modules["cn_screens"] = R
_spec.loader.exec_module(R)
assert R.__file__ == os.path.join(HERE, "run_screens.py")


def main():
    t0 = time.time()
    g4 = N.grid("H4")
    gH1 = N.grid("H1")
    print(f"grids ready H4={len(g4.t)} H1={len(gH1.t)} "
          f"({time.time()-t0:.0f}s)", flush=True)
    R.screens_leadlag(gH1)                                # C (4)
    znet = R.net_resid_z(g4)
    for mech in ("cont", "conv"):
        for k in (1.5, 2.0):
            tr = R.run_residual_family(g4, znet, k, mech, "CN-D",
                                       48 if mech == "cont" else 24,
                                       trend=(mech == "cont"))
            R.log_metrics("CN-D", f"netresid_{mech} k={k}",
                          {"W": 120, "k": k}, tr)
    zid = R.idio_z(g4, 6)
    for mech in ("cont", "conv"):
        for k in (1.5, 2.0):
            tr = R.run_residual_family(g4, zid, k, mech, "CN-E",
                                       48 if mech == "cont" else 24,
                                       trend=(mech == "cont"))
            R.log_metrics("CN-E", f"idio_{mech} k={k}",
                          {"n": 6, "W": 120, "k": k}, tr)
    R.screens_corr_break(gH1)                             # G (2)
    R.screens_session(gH1)                                # H (2)
    zdict4 = {6: g4.zstrength(6, 180)}
    R.screens_dispersion(g4, zdict4)                      # I (2)
    R.screens_jpy_shock(g4)                               # J (1)
    print(f"phase2 done {time.time()-t0:.0f}s, "
          f"experiments used: {N.experiments_used()}")


if __name__ == "__main__":
    main()
