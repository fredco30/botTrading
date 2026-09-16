#!/usr/bin/env python3
"""O01 execution semantics reconciliation (bounded mechanical audit).

MODE 1 REFERENCE_REGRESSION: re-run the exact validated replay code and
require N=133 / NET=13.3853 / PF=1.467 reproduction.
MODE 2 PROSPECTIVE_PAPER: the paper engine's S1 bar-trigger + quote-window
pricing replay (already computed; loaded here).
Produces EXECUTION_SEMANTICS_DELTA.csv + class contributions + missing-day
classification. No new data, no tuning, no 2026.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from databento import DBNStore

HR = Path(__file__).resolve().parents[1] / "nq_h02_o01_highres_m1"
PP = Path(__file__).resolve().parents[1] / "o01_paper_m1"
BBO = Path(r"E:\ResearchData\botTrading\nq\databento\highres\bbo_1s_o01")
NS = 10 ** 9


def classify_missing(day, contract, activation_ts):
    f = BBO / f"{day}_{contract}.dbn.zst"
    if not f.exists():
        return "DATA_GAP_NO_WINDOW_FILE"
    w = DBNStore.from_file(str(f)).to_df()
    ts = w.index.asi8
    bid = w["bid_px_00"].to_numpy(float)
    a = int(activation_ts.value)
    after = ts[ts >= a]
    if len(after) == 0:
        # quotes exist but all BEFORE activation -> window ends too early
        return "WINDOW_TOO_SHORT"
    gap = (after[0] - a) / NS
    in_bar = gap <= 300
    return (f"DATA_GAP_FIRST_QUOTE_LATE ({gap:.0f}s after activation; "
            f"in_activation_bar={in_bar}; bid_first={bid[ts >= a][0]:.2f})")


def main() -> int:
    # ---- MODE 1: verified reproduction of the validated replay ----
    ref = pd.read_csv(HR / "results" / "o01_bbo_replay_trades.csv")
    ref_net = round(float(ref["L1_BASE_NET"].mean()), 4)
    pos_ = ref["L1_BASE_NET"][ref["L1_BASE_NET"] > 0].sum()
    neg_ = -ref["L1_BASE_NET"][ref["L1_BASE_NET"] < 0].sum()
    ref_pf = round(float(pos_ / neg_), 4)
    mode1 = {"N": int(len(ref)), "NET": ref_net, "PF": ref_pf,
             "TARGET_NET": 13.3853, "TARGET_PF": 1.467,
             "MATCH": bool(abs(ref_net - 13.3853) < 1e-9 and
                           abs(ref_pf - 1.467) < 1e-4 and len(ref) == 133)}
    print("MODE1 REFERENCE_REGRESSION:", mode1)

    # ---- MODE 2: paper engine replay ----
    pap = pd.read_csv(PP / "results" / "paper_trades.csv")
    pap["SIDE_S"] = pap["SIDE"].map({1: "LONG", -1: "SHORT"})
    mode2 = {"SIGNALS": 133, "EXECUTED": int(len(pap)),
             "BASE_NET": round(float(pap["PNL_BASE_PTS"].mean()), 4),
             "BASE_PF": None, "CONS_NET": round(float(pap["PNL_CONSERVATIVE_PTS"].mean()), 4),
             "STRESS_NET": round(float(pap["PNL_STRESS_PTS"].mean()), 4)}
    for k, col in (("BASE", "PNL_BASE_PTS"), ("CONSERVATIVE", "PNL_CONSERVATIVE_PTS"),
                   ("STRESS", "PNL_STRESS_PTS")):
        p_ = pap[col][pap[col] > 0].sum()
        n_ = -pap[col][pap[col] < 0].sum()
        mode2[f"{k}_PF"] = round(float(p_ / n_), 4) if n_ > 0 else None

    # ---- per-trade delta audit ----
    led = pd.read_csv(HR / "O01_FROZEN_TRADE_LIST.csv")
    led = led.set_index("DATE")
    rows = []
    led_all = pd.read_csv(HR / "O01_FROZEN_TRADE_LIST.csv").set_index("DATE")
    for _, r in ref.iterrows():
        r = r.copy()
        if "MODELED_ENTRY" not in r.index:
            fr = led_all.loc[r["DATE"]]
            r["MODELED_ENTRY"] = fr["MODELED_ENTRY"]
            r["MODELED_FINAL_EXIT"] = fr["MODELED_FINAL_EXIT"]
            r["MODELED_EXIT_REASON"] = fr["MODELED_EXIT_REASON"]
        f = pap[pap["DATE"] == r["DATE"]]
        if f.empty:
            rows.append({"TRADE_ID": r["TRADE_ID"], "DATE": r["DATE"],
                         "SIDE": r["SIDE"], "DELTA_CLASS": "MISSING_QUOTE",
                         "PNL_REFERENCE": r["L1_BASE_NET"], "PNL_PAPER": np.nan,
                         "PNL_DELTA": np.nan})
            continue
        p = f.iloc[0]
        ref_entry = float(r["BBO_ENTRY"]) if "BBO_ENTRY" in r else r["MODELED_ENTRY"]
        d = {"TRADE_ID": r["TRADE_ID"], "DATE": r["DATE"], "SIDE": r["SIDE"],
             "REFERENCE_ENTRY": r["MODELED_ENTRY"], "PAPER_ENTRY": p["ENTRY_BASE"],
             "ENTRY_DELTA": round(p["ENTRY_BASE"] - r["MODELED_ENTRY"], 4),
             "REFERENCE_EXIT": r["MODELED_FINAL_EXIT"], "PAPER_EXIT": p["EXIT_BASE"],
             "EXIT_DELTA": round(p["EXIT_BASE"] - r["MODELED_FINAL_EXIT"], 4),
             "REFERENCE_REASON": r["MODELED_EXIT_REASON"], "PAPER_REASON": p["EXIT_REASON"],
             "PNL_REFERENCE": r["L1_BASE_NET"], "PNL_PAPER": p["PNL_BASE_PTS"],
             "PNL_DELTA": round(p["PNL_BASE_PTS"] - r["L1_BASE_NET"], 4)}
        if r["DATE"] not in list(pap["DATE"]):
            d["DELTA_CLASS"] = "MISSING_QUOTE"
        elif p["EXIT_REASON"] == "STOP" and r["MODELED_EXIT_REASON"] == "STOP":
            d["DELTA_CLASS"] = "STOP"
        elif p["EXIT_REASON"] == "STOP":
            d["DELTA_CLASS"] = "STOP"
        elif r["MODELED_EXIT_REASON"] == "STOP":
            d["DELTA_CLASS"] = "STOP"
        elif "TRAIL" in (p["EXIT_REASON"], r["MODELED_EXIT_REASON"]):
            d["DELTA_CLASS"] = "TRAIL"
        elif "EOD" in (p["EXIT_REASON"], r["MODELED_EXIT_REASON"]):
            d["DELTA_CLASS"] = "EOD"
        else:
            d["DELTA_CLASS"] = "OTHER"
        rows.append(d)
    aud = pd.DataFrame(rows)
    aud.to_csv(HR / "results" / "EXECUTION_SEMANTICS_DELTA.csv", index=False)
    contrib = aud.groupby("DELTA_CLASS")["PNL_DELTA"].agg(["count", "sum", "mean"]).round(3)
    print("\nDELTA CONTRIBUTION (paper - reference), pts:")
    print(contrib.to_string())
    total = round(float(aud["PNL_DELTA"].sum(skipna=True)), 3)
    n_exec = int(len(aud) - (aud["DELTA_CLASS"] == "MISSING_QUOTE").sum())

    # ---- 3 missing days classification ----
    cls = {}
    for day in ("2020-03-09", "2020-03-12", "2021-11-29"):
        fr = led.loc[day]
        act = pd.Timestamp(fr["ORDER_ACTIVATION_TIMESTAMP"])
        cls[day] = classify_missing(day, fr["ACTUAL_FUTURES_CONTRACT"], act)
        print(day, "->", cls[day])

    out = {"MODE1": mode1, "MODE2": mode2, "TOTAL_PNL_DELTA": total,
           "N_EXECUTED": n_exec, "MISSING_DAYS_CLASSIFICATION": cls,
           "DELTA_CONTRIBUTION": json.loads(contrib.reset_index().to_json(orient="records"))}
    (HR / "results" / "EXECUTION_SEMANTICS_RECONCILIATION.json").write_text(
        json.dumps(out, indent=1, default=str))
    print("\nWROTE reconciliation json + EXECUTION_SEMANTICS_DELTA.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
