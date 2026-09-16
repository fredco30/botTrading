#!/usr/bin/env python3
"""Software regression: drive the NEW PaperEngine with owned historical data
(5m bars + the 133 owned BBO windows) and require identity with the frozen
O01 ledger and the validated BBO replay. Explainable divergences (conservative
fallbacks) are allowed and must be documented. NOT a research backtest."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "nq_opr_modern_m1"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "nq_modern_strategy_lab"))
from o01_engine.engine import PaperEngine  # noqa: E402
from o01_engine.adapters import HistoricalReplayAdapter  # noqa: E402
import nq_lib as N  # noqa: E402

BBO_DIR = Path(r"E:/ResearchData/botTrading/nq/databento/highres/bbo_1s_o01")
NS = 10 ** 9
LEDGERS = ("BASE", "CONSERVATIVE", "STRESS")


def main() -> int:
    df5 = N.load_5m()
    ledger = pd.read_csv(HERE.parent / "nq_h02_o01_highres_m1" /
                         "O01_FROZEN_TRADE_LIST.csv")
    frozen = ledger.set_index("TRADE_ID")
    val = pd.read_csv(HERE.parent / "nq_h02_o01_highres_m1" / "results" /
                      "o01_bbo_replay_trades.csv").set_index("TRADE_ID")
    contract_by_day = dict(zip(ledger["DATE"], ledger["ACTUAL_FUTURES_CONTRACT"]))
    ad = HistoricalReplayAdapter(df5, ledger)

    eng = PaperEngine(HERE / "state_replay",
                      contract_lookup=lambda day: contract_by_day.get(str(day)),
                      persist_every=0)
    et_local = df5.index.tz_convert("America/New_York")
    days = list(dict.fromkeys(et_local.date.tolist()))
    n_ev = 0
    for day in days:
        mask = et_local.date == day
        day_bars = df5[mask]
        for ts, row in day_bars.iterrows():
            ev = ad.day_bar_event(day, row, ts)
            eng.on_event(ev)
            n_ev += 1

    # ---- compare paper trades vs frozen ledger + validated replay ----
    pt = eng.trades
    Path("results").mkdir(exist_ok=True)
    pd.DataFrame([{**t, **{"ENTRY_" + k: v for k, v in t.get("ENTRY", {}).items()},
                   **{"EXIT_" + k: v for k, v in t.get("EXIT", {}).items()}}
                  for t in pt]).to_csv(HERE / "results" / "paper_trades.csv", index=False)
    report = {"N_EVENTS": n_ev, "PAPER_ENGINE_TRADES": len(pt), "EXPECTED": 133,
              "EXACT": [], "EXPLAINABLE": [], "MISSING": []}
    used = set()
    for tid, fr in frozen.iterrows():
        cand = [k for k, t in enumerate(pt)
                if t["DATE"] == fr["DATE"] and k not in used and
                t["SIDE"] == fr["SIDE"]]
        if not cand:
            report["MISSING"].append({"id": tid, "date": fr["DATE"], "side": fr["SIDE"],
                                      "paper_dates_that_day": [t["DATE"] for t in pt if t["DATE"] == fr["DATE"]],
                                      "paper_sides_that_day": [t["SIDE"] for t in pt if t["DATE"] == fr["DATE"]]})
            continue
        k = cand[0]
        used.add(k)
        t = pt[k]
        fr_exit_ts = str(pd.Timestamp(fr["MODELED_FINAL_EXIT_TIMESTAMP"]) +
                         pd.Timedelta(5, "min"))
        same_entry = abs(t["ENTRY"]["BASE"] - fr["MODELED_ENTRY"]) < 1e-6
        reason_ok = t.get("EXIT_REASON") == fr["MODELED_EXIT_REASON"]
        exit_ts_ok = ("EXIT_TS" in t and
                      str(pd.Timestamp(t["EXIT_TS"]).tz_convert("UTC")) ==
                      str(pd.Timestamp(fr_exit_ts).tz_convert("UTC")))
        vb = val.loc[tid]
        if "PNL_BASE_PTS" not in t:
            report["EXPLAINABLE"].append({"id": tid, "why": "paper-exit-missing"})
            continue
        pnl_ok = {kk: abs(t[f"PNL_{kk}_PTS"] - float(vb[f"L1_{kk}_NET"])) < 1e-9
                  for kk in LEDGERS}
        if same_entry and reason_ok and exit_ts_ok and all(pnl_ok.values()):
            report["EXACT"].append(tid)
        else:
            why = []
            if not same_entry:
                why.append(f"entry paper={t['ENTRY']['BASE']} frozen={fr['MODELED_ENTRY']}")
            if not reason_ok:
                why.append(f"reason paper={t.get('EXIT_REASON')} frozen={fr['MODELED_EXIT_REASON']}")
            if not exit_ts_ok:
                why.append(f"exit-ts paper={t.get('EXIT_TS')} frozen={fr_exit_ts}")
            if not all(pnl_ok.values()):
                why.append("pnl " + ";".join(
                    f"{kk} paper={round(t[f'PNL_{kk}_PTS'],3)} val={round(float(vb[f'L1_{kk}_NET']),3)}"
                    for kk in LEDGERS if not pnl_ok[kk]))
            report["EXPLAINABLE"].append({"id": tid, "why": ";".join(why)})
    closed = [t for t in pt if "PNL_BASE_PTS" in t]
    res = {"N_EVENTS": n_ev, "PAPER_ENGINE_TRADES": len(pt), "EXPECTED": 133,
           "EXACT_COUNT": len(report["EXACT"]),
           "EXPLAINABLE_COUNT": len(report["EXPLAINABLE"]),
           "MISSING_COUNT": len(report["MISSING"]),
           "EXPLAINABLE_DETAIL": report["EXPLAINABLE"][:10],
           "MISSING_DETAIL": report["MISSING"][:10]}
    if closed:
        res["REPLAY_NET_POINTS"] = {k: round(float(np.mean(
            [t[f"PNL_{k}_PTS"] for t in closed])), 4) for k in LEDGERS}
        pos_, neg_ = (np.sum([t["PNL_BASE_PTS"] for t in closed if t["PNL_BASE_PTS"] > 0]),
                      -np.sum([t["PNL_BASE_PTS"] for t in closed if t["PNL_BASE_PTS"] < 0]))
        res["REPLAY_BASE_PF"] = round(float(pos_ / neg_), 4) if neg_ > 0 else None
    res["HIGHRES_REFERENCE_NET"] = 13.3853
    res["HIGHRES_REFERENCE_PF"] = 1.467
    res["REGRESSION_MATCH"] = (len(report["EXACT"]) >= 131 and
                               len(report["MISSING"]) == 0)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "regression_summary.json").write_text(
        json.dumps(res, indent=1, default=str))
    print(json.dumps(res, indent=1, default=str))
    return 0 if res["REGRESSION_MATCH"] else 1


if __name__ == "__main__":
    sys.exit(main())
