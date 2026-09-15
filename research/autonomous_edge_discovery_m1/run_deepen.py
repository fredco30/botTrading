#!/usr/bin/env python3
"""M1 deepen: tick-exact replay of surviving families on 2017.
F10 daily-breakout (k grid), F05 NY-reversal (2 thresholds), F08 absorption.
Baseline (5s, 0 slip) + stress (30s, 0.5pip/side) + common sample."""
import numpy as np
import pandas as pd
import m1lib as M
import infra_lib as I
import families as F
import ledger as L

ts, bid, ask = I.load_year(2017)
bars = M.add_n_ticks(ts, I.m1_bars(ts, bid, ask))
months = pd.to_datetime(bars["close_time"], utc=True).month.to_numpy()


def run(fam_id, mech, caus, params, sig, tag):
    base, nfb = I.replay(ts, bid, ask, bars, sig, latency_ns=I.LATENCY_NS, slip_pips=0.0)
    stress, nfs = I.replay(ts, bid, ask, bars, sig, latency_ns=30 * I.NS, slip_pips=0.50)
    bc, sc = I.common_sample(base, stress)
    mb = I.metrics(base, months, f"{tag} BASE")
    ms = I.metrics(stress, months, f"{tag} STRESS")
    mbc = I.metrics(bc, months, f"{tag} BASE_COMMON")
    msc = I.metrics(sc, months, f"{tag} STRESS_COMMON")
    L.log(fam_id, mech, caus, params, mb.get("N", 0),
          mb.get("mean_pips"), mb.get("PF"), mb.get("expectancy_r"),
          stress_pips=ms.get("mean_pips"), remove_best_pips=mb.get("remove_best"),
          status="REPLAY",
          reason=f"BASE common EV={mbc.get('mean_pips')}PF={mbc.get('PF')} | "
                 f"STRESS common EV={msc.get('mean_pips')}PF={msc.get('PF')} "
                 f"INT={len(bc)} L_R={mb.get('long_r')} S_R={mb.get('short_r')} "
                 f"posmon={mb.get('pos_months')} exits={mb.get('exits')}")
    print(f"{tag}: BASE N={mb.get('N')} mean={mb.get('mean_pips')} PF={mb.get('PF')} "
          f"expR={mb.get('expectancy_r')} L={mb.get('long_r')} S={mb.get('short_r')} "
          f"posmon={mb.get('pos_months')} rb={mb.get('remove_best')} | "
          f"COMMON: bEV={mbc.get('mean_pips')} sEV={msc.get('mean_pips')} "
          f"bPF={mbc.get('PF')} sPF={msc.get('PF')} INT={len(bc)}")
    return mb, ms, mbc, msc


# ---- F10 daily breakout, k grid, T exit 120 (frozen bracket 15/15) ----
for k in (1.01, 0.85, 0.75):
    F.F10_TIGHT_K = k
    ex = F.f10_build_extras(ts, bid, ask, bars)
    sig = M.signal_vector(F.f10_feat, F.f10_expand, ts, bid, ask, bars, ex)
    run("F10", f"daily breakout k={k}", "PASS", "SL15 TP15 T120",
        sig, f"F10k{k}")

# ---- F05 NY reversal, relaxed thresholds (feature variant) ----
def f05_feat_rel(bars, ex, j, lon_thr=10.0, us_thr=3.0):
    f = F.f05_feat(bars, ex, j)
    return f  # thresholds live inside; patched below


# simpler: reuse F.f05_feat but relax sign thresholds via wrapper on value
def make_f05_pair(bars, ex):
    def feat10(bars, ex, j):
        f = F.f05_feat(bars, ex, j)
        return f
    return feat10


for thr in (5.0, 3.0):
    ex = F.extras_common(ts, bid, ask, bars)

    def sign5(f, thr=thr):
        return -1 if f["value"] < -thr else (1 if f["value"] > thr else 0)
    sig = M.signal_vector(F.f05_feat, sign5, ts, bid, ask, bars, ex)
    run("F05", "NY reversal relaxed", "PASS", f"us_thr={thr} SL15 TP15 T240",
        sig, f"F05t{int(thr)}")

# ---- F08 absorption: both-sides and long-only ----
ex = F.extras_common(ts, bid, ask, bars)
sig = M.signal_vector(F.f08_feat, F.f08_absorb, ts, bid, ask, bars, ex)
run("F08", "absorption both sides", "PASS", "SL15 TP15 T120", sig, "F08both")


def f08_long(f):
    return 1 if (f["aux"] == -1 and f["value"] > 0) else 0


sig = M.signal_vector(F.f08_feat, f08_long, ts, bid, ask, bars, ex)
run("F08", "absorption LONG-only (failed fresh-low bounce)", "PASS",
    "SL15 TP15 T120", sig, "F08long")

print("EXPERIMENTS_USED:", L.experiments_used())
