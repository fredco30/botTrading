#!/usr/bin/env python3
"""Freeze exact H02 / O01 trade ledgers + execution windows (cost-guard phase).

Reproduces the frozen lab candidates with the frozen engine (families/lab_lib,
untouched). Identity: H02=226 trades, O01=133. Builds per-trade execution
windows (activation - 10min -> final exit + 10min), maps actual contracts from
the roll manifest, verifies 0 roll-cross windows, hashes both ledgers.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_modern_strategy_lab"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
import lab_lib as L  # noqa: E402
import families as F  # noqa: E402
import nq_lib as N  # noqa: E402

HERE = Path(__file__).parent
MANIFEST_DIR = Path(r"E:\ResearchData\botTrading\nq\databento\manifest")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def freeze(candidate_id, factory, expected_n):
    df5 = N.load_5m()
    x = L.build_ctx(df5)
    F.build_extras(x)
    tr = pd.DataFrame(L.run_experiment_full(x, factory({}), L.NQ_COSTS["NORMAL"]))
    tr = tr.sort_values("entry_ts").reset_index(drop=True)
    assert len(tr) == expected_n, f"{candidate_id} IDENTITY FAIL: {len(tr)} != {expected_n}"

    roll = pd.read_csv(MANIFEST_DIR / "roll_audit.csv", parse_dates=["date"])
    pos_of = {ts: k for k, ts in enumerate(df5.index)}
    rows, wins = [], []
    for tid, t in tr.iterrows():
        day = str(N._to_et([t["entry_ts"]])[0].date())
        i0 = pos_of[t["entry_ts"]]
        dec_ts = df5.index[i0 - 1] + pd.Timedelta(5, "min")   # decision bar END
        contract_row = roll[roll["date"] == pd.Timestamp(day)]
        contract = contract_row["raw_symbols"].iloc[0] if len(contract_row) else "UNKNOWN"
        w_start = dec_ts - pd.Timedelta(10, "min")
        w_end = pd.Timestamp(t["exit_ts"]) + pd.Timedelta(10, "min")
        assert w_end < pd.Timestamp("2026-01-01", tz="UTC"), "2026 seal"
        roll_cross = (w_start.date() != pd.Timestamp(day).date()) or \
                     (w_end.date() != pd.Timestamp(day).date())
        rows.append({
            "TRADE_ID": f"{candidate_id}-{tid:04d}",
            "DATE": day,
            "ACTUAL_FUTURES_CONTRACT": contract,
            "SIDE": "LONG" if t["side"] == 1 else "SHORT",
            "DECISION_TIMESTAMP": str(dec_ts),
            "ORDER_ACTIVATION_TIMESTAMP": str(df5.index[i0]),
            "MODELED_ENTRY": round(float(t["fill"]), 2),
            "INITIAL_STOP": round(float(t["level"]), 2),
            "TRAIL_TYPE": "CHANDELIER_1.0_ATR",
            "MODELED_FINAL_EXIT_TIMESTAMP": str(t["exit_ts"]),
            "MODELED_FINAL_EXIT": round(float(t["exit_px"]), 2),
            "MODELED_GROSS_POINTS": round(float(t["gross"]), 4),
            "MODELED_NET_POINTS": round(float(t["net"]), 4),
            "MODELED_EXIT_REASON": t["exit_reason"],
            "WINDOW_START_UTC": str(w_start),
            "WINDOW_END_UTC": str(w_end),
            "ROLL_CROSS": bool(roll_cross),
        })
        wins.append({"DATE": day, "CONTRACT": contract,
                     "START_UTC": str(w_start), "END_UTC": str(w_end)})
    f = pd.DataFrame(rows)
    out = HERE / f"{candidate_id}_FROZEN_TRADE_LIST.csv"
    f.to_csv(out, index=False)
    pd.DataFrame(wins).to_csv(HERE / f"{candidate_id}_execution_windows_raw.csv", index=False)
    return {"count": int(len(f)), "sha256": sha256_file(out),
            "avg_net": round(float(tr["net"].mean()), 4),
            "roll_cross": int(f["ROLL_CROSS"].sum()),
            "windows": wins}


def union_intervals(wins):
    """Proper interval union per (date, contract): merge only overlapping or
    touching (gap <= 5 min) windows — disjoint windows stay separate so the
    estimate bills the minimum data volume."""
    df = pd.DataFrame(wins)
    df["S"] = pd.to_datetime(df["START_UTC"], utc=True)
    df["E"] = pd.to_datetime(df["END_UTC"], utc=True)
    out = []
    for (day, contract), g in df.groupby(["DATE", "CONTRACT"]):
        g = g.sort_values("S")
        cur_s, cur_e = None, None
        for _, r in g.iterrows():
            if cur_s is None:
                cur_s, cur_e = r["S"], r["E"]
            elif r["S"] <= cur_e + pd.Timedelta(5, "min"):
                cur_e = max(cur_e, r["E"])
            else:
                out.append({"DATE": day, "CONTRACT": contract,
                            "START": cur_s, "END": cur_e})
                cur_s, cur_e = r["S"], r["E"]
        out.append({"DATE": day, "CONTRACT": contract, "START": cur_s, "END": cur_e})
    return out


def main() -> int:
    meta = {}
    for cid, fac, n in (("H02", F.H02, 226), ("O01", F.O01, 133)):
        m = freeze(cid, fac, n)
        meta[cid] = m
        print(cid, "count:", m["count"], "avg_net:", m["avg_net"],
              "roll_cross:", m["roll_cross"], "sha:", m["sha256"][:16])
    # unions
    u_both = union_intervals(meta["H02"]["windows"] + meta["O01"]["windows"])
    u_h02 = union_intervals(meta["H02"]["windows"])
    u_o01 = union_intervals(meta["O01"]["windows"])
    for name, u in (("H02", u_h02), ("O01", u_o01), ("COMBINED", u_both)):
        hours = sum((r["END"] - r["START"]).total_seconds() for r in u) / 3600
        print(f"{name}: windows={len(u)} hours={hours:.2f}")
    pd.DataFrame(u_both).to_csv(HERE / "combined_execution_windows.csv", index=False)
    json.dump({"h02": {k: v for k, v in meta["H02"].items() if k != "windows"},
               "o01": {k: v for k, v in meta["O01"].items() if k != "windows"},
               "union_windows": u_both},
              open(HERE / "frozen_trade_list_meta.json", "w"), indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
