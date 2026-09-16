#!/usr/bin/env python3
"""Run LST_OPR_ENGINEERED_V1: variants A / B / C, NORMAL + STRESS costs.

Outputs results/lst_results.json + prints the mission-2N metric blocks.
Diagnostics (2O) are REPORT-ONLY. No optimization happens here.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_modern_strategy_lab"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
import lab_lib as L   # noqa: E402
import lst_lib as S   # noqa: E402
import nq_lib as N    # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "results"
POINT_USD = 20.0
TICK = 0.25


def full_metrics(df5, tf, stats, weeks):
    m = L.metrics(tf, weeks) if not tf.empty else {"N": 0}
    out = dict(stats)
    if tf.empty:
        return {**out, "TRADES": 0}
    net = tf["net"].to_numpy()
    r = tf["R_MULT"].to_numpy()
    rr = tf["R0"].to_numpy()
    pos, neg = net[net > 0].sum(), -net[net < 0].sum()
    sr = np.sort(net)[::-1]
    top = max(1, int(round(0.01 * len(net))))
    dd_pts, _ = N.drawdown_metrics(net)
    dd_r, _ = N.drawdown_metrics(np.nan_to_num(r, nan=0.0))
    yrs = N._to_et(tf["entry_ts"]).year
    # MFE/MAE from 5m bars
    idx = df5.index
    pos_of = {ts: k for k, ts in enumerate(idx)}
    mfe, mae = [], []
    for _, t in tf.iterrows():
        i0 = pos_of.get(t["entry_ts"]); i1 = pos_of.get(t["exit_ts"])
        if i0 is None or i1 is None:
            mfe.append(np.nan); mae.append(np.nan); continue
        side = int(t["side"]); fill = float(t["fill"])
        fav = np.maximum(side * (df5["high"].iloc[i0:i1+1].to_numpy() - fill),
                         side * (df5["low"].iloc[i0:i1+1].to_numpy() - fill))
        adv = np.maximum(side * (fill - df5["high"].iloc[i0:i1+1].to_numpy()),
                         side * (fill - df5["low"].iloc[i0:i1+1].to_numpy()))
        mfe.append(float(fav.max())); mae.append(float(adv.max()))
    tf2 = tf.assign(MFE=mfe, MAE=mae)
    cap = (tf2["net"] / tf2["MFE"].replace(0, np.nan)).median()
    out.update({
        "TRADES": int(len(net)),
        "TRADES_PER_WEEK": round(len(net) / weeks, 3),
        "NET_INDEX_POINTS_PER_TRADE": round(float(net.mean()), 4),
        "NET_TICKS_PER_TRADE": round(float(net.mean()) / TICK, 2),
        "NET_USD_PER_NQ": round(float(net.mean()) * POINT_USD, 2),
        "PF": round(float(pos / neg), 4) if neg > 0 else None,
        "EXPECTANCY_R": round(float(np.nanmean(r)), 4),
        "WIN_RATE": round(float((net > 0).mean()), 4),
        "AVG_WIN_R": round(float(np.nanmean(r[net > 0])), 3) if (net > 0).any() else None,
        "AVG_LOSS_R": round(float(np.nanmean(r[net <= 0])), 3) if (net <= 0).any() else None,
        "MFE_MEAN_PTS": round(float(np.nanmean(mfe)), 3),
        "MAE_MEAN_PTS": round(float(np.nanmean(mae)), 3),
        "CAPTURE_RATIO": round(float(cap), 4) if cap == cap else None,
        "STRESS_READY": True,
        "REMOVE_BEST_1_PERCENT": round(float(sr[top:].mean()), 4),
        "MAX_DD_R": round(dd_r, 3),
        "MAX_DD_USD_1NQ": round(dd_pts * POINT_USD, 2),
        "BY_YEAR_NET_PTS": {int(y): round(float(net[np.asarray(yrs) == y].mean()), 3)
                            for y in sorted(set(yrs))},
        "BY_YEAR_N": {int(y): int((np.asarray(yrs) == y).sum()) for y in sorted(set(yrs))},
        "EXIT_REASON_BREAKDOWN": {k: int(v) for k, v in tf["exit_reason"].value_counts().items()},
        "LONG_N": int((tf["side"] == 1).sum()), "SHORT_N": int((tf["side"] == -1).sum()),
    })
    return out


def diagnostics(df5, lc, tf):
    """2O — report-only. OPR-width quartile, ATR quartile, side, time bucket,
    folds. NO optimization on these."""
    if tf.empty:
        return {}
    idx = df5.index
    pos_of = {ts: k for k, ts in enumerate(idx)}
    wid, atrv, bucket = [], [], []
    for _, t in tf.iterrows():
        # recover day ctx via entry date
        d = None
        et_day = N._to_et([t["entry_ts"]])[0].date()
        for gi, dc in lc.days.items():
            if str(lc.x.day_of[gi]) == str(et_day):
                d = dc
                break
        if d is None or d.oh != d.oh:
            wid.append(np.nan); atrv.append(np.nan)
        else:
            wid.append(d.oh - d.ol); atrv.append(d.atr)
        hm = N._to_et([t["entry_ts"]])[0].hour * 100 + N._to_et([t["entry_ts"]])[0].minute
        bucket.append("0945-1015" if hm < 1015 else ("1015-1100" if hm < 1100 else "1100-1130"))
    tf2 = tf.assign(W=wid, A=atrv, BUCKET=bucket)
    out = {}
    for col, key, lab in (("W", "BY_OPR_WIDTH_QUARTILE", "width"),
                          ("A", "BY_ATR_QUARTILE", "atr")):
        v = tf2[col].to_numpy(float)
        ok = v == v
        q = pd.qcut(pd.Series(v[ok]).rank(method="first"), 4,
                    labels=["Q1", "Q2", "Q3", "Q4"])
        qq = pd.Series(np.nan, index=tf2.index[ok])
        qq[:] = q.values
        g = tf2[ok].assign(Q=qq.values).groupby("Q", observed=True)["net"]
        out[key] = {k: round(float(s.mean()), 3) for k, s in g}
    out["BY_SIDE"] = {"LONG": round(float(tf2[tf2.side == 1]["net"].mean()), 3) if (tf2.side == 1).any() else None,
                      "SHORT": round(float(tf2[tf2.side == -1]["net"].mean()), 3) if (tf2.side == -1).any() else None}
    out["BY_ENTRY_BUCKET"] = {k: round(float(s.mean()), 3) for k, s in tf2.groupby("BUCKET")["net"]}
    folds = tf2["entry_ts"].map(L.fold_of)
    out["BY_FOLD"] = {f: round(float(tf2[np.asarray(folds) == f]["net"].mean()), 3)
                      for f in sorted(set(folds))}
    return out


def gate(m):
    fails = []
    if m.get("TRADES", 0) < 40:
        fails.append(f"N<40 ({m.get('TRADES')})")
    if not (m.get("NET_INDEX_POINTS_PER_TRADE", 0) > 0):
        fails.append("net<=0")
    if m.get("PF") is None or m["PF"] < 1.15:
        fails.append(f"PF={m.get('PF')}")
    if not (m.get("REMOVE_BEST_1_PERCENT", -1) > 0):
        fails.append("rm_best<=0")
    byy = m.get("BY_YEAR_NET_PTS", {})
    if sum(1 for v in byy.values() if v > 0) < 4:
        fails.append("pos_years<4")
    tot = sum(byy.values())
    if tot > 0 and max(byy.values()) / tot > 0.60:
        fails.append("year_concentration")
    return fails


def main() -> int:
    df5 = N.load_5m()
    x = L.build_ctx(df5)
    lc = S.LstCtx(x)
    weeks = len(x.groups) / 5.0
    OUT.mkdir(exist_ok=True)
    results = {}
    for variant in ("A", "B", "C"):
        res = {"NORMAL": None, "STRESS": None}
        for tier in ("NORMAL", "STRESS"):
            tr, stats = S.run_lst(x, lc, variant, S.COSTS[tier])
            tf = pd.DataFrame(tr)
            m = full_metrics(df5, tf, stats, weeks)
            if tier == "NORMAL":
                m["DIAGNOSTICS_2O"] = diagnostics(df5, lc, tf)
            else:
                m = {"STRESS_NET_POINTS": m.get("NET_INDEX_POINTS_PER_TRADE"),
                     "STRESS_PF": m.get("PF"), "STRESS_TRADES": m.get("TRADES"),
                     "STRESS_NET_USD": m.get("NET_USD_PER_NQ")}
            res[tier] = m
        fails = gate(res["NORMAL"])
        res["GATE"] = "PASS" if not fails else "FAIL:" + ";".join(fails)
        results[variant] = res
        n = res["NORMAL"]
        print(f"[{variant}] N={n.get('TRADES')} tpw={n.get('TRADES_PER_WEEK')} "
              f"NET={n.get('NET_INDEX_POINTS_PER_TRADE')}pts (${n.get('NET_USD_PER_NQ')}) "
              f"PF={n.get('PF')} R={n.get('EXPECTANCY_R')} WR={n.get('WIN_RATE')} "
              f"RM={n.get('REMOVE_BEST_1_PERCENT')} STRESS={res['STRESS']['STRESS_NET_POINTS']} "
              f"maxDD=${n.get('MAX_DD_USD_1NQ')} -> {res['GATE'][:90]}")
        print(f"     years={n.get('BY_YEAR_NET_PTS')} exits={n.get('EXIT_REASON_BREAKDOWN')}")
    (OUT / "lst_results.json").write_text(json.dumps(results, indent=1, default=str))
    print("WROTE", OUT / "lst_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
