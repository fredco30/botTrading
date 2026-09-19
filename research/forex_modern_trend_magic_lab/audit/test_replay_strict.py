#!/usr/bin/env python3
"""Deterministic tests for the STRICT replay (audit/replay_strict.py).

Run:  python test_replay_strict.py
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import replay_strict as R

FAIL = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {detail if not cond else ''}")
    if not cond:
        FAIL.append(name)


def make_D(n=40, atr_val=2.0, atr_over=None, sig=10):
    """Synthetic day-frame: 4 days x 10 bars; signal at bar `sig`."""
    o = np.full(n, 100.0); h = np.full(n, 100.5)
    l = np.full(n, 99.5); c = np.full(n, 100.0)
    idx = np.array([np.datetime64('2020-01-0' + str(1 + i // 10), 'D')
                    + np.timedelta64(i % 10, 'h') for i in range(n)])
    idx = np.array([t.astype('datetime64[ns]') for t in idx])
    day = np.array([str(t.astype('datetime64[D]')) for t in idx])
    day = np.array([np.datetime64(d, 'D') for d in day])
    atr = np.full(n, atr_val)
    if atr_over:
        for k, v in atr_over.items():
            atr[k] = v
    # signal bar: high breaks prior day's high
    h[sig] = 101.5
    return dict(o=o, h=h, l=l, c=c, idx=idx, day=day, atr=atr,
                sig=np.array([sig], "int64"))


def test_entry_bar_stopout():
    """D1: entry bar CAN stop out under strict; original skipped it."""
    D = make_D(atr_over={10: 2.0})
    D["o"][11] = 100.0                       # entry fill = 100 + 0.009
    D["l"][11] = 97.5                        # stop = 100.009 - 2.0 = 98.009
    D["l"][12] = 97.5                        # would stop later for non-strict
    s = R.replay(D, strict=True)
    v0 = R.replay(D, strict=False)
    check("strict exits on entry bar", len(s) == 1 and s["entry_i"].iloc[0] == 11
          and s["exit_i"].iloc[0] == 11)
    # stop fill 98.009; net = (98.009-100)/0.01 - 0.9 - 0 = -199.1-0.9 = -200.0
    check("entry-bar stop fill/net hand-calc",
          np.isclose(s["exit_px"].iloc[0], 98.009)
          and np.isclose(s["net_pips"].iloc[0], -200.0),
          (s["exit_px"].iloc[0], s["net_pips"].iloc[0]))
    check("non-strict skips entry bar, stops on bar 12",
          len(v0) == 1 and v0["exit_i"].iloc[0] == 12,
          v0[["entry_i", "exit_i"]].values)


def test_trail_uses_prior_bar_atr():
    """D2: trail level for bar i uses ATR(i-1), never ATR(i)."""
    D = make_D(atr_over={10: 4.0, 12: 2.0, 13: 1.0})
    # initial stop far below: 100.009 - 4.0 = 96.009 (out of the way)
    D["o"][11] = 100.0; D["h"][11] = 101.0; D["l"][11] = 99.9
    D["h"][12] = 101.0; D["l"][12] = 99.9
    # hh through bar 12 = 101.0
    # strict   trail(bar13) = 101 - 3*atr[12] = 95.0 -> l[13]=96.5 holds
    # non-strict trail(bar13) = 101 - 3*atr[13] = 98.0 -> l[13]=96.5 stops
    D["l"][13] = 96.5
    s = R.replay(D, strict=True)
    v0 = R.replay(D, strict=False)
    check("strict: bar 13 low 96.5 above prior-ATR trail 95 -> no stop",
          (len(s) == 0) or (s["exit_i"].iloc[0] > 13),
          s[["entry_i", "exit_i"]].values)
    check("non-strict: bar 13 low 96.5 below current-ATR trail 98 -> stop",
          len(v0) == 1 and v0["exit_i"].iloc[0] == 13,
          v0[["entry_i", "exit_i"]].values)


def test_cost_model():
    """NORMAL: one spread round trip. STRESS: spread + 2 x per-side slip."""
    D = make_D(atr_over={10: 2.0})
    D["o"][11] = 100.0
    D["l"][12] = 97.5                        # stop touch bar 12
    s = R.replay(D, strict=True, slip=0.0)
    # stop = 100.009 - 2 = 98.009; net = (98.009-100)/0.01 - 0.9 = -200.0
    check("NORMAL net = -stop - 1 spread", np.isclose(s["net_pips"].iloc[0], -200.0),
          s["net_pips"].iloc[0])
    s2 = R.replay(D, strict=True, slip=0.5)
    # fill = 100 + 0.009 + 0.005 = 100.014; stop level = 100.014 - 2.0 = 98.014
    # exit fill = 98.014 - 0.005 = 98.009
    # net = (98.009 - 100)/0.01 - 0.9 - 0.5 = -200.5
    expected = (98.014 - 0.005 - 100.0) / 0.01 - 0.9 - 0.5
    check("STRESS net = -stop - spread - 2*slip", np.isclose(s2["net_pips"].iloc[0], expected),
          (s2["net_pips"].iloc[0], expected))


def test_no_same_bar_reentry_and_overlap():
    """Exits and new entries never share a bar; positions never overlap."""
    D = R.prepare()
    tr = R.replay(D, strict=True)
    ei = tr["entry_i"].to_numpy(); xi = tr["exit_i"].to_numpy()
    check("no overlap", bool(np.all(xi[:-1] < ei[1:])))
    check("entry after its signal", bool(np.all(ei - 1 >= 0))
          and bool(np.isin(ei - 1, D["sig"]).all()))
    check("unique entries", len(np.unique(ei)) == len(ei))


def test_reproduction_vs_committed_json():
    """THE reproduction gate: strict replay == committed STRICT_RESULTS.json."""
    with open(os.path.join(HERE, "FX_PDH_001_STRICT_RESULTS.json")) as f:
        j = json.load(f)
    res = R.run(slip=0.0)
    check("n", res["n"] == j["n"], (res["n"], j["n"]))
    check("pf", np.isclose(res["pf"], j["pf"]))
    check("net", np.isclose(res["net_pips_per_trade"], j["net_pips_per_trade"]))
    check("t", np.isclose(res["t_stat"], j["t_stat"]))
    check("by_year", all(np.isclose(res["by_year"][int(y)], j["by_year"][y])
                         for y in j["by_year"]))
    check("equity", np.isclose(res["equity_500_at_05pct"]["ending_equity"],
                               j["equity_500_at_05pct"]["ending_equity"]))


def test_seal():
    try:
        R.T.load_5m("USDJPY", "2025-12-01", "2026-01-10")
        check("2026 sealed in loader", False)
    except AssertionError:
        check("2026 sealed in loader", True)


if __name__ == "__main__":
    for fn in (test_entry_bar_stopout, test_trail_uses_prior_bar_atr,
               test_cost_model, test_no_same_bar_reentry_and_overlap,
               test_seal, test_reproduction_vs_committed_json):
        print(fn.__name__)
        fn()
    print()
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)
    print("ALL STRICT REPLAY TESTS PASSED")
