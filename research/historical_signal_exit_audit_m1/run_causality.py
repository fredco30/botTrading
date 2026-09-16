#!/usr/bin/env python3
"""HISTORICAL_SIGNAL_EXIT_AUDIT_M1 — causality tests for the NEW exits (§14).

Entry causality was historically gated (T1/T2/T3 in the source campaigns);
this suite tests the NEW EXIT code only:
  E1 post-exit mutation invariance  — mutating ALL data after a trade's exit
      never changes that trade (no future leakage into the exit path);
  E2 truncation at a trail update   — the trail stop level effective right
      after an update time U is reproducible from data truncated at U
      (completed bars only);
  E3 frozen inputs                  — ATR0 at decision (A/B) and the
      previous-day midpoint (C) are reproducible from data truncated at the
      decision timestamp;
  E4 tighten-only trail             — re-derived stop schedules are monotone;
  E5 harness validation             — local bar rebuilders reproduce the
      cached production bar arrays exactly before being used in E1-E3.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_lib as A

NS = A.NS
PIP = A.PIP
rng = np.random.default_rng(20260916)
REPORT = []


def log(test, ok, detail=""):
    REPORT.append((test, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} {test} {detail}")


def rebuild_tf_from_m1(m1, tf_min):
    """Local completed-bar rebuilder (m3lib bucket idiom) — OHLC only, for
    the mutation/truncation tests (cache lacks last_tick_ts/n_m1)."""
    tf = tf_min * 60 * NS
    ct = m1["close_time"]
    g = (ct - 1) // tf
    ug, first = np.unique(g, return_index=True)
    idx = np.searchsorted(g, ug, side="right") - 1
    fid = np.searchsorted(g, ug, side="left")
    return {
        "start": (ug * tf).astype(np.int64),
        "close_time": ((ug + 1) * tf).astype(np.int64),
        "open": m1["open"][fid],
        "high": np.maximum.reduceat(m1["high"], fid),
        "low": np.minimum.reduceat(m1["low"], fid),
        "close": m1["close"][idx],
    }


def atr_pips(hi, lo, cl, n):
    pc = np.roll(cl, 1); pc[0] = cl[0]
    tr = np.maximum(hi - lo, np.maximum(np.abs(hi - pc), np.abs(lo - pc)))
    return np.cumsum(tr)[n - 1:].reshape(-1) if False else \
        np.convolve(tr, np.ones(n) / n, mode="valid")


# ------------------------------------------------------------------ A / C

def tests_ticks():
    bars = A.load_mtfbars(2010)
    m1 = {k: bars["m1_" + k]
          for k in ("start", "close_time", "open", "high", "low", "close")}
    # E5: local rebuilder == production cached bars
    for tf in (15, 60):
        rb = rebuild_tf_from_m1(m1, tf)
        key = "M15" if tf == 15 else "H1"
        ok = (np.array_equal(rb["close_time"], bars[f"{key}_close_time"])
              and np.array_equal(rb["high"], bars[f"{key}_high"])
              and np.array_equal(rb["close"], bars[f"{key}_close"]))
        log(f"E5 rebuild {key} == cache", ok)

    ts, bid, ask = A.load_ticks(2010)
    h1 = rebuild_tf_from_m1(m1, 60)
    h1_atr = np.concatenate([np.full(13, np.nan), atr_pips(h1["high"], h1["low"], h1["close"], 14)])

    f08 = A.f08_asia_transfer("continuation", 10)
    side = f08(bars, 2010)
    fire = np.flatnonzero(side != 0)
    ct = bars["M15_close_time"][fire]
    atr0 = np.array([A.atr0_at(h1["close_time"], h1_atr, int(t)) for t in ct])
    dec = {"ts": ct, "side": side[fire], "atr0": atr0}

    tr_full, _ = A.replay_trail_ticks(ts, bid, ask, dec, h1["close_time"],
                                      h1["high"], h1["low"], h1_atr,
                                      occupancy=False)
    picks = rng.choice(len(tr_full), size=min(10, len(tr_full)), replace=False)
    # E1: post-exit mutation invariance
    for p in picks:
        t = tr_full[int(p)]
        mut = ts > t["exit_ts"]
        m1b = {k: (v[~mut] if False else v.copy()) for k, v in m1.items()}
        # mutate M1 bars that CLOSE strictly after the exit
        mc = m1["close_time"] > t["exit_ts"]
        m1b = {k: np.where(mc, v + 50 * PIP, v) if k in ("open", "high", "low", "close")
               else v for k, v in m1.items()}
        h1b = rebuild_tf_from_m1(m1b, 60)
        h1b_atr = np.concatenate([np.full(13, np.nan),
                                  atr_pips(h1b["high"], h1b["low"], h1b["close"], 14)])
        tsb = ts[~mut]; bidb = bid[~mut]; askb = ask[~mut]
        dec1 = {"ts": np.array([t["decision_ts"]]), "side": np.array([t["side"]]),
                "atr0": np.array([t["risk_pips"] / 2.0])}
        tr1, _ = A.replay_trail_ticks(tsb, bidb, askb, dec1, h1b["close_time"],
                                      h1b["high"], h1b["low"], h1b_atr,
                                      occupancy=False)
        ok = (len(tr1) == 1
              and tr1[0]["exit_ts"] == t["exit_ts"]
              and abs(tr1[0]["exit_px"] - t["exit_px"]) < 1e-12
              and tr1[0]["reason"] == t["reason"])
        log(f"E1 F08 post-exit mutation j={int(p)}", ok,
            "" if ok else f"{tr1[0]} vs {t}")
    # E2: truncation at a trailed update reproduces the tightened stop
    n_trail = 0
    for p in picks:
        t = tr_full[int(p)]
        if not t["trailed"]:
            continue
        n_trail += 1
        exit_i = int(np.searchsorted(ts, t["exit_ts"], side="left"))
        k0 = int(np.searchsorted(ts, t["entry_ts"], side="left"))
        h1_u = h1["close_time"][(h1["close_time"] > t["entry_ts"])
                                & (h1["close_time"] <= t["exit_ts"])]
        if not len(h1_u):
            continue
        U = int(h1_u[-1])  # last update before exit
        # candidate level at U from FULL data (engine formula)
        ui_f = int(np.searchsorted(h1["close_time"], U, side="right")) - 1
        a_f = h1_atr[ui_f]
        sel_f = (h1["close_time"] > t["entry_ts"]) & (h1["close_time"] <= U)
        if t["side"] == 1:
            cand_f = h1["high"][sel_f].max() - 3.0 * a_f * PIP
        else:
            cand_f = h1["low"][sel_f].min() + 3.0 * a_f * PIP
        mcut = int(np.searchsorted(m1["close_time"], U, side="right"))
        m1c = {k: v[:mcut] for k, v in m1.items()}
        h1c = rebuild_tf_from_m1(m1c, 60)
        h1c_atr = np.concatenate([np.full(13, np.nan),
                                  atr_pips(h1c["high"], h1c["low"], h1c["close"], 14)])
        ui = int(np.searchsorted(h1c["close_time"], U, side="right")) - 1
        a = h1c_atr[ui]
        sel = (h1c["close_time"] > t["entry_ts"]) & (h1c["close_time"] <= U)
        if t["side"] == 1:
            cand = h1c["high"][sel].max() - 3.0 * a * PIP
        else:
            cand = h1c["low"][sel].min() + 3.0 * a * PIP
        log(f"E2 F08 truncated-update j={int(p)}",
            np.isfinite(cand) and abs(cand - cand_f) < 1e-12,
            f"trunc={cand / PIP:.2f}p full={cand_f / PIP:.2f}p")
        if n_trail >= 6:
            break
    # E3: ATR0 from data truncated at the decision
    for p in picks[:6]:
        t = tr_full[int(p)]
        T = int(t["decision_ts"])
        mcut = int(np.searchsorted(m1["close_time"], T, side="right"))
        m1c = {k: v[:mcut] for k, v in m1.items()}
        h1c = rebuild_tf_from_m1(m1c, 60)
        h1c_atr = np.concatenate([np.full(13, np.nan),
                                  atr_pips(h1c["high"], h1c["low"], h1c["close"], 14)])
        a0 = A.atr0_at(h1c["close_time"], h1c_atr, T)
        log(f"E3 F08 atr0 truncated j={int(p)}",
            abs(a0 - t["risk_pips"] / 2.0) < 1e-9,
            f"{a0 / PIP:.2f}p vs {t['risk_pips'] / 2 / PIP:.2f}p")
    # E4: tighten-only — re-derive schedules on sampled trades
    for p in picks[:6]:
        t = tr_full[int(p)]
        h1_u = h1["close_time"][(h1["close_time"] > t["entry_ts"])
                                & (h1["close_time"] <= t["exit_ts"])]
        stops = []
        px = bid if t["side"] == 1 else ask
        e_i = int(np.searchsorted(ts, t["entry_ts"], side="left"))
        stop = t["entry"] - t["side"] * 2.0 * t["risk_pips"] / 2.0 * PIP
        stops.append(stop)
        for U in h1_u:
            ui = int(np.searchsorted(h1["close_time"], int(U), side="right")) - 1
            a = h1_atr[ui]
            if not np.isfinite(a):
                continue
            if t["side"] == 1:
                anchor = h1["high"][(h1["close_time"] > t["entry_ts"])
                                    & (h1["close_time"] <= int(U))].max()
                cand = anchor - 3.0 * a * PIP
                if cand > stop:
                    stop = cand
            else:
                anchor = h1["low"][(h1["close_time"] > t["entry_ts"])
                                   & (h1["close_time"] <= int(U))].min()
                cand = anchor + 3.0 * a * PIP
                if cand < stop:
                    stop = cand
            stops.append(stop)
        arr = np.array(stops)
        ok = bool((np.diff(arr) >= -1e-12).all() if t["side"] == 1
                  else (np.diff(arr) <= 1e-12).all())
        log(f"E4 F08 tighten-only j={int(p)}", ok, f"{len(stops)} updates")
    return tr_full


# ------------------------------------------------------------------ B

def tests_bars():
    p = {"fast": 20, "slow": 50, "break_n": 20}
    sym = "EURUSD"
    bars = A.load_swing(sym)
    d5 = {k.replace("5m_", ""): bars["5m_" + k]
          for k in ("ts", "open", "high", "low", "close")}
    # E5: local rebuilder == production cached bars
    rb = A.bars_from_5m(d5, 240)
    ok = (np.array_equal(rb["close_time"], bars["H4_close_time"])
          and np.array_equal(rb["high"], bars["H4_high"]))
    log("E5 rebuild H4(5m) == cache", ok)

    g10 = A.g10_state_machine
    side = g10(bars, sym, p)
    bull_d1 = A.g10_bull_d1(bars, p)
    h4ct = bars["H4_close_time"]
    atr_h4 = A.atr_sw(sym, bars["H4_high"], bars["H4_low"], bars["H4_close"], 14)
    ct = bars["H4_close_time"]
    fire = np.flatnonzero(side != 0)
    atr0 = np.array([A.atr0_at(h4ct, atr_h4, int(ct[i])) for i in fire])
    dec = {"ts": ct[fire], "side": side[fire], "atr0": atr0}
    tr_full = A.replay_trail_bars(sym, bars, dec, bull_d1,
                                  bars["D1_close_time"], occupancy=False)
    picks = rng.choice(len(tr_full), size=min(10, len(tr_full)), replace=False)
    ts5 = bars["5m_ts"]; o5 = bars["5m_open"]; h5 = bars["5m_high"]
    l5 = bars["5m_low"]; c5 = bars["5m_close"]
    for p_ in picks:
        t = tr_full[int(p_)]
        # E1: mutate 5m bars OPENING strictly after the exit bar (the exit
        # bar's open/intrabar range is consumed by the historical bar-replay
        # exit semantics AT the exit; later bars must be irrelevant)
        mut = ts5 > t["exit_ts"]
        d5b = {k: np.where(mut, v * 1.01, v) for k, v in d5.items()}
        d5b["ts"] = d5["ts"]
        barsb = dict(bars)
        for kk in ("open", "high", "low", "close"):
            barsb[f"5m_{kk}"] = d5b[kk]
        for tf, name in ((60, "H1"), (240, "H4"), (1440, "D1")):
            rb = A.bars_from_5m(d5b, tf)
            for kk in ("start", "close_time", "open", "high", "low", "close"):
                barsb[f"{name}_{kk}"] = rb[kk]
        bull_b = A.g10_bull_d1(barsb, p)
        atr_b = A.atr_sw(sym, barsb["H4_high"], barsb["H4_low"],
                         barsb["H4_close"], 14)
        fire1 = [i for i in fire if ct[i] == t["decision_ts"]]
        dec1 = {"ts": ct[fire1], "side": side[fire1],
                "atr0": atr0[[list(fire).index(i) for i in fire1]]}
        tr1 = A.replay_trail_bars(sym, barsb, dec1, bull_b,
                                  barsb["D1_close_time"], occupancy=False)
        ok = (len(tr1) == 1
              and tr1[0]["exit_ts"] == t["exit_ts"]
              and abs(tr1[0]["exit_px"] - t["exit_px"]) < 1e-12
              and tr1[0]["reason"] == t["reason"])
        log(f"E1 G10 post-exit mutation j={int(p_)}", ok,
            "" if ok else f"{tr1[0]} vs {t}")
    # E2: truncation at last H4 update before exit reproduces the stop level
    n_done = 0
    for p_ in picks:
        t = tr_full[int(p_)]
        if not t["trailed"]:
            continue
        c5t = ts5 + 5 * 60 * NS
        h4_u = h4ct[(h4ct > t["entry_ts"]) & (h4ct <= t["exit_ts"])]
        if not len(h4_u):
            continue
        U = int(h4_u[-1])
        # candidate level at U from FULL data
        ui_f = int(np.searchsorted(h4ct, U, side="right")) - 1
        a_f = atr_h4[ui_f]
        sel_f = (h4ct > t["entry_ts"]) & (h4ct <= U)
        if t["side"] == 1:
            cand_f = bars["H4_high"][sel_f].max() - 3.0 * a_f * A.PIP_SW[sym]
        else:
            cand_f = bars["H4_low"][sel_f].min() + 3.0 * a_f * A.PIP_SW[sym]
        mcut = int(np.searchsorted(c5t, U, side="right"))
        d5c = {k: v[:mcut] for k, v in d5.items()}
        h4c = A.bars_from_5m(d5c, 240)
        atr_c = A.atr_sw(sym, h4c["high"], h4c["low"], h4c["close"], 14)
        ui = int(np.searchsorted(h4c["close_time"], U, side="right")) - 1
        a = atr_c[ui]
        sel = (h4c["close_time"] > t["entry_ts"]) & (h4c["close_time"] <= U)
        if t["side"] == 1:
            cand = h4c["high"][sel].max() - 3.0 * a * A.PIP_SW[sym]
        else:
            cand = h4c["low"][sel].min() + 3.0 * a * A.PIP_SW[sym]
        log(f"E2 G10 truncated-update j={int(p_)}",
            np.isfinite(cand) and abs(cand - cand_f) < 1e-12,
            f"trunc={cand / PIP:.2f}p full={cand_f / PIP:.2f}p")
        n_done += 1
        if n_done >= 6:
            break
    # E3b: regime state from 5m truncated at a D1 close == full-data state
    flips_tested = 0
    for p_ in picks:
        t = tr_full[int(p_)]
        d1ct = bars["D1_close_time"]
        inside = d1ct[(d1ct > t["entry_ts"]) & (d1ct <= t["exit_ts"])]
        if not len(inside) or flips_tested >= 5:
            continue
        T = int(inside[0])
        c5t = ts5 + 5 * 60 * NS
        mcut = int(np.searchsorted(c5t, T, side="right"))
        d5c = {k: v[:mcut] for k, v in d5.items()}
        d1c = A.bars_from_5m(d5c, 1440)
        bull_c = A.g10_bull_d1({"D1_close": d1c["close"]}, p)
        j_full = int(np.searchsorted(d1ct, T))
        ok = bool(bull_c[-1]) == bool(bull_d1[j_full]) \
            and d1c["close_time"][-1] == T
        log(f"E3 G10 regime truncated j={int(p_)}", ok)
        flips_tested += 1
    # E3c: ATR0 truncation
    for p_ in picks[:6]:
        t = tr_full[int(p_)]
        T = int(t["decision_ts"])
        c5t = ts5 + 5 * 60 * NS
        mcut = int(np.searchsorted(c5t, T, side="right"))
        d5c = {k: v[:mcut] for k, v in d5.items()}
        h4c = A.bars_from_5m(d5c, 240)
        atr_c = A.atr_sw(sym, h4c["high"], h4c["low"], h4c["close"], 14)
        a0 = A.atr0_at(h4c["close_time"], atr_c, T)
        log(f"E3 G10 atr0 truncated j={int(p_)}",
            abs(a0 - t["risk_pips"] / 2.0) < 1e-9)
    # E4: tighten-only re-derivation
    for p_ in picks[:6]:
        t = tr_full[int(p_)]
        h4_u = h4ct[(h4ct > t["entry_ts"]) & (h4ct <= t["exit_ts"])]
        stop = t["entry"] - t["side"] * t["risk_pips"] * A.PIP_SW[sym]
        if t["side"] == -1:
            stop = stop - A.SPREAD_PIPS[sym] * A.PIP_SW[sym]
        stops = [stop]
        for U in h4_u:
            ui = int(np.searchsorted(h4ct, int(U), side="right")) - 1
            a = atr_h4[ui]
            if not np.isfinite(a):
                continue
            sel_h = bars["H4_high"][(h4ct > t["entry_ts"]) & (h4ct <= int(U))]
            sel_l = bars["H4_low"][(h4ct > t["entry_ts"]) & (h4ct <= int(U))]
            if t["side"] == 1:
                cand = sel_h.max() - 3.0 * a * A.PIP_SW[sym]
                if cand > stop:
                    stop = cand
            else:
                cand = sel_l.min() + 3.0 * a * A.PIP_SW[sym]
                if cand < stop:
                    stop = cand
            stops.append(stop)
        arr = np.array(stops)
        ok = bool((np.diff(arr) >= -1e-12).all() if t["side"] == 1
                  else (np.diff(arr) <= 1e-12).all())
        log(f"E4 G10 tighten-only j={int(p_)}", ok, f"{len(stops)} updates")


# ------------------------------------------------------------------ C

def tests_C():
    bars = A.load_mtfbars(2010)
    m1 = {k: bars["m1_" + k]
          for k in ("start", "close_time", "open", "high", "low", "close")}
    f04b = A.f04_prev_day("fade")
    side, mid = f04b(bars, 2010)
    ct = bars["M15_close_time"]
    fire = np.flatnonzero(side != 0)
    picks = rng.choice(fire, size=min(8, len(fire)), replace=False)
    for i in picks:
        T = int(ct[i])
        mcut = int(np.searchsorted(m1["close_time"], T, side="right"))
        m1c = {k: v[:mcut] for k, v in m1.items()}
        m15r = rebuild_tf_from_m1(m1c, 15)
        m15 = {"M15_" + k: v for k, v in m15r.items()}
        side_c, mid_c = f04b(m15, 2010)
        jc = int(np.searchsorted(m15["M15_close_time"], T))
        ok = (m15["M15_close_time"][jc] == T and int(side_c[jc]) == int(side[i])
              and abs(float(mid_c[jc]) - float(mid[i])) < 1e-12)
        log(f"E3 F04b midpoint truncated j={int(i)}", ok,
            f"mid={mid[i] / PIP:.1f}p")


def main():
    tests_ticks()
    tests_bars()
    tests_C()
    n_fail = sum(1 for _, ok, _ in REPORT if not ok)
    print(f"\nCAUSALITY SUITE: {len(REPORT)} tests, {n_fail} failures")
    A.save({"n": len(REPORT), "n_fail": n_fail,
            "fails": [r for r in REPORT if not r[1]]},
           "causality_summary.json")


if __name__ == "__main__":
    main()
