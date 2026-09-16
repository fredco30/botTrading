#!/usr/bin/env python3
"""Replay all 133 frozen O01 trades on BBO-1s + traces + final aggregates."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
import o01_replay as R  # noqa: E402
import nq_lib as N  # noqa: E402

HERE = Path(__file__).parent
OUT = HERE / "results"
POINT_USD = 20.0
SCENARIOS = [("L1_BASE", "NORMAL"), ("L1_CONSERVATIVE", "NORMAL"),
             ("L1_STRESS", "STRESS")]


def main() -> int:
    trades = pd.read_csv(HERE / "O01_FROZEN_TRADE_LIST.csv")
    rows = []
    for k, t in trades.iterrows():
        wid = f"{t['DATE']}_{t['ACTUAL_FUTURES_CONTRACT']}"
        f = R.Path(r"E:/ResearchData/botTrading/nq/databento/highres/bbo_1s_o01") / f"{wid}.dbn.zst"
        if not f.exists():
            print("MISSING", wid)
            continue
        w = R.BboWindow(f)
        rec = {"TRADE_ID": t["TRADE_ID"], "DATE": t["DATE"], "SIDE": t["SIDE"],
               "R0": abs(t["MODELED_ENTRY"] - t["INITIAL_STOP"])}
        for scen, tier in SCENARIOS:
            r = R.replay_o01(dict(t), w, scen, tier)
            rec[f"{scen}_NET"] = r["net"]
            rec[f"{scen}_GROSS"] = r["gross"]
            if scen == "L1_BASE":
                rec.update({
                    "ENTRY_SPREAD": r["entry_spread"], "EXIT_SPREAD": r["exit_spread"],
                    "BBO_ENTRY": r["entry_exec"], "BBO_EXIT": r["exit_exec"],
                    "FLAG": r["flag"], "AMBIGUITY": r["ambiguity"],
                    "ENTRY_DELTA": abs(r["entry_exec"] - t["MODELED_ENTRY"]),
                    "EXIT_DELTA": abs(r["exit_exec"] - t["MODELED_FINAL_EXIT"]),
                })
        rows.append(rec)
        if (k + 1) % 50 == 0:
            print(f"{k + 1}/133", flush=True)
    r = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    r.to_csv(OUT / "o01_bbo_replay_trades.csv", index=False)

    def agg(col):
        v = r[col].to_numpy(float)
        v = v[~np.isnan(v)]
        pos_, neg_ = v[v > 0].sum(), -v[v < 0].sum()
        sr = np.sort(v)[::-1]
        top = max(1, int(round(0.01 * len(v))))
        eq = np.cumsum(v)
        peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))
        dd = float((np.concatenate([[0.0], eq]) - peak).min())
        yrs = pd.DatetimeIndex(pd.to_datetime(r["DATE"])).year
        return {"N": int(len(v)),
                "NET_POINTS": round(float(v.mean()), 4),
                "NET_USD": round(float(v.mean()) * POINT_USD, 2),
                "PF": round(float(pos_ / neg_), 4) if neg_ > 0 else None,
                "WR": round(float((v > 0).mean()), 4),
                "EXP_R": round(float((r[col] / r["R0"].replace(0, np.nan)).mean()), 4),
                "REMOVE_BEST": round(float(sr[top:].mean()), 4),
                "MAX_DD_USD": round(dd * POINT_USD, 2),
                "MAX_DD_POINTS": round(dd, 3),
                "BY_YEAR": {int(y): round(float(v[np.asarray(yrs) == y].mean()), 3)
                            for y in sorted(set(yrs))}}

    summary = {name: agg(f"{name}_NET") for name, _ in SCENARIOS}
    spreads = np.concatenate([r["ENTRY_SPREAD"].dropna().to_numpy(),
                              r["EXIT_SPREAD"].dropna().to_numpy()])
    summary["SPREADS"] = {"MEDIAN": round(float(np.median(spreads)), 4),
                          "P95": round(float(np.percentile(spreads, 95)), 4),
                          "P99": round(float(np.percentile(spreads, 99)), 4)}
    amb = r[r["FLAG"].astype(str).str.startswith(("AMBIGUOUS", "ERROR"))]
    summary["BBO_RESOLVED_TRADES"] = int(len(r) - len(amb))
    summary["BBO_AMBIGUOUS_TRADES"] = int(len(amb))
    summary["AMBIGUOUS_FRACTION"] = round(len(amb) / max(len(r), 1), 4)
    summary["ENTRY_DELTA_MEDIAN"] = round(float(r["ENTRY_DELTA"].median()), 4)
    summary["ENTRY_DELTA_P95"] = round(float(r["ENTRY_DELTA"].quantile(0.95)), 4)
    summary["EXIT_DELTA_MEDIAN"] = round(float(r["EXIT_DELTA"].median()), 4)
    summary["EXIT_DELTA_P95"] = round(float(r["EXIT_DELTA"].quantile(0.95)), 4)
    (OUT / "o01_bbo_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    print(json.dumps(summary, indent=1, default=str))

    # ---- manual traces: first 3 LONG + 3 SHORT ----
    picks = list(trades[trades.SIDE == "LONG"].head(3).iterrows()) + \
            list(trades[trades.SIDE == "SHORT"].head(3).iterrows())
    lines = []
    for _, t in picks:
        wid = f"{t['DATE']}_{t['ACTUAL_FUTURES_CONTRACT']}"
        f = R.Path(r"E:/ResearchData/botTrading/nq/databento/highres/bbo_1s_o01") / f"{wid}.dbn.zst"
        w = R.BboWindow(f)
        act = pd.Timestamp(t["ORDER_ACTIVATION_TIMESTAMP"])
        k0 = w.first_idx_ge(act)
        lines.append("=" * 76)
        lines.append(f"{t['TRADE_ID']} {t['DATE']} {t['SIDE']} "
                     f"contract={t['ACTUAL_FUTURES_CONTRACT']}")
        lines.append(f"  decision={t['DECISION_TIMESTAMP']} activation={act} "
                     f"exit_reason={t['MODELED_EXIT_REASON']}")
        lines.append(f"  first eligible quote: ts={w.ts[k0]} bid={w.bid[k0]} ask={w.ask[k0]}")
        lines.append(f"  frozen entry={t['MODELED_ENTRY']} stop={t['INITIAL_STOP']} "
                     f"frozen exit={t['MODELED_FINAL_EXIT']} @ {t['MODELED_FINAL_EXIT_TIMESTAMP']}")
        for scen, tier in SCENARIOS:
            rr = R.replay_o01(dict(t), w, scen, tier)
            lines.append(f"  [{scen}] entry={rr['entry_exec']} exit={rr['exit_exec']} "
                         f"gross={round(rr['gross'], 3)} fees={rr['fees']} "
                         f"slip={round(rr['slippage'], 3)} NET={round(rr['net'], 3)} "
                         f"flag={rr['flag']}")
    txt = chr(10).join(lines)
    (OUT / "o01_manual_traces.txt").write_text(txt)
    print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
