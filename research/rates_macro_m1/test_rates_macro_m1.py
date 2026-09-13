#!/usr/bin/env python3
"""Synthetic tests for RATES-MACRO-M1 (frozen spec §25).

Every test builds its own synthetic bars/ticks/rolls/gaps — no real data
files are touched. Run: python test_rates_macro_m1.py
"""
import os
import sys
import tempfile

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..",
                                                 "mtf_m1_tick_execution")))

import rates_macro_lib as R  # noqa: E402
import mtf_lib as MTF        # noqa: E402

NS = R.NS
PIP = R.PIP
MIN = R.MIN_NS
T0 = int(pd.Timestamp("2015-03-06T13:30:00Z").value)   # a real NFP Friday
LAT = R.LATENCY_NS

PASS, FAIL = 0, 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f" FAIL {name}")


def m(k):
    """minute offset from T0 in ns (k may be fractional seconds via f)."""
    return T0 + k * MIN


def make_bars(starts_rel, closes):
    return {"start": np.array(sorted(starts_rel), dtype=np.int64),
            "close": np.array([c for _, c in
                               sorted(zip(starts_rel, closes))],
                              dtype=np.float64)}


def full_minute_bars(lo_rel, hi_rel, close_fn):
    """bars for every minute k in [lo_rel, hi_rel)."""
    ks = list(range(lo_rel, hi_rel))
    return make_bars([T0 + k * MIN for k in ks], [close_fn(k) for k in ks])


def baseline_close(k):
    """deterministic wiggle: |1m change| = 1 futures tick (0.03125)."""
    return 110.0 + 0.03125 / 2 * (1 if k % 2 == 0 else -1)


def make_store(bars_zf=None, bars_zn=None, bars_zt=None, rolls=None,
               gaps=None):
    s = R.RateStore(rates_dir=None)
    s.bars = {"ZF": bars_zf, "ZN": bars_zn, "ZT": bars_zt}
    s.rolls = rolls or {"ZF": (np.array([], np.int64),) * 2,
                        "ZN": (np.array([], np.int64),) * 2,
                        "ZT": (np.array([], np.int64),) * 2}
    s.gaps = gaps or {k: (np.array([], np.int64), np.array([], np.int64))
                      for k in ("ZF", "ZN", "ZT")}
    return s


def ok_window(move_ticks=10.0):
    """bars giving a clean shock-able window: baseline |chg| = 1 tick,
    pre_close at T0-1m, event close = pre + move."""
    def close_fn(k):
        if k == -1:
            return 110.0
        if k == 0:
            return 110.0 + move_ticks * 0.03125   # futures ticks
        return baseline_close(k)
    return full_minute_bars(-70, 3, close_fn)


def synth_rate_win(zf_move=+0.3125, zn_move=+0.3125):
    """Hand-built OK windows via a synthetic RateStore (units: futures
    price points). Baseline |1m change| = 0.03125 everywhere ->
    Q95 = 0.03125; move 0.3125 = 10 ticks -> score 10."""
    s = R.RateStore(rates_dir=None)
    s.bars = {"ZF": ok_window(zf_move / 0.03125),
              "ZN": ok_window(zn_move / 0.03125)}
    return {"ZF": s.window("ZF", T0), "ZN": s.window("ZN", T0)}


class FakeStore:
    """TickStore stand-in serving slices of full synthetic arrays."""

    def __init__(self, ts, bid, ask):
        self.ts, self.bid, self.ask = ts, bid, ask

    def get_range(self, a, b):
        i0 = int(np.searchsorted(self.ts, a, side="left"))
        i1 = int(np.searchsorted(self.ts, b, side="left"))
        return self.ts[i0:i1], self.bid[i0:i1], self.ask[i0:i1]


def ticks_from_events(events):
    """events: list of (t_ns, bid, ask) sorted -> arrays."""
    ev = sorted(events)
    ts = np.array([e[0] for e in ev], dtype=np.int64)
    bid = np.array([e[1] for e in ev], dtype=np.float64)
    ask = np.array([e[2] for e in ev], dtype=np.float64)
    return ts, bid, ask


def standard_ticks():
    """Baseline ticks: one per minute at :05s mid 1.1000 (bid 1.0995 /
    ask 1.1005). First minute: ticks at T0, +20s, +40s; entry tick at
    decision+250ms; a target-touching rise 10 min after entry; flat path
    to ~+125m (covers the 60-minute time exit)."""
    ev = []
    for k in range(-62, 0):                     # pre-event baseline minutes
        t = T0 + k * MIN + 5 * 10**9
        ev.append((t, 1.0995, 1.1005))
    ev.append((T0, 1.0995, 1.1005))             # first-minute ticks
    ev.append((T0 + 20 * 10**9, 1.0995, 1.1005))
    ev.append((T0 + 40 * 10**9, 1.0995, 1.1005))
    d = T0 + MIN                                # decision T0+1m
    ev.append((d + LAT, 1.0995, 1.1005))        # entry tick (LONG->ask)
    ev.append((T0 + 11 * MIN + 10 * 10**9, 1.1040, 1.1041))  # above 2R
    for k in range(1, 125):                     # path minutes after T0
        ev.append((T0 + k * MIN + 5 * 10**9, 1.0995, 1.1005))
    return ticks_from_events(ev)


def std_refs(q95_pips=20.0, fx_move_pips=1.0):
    refs = {"fx_p0": 1.1000, "fx_p1": 1.1000 + fx_move_pips * PIP,
            "fx_move_1m_pips": fx_move_pips,
            "fm_low": 1.0990, "fm_high": 1.1005,
            "n_first_minute_ticks": 4}
    base = {"n_changes": 54, "fx_q95": q95_pips * PIP}
    return refs, base


def empty_gaps():
    return np.array([], dtype=np.int64)


# ------------------------------------------------------------------ §1/§2

def test_event_loading():
    print("event loading:")
    csv = ("event_id,family,release_timestamp_utc,tick_alignment_status\n"
           f"NFP-1,NFP,2015-03-06T13:30:00Z,ALIGNED\n"
           f"CPI-1,CPI,2015-03-17T12:30:00Z,ALIGNED\n"
           f"FOMC-1,FOMC,2015-03-18T18:00:00Z,ALIGNED\n"
           f"NFP-2,NFP,2010-01-08T13:30:00Z,ALIGNED\n"   # before discovery
           f"NFP-3,NFP,2019-01-04T13:30:00Z,ALIGNED\n"   # 2019 forbidden
           f"CPI-2,CPI,2016-02-19T13:30:00Z,NO_TICK_WITHIN_5S\n")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "ev.csv")
        open(p, "w").write(csv)
        ev = R.load_events(p)
    check("FOMC / pre-window / 2019+ / non-aligned dropped",
          [e["event_id"] for e in ev] == ["NFP-1", "CPI-1"])
    check("T0 exact official release timestamp (ns)",
          ev[0]["t0_ns"] == int(pd.Timestamp("2015-03-06T13:30:00Z").value))
    check("discovery start 2010-06-07 inclusive",
          R.DISCOVERY_START_NS == int(
              pd.Timestamp("2010-06-07T00:00:00Z").value))
    check("discovery end 2019-01-01 exclusive",
          R.DISCOVERY_END_NS == int(
              pd.Timestamp("2019-01-01T00:00:00Z").value))


def test_2019_hard_cutoff():
    print("2019 hard cutoff / protected OOS guard:")
    try:
        MTF.assert_month_in_discovery(2019, 1)
        raised = False
    except ValueError:
        raised = True
    check("2019-01 partition open raises", raised)
    try:
        MTF.assert_month_in_discovery(2020, 6)
        raised = False
    except ValueError:
        raised = True
    check("2020 partition open raises", raised)
    check("TickStore path guard 2018-12 ok",
          (MTF.assert_month_in_discovery(2018, 12) is None))


# ------------------------------------------------------------------ §3-§7

def test_rate_windows():
    print("rate bar causality & shock:")

    def bars_with_event_close(ev_close):
        def fn(k):
            if k == -1:
                return 110.0
            if k == 0:
                return ev_close
            return baseline_close(k)
        return full_minute_bars(-70, 3, fn)

    s = make_store(bars_zf=bars_with_event_close(110.3125),
                   bars_zn=bars_with_event_close(110.3125))
    w = s.window("ZF", T0)
    check("PRE_CLOSE causal = last completed close before T0",
          w["pre_close"] == 110.0
          and w["pre_bar_start"] == T0 - MIN)
    check("POST1_CLOSE = close of completed event minute",
          w["post1_close"] == 110.3125)
    check("RATE_MOVE = POST1 - PRE", abs(w["rate_move"] - 0.3125) < 1e-12)

    # event bar missing -> unusable (no forming-bar lookahead possible)
    ks = [k for k in range(-70, 3) if k != 0]
    s2 = make_store(
        bars_zf=make_bars([T0 + k * MIN for k in ks],
                          [baseline_close(k) for k in ks]),
        bars_zn=ok_window(10))
    check("missing event-minute bar -> EVENT_BAR_MISSING",
          s2.window("ZF", T0)["status"] == "EVENT_BAR_MISSING")

    # Q95 + baseline excludes [T0-5m, T0)
    s3 = make_store(bars_zf=ok_window(10), bars_zn=ok_window(10))
    w3 = s3.window("ZF", T0)
    rets = [baseline_close(k) - baseline_close(k - 1)
            for k in range(-59, -5)]                # consecutive pairs
    check("RATE_Q95 = 95th pct of baseline |changes|",
          abs(w3["rate_q95"] - np.percentile(np.abs(rets), 95)) < 1e-12)
    check("baseline returns = 54 (55 bars, T0-5m..T0-1m excluded)",
          w3["n_baseline_returns"] == 54)

    def close_with_huge_tail(k):
        if k >= -5:
            return 1e9                              # absurd: must be ignored
        if k == -6 - 60:
            pass
        return baseline_close(k)
    # -60..-6 normal baseline; -5..-1 absurd
    bars_tail = full_minute_bars(-70, 3, close_with_huge_tail)
    # keep pre/event bars sane (they are >= T0-1m -> would be 1e9; fix)
    bars_tail["close"][np.isclose(bars_tail["close"], 1e9)
                       & (bars_tail["start"] >= T0 - 5 * MIN)] = 110.0
    bars_tail["close"][bars_tail["start"] == T0] = 110.3125
    s4 = make_store(bars_zf=bars_tail, bars_zn=ok_window(10))
    w4 = s4.window("ZF", T0)
    check("baseline excludes T0-5m window (tail values ignored)",
          w4["status"] == "OK"
          and abs(w4["rate_q95"] - w3["rate_q95"]) < 1e-12)

    # rate score
    check("RATE_SCORE = |move|/Q95",
          abs(w3["rate_score"] - abs(w3["rate_move"]) / w3["rate_q95"])
          < 1e-12)

    # baseline too small: event minute exists, baseline minutes sparse
    ks = list(range(-70, -45)) + list(range(-2, 3))
    sparse = make_bars([T0 + k * MIN for k in ks],
                       [baseline_close(k) for k in ks])
    s5 = make_store(bars_zf=sparse, bars_zn=ok_window(10))
    check("N_BASELINE_RETURNS < 30 -> BASELINE_INVALID",
          s5.window("ZF", T0)["status"] == "BASELINE_INVALID")


def test_roll_guard():
    print("roll-window exclusion:")
    s = make_store(bars_zf=ok_window(10), bars_zn=ok_window(10))
    # transition overlapping [T0-60m, T0+1m]
    s.rolls["ZF"] = (np.array([T0 - 30 * MIN]), np.array([T0 - 29 * MIN]))
    check("roll inside window -> ROLL_WINDOW_INVALID",
          s.window("ZF", T0)["status"] == "ROLL_WINDOW_INVALID")
    # edge: new contract first print exactly at T0+1m (window end incl.)
    s.rolls["ZF"] = (np.array([T0]), np.array([T0 + MIN]))
    check("roll ending exactly at T0+1m excluded (frozen <=)",
          s.window("ZF", T0)["status"] == "ROLL_WINDOW_INVALID")
    # transition fully after the window
    s.rolls["ZF"] = (np.array([T0 + 2 * MIN]), np.array([T0 + 3 * MIN]))
    check("roll after window -> OK", s.window("ZF", T0)["status"] == "OK")
    # transition fully before the window
    s.rolls["ZF"] = (np.array([T0 - 61 * MIN]),
                     np.array([T0 - 61 * MIN + 10 * 10**9]))
    check("roll before window -> OK", s.window("ZF", T0)["status"] == "OK")
    # ZN roll still excludes even when ZF fine
    s.rolls["ZF"] = (np.array([], np.int64), np.array([], np.int64))
    s.rolls["ZN"] = (np.array([T0 - 10 * MIN]), np.array([T0 - 5 * MIN]))
    check("ZN roll excludes event",
          s.window("ZN", T0)["status"] == "ROLL_WINDOW_INVALID")


def test_rate_gap_guard():
    print("rate unexpected-gap exclusion:")
    s = make_store(bars_zf=ok_window(10), bars_zn=ok_window(10))
    s.gaps["ZF"] = (np.array([T0 - 30 * 10**9]),
                    np.array([T0 + 30 * 10**9]))
    check("unexpected gap between PRE_CLOSE and T0 -> RATE_WINDOW_INVALID",
          s.window("ZF", T0)["status"] == "RATE_WINDOW_INVALID")
    s.gaps["ZF"] = (np.array([], np.int64), np.array([], np.int64))
    s.gaps["ZF"] = (np.array([T0 - 45 * MIN]), np.array([T0 - 43 * MIN]))
    w = s.window("ZF", T0)
    check("unexpected gap inside baseline skips crossed returns only",
          w["status"] == "OK" and w["n_baseline_returns"] == 52)


def test_shock_and_direction():
    print("shock qualification & economic direction:")
    zf = ok_window(10)   # +10 ticks
    zn_up = ok_window(10)
    zn_dn = ok_window(-10)
    zn_small = ok_window(1)  # 1 tick -> score 1 < 2
    check("same sign, both scores >= 2 -> shock",
          R.primary_rate_shock(make_store(zf, zn_up).window("ZF", T0),
                               make_store(zf, zn_up).window("ZN", T0)))
    sm = make_store(zf, zn_small)
    check("ZN score < 2 -> no shock",
          not R.primary_rate_shock(sm.window("ZF", T0), sm.window("ZN", T0)))
    om = make_store(zf, zn_dn)
    check("opposite signs -> no shock",
          not R.primary_rate_shock(om.window("ZF", T0), om.window("ZN", T0)))
    zz = ok_window(0)
    zm = make_store(zf, zz)
    check("zero move -> no shock",
          not R.primary_rate_shock(zm.window("ZF", T0), zm.window("ZN", T0)))
    wup = make_store(ok_window(10), zn_up).window("ZF", T0)
    wdn = make_store(ok_window(-10), zn_dn).window("ZF", T0)
    check("futures UP -> EURUSD LONG", R.rate_direction(wup) == +1)
    check("futures DOWN -> EURUSD SHORT", R.rate_direction(wdn) == -1)
    # ZT diagnostic cannot change the signal: run_event never receives ZT
    ts, bid, ask = standard_ticks()
    refs, base = std_refs()
    ev = {"event_id": "X", "family": "NFP", "t0_ns": T0}
    rw = synth_rate_win(+0.3125, +0.3125)
    rw["ZT"] = ok_window(-10)                       # ZT disagrees
    t1, _ = R.run_event(ev, rw, refs, base, FakeStore(ts, bid, ask),
                        empty_gaps())
    del rw["ZT"]
    t2, _ = R.run_event(ev, rw, refs, base, FakeStore(ts, bid, ask),
                        empty_gaps())
    check("ZT input cannot alter trades (structural)",
          [(x["kind"], x["net_pips"]) for x in t1]
          == [(x["kind"], x["net_pips"]) for x in t2])


# ------------------------------------------------------------------ §10

def test_fx_refs():
    print("FX P0/P1 causality & FX_Q95:")
    ev = []
    for k in range(-62, 0):
        px = 1.1000 + (0.0002 if k % 3 == 0 else 0.0)
        ev.append((T0 + k * MIN + 5 * 10**9, px - 0.00005, px + 0.00005))
    ev.append((T0 - 2 * 10**9, 1.09995, 1.10005))    # last tick before T0
    ev.append((T0, 1.10015, 1.10025))                # AT T0: not P0
    ev.append((T0 + 30 * 10**9, 1.09895, 1.09905))   # first-minute low
    ev.append((T0 + 45 * 10**9, 1.10145, 1.10155))   # first-minute high
    ev.append((T0 + MIN, 1.10245, 1.10255))          # AT T0+1m: is P1
    for k in range(2, 5):
        ev.append((T0 + k * MIN + 10**9, 1.10245, 1.10255))
    ts, bid, ask = ticks_from_events(ev)
    mid = (bid + ask) / 2.0
    refs, base = R.fx_event_refs(ts, mid, T0)
    check("FX_P0 = last tick strictly BEFORE T0 (tick at T0 excluded)",
          abs(refs["fx_p0"] - 1.1000) < 1e-12)
    check("FX_P1 = first tick AT/AFTER T0+1m",
          abs(refs["fx_p1"] - 1.1025) < 1e-12)
    check("first-minute MID extremes",
          abs(refs["fm_low"] - 1.0990) < 1e-12
          and abs(refs["fm_high"] - 1.1015) < 1e-12)
    check("FX_MOVE_1M_PIPS = P1 - P0 in pips",
          abs(refs["fx_move_1m_pips"] - 25.0) < 1e-9)
    # FX_Q95: bucket-close mids for minutes -60..-6 (55 buckets, 54 chg)
    closes = []
    for k in range(-60, -5):
        px = 1.1000 + (0.0002 if k % 3 == 0 else 0.0)
        closes.append(px)
    chg = np.diff(closes)
    check("FX_Q95 = 95th pct of |1m bucket-close changes|",
          abs(base["fx_q95"] - np.percentile(np.abs(chg), 95)) < 1e-12)
    check("FX baseline change count = 54", base["n_changes"] == 54)

    # empty bucket -> two spanning changes skipped (55-1 buckets -> 52)
    ev2 = [e for e in ev
           if not (T0 - 30 * MIN <= e[0] < T0 - 29 * MIN)]
    ts2, bid2, ask2 = ticks_from_events(ev2)
    _, base2 = R.fx_event_refs(ts2, (bid2 + ask2) / 2.0, T0)
    check("empty baseline bucket -> spanning changes skipped (52)",
          base2["n_changes"] == 52)

    # too few FX changes -> fx_q95 None (refs themselves still valid)
    ev5 = ([(T0 + k * MIN + 5 * 10**9, 1.0995, 1.1005)
            for k in range(-35, -30)]
           + [(T0 - 2 * 10**9, 1.09995, 1.10005)]
           + [(T0 + 30 * 10**9, 1.0995, 1.1005)]
           + [(T0 + MIN, 1.0995, 1.1005)])
    ts5, bid5, ask5 = ticks_from_events(ev5)
    refs5, base5 = R.fx_event_refs(ts5, (bid5 + ask5) / 2.0, T0)
    check("too few FX changes -> fx_q95 None",
          refs5 is not None and base5["fx_q95"] is None)

    # P0 too old / P1 too late
    ev3 = [e for e in ev if e[0] < T0 - 60 * MIN] + \
          [e for e in ev if e[0] >= T0]
    ts3, bid3, ask3 = ticks_from_events(ev3)
    check("no tick in [T0-60m, T0) -> FX_REF_INVALID",
          R.fx_event_refs(ts3, (bid3 + ask3) / 2.0, T0)[0] is None)
    ev4 = [e for e in ev if e[0] < T0 + MIN] + \
          [(T0 + 3 * MIN, 1.1024, 1.1026)]
    ts4, bid4, ask4 = ticks_from_events(ev4)
    check("no FX_P1 within T0+2m -> FX_REF_INVALID",
          R.fx_event_refs(ts4, (bid4 + ask4) / 2.0, T0)[0] is None)


# ------------------------------------------------------------- §11/§15

def test_entry_execution():
    print("entry execution (250 ms latency, sides):")
    d = T0 + MIN
    ev = [(d + LAT - 10**8, 1.1000, 1.1002),    # 100ms before latency
          (d + LAT, 1.1010, 1.1012),            # exactly at latency: valid
          (d + LAT + 5 * 10**8, 1.1020, 1.1022)]
    ts, bid, ask = ticks_from_events(ev)
    r = R.resolve_entry_60s(ts, bid, ask, d, 1, empty_gaps())
    check("LONG fills at first ASK at/after decision+250ms",
          r["status"] == "FILLED" and r["price"] == 1.1012
          and r["fill_ts"] == d + LAT)
    r = R.resolve_entry_60s(ts, bid, ask, d, -1, empty_gaps())
    check("SHORT fills at first BID at/after decision+250ms",
          r["status"] == "FILLED" and r["price"] == 1.1010)
    ev2 = [(d + LAT + 61 * 10**9, 1.1000, 1.1002)]
    ts2, bid2, ask2 = ticks_from_events(ev2)
    check("no executable quote within 60s -> NO_FILL",
          R.resolve_entry_60s(ts2, bid2, ask2, d, 1, empty_gaps())
          ["status"] == "NO_FILL")
    gs = np.array([d + 10**8], dtype=np.int64)
    check("true data gap between decision and fill -> NO_FILL_GAP",
          R.resolve_entry_60s(ts, bid, ask, d, 1, gs)
          ["status"] == "NO_FILL_GAP")
    # forming-rate-bar lookahead: nothing before decision+250ms is usable
    ev3 = [(d + LAT - 1, 0.9, 0.9)]             # absurd pre-latency quote
    ts3, bid3, ask3 = ticks_from_events(ev3)
    check("decision+250ms floor (no earlier fill)",
          R.resolve_entry_60s(ts3, bid3, ask3, d, 1, empty_gaps())
          ["status"] == "NO_FILL")


def test_exit_execution():
    print("stop/target/time execution:")
    d = T0 + MIN
    entry_ts = d + LAT
    e = 1.1012                                   # LONG entry (ask)
    stop = 1.0990
    tgt = e + 2.0 * (e - stop)                   # 2R
    # stop overshoot: one tick far below stop
    ev = [(entry_ts, 1.1002, e),
          (entry_ts + 10**9, stop - 20 * PIP, stop - 20 * PIP + 0.0001)]
    ts, bid, ask = ticks_from_events(ev)
    res = MTF.resolve_trade(ts, bid, ask, 1, 0, entry_ts, stop, tgt,
                            entry_ts + R.AB_TIME_NS, empty_gaps())
    check("LONG STOP fills at actual (overshoot) BID",
          res["status"] == "STOP"
          and res["exit_price"] < stop)
    # target cap: one tick far above target
    ev = [(entry_ts, 1.1002, e),
          (entry_ts + 10**9, tgt + 30 * PIP, tgt + 30 * PIP + 0.0001)]
    ts, bid, ask = ticks_from_events(ev)
    res = MTF.resolve_trade(ts, bid, ask, 1, 0, entry_ts, stop, tgt,
                            entry_ts + R.AB_TIME_NS, empty_gaps())
    check("LONG TARGET capped at target price",
          res["status"] == "TARGET" and res["exit_price"] == tgt)
    # SHORT mirrors: entry on bid, stop on ASK overshoot
    e_s = 1.1002
    stop_s = e_s + 22 * PIP
    tgt_s = e_s - 2.0 * (stop_s - e_s)
    ev = [(entry_ts, e_s, 1.1012),
          (entry_ts + 10**9, stop_s + 25 * PIP - 0.0001,
           stop_s + 25 * PIP)]
    ts, bid, ask = ticks_from_events(ev)
    res = MTF.resolve_trade(ts, bid, ask, -1, 0, entry_ts, stop_s, tgt_s,
                            entry_ts + R.AB_TIME_NS, empty_gaps())
    check("SHORT STOP fills at actual (overshoot) ASK",
          res["status"] == "STOP" and res["exit_price"] > stop_s)
    ev = [(entry_ts, e_s, 1.1012),
          (entry_ts + 10**9, tgt_s - 30 * PIP - 0.0001, tgt_s - 30 * PIP)]
    ts, bid, ask = ticks_from_events(ev)
    res = MTF.resolve_trade(ts, bid, ask, -1, 0, entry_ts, stop_s, tgt_s,
                            entry_ts + R.AB_TIME_NS, empty_gaps())
    check("SHORT TARGET capped at target price",
          res["status"] == "TARGET" and res["exit_price"] == tgt_s)
    # TIME exit: LONG at BID, SHORT at ASK, first tick >= entry+T
    t_exit = entry_ts + R.AB_TIME_NS
    ev = [(entry_ts, 1.1002, e),
          (t_exit - 10**6, 1.1002, 1.1004),
          (t_exit + 3 * 10**9, 1.1010, 1.1012)]
    ts, bid, ask = ticks_from_events(ev)
    res = MTF.resolve_trade(ts, bid, ask, 1, 0, entry_ts, stop, tgt,
                            t_exit, empty_gaps())
    check("LONG TIME exit at BID after entry+60m",
          res["status"] == "TIME" and res["exit_ts"] == t_exit + 3 * 10**9
          and res["exit_price"] == 1.1010)
    res = MTF.resolve_trade(ts, bid, ask, -1, 0, entry_ts, stop_s, tgt_s,
                            t_exit, empty_gaps())
    check("SHORT TIME exit at ASK", res["status"] == "TIME"
          and res["exit_price"] == 1.1012)
    # data gap inside the trade invalidates it
    gs = np.array([entry_ts + 60 * 10**9], dtype=np.int64)
    ev = [(entry_ts, 1.1002, e), (entry_ts + 10**9, 1.1002, 1.1004),
          (t_exit + 10**9, 1.1002, 1.1004)]
    ts, bid, ask = ticks_from_events(ev)
    res = MTF.resolve_trade(ts, bid, ask, 1, 0, entry_ts, stop, tgt,
                            t_exit, gs)
    check("gap intersecting open trade -> DATA_GAP_INVALID",
          res["status"] == "DATA_GAP_INVALID")


# ------------------------------------------------------------ §12-§14

def run_std_event(kind_override=None, refs=None, base=None, ticks=None,
                  direction=+1):
    rw = synth_rate_win(+0.3125 * direction, +0.3125 * direction)
    r, b = std_refs()
    ts, bid, ask = standard_ticks()
    ev = {"event_id": "X", "family": "NFP", "t0_ns": T0}
    trades, notes = R.run_event(ev, rw, refs or r, base or b,
                                FakeStore(ts, bid, ask), empty_gaps())
    return trades, notes


def test_strategies():
    print("strategy A/B/C rules:")
    trades, notes = run_std_event()
    a = [t for t in trades if t["kind"] == "A"][0]
    check("A LONG entry at ASK after latency",
          a["entry"] == 1.1005
          and a["entry_ts"] == T0 + MIN + R.LATENCY_NS)
    check("A stop = first-minute MID low",
          a["stop"] == 1.0990)
    risk = (1.1005 - 1.0990) / PIP                     # 15 pips
    check("A target = 2.0R", abs(a["target"] - (1.1005 + 30 * PIP)) < 1e-12)
    check("A net on target fill = 2R = 30 pips",
          a["exit_reason"] == "TARGET"
          and abs(a["net_pips"] - 30.0) < 1e-6)
    check("risk_pips recorded", abs(a["risk_pips"] - risk) < 1e-9)
    # A SHORT: rates down -> direction -1, entry at BID, stop at fm high
    rw = synth_rate_win(-0.3125, -0.3125)
    refs, base = std_refs()
    ts, bid, ask = standard_ticks()
    ev = {"event_id": "X", "family": "NFP", "t0_ns": T0}
    trades_s, _ = R.run_event(ev, rw, refs, base, FakeStore(ts, bid, ask),
                              empty_gaps())
    a_s = [t for t in trades_s if t["kind"] == "A"][0]
    check("A SHORT: entry at BID, stop = first-minute MID high",
          a_s["direction"] == -1 and a_s["entry"] == 1.0995
          and a_s["stop"] == 1.1005)
    check("A SHORT target 2R below entry",
          abs(a_s["target"] - (1.0995 - 2.0 * 10 * PIP)) < 1e-12)

    # B lag rule
    refs, base = std_refs(q95_pips=20.0, fx_move_pips=10.0)
    trades, notes = run_std_event(refs=refs, base=base)
    check("B eligible when |FX1M| <= FX_Q95",
          any(t["kind"] == "B" for t in trades))
    refs, base = std_refs(q95_pips=20.0, fx_move_pips=25.0)
    trades, notes = run_std_event(refs=refs, base=base)
    check("B NOT eligible when |FX1M| > FX_Q95",
          notes.get("B") == "NOT_ELIGIBLE_FX_ALREADY_MOVED"
          and not any(t["kind"] == "B" for t in trades))

    # C disagreement
    refs, base = std_refs(q95_pips=20.0, fx_move_pips=-15.0)
    refs["fm_high"] = 1.1005
    refs["fm_low"] = 1.0985
    trades, notes = run_std_event(refs=refs, base=base)
    c = [t for t in trades if t["kind"] == "C"]
    check("C eligible on opposite-sign FX move >= 0.5*FX_Q95",
          len(c) == 1 and c[0]["direction"] == 1)
    check("C target = FX_P0", abs(c[0]["target"] - 1.1000) < 1e-12)
    refs, base = std_refs(q95_pips=20.0, fx_move_pips=-8.0)
    trades, notes = run_std_event(refs=refs, base=base)
    check("C NOT eligible when |FX1M| < 0.5*FX_Q95",
          notes.get("C") == "NOT_ELIGIBLE_FX_MOVE_TOO_SMALL")
    refs, base = std_refs(q95_pips=20.0, fx_move_pips=+15.0)
    trades, notes = run_std_event(refs=refs, base=base)
    check("C NOT eligible when FX agrees with rate direction",
          notes.get("C") == "NOT_ELIGIBLE_NO_DISAGREEMENT")
    # C target already crossed: LONG entry (ask) <= FX_P0
    refs, base = std_refs(q95_pips=20.0, fx_move_pips=-15.0)
    refs["fm_high"] = 1.1005
    refs["fm_low"] = 1.0980
    ev = [(T0 + MIN + R.LATENCY_NS, 1.09985, 1.09995)]   # ask 0.9995 < P0? no
    ts, bid, ask = ticks_from_events(
        [(T0 + MIN + R.LATENCY_NS, 1.0990, 1.0995)]
        + [(T0 + k * MIN + 5 * 10**9, 1.0990, 1.0995)
           for k in range(2, 40)])
    rw = synth_rate_win(+0.3125, +0.3125)
    trades, notes = R.run_event({"event_id": "X", "family": "NFP",
                                 "t0_ns": T0}, rw, refs, base,
                                FakeStore(ts, bid, ask), empty_gaps())
    check("C target already crossed at entry -> NO_TRADE",
          notes.get("C") == "NO_TRADE_TARGET_ALREADY_CROSSED")

    # invalid stop / tiny risk
    refs, base = std_refs()
    refs["fm_low"] = 1.1008                       # above entry ask 1.1005
    trades, notes = run_std_event(refs=refs, base=base)
    check("LONG stop >= entry -> NO_TRADE_INVALID_STOP",
          notes.get("A") == "NO_TRADE_INVALID_STOP")
    refs, base = std_refs()
    refs["fm_low"] = 1.10045                      # 0.5 pip risk < 1.0
    trades, notes = run_std_event(refs=refs, base=base)
    check("risk < 1.0 pip -> NO_TRADE_RISK_TOO_SMALL",
          notes.get("A") == "NO_TRADE_RISK_TOO_SMALL")
    # no first-minute ticks
    refs, base = std_refs()
    refs["fm_low"] = refs["fm_high"] = None
    trades, notes = run_std_event(refs=refs, base=base)
    check("no first-minute ticks -> NO_TRADE_FIRST_MINUTE_NO_TICKS",
          notes.get("A") == "NO_TRADE_FIRST_MINUTE_NO_TICKS")
    # TIME exit end-to-end (rise tick below the far target: untouched)
    refs, base = std_refs(q95_pips=20.0, fx_move_pips=0.0)
    refs["fm_low"] = 1.0900                        # far stop
    refs["fm_high"] = 1.1015
    trades, notes = run_std_event(refs=refs, base=base)
    a = [t for t in trades if t["kind"] == "A"][0]
    check("A TIME exit after entry+60m when untouched",
          a["exit_reason"] == "TIME"
          and a["exit_ts"] >= a["entry_ts"] + R.AB_TIME_NS)


# ------------------------------------------------------------- §17/§22-24

def mktrade(net, risk=20.0, year=2015, family="NFP", ts=0):
    return {"kind": "A", "family": family, "year": year,
            "entry_ts": ts, "net_pips": net, "risk_pips": risk,
            "exit_reason": "TARGET" if net > 0 else "STOP"}


def test_metrics_and_gates():
    print("metrics, stress, gates:")
    nets = [10, -20, 30, 8, -20, 12, 25, -20, 9, 40, -20, 11]
    trades = [mktrade(n, ts=i) for i, n in enumerate(nets)]
    m = R.strategy_metrics(trades, [5.0], [5.0], 0.8, 0.7)
    mean = float(np.mean(nets))
    check("net mean (4-dp rounded)",
          abs(m["net_mean_pips"] - mean) < 1e-3)
    check("STRESS arithmetic (per side x2)",
          abs(m["stress_025_mean"] - (mean - 0.50)) < 1e-3
          and abs(m["stress_050_mean"] - (mean - 1.00)) < 1e-3
          and abs(m["stress_100_mean"] - (mean - 2.00)) < 1e-3)
    wins = sum(n for n in nets if n > 0)
    losses = -sum(n for n in nets if n < 0)
    check("profit factor", abs(m["profit_factor"] - wins / losses) < 1e-6)
    check("expectancy R = mean(net/risk)",
          abs(m["expectancy_r"] - np.mean(np.array(nets) / 20.0)) < 1e-3)
    check("remove_best_1pct drops top 1% (ceil)",
          abs(m["remove_best_1pct_mean"]
              - float(np.mean(sorted(nets)[:-1]))) < 1e-3)
    check("CI95 bootstrap seed-42 deterministic",
          m["ci95_lo"] == round(MTF.bootstrap_ci95(np.array(nets,
                                                         float))[0], 4))
    # POSITIVE_YEARS denominator: years with >= 3 trades only
    tr = ([mktrade(5, year=2013, ts=i) for i in range(4)]
          + [mktrade(-1, year=2013, ts=10)]
          + [mktrade(-2, year=2014, ts=i) for i in range(4)]
          + [mktrade(7, year=2015, ts=i) for i in range(2)])
    m = R.strategy_metrics(tr, [5.0], [5.0], 0.8, 0.7)
    check("YEARS_ELIGIBLE counts years with >=3 trades (2013,2014)",
          m["years_eligible"] == 2)
    check("POSITIVE_YEARS counts positive eligible years (2013)",
          m["positive_years"] == 1)
    # DATA_GAP_INVALID excluded from metrics, counted
    tr2 = tr + [{"kind": "A", "family": "NFP", "year": 2015,
                 "entry_ts": 99, "net_pips": float("nan"),
                 "risk_pips": 20.0, "exit_reason": "DATA_GAP_INVALID"}]
    m2 = R.strategy_metrics(tr2, [5.0], [5.0], 0.8, 0.7)
    check("DATA_GAP_INVALID excluded from N, counted separately",
          m2["n_trades"] == len(tr) and m2["n_gap_invalid"] == 1)
    # fail-fast REJECT
    tr3 = [mktrade(-5, ts=i) for i in range(5)]
    check("mean <= 0 -> REJECT",
          R.strategy_metrics(tr3, [5.0], [5.0], 0.8, 0.7)["verdict"]
          == "REJECT")
    # REMOVE_BEST <= 0 -> REJECT (one dominant winner, all others lose;
    # PF <= 1.0 with positive mean is mathematically impossible, so the
    # fail-fast PF branch is exercised via remove-best here)
    tr4 = [mktrade(1000, ts=0)] + \
          [mktrade(-1, ts=1 + i) for i in range(59)]
    m4 = R.strategy_metrics(tr4, [5.0], [5.0], 0.8, 0.7)
    check("remove_best <= 0 -> REJECT",
          m4["net_mean_pips"] > 0 and m4["profit_factor"] > 1.0
          and m4["remove_best_1pct_mean"] <= 0
          and m4["verdict"] == "REJECT")
    # FAIL_GATE: positive but below gate thresholds (n < 40)
    tr5 = [mktrade(3, ts=i) for i in range(10)]
    m5 = R.strategy_metrics(tr5, [5.0], [5.0], 0.8, 0.7)
    check("positive-but-small -> FAIL_GATE", m5["verdict"] == "FAIL_GATE")
    # NFP/CPI positivity condition on pooled PASS
    tr6 = ([mktrade(6, family="NFP", ts=i) for i in range(50)]
           + [mktrade(-1, family="CPI", ts=100 + i) for i in range(45)])
    m6 = R.strategy_metrics(tr6, [5.0], [5.0], 0.8, 0.7)
    pooled_ok = (m6["nfp_mean"] > 0 and m6["cpi_mean"] > 0)
    check("CPI mean <= 0 blocks PASS (gate logic)",
          (not pooled_ok) and m6["verdict"] != "PASS")
    # full synthetic PASS-path gate arithmetic (not a real strategy)
    tr7 = [mktrade(10, family="NFP", ts=i) for i in range(30)]
    tr7 += [mktrade(6, family="CPI", ts=100 + i) for i in range(30)]
    for y in range(2010, 2019):
        tr7 += [mktrade(4, family="NFP", year=y, ts=1000 + i)
                for i in range(3)]
    m7 = R.strategy_metrics(tr7, [5.0], [5.0], 0.8, 0.7)
    check("gate arithmetic accepts a fully-passing synthetic sample",
          m7["verdict"] == "PASS")


def main():
    test_event_loading()
    test_2019_hard_cutoff()
    test_rate_windows()
    test_roll_guard()
    test_rate_gap_guard()
    test_shock_and_direction()
    test_fx_refs()
    test_entry_execution()
    test_exit_execution()
    test_strategies()
    test_metrics_and_gates()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
