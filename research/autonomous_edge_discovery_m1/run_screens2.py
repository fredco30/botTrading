#!/usr/bin/env python3
"""M1 driver: gate every family, then cheap screens on full 2017.
One ledger row per config. Compact output only."""
import numpy as np
import pandas as pd
import m1lib as M
import infra_lib as I
import families as F
import ledger as L

ts, bid, ask = I.load_year(2017)
bars = M.add_n_ticks(ts, I.m1_bars(ts, bid, ask))
months = pd.to_datetime(bars["close_time"], utc=True).month.to_numpy()
EX = F.extras_common(ts, bid, ask, bars)

FAMILIES = [
    ("F06", "directional deceleration (loose)", F.extras_common, F.f06_feat,
     [("decel", F.f06_decel)]),
    ("F08", "absorption vs fresh 2h extreme (loose)", F.extras_common, F.f08_feat,
     [("absorb", F.f08_absorb)]),
    ("F10", "range-persistence expansion day (loose)", F.f10_build_extras, F.f10_feat,
     [("expand", F.f10_expand)]),
    ("F12", "vol-expansion directional continuation", F.f12_build_extras, F.f12_feat,
     [("cont", F.f12_cont)]),
    ("F13", "NY-window breakout w/ day-trend align", F.f13_build_extras, F.f13_feat,
     [("nybrk", F.f13_nybrk)]),
    ("F01OLD", "serial-dep x vol regime", F.extras_common, F.f01_feat,
     [("cont_hi", F.f01_cont), ("rev_lo", F.f01_rev)]),
    ("F02", "compression->box breakout", F.extras_common, F.f02_feat,
     [("breakout", F.f02_break)]),
    ("F03", "failed break out of compression -> fade", F.extras_common, F.f03_feat,
     [("fade", F.f03_fade)]),
    ("F04", "overnight->London flip", F.extras_common, F.f04_feat,
     [("flip", F.f04_flip)]),
    ("F05", "London->NY reversal handoff", F.extras_common, F.f05_feat,
     [("rev", F.f05_rev)]),
    ("F06", "directional deceleration", F.extras_common, F.f06_feat,
     [("decel", F.f06_decel)]),
    ("F07", "fresh 24h extreme continuation", F.extras_common, F.f07_feat,
     [("fresh", F.f07_fresh)]),
    ("F08", "absorption vs fresh 2h extreme", F.extras_common, F.f08_feat,
     [("absorb", F.f08_absorb)]),
    ("F10", "range-persistence expansion day", F.f10_build_extras, F.f10_feat,
     [("expand", F.f10_expand)]),
    ("F11", "tick-activity surge w/ direction", F.f11_build_extras, F.f11_feat,
     [("surge", F.f11_surge)]),
    ("F12", "vol-expansion directional continuation", F.f12_build_extras, F.f12_feat,
     [("cont", F.f12_cont)]),
]

for fam_id, mech, bex, feat, configs in FAMILIES:
    try:
        L.register_family(fam_id)
    except RuntimeError as e:
        print(e)
        break
    ex = bex(ts, bid, ask, bars)
    ok, ntest = M.causality_gate(fam_id, feat, bex, bars, ex, 28)
    if not ok:
        L.log(fam_id, mech, "FAIL", "gate", status="CAUSALITY_FAIL",
              reason="rejected pre-PnL")
        continue
    ex = bex(ts, bid, ask, bars)
    for cfg_name, sign_of in configs:
        sig = M.signal_vector(feat, sign_of, ts, bid, ask, bars, ex)
        n_sig = int((sig != 0).sum())
        if n_sig == 0:
            L.log(fam_id, mech, "PASS", cfg_name, 0, status="NO_EVENTS", reason="")
            print(f"{fam_id}/{cfg_name}: 0 events")
            continue
        longs = sig == 1
        shorts = sig == -1
        scr = M.fwd_screen(sig != 0, bars, horizons=(60, 120, 240))
        sl = M.fwd_screen(longs, bars, horizons=(120,))
        ss = M.fwd_screen(shorts, bars, horizons=(120,))
        best_h = max(scr, key=lambda h: scr[h][1] if scr[h][0] >= 30 else -9e9)
        N, m, t = scr[best_h]
        mon = M.monthly_consistency(sig, bars, months)
        L.log(fam_id, mech, "PASS", cfg_name, N, m,
              status="SCREEN",
              reason=f"h={best_h} t={t} N120 L={sl[120]} S={ss[120]} "
                     f"mon120={mon}")
        print(f"{fam_id}/{cfg_name}: N={n_sig} h{best_h} mean={m} t={t} "
              f"L120={sl[120]} S120={ss[120]} mon={mon}")
print("EXPERIMENTS_USED:", L.experiments_used())
