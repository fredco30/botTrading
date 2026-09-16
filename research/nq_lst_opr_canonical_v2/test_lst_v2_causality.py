#!/usr/bin/env python3
"""Causality + frozen-mechanics tests for LST_OPR_CANONICAL_V2 (section 25)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_modern_strategy_lab"))
import lab_lib as L   # noqa: E402
import lst_v2_lib as S  # noqa: E402

ET = "America/New_York"


def mk_frame(day, bars):
    rows = []
    for hhmm, o, h, l, c, v in bars:
        t = pd.Timestamp(f"{day} {hhmm//100:02d}:{hhmm%100:02d}", tz=ET).tz_convert("UTC")
        rows.append((t, o, h, l, c, v))
    return pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close",
                                       "volume"]).set_index("ts").assign(n_min=5, n_instr=1)


PM = [((240 + i * 5) // 60 * 100 + (240 + i * 5) % 60, 100, 101, 99, 100, 10)
      for i in range(13)]
BASE = [(930, 100, 100.4, 99.6, 100.2, 10),
        (935, 100.2, 100.6, 99.8, 100.4, 10),
        (940, 100.4, 100.8, 100.0, 100.6, 10)]   # OPR = 100.8 / 99.6


def run(frame, variant="A", atr=2.0, flow=1):
    x = L.build_ctx(frame)
    vc = S.V2Ctx(x)
    for gi in vc.days:
        d = vc.days[gi]
        d.side, d.atr = flow, atr
        sp = x.sess_pos[x.groups[gi][:3]]
        d.oh, d.ol = float(x.h[sp].max()), float(x.l[sp].min())
    tr, stats = S.run_v2(x, vc, variant, S.COSTS["NORMAL"])
    return pd.DataFrame(tr), stats, x, vc


def test_breakout_retest_entry_next_open_and_2r_target():
    f = mk_frame("2021-06-01", PM + BASE + [
        (945, 100.6, 101.6, 100.5, 101.4, 10),   # breakout (close 101.4 > 100.8)
        (950, 101.4, 101.5, 100.9, 101.0, 10),   # no touch (100.9 > 100.8)
        (955, 101.0, 101.2, 100.7, 100.9, 10),   # retest: low 100.7<=100.8, close>=OH
        (1000, 100.9, 103.9, 100.9, 103.8, 10),  # ENTRY 100.9; R=0.2? -> widened? NO min: stop=100.7, R=0.2, tgt=101.3 touched intrabar
    ])
    tf, st, x, vc = run(f)
    assert len(tf) == 1
    t = tf.iloc[0]
    assert t["kind"] == "A" and t["side"] == 1
    assert abs(t["fill"] - 100.9) < 1e-9
    assert abs(t["level"] - 100.7) < 1e-9           # technical stop, no minimum
    assert t["exit_reason"] == "2R_TARGET"
    assert abs(t["exit_px"] - 101.3) < 1e-9         # entry + 2*0.2
    assert abs(t["gross"] - 0.4) < 1e-9


def test_runaway_cancel_before_entry():
    f = mk_frame("2021-06-01", PM + BASE + [
        (945, 100.6, 101.6, 100.5, 101.4, 10),   # breakout; atr=2 -> runaway >= 102.8? no
        (950, 101.4, 103.0, 101.2, 102.9, 10),   # high 103.0 >= 102.8 -> CANCELLED_ATR
        (955, 102.0, 102.1, 100.7, 100.9, 10),   # would-be retest (ignored)
    ])
    tf, st, x, vc = run(f)
    assert len(tf) == 0
    assert st["CANCELLED_ATR"] == 1


def test_no_6bar_timeout_late_retest_still_trades():
    f = mk_frame("2021-06-01", PM + BASE + [
        (945, 100.6, 101.6, 100.5, 101.4, 10),   # breakout
        (950, 101.4, 101.5, 101.3, 101.4, 10),
        (955, 101.4, 101.5, 101.3, 101.5, 10),
        (1000, 101.5, 101.6, 101.4, 101.5, 10),
        (1005, 101.5, 101.6, 101.4, 101.6, 10),
        (1010, 101.6, 101.7, 101.5, 101.6, 10),
        (1015, 101.6, 101.7, 101.5, 101.7, 10),  # bar 6 after breakout: V1 dead here
        (1020, 101.7, 101.0, 100.7, 100.9, 10),  # retest (touch 100.7, close 100.9)
        (1025, 100.9, 101.0, 100.8, 100.9, 10),  # ENTRY at open 100.9
    ])
    tf, st, x, vc = run(f)
    assert len(tf) == 1 and tf.iloc[0]["fill"] == 100.9


def test_obstacle_filter_blocks():
    f = mk_frame("2021-06-01", PM + BASE + [
        (945, 100.6, 101.6, 100.5, 101.4, 10),
        (950, 101.4, 101.5, 100.9, 101.0, 10),
        (955, 101.0, 101.2, 100.7, 100.9, 10),   # retest close 100.9, ext 100.7, R=0.2
    ])
    x = L.build_ctx(f)
    x.pdh[0] = 101.0     # obstacle 0.1 above projection < R=0.2 -> blocked
    assert S._a_obstacle_ok(x, 0, 1, 100.9, 100.7) is False
    x.pdh[0] = 101.5     # 0.6 above >= 0.2 -> pass
    assert S._a_obstacle_ok(x, 0, 1, 100.9, 100.7) is True


def test_b_target_after_valid_rr():
    # shallow false break -> deep RR: ext 99.5, retest close 99.7 =>
    # RR = (100.8-99.7)/(99.7-99.5) = 5.5 >= 2 -> trade, target = OH 100.8
    f = mk_frame("2021-06-01", PM + BASE + [
        (945, 100.2, 100.4, 99.5, 100.1, 10),    # false break low 99.5 < OL 99.6
        (950, 99.7, 99.85, 99.65, 99.8, 10),     # reintegration close 99.8; ext 99.5; runaway<high<100.1 ok
        (955, 99.8, 99.85, 99.55, 99.7, 10),     # retest: low 99.55<=99.6, close 99.7>=99.6, RR 5.5 -> armed
        (1000, 99.7, 100.9, 99.65, 100.8, 10),   # ENTRY 99.7 -> target 100.8 touched
    ])
    tf, st, x, vc = run(f, variant="B")
    assert len(tf) == 1
    t = tf.iloc[0]
    assert abs(t["level"] - 99.5) < 1e-9
    assert t["exit_reason"] == "OPPOSITE_OPR_TARGET"
    assert abs(t["exit_px"] - 100.8) < 1e-9
    assert abs(t["gross"] - 1.1) < 1e-9


def test_b_rr_gate_blocks_low_rr():
    f = mk_frame("2021-06-01", PM + BASE + [
        (945, 100.2, 100.4, 99.0, 100.1, 10),
        (950, 100.1, 100.3, 99.9, 100.2, 10),
        (955, 100.2, 100.3, 99.5, 99.8, 10),     # retest: RR = (100.8-99.8)/(99.8-99.0)=1.25 <2
    ])
    tf, st, x, vc = run(f, variant="B")
    assert len(tf) == 0 and st["RR_REJECTS"] == 1


def test_b_cancel_1r_runaway():
    f = mk_frame("2021-06-01", PM + BASE + [
        (945, 100.2, 100.4, 99.0, 100.1, 10),    # false break; ext 99.0
        (950, 100.1, 100.3, 99.9, 100.2, 10),    # reintegration; ref 100.2, R=1.2 -> runaway >= 101.4
        (955, 100.2, 101.5, 100.1, 101.4, 10),   # high 101.5 >= 101.4 -> CANCELLED_1R
    ])
    tf, st, x, vc = run(f, variant="B")
    assert len(tf) == 0 and st["CANCELLED_1R"] == 1


def test_b_cycle_reform_no_cancel():
    f = mk_frame("2021-06-01", PM + BASE + [
        (945, 100.2, 100.4, 99.0, 100.1, 10),    # false break #1
        (950, 100.1, 100.3, 99.9, 100.2, 10),    # reintegration #1 (ref 100.2)
        (955, 100.2, 100.3, 99.4, 99.3, 10),     # close < OL -> cycle REFORMS (ext 99.0->99.0? low 99.4 keeps ext 99.0)
        (1000, 99.3, 99.8, 99.2, 99.7, 10),      # close 99.7 > 99.6 -> reintegration #2 (ref 99.7, ext 99.0)
        (1005, 99.7, 99.8, 99.5, 99.7, 10),      # retest: touch 99.5<=99.6, close>=99.6
    ])
    tf, st, x, vc = run(f, variant="B")
    # final retest RR = (100.8-99.7)/(99.7-99.0) = 1.571 < 2 -> RR_REJECT
    assert st["RR_REJECTS"] == 1 and len(tf) == 0


def test_opr_unavailable_first_window_bar_only():
    # breakout close ABOVE OH at 09:45 uses the completed OPR; if OPR bars were
    # missing the day is neutral. Structural: ensure decisions start at 09:45.
    f = mk_frame("2021-06-01", PM + BASE + [
        (945, 100.6, 101.6, 100.5, 101.4, 10),
    ])
    tf, st, x, vc = run(f)
    # no retest before window end -> no trade, but setup counted
    assert st["SETUPS_A"] == 1 and len(tf) == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
