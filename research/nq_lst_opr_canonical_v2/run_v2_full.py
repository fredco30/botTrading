#!/usr/bin/env python3
"""Run LST_OPR_CANONICAL_V2: A / B / C, NORMAL + STRESS, full 2N metrics."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_modern_strategy_lab"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_lst_opr_engineered_v1"))
import lab_lib as L   # noqa: E402
import lst_v2_lib as S  # noqa: E402
import nq_lib as N    # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "results"
POINT_USD = 20.0
TICK = 0.25


def full_metrics(df5, vc, tf, stats, weeks):
    m = dict(stats)
    if tf is None or tf.empty:
        return {**m, "TRADES": 0}
    net = tf["net"].to_numpy()
    r = tf["R_MULT"].to_numpy()
    pos, neg = net[net > 0].sum(), -net[net < 0].sum()
    sr = np.sort(net)[::-1]
    top = max(1, int(round(0.01 * len(net))))
    dd_pts, _ = N.drawdown_metrics(net)
    dd_r, _ = N.drawdown_metrics(np.nan_to_num(r, nan=0.0))
    yrs = N._to_et(tf["entry_ts"]).year
    idx = df5.index
    pos_of = {ts: k for k, ts in enumerate(idx)}
    mfe, mae = [], []
    for _, t in tf.iterrows():
        i0 = pos_of.get(t["entry_ts"]); i1 = pos_of.get(t["exit_ts"])
        if i0 is None or i1 is None:
            mfe.append(np.nan); mae.append(np.nan); continue
        side = int(t["side"]); fill = float(t["fill"])
        hs = df5["high"].iloc[i0:i1+1].to_numpy(); ls = df5["low"].iloc[i0:i1+1].to_numpy()
        mfe.append(float(np.maximum(side*(hs-fill), side*(ls-fill)).max()))
        mae.append(float(np.maximum(side*(fill-hs), side*(fill-ls)).max()))
    tf2 = tf.assign(MFE=mfe, MAE=mae)
    cap = (tf2["net"] / tf2["MFE"].replace(0, np.nan)).median()
    m.update({
        "TRADES": int(len(net)),
        "TRADES_PER_WEEK": round(len(net) / weeks, 3),
        "GROSS_POINTS_PER_TRADE": round(float(tf["gross"].mean()), 4),
        "NET_POINTS_PER_TRADE": round(float(net.mean()), 4),
        "NET_TICKS_PER_TRADE": round(float(net.mean()) / TICK, 2),
        "NET_USD_PER_NQ": round(float(net.mean()) * POINT_USD, 2),
        "PF": round(float(pos / neg), 4) if neg > 0 else None,
        "EXPECTANCY_R": round(float(np.nanmean(r)), 4),
        "WIN_RATE": round(float((net > 0).mean()), 4),
        "AVG_WIN_R": round(float(np.nanmean(r[net > 0])), 3) if (net > 0).any() else None,
        "AVG_LOSS_R": round(float(np.nanmean(r[net <= 0])), 3) if (net <= 0).any() else None,
        "REMOVE_BEST_1_PERCENT": round(float(sr[top:].mean()), 4),
        "MAX_DD_R": round(dd_r, 3),
        "MAX_DD_POINTS": round(dd_pts, 2),
        "MAX_DD_USD_1NQ": round(dd_pts * POINT_USD, 2),
        "BY_YEAR_NET_PTS": {int(y): round(float(net[np.asarray(yrs) == y].mean()), 3)
                            for y in sorted(set(yrs))},
        "BY_YEAR_N": {int(y): int((np.asarray(yrs) == y).sum()) for y in sorted(set(yrs))},
        "LONG_N": int((tf["side"] == 1).sum()), "SHORT_N": int((tf["side"] == -1).sum()),
        "EXIT_REASON": {k: int(v) for k, v in tf["exit_reason"].value_counts().items()},
        "MFE_MEAN_PTS": round(float(np.nanmean(mfe)), 3),
        "MAE_MEAN_PTS": round(float(np.nanmean(mae)), 3),
        "CAPTURE_RATIO": round(float(cap), 4) if cap == cap else None,
    })
    return m


def diagnostics(df5, vc, tf):
    if tf.empty:
        return {}
    et = N._to_et(tf["entry_ts"])
    wid, atrv, fs = [], [], []
    day_map = {str(vc.x.day_of[gi]): d for gi, d in vc.days.items()}
    h1 = S.build_h1(df5)
    for ts, day in zip(tf["entry_ts"], et.date):
        d = day_map.get(str(day))
        if d is None or d.oh != d.oh:
            wid.append(np.nan); atrv.append(np.nan); fs.append(np.nan)
            continue
        wid.append(d.oh - d.ol); atrv.append(d.atr)
        # flow strength: |decision H1 close - EMA50| / ATR (diagnostic only)
        t_start = (int(ts.value) // (3600 * 10**9) - 1) * (3600 * 10**9)
        pos = h1.index.asi8.searchsorted(t_start)
        if pos < len(h1) and h1.index.asi8[pos] == t_start and h1["atr14"].iloc[pos] == h1["atr14"].iloc[pos]:
            fs.append(abs(h1["close"].iloc[pos] - h1["ema50"].iloc[pos]) / h1["atr14"].iloc[pos])
        else:
            fs.append(np.nan)
    hm = et.hour * 100 + et.minute
    bucket = ["0945-1015" if v < 1015 else ("1015-1100" if v < 1100 else "1100-1130") for v in hm]
    tf2 = tf.assign(W=wid, A=atrv, F=fs, BUCKET=bucket)
    out = {}
    for col, key in (("W", "BY_OPR_WIDTH_ATR_QUARTILE"), ("A", "BY_ATR_QUARTILE"),
                     ("F", "BY_FLOW_STRENGTH_QUARTILE")):
        v = tf2[col].to_numpy(float)
        ok = v == v
        if ok.sum() < 8:
            out[key] = "INSUFFICIENT"
            continue
        q = pd.qcut(pd.Series(v[ok]).rank(method="first"), 4, labels=["Q1", "Q2", "Q3", "Q4"])
        out[key] = {k: round(float(s.mean()), 3)
                    for k, s in tf2[ok].assign(Q=q.values).groupby("Q", observed=True)["net"]}
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
    if not (m.get("NET_POINTS_PER_TRADE", 0) > 0):
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
    vc = S.V2Ctx(x)
    weeks = len(x.groups) / 5.0
    OUT.mkdir(exist_ok=True)
    results = {}
    for variant in ("A", "B", "C"):
        res = {}
        for tier in ("NORMAL", "STRESS"):
            tr, stats = S.run_v2(x, vc, variant, S.COSTS[tier])
            tf = pd.DataFrame(tr)
            m = full_metrics(df5, vc, tf, stats, weeks)
            if tier == "NORMAL":
                m["DIAGNOSTICS_2O"] = diagnostics(df5, vc, tf)
            else:
                m = {"STRESS_POINTS": m.get("NET_POINTS_PER_TRADE"),
                     "STRESS_PF": m.get("PF"), "STRESS_TRADES": m.get("TRADES"),
                     "STRESS_NET_USD": m.get("NET_USD_PER_NQ")}
            res[tier] = m
        fails = gate(res["NORMAL"])
        res["GATE"] = "PASS" if not fails else "FAIL:" + ";".join(fails)
        results[variant] = res
        n = res["NORMAL"]
        print(f"[{variant}] N={n.get('TRADES')} tpw={n.get('TRADES_PER_WEEK')} "
              f"NET={n.get('NET_POINTS_PER_TRADE')}pts (${n.get('NET_USD_PER_NQ')}) "
              f"PF={n.get('PF')} R={n.get('EXPECTANCY_R')} WR={n.get('WIN_RATE')} "
              f"RM={n.get('REMOVE_BEST_1_PERCENT')} STRESS={res['STRESS']['STRESS_POINTS']} "
              f"maxDD=${n.get('MAX_DD_USD_1NQ')} -> {res['GATE'][:90]}")
        print(f"     setups={n.get('SETUPS_A')}/{n.get('SETUPS_B')} "
              f"cancelATR={n.get('CANCELLED_ATR')} cancel1R={n.get('CANCELLED_1R')} "
              f"obsRej={n.get('OBSTACLE_REJECTS')} rrRej={n.get('RR_REJECTS')}")
        print(f"     years={n.get('BY_YEAR_NET_PTS')} exits={n.get('EXIT_REASON')}")
    (OUT / "lst_v2_results.json").write_text(json.dumps(results, indent=1, default=str))
    print("WROTE", OUT / "lst_v2_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
