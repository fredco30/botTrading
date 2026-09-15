#!/usr/bin/env python3
"""AUTONOMOUS_EDGE_DISCOVERY_M2 — complete strategies for tick-exact replay.

F17b (primary): post-spike deep-retrace fade.
  Context : bar k with range >= SPIKE_K x mean30(range) and body >= 0.6 x range
            (directional range expansion), followed by 3 completed bars whose
            extreme retraces >= RETR x spike range.
  Direction: AGAINST the spike (up-spike -> SHORT, down-spike -> LONG).
  Entry   : first executable tick after decision+5s on the execution side
            (SHORT = BID, LONG = ASK). Decision = close_time of bar j = k+3.
  Exit    : symmetric bracket SL/TP (pips), time exit T minutes.
  Session : none. Occupancy: one position at a time (never more).

F16a (backup): tick-flow imbalance continuation, h=240 bracket.
"""
import numpy as np

import families_m2 as F
import m2lib as M


def f17b_sig(thr):
    def sig_fn(ex, y):
        n = len(ex["close"])
        sig = np.zeros(n, np.int8)
        for j in range(31, n):
            f = F.f17_feat(None, ex, j)
            if f is None:
                continue
            if f["aux"] == 1 and f["value"] >= thr:
                sig[j] = -1
            elif f["aux"] == -1 and f["value"] >= thr:
                sig[j] = 1
        return sig
    return sig_fn


def f16a_sig(z=0.25, w=15):
    def sig_fn(ex, y):
        up, dn = ex["up"], ex["dn"]
        s_up = M.pd.Series(up).rolling(w).sum().to_numpy()
        s_dn = M.pd.Series(dn).rolling(w).sum().to_numpy()
        imb = (s_up - s_dn) / np.maximum(s_up + s_dn, 1)
        n = len(imb)
        sig = np.zeros(n, np.int8)
        ok = np.isfinite(imb) & (np.arange(n) >= w)
        sig[ok & (imb >= z)] = 1
        sig[ok & (imb <= -z)] = -1
        return sig
    return sig_fn


STRATEGIES = {
    # ---- F17b threshold neighborhood (T240, SL15/TP15) -----------------
    "f17b_t067_T240": dict(sig_fn=f17b_sig(2 / 3), sl=15, tp=15, tmin=240),
    "f17b_t060_T240": dict(sig_fn=f17b_sig(0.60), sl=15, tp=15, tmin=240),
    "f17b_t075_T240": dict(sig_fn=f17b_sig(0.75), sl=15, tp=15, tmin=240),
    # ---- time-exit neighborhood ----------------------------------------
    "f17b_t067_T120": dict(sig_fn=f17b_sig(2 / 3), sl=15, tp=15, tmin=120),
    # ---- bracket plateau ------------------------------------------------
    "f17b_t067_T240_b10": dict(sig_fn=f17b_sig(2 / 3), sl=10, tp=10, tmin=240),
    "f17b_t067_T240_b20": dict(sig_fn=f17b_sig(2 / 3), sl=20, tp=20, tmin=240),
    # ---- F16a backup -----------------------------------------------------
    "f16a_T240": dict(sig_fn=f16a_sig(), sl=15, tp=15, tmin=240),
}
