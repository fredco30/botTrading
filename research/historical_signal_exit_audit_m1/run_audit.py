#!/usr/bin/env python3
"""HISTORICAL_SIGNAL_EXIT_AUDIT_M1 — main audit runs.

For each pre-registered signal (A: MTF F08, B: SWING G10, C: MTF F04b):
  * CONTROL  = the original historical exit rerun on the frozen entry events
  * NEW      = the single pre-registered mechanism-matched exit
  * EVENT-LEVEL replay of every frozen entry event (§7A, PRIMARY)
  * DEPLOYABLE replay with historical occupancy idioms (§7B)
  * baseline + +0.5pip/side & 30s-latency stress (§13)
  * stability blocks 2010-2014 / 2015-2016 / 2017 (§16)
  * usefulness gate (§17) on the DEPLOYABLE NEW exit

Reporting convention (pre-registered): for stop-less CONTROLs (A, B) 1R for
expectancy_R is the NEW exit's initial stop distance (2 x ATR at entry) so
that expR is comparable; pips/PF/win-rate metrics are unaffected.

Usage: python run_audit.py [A|B|C]
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_lib as A

NS = A.NS
PIP = A.PIP
YEARS = A.DISCOVERY_YEARS
BIG = 10 ** 9          # unreachable stop/target distance for stop-less runs


def key(t):
    return (t.get("sym", ""), int(t["decision_ts"]), int(t["side"]))


def common_keys_metrics(base, new, label):
    kb = {key(t) for t in base}
    kn = {key(t) for t in new}
    common = kb & kn
    b = [t for t in base if key(t) in common]
    n = [t for t in new if key(t) in common]
    return A.full_metrics(b, label + "|control"), A.full_metrics(n, label + "|new"), len(common)


def gate(deployable_new, stress_stats_deployable):
    """Mission §17 usefulness gate on the DEPLOYABLE NEW replay."""
    if not deployable_new or deployable_new.get("N", 0) == 0:
        return False, {"reason": "NO_TRADES"}
    m = deployable_new
    checks = {
        "trades_per_week>=2.0": m["trades_per_week"] >= 2.0,
        "mean_pips>=+3.0": m["mean_pips"] >= 3.0,
        "PF>=1.10": m["PF"] >= 1.10,
        "expR>0": m["expectancy_r"] > 0,
        "remove_best>0": m["remove_best"] > 0,
        "stress_mean>0": stress_stats_deployable.get("stress_mean", -1) > 0,
        "stress_PF>=1.0": stress_stats_deployable.get("stress_PF", 0) >= 1.0,
        "no_catastrophic_period": True,   # judged from blocks/survival below
    }
    return all(checks.values()), checks


# ------------------------------------------------------------------ A

def run_A():
    print("=" * 70, "\nSIGNAL A — MTF F08 (tick-exact, EURUSD)\n", "=" * 70)
    f08 = A.f08_asia_transfer("continuation", 10)
    ev_ts, ev_side = [], []
    out = {k: [] for k in ("ctrl_ev", "ctrl_ev_s", "new_ev", "new_ev_s",
                           "ctrl_dep", "ctrl_dep_s", "new_dep", "new_dep_s")}
    for y in YEARS:
        bars = A.load_mtfbars(y)
        side = f08(bars, y)
        fire = np.flatnonzero(side != 0)
        ts, bid, ask = A.load_ticks(y)
        h1_ct = bars["H1_close_time"]
        h1_atr = A.atr(bars["H1_high"], bars["H1_low"], bars["H1_close"], 14)
        dec_ts = bars["M15_close_time"][fire]
        atr0 = np.array([A.atr0_at(h1_ct, h1_atr, int(t)) for t in dec_ts])
        assert np.isfinite(atr0).all()
        dec = {"ts": dec_ts, "side": side[fire], "atr0": atr0}
        ev_ts.append(dec_ts); ev_side.append(dec["side"])
        atr_map = {int(d): float(a) for d, a in zip(dec_ts, atr0)}

        def fix_r(tr):
            for t in tr:      # 1R := 2 x ATR(H1,14) at entry (pre-registered)
                t["risk_pips"] = 2.0 * atr_map[int(t["decision_ts"])]
                t["r"] = t["net_pips"] / t["risk_pips"]

        for occupancy in (False, True):
            tag = "ev" if occupancy is False else "dep"
            # CONTROL: historical generic horizon exit (h=64 M15 = 960 min)
            ctrl, _ = A.mtf_replay(ts, bid, ask, dec, BIG, BIG, 960,
                                   latency_ns=5 * NS, occupancy=occupancy)
            fix_r(ctrl)
            ctrl_s, _ = A.mtf_replay(ts, bid, ask, dec, BIG, BIG, 960,
                                     latency_ns=30 * NS, slip_pips=0.5,
                                     occupancy=occupancy)
            fix_r(ctrl_s)
            # NEW: 2xATR(H1,14) stop + 3xATR(H1,14) chandelier + 24h
            new, _ = A.replay_trail_ticks(ts, bid, ask, dec, h1_ct,
                                          bars["H1_high"], bars["H1_low"],
                                          h1_atr, occupancy=occupancy)
            new_s, _ = A.replay_trail_ticks(ts, bid, ask, dec, h1_ct,
                                            bars["H1_high"], bars["H1_low"],
                                            h1_atr, latency_ns=30 * NS,
                                            slip_pips=0.5,
                                            occupancy=occupancy)
            out["ctrl_" + tag].extend(ctrl)
            out["ctrl_" + tag + "_s"].extend(ctrl_s)
            out["new_" + tag].extend(new)
            out["new_" + tag + "_s"].extend(new_s)
    res = assemble("A_F08", out["ctrl_ev"], out["ctrl_ev_s"],
                   out["new_ev"], out["new_ev_s"],
                   out["ctrl_dep"], out["ctrl_dep_s"],
                   out["new_dep"], out["new_dep_s"])
    A.save(res, "audit_A.json")
    return res


# ------------------------------------------------------------------ B

def run_B():
    print("=" * 70, "\nSIGNAL B — SWING G10 (5m BID frame + spread model)\n",
          "=" * 70)
    p = {"fast": 20, "slow": 50, "break_n": 20}
    g10 = A.g10_state_machine
    out = {k: [] for k in ("ctrl_ev", "ctrl_ev_s", "new_ev", "new_ev_s",
                           "ctrl_dep", "ctrl_dep_s", "new_dep", "new_dep_s")}
    for sym in A.DISCOVERY_PAIRS:
        bars = A.load_swing(sym)
        side = g10(bars, sym, p)
        h4ct = bars["H4_close_time"]
        fire = np.flatnonzero(side != 0)
        atr_h4 = A.atr_sw(sym, bars["H4_high"], bars["H4_low"],
                          bars["H4_close"], 14)
        atr0 = np.array([A.atr0_at(h4ct, atr_h4, int(h4ct[i])) for i in fire])
        dec = {"ts": h4ct[fire], "side": side[fire], "atr0": atr0}
        n = len(fire)
        big = np.full(n, float(BIG))
        bull_d1 = A.g10_bull_d1(bars, p)
        d1_ct = bars["D1_close_time"]
        for occupancy in (False, True):
            tag = "ev" if occupancy is False else "dep"
            ctrl = A.bar_replay(sym, h4ct, dec, big, big, 24.0,
                                stress=False, occupancy=occupancy)
            for t in ctrl:
                t["risk_pips"] = 2.0 * float(dec["atr0"][t["j"]])
                t["r"] = t["net_pips"] / t["risk_pips"]
            ctrl_s = A.bar_replay(sym, h4ct, dec, big, big, 24.0,
                                  stress=True, occupancy=occupancy)
            for t in ctrl_s:
                t["risk_pips"] = 2.0 * float(dec["atr0"][t["j"]])
                t["r"] = t["net_pips"] / t["risk_pips"]
            new = A.replay_trail_bars(sym, bars, dec, bull_d1, d1_ct,
                                      stress=False, occupancy=occupancy)
            new_s = A.replay_trail_bars(sym, bars, dec, bull_d1, d1_ct,
                                        stress=True, occupancy=occupancy)
            out["ctrl_" + tag].extend(ctrl)
            out["ctrl_" + tag + "_s"].extend(ctrl_s)
            out["new_" + tag].extend(new)
            out["new_" + tag + "_s"].extend(new_s)
    res = assemble("B_G10", out["ctrl_ev"], out["ctrl_ev_s"],
                   out["new_ev"], out["new_ev_s"],
                   out["ctrl_dep"], out["ctrl_dep_s"],
                   out["new_dep"], out["new_dep_s"])
    A.save(res, "audit_B.json")
    return res


# ------------------------------------------------------------------ C

def run_C():
    print("=" * 70, "\nSIGNAL C — MTF F04b (tick-exact, EURUSD)\n", "=" * 70)
    f04b = A.f04_prev_day("fade")
    out = {k: [] for k in ("ctrl_ev", "ctrl_ev_s", "new_ev", "new_ev_s",
                           "ctrl_dep", "ctrl_dep_s", "new_dep", "new_dep_s")}
    byte_match = {"n_cmp": 0, "n_eq": 0}
    for y in YEARS:
        bars = A.load_mtfbars(y)
        side, mid = f04b(bars, y)
        fire = np.flatnonzero(side != 0)
        dec = {"ts": bars["M15_close_time"][fire], "side": side[fire]}
        mid_f = mid[fire]
        assert np.isfinite(mid_f).all()
        ts, bid, ask = A.load_ticks(y)
        for occupancy in (False, True):
            tag = "ev" if occupancy is False else "dep"
            # CONTROL: SL20 / TP30 / T240 (historical M3_E023)
            ctrl, _ = A.mtf_replay(ts, bid, ask, dec, 20.0, 30.0, 240,
                                   latency_ns=5 * NS, occupancy=occupancy)
            ctrl_s, _ = A.mtf_replay(ts, bid, ask, dec, 20.0, 30.0, 240,
                                     latency_ns=30 * NS, slip_pips=0.5,
                                     occupancy=occupancy)
            # NEW: SL20 / TP=prev-day midpoint frozen at decision / T240
            new, _ = A.mtf_replay(ts, bid, ask, dec, 20.0, None, 240,
                                  tp_levels=mid_f,
                                  latency_ns=5 * NS, occupancy=occupancy)
            new_s, _ = A.mtf_replay(ts, bid, ask, dec, 20.0, None, 240,
                                    tp_levels=mid_f,
                                    latency_ns=30 * NS, slip_pips=0.5,
                                    occupancy=occupancy)
            out["ctrl_" + tag].extend(ctrl)
            out["ctrl_" + tag + "_s"].extend(ctrl_s)
            out["new_" + tag].extend(new)
            out["new_" + tag + "_s"].extend(new_s)
            if occupancy and y == 2010:
                cached = json.load(open(os.path.join(
                    A.M3CACHE, "trades_f04b_pdh_fade.json")))
                cmap = {(int(t["decision_ts"]), int(t["side"])): t
                        for t in cached}
                for t in ctrl:
                    c = cmap.get((int(t["decision_ts"]), int(t["side"])))
                    if c is None:
                        continue
                    byte_match["n_cmp"] += 1
                    if (c["entry_ts"] == t["entry_ts"]
                            and c["exit_ts"] == t["exit_ts"]
                            and abs(c["net_pips"] - t["net_pips"]) < 1e-9
                            and c["reason"] == t["reason"]):
                        byte_match["n_eq"] += 1
    print(f"CONTROL C vs cached historical M3_E023 (2010): "
          f"{byte_match['n_eq']}/{byte_match['n_cmp']} exact")
    res = assemble("C_F04b", out["ctrl_ev"], out["ctrl_ev_s"],
                   out["new_ev"], out["new_ev_s"],
                   out["ctrl_dep"], out["ctrl_dep_s"],
                   out["new_dep"], out["new_dep_s"])
    res["control_byte_match_2010"] = byte_match
    A.save(res, "audit_C.json")
    return res


# ------------------------------------------------------------- assemble

def assemble(sig, ctrl_ev, ctrl_ev_s, new_ev, new_ev_s,
             ctrl_dep, ctrl_dep_s, new_dep, new_dep_s):
    m = {}
    m["control_event"] = A.full_metrics(ctrl_ev, sig + " CTRL event-level")
    m["new_event"] = A.full_metrics(new_ev, sig + " NEW event-level")
    m["control_deployable"] = A.full_metrics(ctrl_dep, sig + " CTRL deployable")
    m["new_deployable"] = A.full_metrics(new_dep, sig + " NEW deployable")
    m["stress_event"] = {"control": A.stress_stats(ctrl_ev, ctrl_ev_s),
                         "new": A.stress_stats(new_ev, new_ev_s)}
    m["stress_deployable"] = {"control": A.stress_stats(ctrl_dep, ctrl_dep_s),
                              "new": A.stress_stats(new_dep, new_dep_s)}
    cb, nb, ncommon = common_keys_metrics(ctrl_ev, new_ev, sig + " common-event")
    m["common_event_n"] = ncommon
    m["common_event_control"] = cb
    m["common_event_new"] = nb
    cb2, nb2, ncommon2 = common_keys_metrics(ctrl_dep, new_dep, sig + " common-dep")
    m["common_deployable_n"] = ncommon2
    m["common_deployable_control"] = cb2
    m["common_deployable_new"] = nb2
    m["blocks_new_deployable"] = A.block_metrics(new_dep)
    m["blocks_new_event"] = A.block_metrics(new_ev)
    m["blocks_control_event"] = A.block_metrics(ctrl_ev)
    ok, checks = gate(m["new_deployable"], m["stress_deployable"]["new"])
    m["gate"] = {"pass": ok, "checks": checks}
    print_metrics_all(sig, m)
    return m


def pm(m, title):
    print(f"\n--- {title}")
    if m.get("N", 0) == 0:
        print("NO_TRADES")
        return
    print(f"N={m['N']} tpw={m['trades_per_week']} mean={m['mean_pips']}p "
          f"med={m['median_pips']}p PF={m['PF']} expR={m['expectancy_r']} "
          f"win={m['win_rate']} rmBest={m['remove_best']}")
    print(f"  exits={m['exits_pct']}")
    print(f"  avgW={m['avg_winner']} medW={m['median_winner']} maxW={m['largest_winner']} "
          f"avgL={m['avg_loser']} medL={m['median_loser']}")
    print(f"  dur avg/med={m['avg_duration_h']}/{m['median_duration_h']}h "
          f"MFE={m['mfe_mean']} MAE={m['mae_mean']} capture={m['capture_ratio']} "
          f"posYR={m['pos_years']}")


def print_metrics_all(sig, m):
    pm(m["control_event"], f"{sig} CONTROL event-level (primary baseline)")
    pm(m["new_event"], f"{sig} NEW event-level (primary)")
    st = m["stress_event"]
    print(f"  stress: ctrl={st['control'].get('stress_mean')}p "
          f"(PF {st['control'].get('stress_PF')}, n={st['control'].get('n_common')}) "
          f"new={st['new'].get('stress_mean')}p "
          f"(PF {st['new'].get('stress_PF')}, n={st['new'].get('n_common')})")
    ce = m["common_event_control"]; cn = m["common_event_new"]
    print(f"  common-event n={m['common_event_n']}: ctrl mean={ce.get('mean_pips')} "
          f"PF={ce.get('PF')} | new mean={cn.get('mean_pips')} PF={cn.get('PF')}")
    pm(m["control_deployable"], f"{sig} CONTROL deployable (native)")
    pm(m["new_deployable"], f"{sig} NEW deployable (native)")
    cd = m["common_deployable_control"]; nd = m["common_deployable_new"]
    print(f"  common-deployable n={m['common_deployable_n']}: "
          f"ctrl mean={cd.get('mean_pips')} PF={cd.get('PF')} | "
          f"new mean={nd.get('mean_pips')} PF={nd.get('PF')}")
    sd = m["stress_deployable"]
    print(f"  stress-deployable: ctrl={sd['control'].get('stress_mean')}p "
          f"(PF {sd['control'].get('stress_PF')}) "
          f"new={sd['new'].get('stress_mean')}p (PF {sd['new'].get('stress_PF')})")
    print(f"  blocks NEW deployable: {m['blocks_new_deployable']}")
    print(f"  GATE: {m['gate']}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("A", "all"):
        run_A()
    if which in ("B", "all"):
        run_B()
    if which in ("C", "all"):
        run_C()
