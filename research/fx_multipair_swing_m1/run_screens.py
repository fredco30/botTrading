#!/usr/bin/env python3
"""Stage 1 gross screens: all families, coarse grids, pooled EURUSD+GBPUSD
2010-2017. One ledger row per config scan (gross BID, no costs). Survivors
(net-of-cost potential) advance to bar_replay in run_deepen.py."""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import swing_lib as S
import families_sw as F

HORIZONS = {"D1": (1, 2, 3, 5, 10), "H4": (2, 3, 6, 12, 24), "H1": (4, 8, 24, 48)}

GRIDS = [
    # (family_id, mechanism, signal_fn, [params...])
    ("G01", "donchian_breakout", F.g01_donchian,
     [{"n": 10}, {"n": 20}, {"n": 40}]),
    ("G02", "tsmom", F.g02_tsmom,
     [{"k": 10}, {"k": 20}, {"k": 60}]),
    ("G03", "trend_pullback", F.g03_trend_pullback,
     [{"trend_n": 50, "pb_n": 20, "depth": 0.5},
      {"trend_n": 100, "pb_n": 20, "depth": 1.0}]),
    ("G04", "extreme_fade", F.g04_extreme_fade,
     [{"z_n": 50, "z": 2.0}, {"z_n": 100, "z": 2.5}]),
    ("G05", "pdh_pdl_acceptance", F.g05_acceptance,
     [{}]),
    ("G06", "compression_breakout", F.g06_compression,
     [{"ratio": 0.8}, {"ratio": 0.7}]),
    ("G07", "displacement_continuation", F.g07_displacement,
     [{"mult": 2.0}, {"mult": 2.5}]),
    ("G08", "efficiency_extreme", F.g08_efficiency,
     [{"k": 10, "eff": 0.5}, {"k": 20, "eff": 0.45}]),
    ("G09", "usd_regime", F.g09_usd_regime,
     [{"z_n": 20, "z": 1.5}, {"z_n": 60, "z": 1.5}]),
    ("G10", "d1_trend_h4_break", F.g10_state_machine,
     [{"fast": 20, "slow": 50, "break_n": 20},
      {"fast": 50, "slow": 100, "break_n": 10}]),
    ("G11", "vol_regime_transition", F.g11_vol_regime,
     [{"win": 252, "ma_n": 20, "hi": 0.8, "lo": 0.2},
      {"win": 126, "ma_n": 50, "hi": 0.9, "lo": 0.1}]),
    ("G12", "monday_range_break", F.g12_monday_range,
     [{"end_hr": 8}]),
]


def main():
    only = sys.argv[1:] if len(sys.argv) > 1 else None
    for fam, mech, fn, grid in GRIDS:
        if only and fam not in only:
            continue
        horizons = HORIZONS[fn.signal_tf]
        for p in grid:
            res_e, ns_e = F.scan_signal("EURUSD", fn, p, horizons)
            res_g, ns_g = F.scan_signal("GBPUSD", fn, p, horizons)
            pooled = F.pool_two(res_e, res_g, horizons)
            title = f"{fam} {mech} {p}"
            # pick best horizon by pooled mean for the ledger row
            best_h, best = None, -1e18
            for h in horizons:
                v = pooled[h]
                if len(v) >= 30 and v.mean() > best:
                    best_h, best = h, float(v.mean())
            v = pooled[best_h] if best_h else pooled[horizons[0]]
            mean = float(v.mean()) if len(v) else np.nan
            wins = v[v > 0]; losses = -v[v < 0]
            pf = (wins.sum() / losses.sum()) if len(wins) and len(losses) \
                and losses.sum() > 0 else np.nan
            S.log(fam, mech, "PENDING", f"{p}|h={best_h}",
                  N=len(v), mean_pips=mean, PF=pf,
                  status="SCAN", reason=f"signals e={ns_e} g={ns_g}")
            print(F.summarize_scan(title, pooled, ns_e + ns_g, horizons))


if __name__ == "__main__":
    main()
