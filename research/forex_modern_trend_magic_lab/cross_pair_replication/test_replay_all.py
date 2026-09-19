#!/usr/bin/env python3
"""Deterministic tests for the cross-pair replication (REPLICATION ONLY).

Run:  python test_replay_all.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "audit"))
import replay_all as RA
import replay_strict as R

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {detail if not cond else ''}")
    if not cond:
        FAIL.append(name)


def test_usdjpy_engine_control():
    """Section 10 control: USDJPY must reproduce STRICT V1 exactly."""
    with open(os.path.join(os.path.dirname(HERE), "audit",
                           "FX_PDH_001_STRICT_RESULTS.json")) as f:
        j = json.load(f)
    conv = RA.conversion_closes()
    res = RA.collect("USDJPY", conv, slip=0.0)
    check("n == 639", res["n"] == j["n"], (res["n"], j["n"]))
    check("pf == frozen", np.isclose(res["pf"], j["pf"]))
    check("net == frozen", np.isclose(res["net_pips_per_trade"],
                                      j["net_pips_per_trade"]))
    check("rb1 == frozen", np.isclose(res["remove_best_1pct"],
                                      j["remove_best_1pct"]))
    check("t == frozen", np.isclose(res["t_stat"], j["t_stat"]))
    check("by_year == frozen", all(
        np.isclose(res["by_year"][int(y)], j["by_year"][y])
        for y in j["by_year"]))
    s = RA.collect("USDJPY", conv, slip=RA.SLIP_STRESS)
    check("stress == frozen", np.isclose(s["net_pips_per_trade"],
                                         j["stress_net_pips_per_trade"]))


def test_pip_value_conversions():
    """Quote-currency-aware EUR pip value at hand-fixed rates."""
    n = 5
    idx = np.array([np.datetime64('2022-06-01T00:00', 'ns') + np.timedelta64(i, 'h')
                    for i in range(n)], dtype='datetime64[ns]')
    conv = {
        "EURUSD": (idx, np.full(n, 1.10)),
        "GBPUSD": (idx, np.full(n, 1.25)),
        "USDJPY": (idx, np.full(n, 150.0)),
    }
    # EURUSD: 1000 x 1e-4 USD = 0.10 USD/pip -> x1.10 = 0.11 EUR
    v = RA.pip_eur_series("EURUSD", idx[:1], None, conv)[0]
    check("EURUSD pip EUR", np.isclose(v, 0.10 * 1.10), v)
    # USDJPY: 1000 x 0.01 JPY = 10 JPY / 150 = 0.06667 USD -> x1.10 = 0.07333
    v = RA.pip_eur_series("USDJPY", idx[:1], None, conv)[0]
    check("USDJPY pip EUR", np.isclose(v, 10 / 150 * 1.10), v)
    # EURJPY: same JPY pip value -> EUR = 10/150 ... via USD chain x1.10
    v = RA.pip_eur_series("EURJPY", idx[:1], None, conv)[0]
    check("EURJPY pip EUR", np.isclose(v, 10 / 150 * 1.10), v)
    # GBPJPY: 10 JPY / 150 USD x1.10 (identical chain, base irrelevant)
    v = RA.pip_eur_series("GBPJPY", idx[:1], None, conv)[0]
    check("GBPJPY pip EUR", np.isclose(v, 10 / 150 * 1.10), v)
    # EURGBP: 1000 x 1e-4 GBP = 0.10 GBP x1.25 USD x1.10 EUR
    v = RA.pip_eur_series("EURGBP", idx[:1], None, conv)[0]
    check("EURGBP pip EUR", np.isclose(v, 0.10 * 1.25 * 1.10), v)


def test_costs_never_double_charged():
    """NORMAL adds exactly one spread; STRESS adds spread + 2 x 0.5."""
    conv = RA.conversion_closes()
    R.PAIR = "EURGBP"; R.PIP = RA.PIP_SIZE["EURGBP"]; R.SPREAD = RA.SPREAD["EURGBP"]
    D = R.prepare()
    n0 = R.replay(D, strict=True, slip=0.0)
    s0 = R.replay(D, strict=True, slip=0.5)
    # cost scenarios may change exits/re-entries, so compare COMMON entries.
    # Invariant: adverse costs NEVER improve a common entry (worse entry fill
    # raises the stop level; exit slip lowers fills; stops trigger no later).
    # Exact deltas: -slip on initial-stop-dominated exits, -2*slip on
    # trail-dominated exits, larger-negative on path-redirected exits.
    merged = n0.merge(s0, on="entry_i", suffixes=("_n", "_s"))
    deltas = merged["net_pips_s"] - merged["net_pips_n"]
    check("common-entry stress never better (all deltas <= -slip/2)",
          len(merged) > 0 and bool((deltas <= -0.25).all()),
          (len(merged), float(deltas.max())))
    # NORMAL accounting invariant: net == (exit fill - entry bid open)/PIP - spread
    expected = ((n0["exit_px"] - D["o"][n0["entry_i"]]) / R.PIP) - R.SPREAD
    check("NORMAL net = fill-to-open - 1 spread (no double charge)",
          np.allclose(n0["net_pips"], expected))


def test_seal_all_pairs():
    for sym in RA.PAIRS:
        try:
            R.T.load_5m(sym, "2025-12-01", "2026-01-10")
            check(f"{sym} sealed", False)
        except AssertionError:
            check(f"{sym} sealed", True)


if __name__ == "__main__":
    for fn in (test_usdjpy_engine_control, test_pip_value_conversions,
               test_costs_never_double_charged, test_seal_all_pairs):
        print(fn.__name__)
        fn()
    print()
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)
    print("ALL CROSS-PAIR REPLICATION TESTS PASSED")
