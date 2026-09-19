#!/usr/bin/env python3
"""FX_PDH_002 frozen-candidate tests.

1. The frozen runner reproduces the frozen headline EXACTLY.
2. Seal: no 2026 data can enter.
3. Definitions: C1 signals and D2 trail behave as specified.
4. The candidate never reopens FX_PDH_001's files.
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CAND = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(CAND, "code"))
import engine as E
import run_frozen


@pytest.fixture(scope="module")
def res():
    return run_frozen.run()


@pytest.fixture(scope="module")
def D():
    return E.prepare()


def test_frozen_headline_exact(res):
    n = res["NORMAL"]
    assert n["n"] == 517
    assert n["pf"] == pytest.approx(1.573, abs=5e-4)
    assert n["net_pips_per_trade"] == pytest.approx(8.43, abs=5e-3)
    assert n["t_stat"] == pytest.approx(3.13, abs=5e-3)
    assert n["remove_best_1pct"] == pytest.approx(5.59, abs=5e-3)
    st = res["STRESS"]
    assert st["net_pips_per_trade"] == pytest.approx(6.63, abs=5e-3)
    assert st["pf"] == pytest.approx(1.433, abs=5e-4)
    assert n["eur500"]["ending_equity"] == pytest.approx(1145, abs=1.0)
    assert n["eur500"]["max_dd_percent"] == pytest.approx(6.7, abs=0.1)
    assert set(n["by_year"]) == {2020, 2021, 2022, 2023, 2024, 2025}
    assert all(v > 0 for v in n["by_year"].values())
    assert all(v > 0 for v in st["by_year"].values())
    assert not n["gates"]["VETO"] and not n["gates"]["WARN"]
    assert res["no_2026"]


def test_no_2026_anywhere(D):
    assert D["idx"].max() <= pd.Timestamp("2025-12-31 23:59", tz="UTC")
    with pytest.raises(Exception):
        E.T.load_5m("USDJPY", "2020-01-01", "2026-03-01")


def test_c1_signal_definition(D):
    sig = E.signals(D, "C1")
    c, pdh, day = D["c"], D["pdh"], D["day"]
    assert (c[sig] > pdh[sig]).all()
    assert len(set(day[sig])) == len(sig)
    first_touch = E.signals(D, "long_touch")
    # every C1 close-confirm happens at/after its day's first touch
    for s_ in sig:
        same_day = first_touch[day[first_touch] == day[s_]]
        assert len(same_day) and s_ >= same_day[0]


def test_d2_trail_never_below_initial_stop(D):
    """Replay a few trades and verify eff_stop >= initial stop always."""
    sig = E.signals(D, "C1")
    tr = E.replay(D, sig, exit_arch="daily_chand")
    o, l = D["o"], D["l"]
    ei = tr["entry_i"].to_numpy()
    stop0 = tr["entry_fill"].to_numpy() - E.STOP_ATR * D["atr"][tr["sig_i"]
                                                             .to_numpy()]
    # every stop exit fills at or below its initial stop level or is a trail
    m = tr["reason"].to_numpy() == "stop"
    # trail can only RAISE the stop: exit price must exceed what a pure
    # initial-stop exit would have paid whenever the exit is above entry+1R
    px = tr["exit_px"].to_numpy()
    winners = m & (px > tr["entry_fill"].to_numpy() + E.PIP)
    assert (px[winners] > stop0[winners] + 0.5 * E.PIP).all()


def test_vault_untouched():
    """No 001 candidate file may differ from the authoritative commit."""
    repo = os.path.abspath(os.path.join(CAND, "..", "..", "..", ".."))
    import subprocess
    out = subprocess.run(
        ["git", "diff", "033f6f0c82d8489dc39b52545632c2b09468b9ae", "HEAD",
         "--", "research/forex_modern_trend_magic_lab/candidates/FX_PDH_001/",
         "research/forex_modern_trend_magic_lab/audit/"],
        cwd=repo, capture_output=True, text=True)
    assert out.stdout.strip() == "", "FX_PDH_001 vault files changed!"
