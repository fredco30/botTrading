#!/usr/bin/env python3
"""MR_E017 FINAL INDEPENDENT AUDIT — standalone scalar implementation.

Imports NOTHING from the research code (no swing_lib/mrlib/run_screens):
re-derives rates features, FX features, decisions, sides, entries, stops,
targets, exits AND the ONE-POSITION-AT-A-TIME state machine directly from
raw parquet + roll_map.csv + the constants frozen in the spec
(708cfab). Compares against the reference trade dumps with exact
trade-set identity: AUDIT_N == REFERENCE_N, MISSING=0, EXTRA=0,
CONTENT_MISMATCHES=0.

Frozen constants (spec §3-§4): thr 2.5, cap 0.0 (ATR units), fx lookback 6
H4 bars, rates horizon 24h, vol window 30d = 43200 1m-grid bars, ATR(H4,14),
stop=target=2.5xATR, hold 48h, spreads 0.6/1.0/0.9 pip (EURUSD/GBPUSD/
USDJPY), fills per BID-layer model documented in the spec.
"""
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
NS = 10 ** 9
PIP = {"EURUSD": 1e-4, "USDJPY": 1e-2}
SPREAD = {"EURUSD": 0.6, "USDJPY": 0.9}
FX_DIR = os.path.join(HERE, "..", "..", "data_raw", "parquet")
ZN_PQ = "E:/ResearchData/botTrading/rates/databento/parquet/ZN.parquet"
THR, CAP, STOP_MULT, HOLD_H, VOL_BARS, ATR_N, FX_LB = \
    2.5, 0.0, 2.5, 48, 30 * 1440, 14, 6
TOL = 1e-6

SETS = {
    "EURUSD_DISCOVERY": dict(
        sym="EURUSD", fx=("2010-01-04", "2018-01-01"),
        rates=("2010-06-07", "2018-01-01")),
    "USDJPY_STAGE_A": dict(
        sym="USDJPY", fx=("2010-01-04", "2018-01-01"),
        rates=("2010-06-07", "2018-01-01")),
    "EURUSD_2018H2_STAGE_B": dict(
        sym="EURUSD", fx=("2018-07-01", "2019-01-01"),
        rates=("2018-05-25", "2019-01-01")),
}


def h4_bars(sym, t0, t1):
    df = pd.read_parquet(f"{FX_DIR}/{sym}_5m.parquet")
    df = df[(df.index >= pd.Timestamp(t0, tz="UTC"))
            & (df.index < pd.Timestamp(t1, tz="UTC"))]
    df = df[df["low"] > 0]
    ctns = df.index.view("int64") + 300 * NS          # 5m close times
    bucket = (ctns - 1) // (4 * 3600 * NS)
    g = df.groupby(bucket)
    o, h = g["open"].first(), g["high"].max()
    l, c = g["low"].min(), g["close"].last()
    ct_h4 = (np.array(o.index) + 1) * 4 * 3600 * NS   # close-time labels
    tr = pd.concat([h - l, (h - c.shift(1)).abs(), (l - c.shift(1)).abs()],
                   axis=1).max(axis=1)
    atr_pips = tr.rolling(ATR_N).mean().to_numpy() / PIP[sym]
    ts_open = ctns - 300 * NS                          # bar OPEN times
    return (ts_open, df["open"].to_numpy(float),
            df["high"].to_numpy(float), df["low"].to_numpy(float),
            df["close"].to_numpy(float), ct_h4, o.to_numpy(float),
            c.to_numpy(float), atr_pips)


def z24_series(t0, t1):
    zdf = pd.read_parquet(ZN_PQ)
    ts = zdf.index.view("int64")
    cl = zdf["close"].to_numpy(float)
    m = (ts >= int(pd.Timestamp(t0, tz="UTC").value)) & \
        (ts < int(pd.Timestamp(t1, tz="UTC").value))
    ts, cl = ts[m], cl[m]
    rolls = pd.read_csv(os.path.join(HERE, "roll_map.csv"))
    ends = np.array([int(pd.Timestamp(x, tz="UTC").value) + 86399 * NS
                     for x in rolls[rolls["symbol"] == "ZN"]["end_date"]])
    cidx = np.searchsorted(ends, ts, side="left")
    adj = cl.copy()
    shift = 0.0
    for i in range(1, len(ts)):
        if cidx[i] != cidx[i - 1]:
            shift += cl[i - 1] - cl[i]
        adj[i] = cl[i] + shift
    ct = ts + 60 * NS
    cs = np.cumsum(np.diff(np.log(adj), prepend=np.log(adj[0])))
    s = np.searchsorted(ct, ct - 24 * 3600 * NS, side="left")
    e = np.arange(len(ct))
    h24 = cs[e] - np.where(s > 0, cs[s - 1], 0.0)
    std = pd.Series(h24).rolling(VOL_BARS).std(ddof=0).to_numpy()
    return ct, np.where(std > 0, h24 / std, np.nan)


def audit_set(name, cfg, ref):
    sym = cfg["sym"]
    ts5, o5, h5, l5, c5, ct_h4, _, c_h4, atr = h4_bars(sym, *cfg["fx"])
    zct, zgrid = z24_series(*cfg["rates"])
    e = np.searchsorted(zct, ct_h4, side="right") - 1
    z24 = np.where(e >= 0, zgrid[np.maximum(e, 0)], np.nan)
    fx24 = np.zeros(len(c_h4))
    fx24[FX_LB:] = np.log(c_h4[FX_LB:] / c_h4[:-FX_LB]) / \
        np.maximum(atr[FX_LB:], 1e-12)
    valid = np.isfinite(atr) & (atr > 0)
    usd = np.where(z24 >= THR, -1, np.where(z24 <= -THR, 1, 0))
    take = (usd != 0) & (np.nan_to_num(fx24) * usd <= CAP) & valid
    pip = PIP[sym]
    spread = SPREAD[sym] * pip
    audit = []
    last_exit = -1
    broken = False
    for i in np.flatnonzero(take):
        if broken:
            break
        d = int(ct_h4[i])
        if d < last_exit:                     # suppression while position open
            continue
        s = int(usd[i])
        dist = float(atr[i] * STOP_MULT)      # pips
        k = int(np.searchsorted(ts5, d, side="left"))
        if k >= len(ts5) - 1:
            broken = True
            break
        sd = dist * pip
        if s == 1:
            entry = float(o5[k]) + spread
            stop = entry - sd; tgt = entry + sd
        else:
            entry = float(o5[k])
            stop_bid = entry + sd - spread; stop = entry + sd
            tgt_bid = entry - sd - spread; tgt = entry - sd
        m_end = int(np.searchsorted(ts5, int(ts5[k]) + HOLD_H * 3600 * NS,
                                    side="right")) - 1
        m0 = k + 1
        exit_px = exit_ts = None; reason = "OPEN"
        if m_end >= m0:
            i_s = np.flatnonzero(l5[m0:m_end + 1] <= stop) if s == 1 \
                else np.flatnonzero(h5[m0:m_end + 1] >= stop_bid)
            i_t = np.flatnonzero(h5[m0:m_end + 1] >= tgt) if s == 1 \
                else np.flatnonzero(l5[m0:m_end + 1] <= tgt_bid)
            i_s = int(i_s[0]) if len(i_s) else 10 ** 12
            i_t = int(i_t[0]) if len(i_t) else 10 ** 12
            if i_s <= i_t and i_s < 10 ** 12:
                m = m0 + i_s
                exit_px = (min(stop, float(o5[m0 + i_s])) if s == 1
                           else max(stop, float(o5[m0 + i_s]) + spread))
                exit_ts = int(ts5[m]); reason = "STOP"
            elif i_t < 10 ** 12:
                m = m0 + i_t
                exit_px = float(tgt)
                exit_ts = int(ts5[m]); reason = "TARGET"
            else:
                m = m_end
                exit_px = float(c5[m]) if s == 1 else float(c5[m]) + spread
                exit_ts = int(ts5[m]) + 300 * NS; reason = "TIME"
        else:
            m = min(m_end, len(ts5) - 1)
            exit_px = float(c5[m]) if s == 1 else float(c5[m]) + spread
            exit_ts = int(ts5[m]) + 300 * NS; reason = "TIME"
        audit.append({
            "decision_ts": d,
            "max_rates_input_ts": int(zct[max(e[i], 0)]),
            "max_fx_input_close": d,          # H4 close label == decision ts
            "side": s, "entry_ts": int(ts5[k]), "entry": float(entry),
            "atr_pips": float(atr[i]), "stop_dist": dist,
            "target_dist": dist, "exit_ts": int(exit_ts),
            "reason": reason, "exit_px": float(exit_px),
            "net_pips": s * (exit_px - entry) / pip,
            "r": s * (exit_px - entry) / sd})
        last_exit = int(exit_ts)

    # ---------------- trade-set identity ----------------
    ref_by = {int(t["decision_ts"]): t for t in ref}
    aud_by = {t["decision_ts"]: t for t in audit}
    missing = sorted(set(ref_by) - set(aud_by))
    extra = sorted(set(aud_by) - set(ref_by))
    matched, bad = 0, []
    for dts in sorted(set(ref_by) & set(aud_by)):
        r0, a = ref_by[dts], aud_by[dts]
        checks = {
            "side": r0["side"] == a["side"],
            "entry_ts": r0["entry_ts"] == a["entry_ts"],
            "entry_px": abs(r0["entry"] - a["entry"]) < TOL,
            "atr": abs(r0["risk_pips"] / STOP_MULT - a["atr_pips"]) < TOL,
            "stop_dist": abs(r0["risk_pips"] - a["stop_dist"]) < TOL,
            "target_dist": abs(r0["risk_pips"] - a["target_dist"]) < TOL,
            "exit_ts": r0["exit_ts"] == a["exit_ts"],
            "reason": r0["reason"] == a["reason"],
            "exit_px": abs(r0["exit_px"] - a["exit_px"]) < TOL,
            "net_pips": abs(r0["net_pips"] - a["net_pips"]) < TOL,
            "r": abs(r0["r"] - a["r"]) < TOL,
            "causal_rates": a["max_rates_input_ts"] <= dts,
            "causal_fx": a["max_fx_input_close"] <= dts,
        }
        if all(checks.values()):
            matched += 1
        else:
            bad.append({"decision_ts": dts,
                        "failed": [k for k, v in checks.items() if not v],
                        "expected": {k: r0[k] for k in
                                     ("side", "entry", "net_pips", "r",
                                      "reason")},
                        "observed": {k: a[k] for k in
                                     ("side", "entry", "net_pips", "r",
                                      "reason")}})
    res = {"REFERENCE_N": len(ref), "AUDIT_N": len(audit),
           "MATCHED_N": matched, "MISSING_TRADES": len(missing),
           "EXTRA_TRADES": len(extra), "CONTENT_MISMATCHES": len(bad)}
    if bad:
        res["first_mismatch"] = bad[0]
    if missing:
        res["first_missing_ts"] = missing[0]
    if extra:
        res["first_extra_ts"] = extra[0]
    causality_ok = all(t["max_rates_input_ts"] <= t["decision_ts"]
                       and t["max_fx_input_close"] <= t["decision_ts"]
                       for t in audit)
    res["causality_all_trades"] = "PASS" if causality_ok else "FAIL"
    res["set_pass"] = (res["AUDIT_N"] == res["REFERENCE_N"]
                       and res["MISSING_TRADES"] == 0
                       and res["EXTRA_TRADES"] == 0
                       and res["CONTENT_MISMATCHES"] == 0
                       and causality_ok)
    print(f"{name}: REF={res['REFERENCE_N']} AUDIT={res['AUDIT_N']} "
          f"MATCHED={matched} MISSING={res['MISSING_TRADES']} "
          f"EXTRA={res['EXTRA_TRADES']} MISMATCH={res['CONTENT_MISMATCHES']} "
          f"CAUSALITY={res['causality_all_trades']} -> "
          f"{'PASS' if res['set_pass'] else 'FAIL'}")
    if bad:
        print("  first mismatch:", json.dumps(bad[0], default=str)[:400])
    return res


ref_all = json.load(open(os.path.join(HERE, "cache",
                                      "reference_trades_final.json")))
results = {}
for name, cfg in SETS.items():
    key = {"EURUSD_DISCOVERY": "A_eurusd_discovery",
           "USDJPY_STAGE_A": "B_usdjpy_stage_a",
           "EURUSD_2018H2_STAGE_B": "C_eurusd_2018h2"}[name]
    results[name] = audit_set(name, cfg, ref_all[key])

all_pass = all(r["set_pass"] for r in results.values())
print(f"\nFINAL_STATUS={'FULL_INDEPENDENT_AUDIT_PASS' if all_pass else 'AUDIT_FAIL'}")
json.dump(results, open(os.path.join(HERE, "cache",
                                     "final_independent_audit.json"), "w"),
          indent=1, default=str)
