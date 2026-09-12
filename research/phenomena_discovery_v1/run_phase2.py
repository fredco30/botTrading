#!/usr/bin/env python3
"""Run Phase 2 screens (Discovery only, via the central gate).

Writes phase2_results.json. No V1/V2 access here — gate.window("V1"/"V2")
raises unless authorized after a documented freeze decision.
"""
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import phase2_lib as Q  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main(only=None):
    results = {}

    def run(name, fn):
        if only and name not in only:
            return
        try:
            results[name] = fn()
            print(f"  {name}: OK", flush=True)
        except Exception as e:
            results[name] = {"ERROR": str(e)[:200],
                             "TRACE": traceback.format_exc()[-600:]}
            print(f"  {name}: ERROR {str(e)[:120]}", flush=True)

    run("P010_EURGBP_TRIANGLE",
        lambda: Q.p010_cross_pair(("EURUSD", "GBPUSD", "EURGBP")))
    run("P010_EURJPY_TRIANGLE",
        lambda: Q.p010_cross_pair(("EURUSD", "USDJPY", "EURJPY")))
    run("P010_GBPJPY_TRIANGLE",
        lambda: Q.p010_cross_pair(("GBPUSD", "USDJPY", "GBPJPY")))
    run("P026_US2Y_TO_USDJPY", Q.p026_us2y)
    run("P025_CARRY_EURUSD",
        lambda: Q.p025_carry("EURUSD", Q._fred_series("ECBDFR.csv", "ECBDFR")
                             - Q._fred_series("DFEDTARU.csv", "DFEDTARU")))
    run("P025_CARRY_GBPUSD",
        lambda: Q.p025_carry("GBPUSD", Q._fred_series("BOERUKM.csv", "BOERUKM")
                             - Q._fred_series("DFEDTARU.csv", "DFEDTARU")))
    run("P025_CARRY_USDJPY",
        lambda: Q.p025_carry("USDJPY", Q._fred_series("DFEDTARU.csv", "DFEDTARU")
                             - Q._boj()))
    run("P027_GOLD_JPY", Q.p027_gold_jpy)
    run("P020_LONDON_FIX_EURUSD", lambda: Q.p020_london_fix("EURUSD"))
    run("P020_LONDON_FIX_GBPUSD", lambda: Q.p020_london_fix("GBPUSD"))
    run("P013_MONTH_END_EURUSD", lambda: Q.p013_month_end("EURUSD"))
    run("P013_MONTH_END_USDJPY", lambda: Q.p013_month_end("USDJPY"))
    run("P032_POST_FOMC", Q.p032_fomc)
    run("P004_PDH_PDL_EURUSD", lambda: Q.p004_pdh_pdl("EURUSD"))
    run("P004_PDH_PDL_GBPUSD", lambda: Q.p004_pdh_pdl("GBPUSD"))
    run("P004_PDH_PDL_USDJPY", lambda: Q.p004_pdh_pdl("USDJPY"))
    run("P006_NY_OVERLAP_EURUSD", lambda: Q.p006_ny_overlap("EURUSD"))
    run("P006_NY_OVERLAP_GBPUSD", lambda: Q.p006_ny_overlap("GBPUSD"))
    run("P034_COMPRESSION_EURUSD", lambda: Q.p034_compression("EURUSD"))
    run("P034_COMPRESSION_USDJPY", lambda: Q.p034_compression("USDJPY"))

    out_path = os.path.join(HERE, "phase2_results.json")
    merged = {}
    if os.path.exists(out_path) and not only:
        os.replace(out_path, out_path + ".bak")   # full pass: fresh start
    elif os.path.exists(out_path):
        with open(out_path, encoding="utf-8") as f:
            merged = json.load(f)                 # partial run: merge, keep others
    merged.update(results)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=1, default=str)
    print(f"WROTE phase2_results.json ({len(merged)} screens)")


if __name__ == "__main__":
    only = sys.argv[1:] or None
    main(only)
