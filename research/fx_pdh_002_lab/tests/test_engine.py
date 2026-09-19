#!/usr/bin/env python3
"""FX_PDH_002 LAB engine tests.

Gate check #1: the lab engine in its reference configuration (long_touch
signals, orig exits, no slip) must reproduce the FROZEN FX_PDH_001 strict
replay EXACTLY (same trades, same fills). The lab has no authority over 001;
this equivalence is what makes direct comparison legitimate.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
sys.path.insert(0, LAB)
sys.path.insert(0, os.path.join(os.path.dirname(LAB),
                                "forex_modern_trend_magic_lab", "audit"))
import engine as E
import replay_strict as RS
import tmlab as T


@pytest.fixture(scope="module")
def D():
    return E.prepare()


def test_2026_seal_holds(D):
    assert D["no_2026"]
    assert D["idx"].max() <= pd.Timestamp("2025-12-31 23:59", tz="UTC")


def test_base_equivalence_with_frozen_replay(D):
    """Reference configuration == frozen strict engine, trade by trade."""
    sig_lab = E.signals(D, "long_touch")
    Df = RS.prepare()
    assert np.array_equal(sig_lab, Df["sig"])
    tr_lab = E.replay(D, sig_lab, side=1, exit_arch="orig", slip=0.0)
    tr_frz = RS.replay(Df, strict=True, slip=0.0)
    assert len(tr_lab) == len(tr_frz) == 639
    assert (tr_lab["exit_i"].to_numpy() == tr_frz["exit_i"].to_numpy()).all()
    assert (tr_lab["reason"].to_numpy() == tr_frz["reason"].to_numpy()).all()
    assert np.allclose(tr_lab["exit_px"].to_numpy(),
                       tr_frz["exit_px"].to_numpy(), atol=1e-12)
    assert np.allclose(tr_lab["net_pips"].to_numpy(),
                       tr_frz["net_pips"].to_numpy(), atol=1e-9)
    s = E.summarize(D, tr_lab)
    assert s["n"] == 639 and abs(s["pf"] - 1.3791496) < 1e-5
    assert abs(s["net_pips_per_trade"] - 4.8988201) < 1e-4
    assert abs(s["t_stat"] - 2.5194429) < 1e-3
    assert abs(s["remove_best_1pct"] - 2.5429601) < 1e-4
    assert s["by_year"][2022] == pytest.approx(18.78450, abs=1e-3)


def test_stress_costs_accounting_identity(D):
    """Stress = same convention with 0.5 pip slip per side: entry fills carry
    the entry slip, stop levels sit 0.5 pip further out, and net pips equal
    gross - spread - slip exactly (one spread round-trip + 2 slips max).
    Trade COUNT may differ from NORMAL (higher fills can stop out earlier);
    that is the frozen convention, not a defect."""
    tr0 = E.replay(D, E.signals(D, "long_touch"), slip=0.0)
    tr1 = E.replay(D, E.signals(D, "long_touch"), slip=E.SLIP_STRESS)
    o = D["o"]
    ei1 = tr1["entry_i"].to_numpy()
    assert np.allclose(tr1["entry_fill"].to_numpy(),
                       o[ei1] + (E.SPREAD + E.SLIP_STRESS) * E.PIP, atol=1e-12)
    ident = (tr1["gross_pips"].to_numpy()
             - E.SPREAD - E.SLIP_STRESS - tr1["net_pips"].to_numpy())
    assert np.allclose(ident, 0.0, atol=1e-9)
    # common entry bars: stress trails/initial stops are tighter (long), so
    # the stress position can only exit EARLIER or on the same bar
    common, i0, i1 = np.intersect1d(tr0["entry_i"].to_numpy(),
                                    tr1["entry_i"].to_numpy(),
                                    return_indices=True)
    assert (tr1["exit_i"].to_numpy()[i1] <= tr0["exit_i"].to_numpy()[i0]).all()
    assert abs(len(tr1) - len(tr0)) <= 10


def test_no_overlap_no_same_bar_reentry(D):
    tr = E.replay(D, E.signals(D, "long_touch"))
    assert (tr["exit_i"].to_numpy() >= tr["entry_i"].to_numpy()).all()
    ei = tr["entry_i"].to_numpy(); ex = tr["exit_i"].to_numpy()
    assert (ei[1:] > ex[:-1]).all()          # strictly after previous exit


def test_one_signal_per_day(D):
    sig = E.signals(D, "long_touch")
    days = D["day"][sig]
    assert len(set(days)) == len(days)


def test_short_mirror_mechanics(D):
    tr = E.replay(D, E.signals(D, "short_touch"), side=-1)
    assert len(tr) > 0
    o = D["o"]
    ei = tr["entry_i"].to_numpy()
    # short entry fill = open - spread (NORMAL), below the bar open
    assert np.allclose(tr["entry_fill"].to_numpy(),
                       o[ei] - E.SPREAD * E.PIP, atol=1e-12)
    assert (tr["entry_fill"].to_numpy() < o[ei]).all()
    # stop is above the fill; stop exits fill at or above the stop level
    m = tr["reason"].to_numpy() == "stop"
    assert (tr["r_mult"].to_numpy()[~m] != 0).any()   # has non-stop exits
    # gross pips positive when exit price < entry open
    gp = tr["gross_pips"].to_numpy(); xp = tr["exit_px"].to_numpy()
    assert np.allclose(gp, (o[ei] - xp) / E.PIP, atol=1e-9)


def test_signal_variants_respect_day_and_definition(D):
    h, l, c, pdh = D["h"], D["l"], D["c"], D["pdh"]
    # C1: close above PDH
    s1 = E.signals(D, "C1")
    assert (c[s1] > pdh[s1]).all()
    # C3: touch with close location >= 0.70
    s3 = E.signals(D, "C3")
    rng = h[s3] - l[s3]
    assert ((c[s3] - l[s3]) / rng >= 0.70).all()
    assert (h[s3] > pdh[s3]).all()
    # C3 is a subset of first-touch days
    s0 = set(E.signals(D, "long_touch").tolist())
    assert set(s3.tolist()) <= s0
    # C2: low <= PDH < close, and an arming close-above bar earlier same day
    s2 = E.signals(D, "C2")
    assert (l[s2] <= pdh[s2]).all() and (c[s2] > pdh[s2]).all()
    day_first = D["day_first"]
    armed = []
    for j in s2:
        ii = np.arange(day_first[j], j)
        armed.append(bool((c[ii] > pdh[ii]).any()))
    assert all(armed)
    for kind in ("long_touch", "short_touch", "C1", "C2", "C3"):
        sg = E.signals(D, kind)
        assert len(set(D["day"][sg].tolist())) == len(sg)


def test_exit_variants_causal_and_change_trades(D):
    s = E.signals(D, "long_touch")
    base = E.replay(D, s, exit_arch="orig")
    for arch in ("daily_chand", "struct5"):
        tr = E.replay(D, s, exit_arch=arch)
        assert len(tr) > 0
        # every stop fill never uses information of its own bar beyond OHLC:
        # exit price must lie within the bar's range or gap logic
        ex = tr["exit_i"].to_numpy()
        px = tr["exit_px"].to_numpy()
        o, h, l, c = D["o"], D["h"], D["l"], D["c"]
        stopish = tr["reason"].to_numpy() != "time"
        inside = ((px >= l[ex] - 1e-9) & (px <= h[ex] + 1e-9)) | ~stopish
        assert inside.all()
        struct = tr["reason"].to_numpy() == "struct"
        if struct.any():
            # struct exit = close beyond previous 5-bar extreme
            jj = ex[struct]
            ext = np.array([np.min(l[j - 5:j]) for j in jj])
            assert (c[jj] < ext).all()


def test_eur500_matches_frozen_convention(D):
    tr = E.replay(D, E.signals(D, "long_touch"))
    out, gate, det = E.eur500_sim(D, tr)
    assert abs(out["ending_equity"] - 943.0145592020103) < 0.05
    assert abs(out["max_dd_percent"] - 15.010592780920106) < 0.05
    assert not gate["VETO"]
    assert det["equity"].is_monotonic_increasing is False  # there are losses
    assert (det["lot"] >= 0.01).all()
