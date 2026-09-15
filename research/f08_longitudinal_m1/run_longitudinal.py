#!/usr/bin/env python3
"""F08_LONGITUDINAL_M1 — frozen replay of F08 (lb=180, fade=2 absorption
reversal) on 2010..2016. NO rule changes: imports the frozen feature and
sign functions exactly as committed at 482c02c.

Steps per year: load validated ticks -> M1 bars -> frozen extras/feature ->
signal vector -> tick-exact replay (baseline 5s/0slip; stress 30s/+0.5pip/side)
-> common intersection. Plus: causality gate re-run on 2010 (unseen year)."""
import json
import sys
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "autonomous_edge_discovery_m1"))
import m1lib as M          # frozen infrastructure (validated)
import infra_lib as I      # frozen replay engine
import families as F       # frozen feature helpers
from f08_plateau import make_feat, build_ex, sign_both   # FROZEN C1 feature
import validated_mtf_lib as mtf_lib

PIP = I.PIP
FEAT = make_feat(180, 2)
BEX = build_ex(180)
SIGN = sign_both

YEARS = [2010, 2011, 2012, 2013, 2014, 2015, 2016]


# ---------------- causality gate re-run on unseen 2010 data (mission 5) ----
def gate_2010():
    ts, bid, ask = I.load_year(2010)
    bars = M.add_n_ticks(ts, I.m1_bars(ts, bid, ask))
    ex = BEX(ts, bid, ask, bars)
    n = len(bars["close"])
    rng = np.random.default_rng(20100104)
    finite = []
    for j in range(500, n):
        f = FEAT(bars, ex, j)
        if f is not None and f["value"] is not None and np.isfinite(f["value"]):
            finite.append(j)
    picks = list(rng.permutation(finite)[:24])
    t1 = t2 = t3 = True
    for j in picks:
        T = int(bars["close_time"][j])
        f = FEAT(bars, ex, int(j))
        its, aux = [int(x) for x in f["input_ts"]], f.get("aux")
        t1 &= all(x <= T for x in its)
        m = int(np.searchsorted(ts, T, side="right"))
        bt = M.add_n_ticks(ts[:m], I.m1_bars(ts[:m], bid[:m], ask[:m]))
        et = BEX(ts[:m], bid[:m], ask[:m], bt)
        jt = int(np.searchsorted(bt["close_time"], T, side="left"))
        f2 = FEAT(bt, et, jt) if (jt < len(bt["close_time"])
                                  and bt["close_time"][jt] == T) else None
        t2 &= (f2 is not None and f2["value"] is not None
               and f2["value"] == f["value"]
               and [int(x) for x in f2["input_ts"]] == its
               and f2.get("aux") == aux)
        b3, a3 = bid.copy(), ask.copy()
        mut = ts > T
        b3[mut] += 50 * PIP
        a3[mut] += 50 * PIP
        bm = M.add_n_ticks(ts, I.m1_bars(ts, b3, a3))
        em = BEX(ts, b3, a3, bm)
        f3 = FEAT(bm, em, int(j))
        t3 &= (f3 is not None and f3["value"] is not None
               and f3["value"] == f["value"]
               and [int(x) for x in f3["input_ts"]] == its
               and f3.get("aux") == aux)
    ok = t1 and t2 and t3 and len(picks) >= 20
    print(f"CAUSALITY_GATE_2010: T1={t1} T2={t2} T3={t3} ({len(picks)} tested) "
          f"-> {'PASS' if ok else 'FAIL'}")
    return ok


def year_run(year):
    ts, bid, ask = I.load_year(year)
    bars = M.add_n_ticks(ts, I.m1_bars(ts, bid, ask))
    ex = BEX(ts, bid, ask, bars)
    sig = M.signal_vector(FEAT, SIGN, ts, bid, ask, bars, ex)
    base, _ = I.replay(ts, bid, ask, bars, sig, latency_ns=I.LATENCY_NS, slip_pips=0.0)
    stress, _ = I.replay(ts, bid, ask, bars, sig, latency_ns=30 * I.NS, slip_pips=0.50)
    bc, sc = I.common_sample(base, stress)
    months = pd.to_datetime(bars["close_time"], utc=True).month.to_numpy()
    mb = I.metrics(base, months, f"{year} BASE")
    ms = I.metrics(stress, months, f"{year} STRESS")
    mbc = I.metrics(bc, months, f"{year} BASE_COMMON")
    msc = I.metrics(sc, months, f"{year} STRESS_COMMON")
    return base, stress, bc, sc, mb, ms, mbc, msc


def agg_metrics(trades, label):
    """Pooled aggregate metrics from trade dicts (chronological)."""
    if not trades:
        return {"label": label, "N": 0}
    net = np.array([t["net_pips"] for t in trades])
    r = np.array([t["r"] for t in trades])
    ym = [f"{pd.Timestamp(t['entry_ts'], unit='ns', tz='UTC').year}-"
          f"{pd.Timestamp(t['entry_ts'], unit='ns', tz='UTC').month:02d}"
          for t in trades]
    dfm = pd.Series(net, index=ym).groupby(level=0).sum()
    pos_months = int((dfm > 0).sum())
    lr = [t["r"] for t in trades if t["side"] == 1]
    sr = [t["r"] for t in trades if t["side"] == -1]
    order = np.argsort([t["entry_ts"] for t in trades])
    cum = np.cumsum(r[order])
    peak = np.maximum.accumulate(cum)
    consec = best = 0
    for v in r[order]:
        consec = consec + 1 if v < 0 else 0
        best = max(best, consec)
    years = sorted({pd.Timestamp(t['entry_ts'], unit='ns', tz='UTC').year
                    for t in trades})
    pos_years = 0
    for y in years:
        yt = [t for t in trades
              if pd.Timestamp(t['entry_ts'], unit='ns', tz='UTC').year == y]
        if sum(t["net_pips"] for t in yt) > 0:
            pos_years += 1
    wins, losses = net[net > 0], net[net < 0]
    pf = min(float(wins.sum() / abs(losses.sum())), 999.0) if len(losses) and losses.sum() else 999.0
    return {"label": label, "N": len(trades),
            "mean_pips": round(float(net.mean()), 3),
            "total_pips": round(float(net.sum()), 2), "PF": round(pf, 3),
            "expectancy_r": round(float(r.mean()), 4),
            "win_rate": round(float((net > 0).mean()), 4),
            "long_r": round(float(np.mean(lr)), 4) if lr else None,
            "short_r": round(float(np.mean(sr)), 4) if sr else None,
            "pos_months": pos_months, "n_months": len(dfm),
            "pos_years": f"{pos_years}/{len(years)}",
            "remove_best": round(float(I.remove_best_1pct(net)), 3),
            "max_dd_r": round(float((peak - cum).max()), 2),
            "max_consec_losses": int(best)}


def main():
    if not gate_2010():
        print("FEATURE_CAUSALITY=FAIL -> STOP")
        return
    out = {"years": {}, "trades": {}}
    all_base, all_stress, all_bc, all_sc = [], [], [], []
    for y in YEARS:
        base, stress, bc, sc, mb, ms, mbc, msc = year_run(y)
        out["years"][y] = {"base": mb, "stress": ms,
                           "base_common": mbc, "stress_common": msc}
        out["trades"][y] = base
        all_base += base
        all_stress += stress
        all_bc += bc
        all_sc += sc
        print(f"{y}: N={mb.get('N')} mean={mb.get('mean_pips')} PF={mb.get('PF')} "
              f"expR={mb.get('expectancy_r')} L={mb.get('long_r')} S={mb.get('short_r')} "
              f"posmon={mb.get('pos_months')} rb={mb.get('remove_best')} "
              f"sCOMMON_EV={msc.get('mean_pips')}")
    out["agg_2010_2016"] = {
        "base": agg_metrics(all_base, "AGG 2010-2016 BASE"),
        "stress": agg_metrics(all_stress, "AGG 2010-2016 STRESS"),
        "base_common": agg_metrics(all_bc, "AGG 2010-2016 BASE_COMMON"),
        "stress_common": agg_metrics(all_sc, "AGG 2010-2016 STRESS_COMMON")}
    json.dump(out, open("longitudinal_results.json", "w"), indent=1, default=str)
    print(json.dumps(out["agg_2010_2016"]["base"], indent=1))
    print(json.dumps(out["agg_2010_2016"]["stress_common"], indent=1))
    print("LONGITUDINAL_DONE")


if __name__ == "__main__":
    main()
