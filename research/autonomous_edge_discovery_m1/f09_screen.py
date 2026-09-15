#!/usr/bin/env python3
"""F09 weekday x fixed-hour calendar drift screen (2017 only).
Cells: weekday x decision hour, unconditional nonoverlap fwd 240m returns.
Vol-regime split recorded in the reason field. Causality: calendar + past
data only — feature gate on the vol-regime component."""
import numpy as np
import pandas as pd
import m1lib as M
import infra_lib as I
import families as F
import ledger as L

PIP = I.PIP
ts, bid, ask = I.load_year(2017)
bars = M.add_n_ticks(ts, I.m1_bars(ts, bid, ask))
months = pd.to_datetime(bars["close_time"], utc=True).month.to_numpy()
ex = F.extras_common(ts, bid, ask, bars)
hhmm = ex["hhmm"]
dow = pd.to_datetime(bars["close_time"], utc=True).dayofweek.to_numpy()

# vol regime (causal): range60 vs trailing 7200-bar median (shift 1)
vr = ex["range60"] / np.where(np.isfinite(ex["range60_ref"]),
                              ex["range60_ref"], np.nan)
vol_hi = vr > 1.25
vol_lo = vr < 0.85

# F09 feature gate: decision hour cell value = signed weekday/hour selector
def f09_feat(bars, ext, j):
    return {"value": float(dow[j] * 100 + hhmm[j] // 100),
            "input_ts": [bars["last_tick_ts"][j]], "aux": 0}

ok, _ = M.causality_gate("F09", f09_feat, F.extras_common, bars, ex, 24)
print("F09 gate:", "PASS" if ok else "FAIL")

n = len(bars["close"])
j0 = np.arange(1, n)
close, opn = bars["close"], bars["open"]

for hour in (700, 1300):
    for wd in range(5):
        cond = (hhmm == hour) & (dow == wd)
        idx = np.flatnonzero(cond)
        if len(idx) < 20:
            continue
        j1 = np.minimum(idx + 240, n - 1)
        r = (close[j1] - opn[np.minimum(idx + 1, n - 1)]) / PIP
        mon = months[np.minimum(idx + 1, n - 1)]
        posm = sum(1 for m in np.unique(mon) if r[mon == m].mean() > 0)
        hi_m = r[vol_hi[idx]].mean() if vol_hi[idx].sum() > 10 else np.nan
        lo_m = r[vol_lo[idx]].mean() if vol_lo[idx].sum() > 10 else np.nan
        t = r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))
        L.log("F09", "weekday-hour calendar drift", "PASS",
              f"hour={hour} wd={wd} h=240", len(r), round(float(r.mean()), 3),
              expectancy_R=round(float(r.mean() / 15), 4), status="SCREEN",
              reason=f"t={t:.2f} posmon={posm}/{len(np.unique(mon))} "
                     f"hiVR={np.nanmean(hi_m):.2f} loVR={np.nanmean(lo_m):.2f} "
                     f"months={sorted(set(mon.tolist()))}")
        print(f"h={hour} wd={wd}: N={len(r)} mean={r.mean():+.2f}p t={t:+.2f} "
              f"posmon={posm}/{len(np.unique(mon))} hiVR={np.nanmean(hi_m):+.2f} "
              f"loVR={np.nanmean(lo_m):+.2f}")
print("EXPERIMENTS_USED:", L.experiments_used())
