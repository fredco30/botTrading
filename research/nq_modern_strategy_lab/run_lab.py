#!/usr/bin/env python3
"""Run all preregistered lab experiments -> EXPERIMENT_LEDGER + results JSON."""
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import lab_lib as L  # noqa: E402
import families as F  # noqa: E402

HERE = Path(__file__).parent
WEEKS = 1548 / 5.0  # RTH days in sample / 5


def main() -> int:
    df = L.N.load_5m()
    x = L.build_ctx(df)
    F.build_extras(x)
    rows = []
    t0 = time.time()
    for exp_id, fam, mech, entry, exitd, factory in F.EXPERIMENTS:
        state = {}
        fn = factory(state)
        tr = L.run_experiment_full(x, fn, L.NQ_COSTS["NORMAL"])
        tf = pd.DataFrame(tr)
        m = L.metrics(tf, WEEKS)
        ok, fails = L.gate_check(m)
        # stress view
        state2 = {}
        tr2 = L.run_experiment_full(x, factory(state2), L.NQ_COSTS["STRESS"])
        m2 = L.metrics(pd.DataFrame(tr2), WEEKS)
        # stress must reuse the SAME entry decisions: rebuild entry series by
        # rerunning with stress cost on identical state machine (deterministic,
        # state dicts fresh) — trades identical, only costs differ.
        row = {
            "exp": exp_id, "family": fam, "mechanism": mech,
            "entry": entry, "exit": exitd,
            "N": m.get("N", 0), "TPW": m.get("TPW", 0),
            "NET": m.get("NET"), "NET_USD": m.get("NET_USD"),
            "PF": m.get("PF"), "WR": m.get("WR"), "EXP_R": m.get("EXP_R"),
            "RM_BEST1": m.get("RM_BEST1"), "MAXDD_USD": m.get("MAXDD_USD"),
            "BY_FOLD": json.dumps(m.get("BY_FOLD", {})),
            "BY_YEAR": json.dumps(m.get("BY_YEAR", {})),
            "STRESS_NET": m2.get("NET"), "STRESS_PF": m2.get("PF"),
            "GATE": "PASS" if ok else "FAIL:" + ";".join(fails),
        }
        rows.append(row)
        print(f"{exp_id} {fam:22s} N={m.get('N',0):4d} TPW={m.get('TPW',0):4.2f} "
              f"NET={m.get('NET')} PF={m.get('PF')} R={m.get('EXP_R')} "
              f"S_NET={m2.get('NET')} -> {row['GATE'][:80]}")
    led = pd.DataFrame(rows)
    led.to_csv(HERE / "EXPERIMENT_LEDGER.csv", index=False)
    (HERE / "results_lab.json").write_text(json.dumps(rows, indent=1, default=str))
    npass = int((led["GATE"] == "PASS").sum())
    print(f"\nEXPERIMENTS={len(rows)}  PASS={npass}  elapsed={time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
