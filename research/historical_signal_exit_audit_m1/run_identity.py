#!/usr/bin/env python3
"""HISTORICAL_SIGNAL_EXIT_AUDIT_M1 — ENTRY FREQUENCY AUDIT + ENTRY IDENTITY.

Reconstructs the exact historical entry event sets for the pre-registered
shortlist (A: MTF F08, B: SWING G10, C: MTF F04b) from the historical source
code and the validated local caches, verifies each against its historical
ledger/cached artifacts, and writes ENTRY_IDENTITY.md.

No exit PnL is computed here. Any unexplained mismatch => STOP that signal.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_lib as A

PIP = A.PIP
NS = A.NS
YEARS = A.DISCOVERY_YEARS


def screen_h_mtf(bars, side, h):
    """[m3lib@29dfb7b screen_year idiom] gross mid, entry next bar open,
    exit close[i+h], non-overlapping in bar index."""
    opn = bars["M15_open"]; close = bars["M15_close"]; n = len(close)
    rets = []
    last = -10 ** 9
    for i in np.flatnonzero(side != 0):
        if i <= last or i + 1 >= n:
            continue
        j = min(i + h, n - 1)
        rets.append(side[i] * (close[j] - opn[i + 1]) / PIP)
        last = j
    return np.asarray(rets)


def fmt_ts(ns):
    return pd.Timestamp(int(ns), unit="ns", tz="UTC").strftime("%Y-%m-%d %H:%M")


def identity_A():
    """MTF F08 — London 07:00 continuation of Asia move >= 10 pips."""
    f08 = A.f08_asia_transfer("continuation", 10)
    ev_ts, ev_side, screen = [], [], {}
    for y in YEARS:
        bars = A.load_mtfbars(y)
        side = f08(bars, y)
        fire = np.flatnonzero(side != 0)
        ev_ts.append(bars["M15_close_time"][fire])
        ev_side.append(side[fire])
        screen[y] = screen_h_mtf(bars, side, 64)
    ts = np.concatenate(ev_ts)
    sd = np.concatenate(ev_side)
    pool = np.concatenate([screen[y] for y in YEARS])
    res = {
        "name": "A — MTF F08 Asia->London continuation (|move|>=10p)",
        "source_commit": "29dfb7b1710c58bb939e39a869d3aff26be01af9",
        "source_path": "research/mtf_discovery_m1/families_m3.py::f08_asia_transfer",
        "params": 'mode="continuation", min_move=10.0, signal_tf=M15, EURUSD',
        "event_count": int(len(ts)),
        "long": int((sd == 1).sum()), "short": int((sd == -1).sum()),
        "first": fmt_ts(ts.min()), "last": fmt_ts(ts.max()),
        "events_per_week": round(len(ts) / ((ts.max() - ts.min()) / (7 * 86400.0 * NS)), 3),
        "event_hash": A.event_hash(ts, sd),
        "hist_screen_N": 1257, "screen_N": int(len(pool)),
        "hist_screen_mean": 3.9016,
        "screen_mean": round(float(pool.mean()), 4) if len(pool) else None,
        "hist_ref": "M3_E015 SCREEN_PASS h=64 gross +3.90 posYR 7/8 (REJECT was "
                    "side-concentration sanity: S +8.0 / L +0.3, RESULT.md §12)",
        "ok": (len(pool) == 1257 and abs(float(pool.mean()) - 3.9016) < 5e-3),
    }
    return res, (ts, sd)


def identity_C():
    """MTF F04b — previous-day H/L fade, M15 trigger 07-17h UTC."""
    f04b = A.f04_prev_day("fade")
    ev_ts, ev_side, ev_mid = [], [], []
    check = {"n_hist": 0, "n_match": 0, "mismatch": []}
    for y in YEARS:
        bars = A.load_mtfbars(y)
        side, mid = f04b(bars, y)
        fire = np.flatnonzero(side != 0)
        ev_ts.append(bars["M15_close_time"][fire])
        ev_side.append(side[fire])
        ev_mid.append(mid[fire])
    ts = np.concatenate(ev_ts)
    sd = np.concatenate(ev_side)
    mid = np.concatenate(ev_mid)
    # exact historical tick-replay comparison (cached artifact, M3_E023)
    cached = json.load(open(os.path.join(
        A.M3CACHE, "trades_f04b_pdh_fade.json")))
    ev_map = {(int(t), int(s)): float(m)
              for t, s, m in zip(ts, sd, mid)}
    for t in cached:
        check["n_hist"] += 1
        k = (int(t["decision_ts"]), int(t["side"]))
        if k in ev_map:
            check["n_match"] += 1
        else:
            check["mismatch"].append(k)
    res = {
        "name": "C — MTF F04b previous-day H/L fade (M15 07-17h)",
        "source_commit": "29dfb7b1710c58bb939e39a869d3aff26be01af9",
        "source_path": "research/mtf_discovery_m1/families_m3.py::f04_prev_day",
        "params": 'mode="fade", M15 trigger 07:00-17:00 UTC, EURUSD; '
                  "hist exit SL20/TP30/T240",
        "event_count": int(len(ts)),
        "long": int((sd == 1).sum()), "short": int((sd == -1).sum()),
        "first": fmt_ts(ts.min()), "last": fmt_ts(ts.max()),
        "events_per_week": round(len(ts) / ((ts.max() - ts.min()) / (7 * 86400.0 * NS)), 3),
        "event_hash": A.event_hash(ts, sd),
        "mid_finite": int(np.isfinite(mid).sum()),
        "cached_trades": check["n_hist"],
        "cached_in_events": check["n_match"],
        "hist_ref": "M3_E023 DEEPEN tick replay SL20/TP30/T240: N=1183 "
                    "mean +0.388 PF 1.04",
        "ok": (check["n_match"] == check["n_hist"] == 1183
               and np.isfinite(mid).sum() == len(ts)),
    }
    return res, (ts, sd, mid)


def identity_B():
    """SWING G10 — D1 EMA20/50 trend x H4 Donchian20 close break."""
    p = {"fast": 20, "slow": 50, "break_n": 20}
    g10 = A.g10_state_machine
    per, ev_all = {}, []
    scan_pool = []
    raw_n = 0
    for sym in A.DISCOVERY_PAIRS:
        bars = A.load_swing(sym)
        side = g10(bars, sym, p)
        ct = bars["H4_close_time"]
        fire = np.flatnonzero(side != 0)
        raw_n += len(fire)
        ev_all.append((sym, ct[fire], side[fire]))
        sc_d, nsig = A.scan_signal(sym, g10, p, (6,))
        sc = sc_d[6]
        per[sym] = {"events": int(len(fire)), "scan_N": int(len(sc)),
                    "scan_mean": round(float(sc.mean()), 4) if len(sc) else None}
        scan_pool.append(sc)
    pool = np.concatenate(scan_pool)
    wins = pool[pool > 0]; losses = -pool[pool < 0]
    pf = float(wins.sum() / losses.sum()) if len(wins) and len(losses) else None
    all_ts = np.concatenate([e[1] for e in ev_all])
    all_sd = np.concatenate([e[2] for e in ev_all])
    res = {
        "name": "B — SWING G10 D1-trend x H4-Donchian20 state machine",
        "source_commit": "7e3bd46baea6dcd6ec4e5bf763e8d3c6eda1233b",
        "source_path": "research/fx_multipair_swing_m1/families_sw.py::g10_state_machine",
        "params": str(p) + " signal_tf=H4, pairs EURUSD+GBPUSD",
        "event_count": int(raw_n),
        "long": int((all_sd == 1).sum()), "short": int((all_sd == -1).sum()),
        "pair_counts": {s: per[s] for s in A.DISCOVERY_PAIRS},
        "first": fmt_ts(all_ts.min()), "last": fmt_ts(all_ts.max()),
        "events_per_week": round(raw_n / ((all_ts.max() - all_ts.min()) / (7 * 86400.0 * NS)), 3),
        "event_hash": A.event_hash(all_ts, all_sd, pairs=A.DISCOVERY_PAIRS),
        "hist_scan_N": 1057, "pooled_scan_N": int(len(pool)),
        "hist_scan_mean": 1.7871, "pooled_scan_mean": round(float(pool.mean()), 4),
        "hist_scan_PF": 1.0644, "pooled_scan_PF": round(pf, 4) if pf else None,
        "hist_ref": "SW_E029 SCAN h=6 (best of grid, never deepened): N=1057 "
                    "mean +1.7871 PF 1.0644",
        "ok": (len(pool) == 1057 and abs(float(pool.mean()) - 1.7871) < 5e-3
               and abs((pf or 0) - 1.0644) < 5e-3),
    }
    return res, ev_all


def main():
    rA, evA = identity_A()
    rC, evC = identity_C()
    rB, evB = identity_B()
    lines = ["# ENTRY_IDENTITY — HISTORICAL_SIGNAL_EXIT_AUDIT_M1", "",
             "Frozen historical entry event sets, reconstructed from the",
             "source commits and verified against historical artifacts.",
             "ENTRY LOGIC IS FROZEN: no threshold/lookback/session/TF/pair/",
             "direction/trigger change. Any mismatch => STOP that signal.", ""]
    for tag, r in (("SIGNAL_A", rA), ("SIGNAL_B", rB), ("SIGNAL_C", rC)):
        lines += [f"## {tag}: {r['name']}", "",
                  f"SOURCE_COMMIT={r['source_commit']}",
                  f"SOURCE_CODE_PATH={r['source_path']}",
                  f"SOURCE_PARAMETERS={r['params']}",
                  f"EVENT_COUNT={r['event_count']} (raw fires, event-level set)",
                  f"EVENTS_PER_WEEK={r['events_per_week']}",
                  f"PAIR_COUNTS={r.get('pair_counts', 'EURUSD only')}",
                  f"LONG_COUNT={r['long']}  SHORT_COUNT={r['short']}",
                  f"FIRST_EVENT={r['first']}",
                  f"LAST_EVENT={r['last']}",
                  f"EVENT_HASH={r['event_hash']}", ""]
        if "mid_finite" in r:
            lines += [f"MIDPOINT_FROZEN_FINITE={r['mid_finite']}/{r['event_count']}",
                      f"HIST_CACHED_TRADES={r['cached_trades']} "
                      f"SUBSET_MATCH={r['cached_in_events']}", ""]
        if "screen_N" in r:
            lines += [f"HIST_SCREEN N/mean = {r['hist_screen_N']} / "
                      f"{r['hist_screen_mean']} | replicated = "
                      f"{r['screen_N']} / {r['screen_mean']}", ""]
        if "pooled_scan_N" in r:
            lines += [f"HIST_SCAN N/mean/PF = {r['hist_scan_N']} / "
                      f"{r['hist_scan_mean']} / {r['hist_scan_PF']} | "
                      f"replicated = {r['pooled_scan_N']} / "
                      f"{r['pooled_scan_mean']} / {r['pooled_scan_PF']}",
                      f"per-pair events+scan: {r['pair_counts']}", ""]
        lines += [f"HISTORICAL_REF={r['hist_ref']}", "",
                  f"IDENTITY_CHECK={'PASS' if r['ok'] else 'FAIL — STOP THIS SIGNAL'}",
                  "", "---", ""]
    out = os.path.join(A.OUT, "ENTRY_IDENTITY.md")
    with open(out, "w") as f:
        f.write("\n".join(lines))
    A.save({"A": rA, "B": rB, "C": rC}, "identity_results.json")
    for tag, r in (("A", rA), ("B", rB), ("C", rC)):
        print(f"{tag}: N={r['event_count']} {r['events_per_week']}/wk "
              f"L={r['long']} S={r['short']} ok={r['ok']}")
    print("wrote", out)


if __name__ == "__main__":
    main()
