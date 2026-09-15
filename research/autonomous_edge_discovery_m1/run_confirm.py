#!/usr/bin/env python3
"""AED_M1 CONFIRMATION on 2018-01-01..2018-06-30.
Uses the FROZEN feature (f08_plateau.make_feat(180,2) + sign_both) and the
frozen execution, unchanged. Baseline + stress + common sample + monthly."""
import numpy as np
import pandas as pd
import m1lib as M
import infra_lib as I
from f08_plateau import make_feat, build_ex, sign_both

PIP = I.PIP
ts, bid, ask = I.load_half_year(2018, list(range(1, 7)))
print(f"2018H1 ticks: {len(ts):,}")
bars = M.add_n_ticks(ts, I.m1_bars(ts, bid, ask))
months = pd.to_datetime(bars["close_time"], utc=True).month.to_numpy()
ex = build_ex(180)(ts, bid, ask, bars)
feat = make_feat(180, 2)
sig = M.signal_vector(feat, sign_both, ts, bid, ask, bars, ex)
print(f"frozen signals: {int((sig != 0).sum())}")

base, nfb = I.replay(ts, bid, ask, bars, sig, latency_ns=I.LATENCY_NS, slip_pips=0.0)
stress, nfs = I.replay(ts, bid, ask, bars, sig, latency_ns=30 * I.NS, slip_pips=0.50)
bc, sc = I.common_sample(base, stress)
mb = I.metrics(base, months, "C1 2018H1 BASE")
ms = I.metrics(stress, months, "C1 2018H1 STRESS")
mbc = I.metrics(bc, months, "C1 2018H1 BASE_COMMON")
msc = I.metrics(sc, months, "C1 2018H1 STRESS_COMMON")
for m in (mb, ms, mbc, msc):
    print(m)
print(f"NO_FILL base={nfb} stress={nfs}")

# monthly detail + save trades for independent audit
import json
out = {"base": mb, "stress": ms, "base_common": mbc, "stress_common": msc}
mon = {}
for t in base:
    m = int(months[t["j"]])
    mon.setdefault(m, []).append(t["net_pips"])
out["monthly_base"] = {m: {"N": len(v), "mean": round(float(np.mean(v)), 3),
                           "sum": round(float(np.sum(v)), 2)}
                       for m, v in sorted(mon.items())}
l = [t["r"] for t in base if t["side"] == 1]
s = [t["r"] for t in base if t["side"] == -1]
out["long_r"] = round(float(np.mean(l)), 4) if l else None
out["short_r"] = round(float(np.mean(s)), 4) if s else None
json.dump(out, open("confirm_2018h1.json", "w"), indent=1, default=str)
json.dump(base, open("confirm_trades_2018h1.json", "w"), indent=1, default=str)
print("monthly_base:", out["monthly_base"])
print("long_r:", out["long_r"], "short_r:", out["short_r"])
print("CONFIRM_DONE")
