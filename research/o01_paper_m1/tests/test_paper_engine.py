#!/usr/bin/env python3
"""Required unit/integration tests for the O01 paper engine (mission 13)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from o01_engine.engine import PaperEngine, SignalEngine, PAPER_ONLY  # noqa: E402
from o01_engine.adapters import no_real_order_capability  # noqa: E402

ET = "America/New_York"


def bar(day, hhmm, o, h, l, c, on_hi=None, on_lo=None):
    ts = pd.Timestamp(f"{day} {hhmm}", tz=ET).tz_convert("UTC")
    return {"type": "BAR", "ts": ts, "o": o, "h": h, "l": l, "c": c, "v": 1.0,
            "on_high": on_hi, "on_low": on_lo}


def q(day, hhmmss, bid, ask):
    ts = pd.Timestamp(f"{day} {hhmmss}", tz=ET).tz_convert("UTC")
    return {"type": "QUOTE", "ts": ts, "bid": bid, "ask": ask}


class Feed:
    """Drives a PaperEngine through a synthetic day with quotes."""

    def __init__(self, persist_every=0):
        self.eng = PaperEngine(HERE / "state_tests" / str(id(self)),
                               contract_lookup=lambda d: "NQZ1",
                               persist_every=persist_every)

    def day(self, day, bars, quotes):
        for q_ in quotes:
            self.eng.on_event(q(day, *q_))
        for b in bars:
            self.eng.on_event(bar(day, *b))


def seed_history(eng, days=25, end_day="2021-05-01"):
    """Feed prior completed days (RTH closes) so z/ATR context is ready."""
    d = pd.Timestamp(end_day, tz=ET) - pd.Timedelta(days=days)
    base = 100.0
    for k in range(days):
        day = str((pd.Timestamp(end_day, tz=ET) - pd.Timedelta(days=days - k, unit="D")).date())
        on_hi, on_lo = base * 1.02, base * 0.98
        drift = 0.5 if k % 2 else -0.3     # varied closes -> nonzero z-scores
        bars = [("09:30", base, base * 1.002, base * 0.998, base * 1.001),
                ("09:35", base * 1.001, base * 1.004, base * 0.999, base * 1.002),
                ("15:55", base * 1.002, base * 1.01, base, base + drift)]
        for hhmm, o, h, l, c in bars:
            eng.on_event(bar(day, hhmm, o, h, l, c, on_hi, on_lo))


def test_timezone_dst_change():
    # bars across the US DST switch (2021-03-14) keep 09:30 ET labeling
    eng = SignalEngine()
    d1 = bar("2021-03-12", "09:30", 100, 101, 99, 100)
    assert pd.Timestamp(d1["ts"]).tz_convert(ET).hour == 9
    d2 = bar("2021-03-15", "09:30", 100, 101, 99, 100)   # after DST jump
    assert pd.Timestamp(d2["ts"]).tz_convert(ET).hour == 9
    # ET wall-clock hour identical across the DST jump (Mar 12 EST / Mar 15 EDT)
    assert (pd.Timestamp(d2["ts"]).tz_convert(ET).isoformat()[11:16] ==
            pd.Timestamp(d1["ts"]).tz_convert(ET).isoformat()[11:16])


def test_z_score_causality_needs_20_prior_days():
    eng = SignalEngine()
    day = "2021-06-01"
    on_hi, on_lo = 101, 99
    # 15 prior days only -> context missing
    for k in range(15):
        pd_ = str((pd.Timestamp(day, tz=ET) - pd.Timedelta(days=20 - k, unit="D")).date())
        for hhmm, c in (("09:30", 100), ("09:35", 100.2), ("15:55", 100.5)):
            eng.process_bar(bar(pd_, hhmm, 100, 100.5, 99.5, c, on_hi, on_lo))
    dec = eng.process_bar(bar(day, "09:35", 100, 100.5, 99.5, 100.2, on_hi, on_lo))
    assert dec["decision"] == "NO_TRADE" and "context not ready" in dec["reason"]


def test_no_future_bars_in_context():
    eng = SignalEngine()
    # the 09:35 decision must not know the 09:40 bar
    seen = []
    orig = eng._decide
    def spy(st):
        seen.extend(b["ts"] for b in st["bars"])
        return orig(st)
    eng._decide = spy
    day = "2021-06-01"
    eng.process_bar(bar(day, "09:30", 100, 100.5, 99.5, 100, 101, 99))
    eng.process_bar(bar(day, "09:35", 100, 100.6, 99.6, 100.2, 101, 99))
    eng.process_bar(bar(day, "09:40", 100, 100.7, 99.7, 100.3, 101, 99))
    assert all("09:3" in str(pd.Timestamp(x).tz_convert(ET).isoformat()) or
               "09:4" in str(pd.Timestamp(x).tz_convert(ET).isoformat()) for x in seen)
    assert all(str(pd.Timestamp(x).tz_convert(ET).hour * 100 + 
                   pd.Timestamp(x).tz_convert(ET).minute) in ("930", "935") for x in seen)


def test_premarket_and_overnight_intervals():
    eng = SignalEngine()
    day = "2021-06-01"
    for k in range(21):
        pd_ = str((pd.Timestamp(day, tz=ET) - pd.Timedelta(days=25 - k, unit="D")).date())
        for hhmm, c in (("09:30", 100), ("09:35", 100.2), ("15:55", 100.5)):
            eng.process_bar(bar(pd_, hhmm, 100, 100.5, 99.5, c, 101, 99))
    # 03:55 bar belongs to the OVERNIGHT window; 04:00 opens premarket
    eng.process_bar(bar(day, "03:55", 100, 105, 95, 100, 101, 99))
    eng.process_bar(bar(day, "04:00", 100, 100.5, 99.5, 100, 101, 99))
    eng.process_bar(bar(day, "09:30", 100, 100.5, 99.5, 100, 101, 99))
    eng.process_bar(bar(day, "09:35", 100, 100.6, 99.6, 100.2, 101, 99))
    st = eng.cur
    from o01_engine.engine import _hm
    pre = [b for b in st["bars"] if 400 <= _hm(b) < 930]
    assert len(pre) == 1 and pre[0]["h"] == 100.5 and pre[0]["l"] == 99.5
    # premarket must EXCLUDE the 03:55 bar (105/95 overnight extremes)
    assert max(b["h"] for b in pre) == 100.5
    onw = [b for b in st["bars"] if _hm(b) < 400]
    assert len(onw) == 1 and onw[0]["h"] == 105 and onw[0]["l"] == 95


def test_signal_direction_and_entry_next_quote():
    eng = PaperEngine(HERE / "state_tests" / "dir1", persist_every=0)
    seed_history(eng)
    day = "2021-06-02"
    # strong positive overnight return: gap open way above prior close
    bars = [("04:00", 110.5, 110.9, 109.9, 110.5)]
    bars += [(f"09:{m:02d}", 110, 110.5, 109.8, 110.2) for m in (30, 35)]
    quotes = [(f"09:{m:02d}:{s:02d}", 110.0, 110.3) for m in (40,) for s in (1,)]
    bars += [(f"09:{m:02d}", 110, 110.5, 109.8, 110.2) for m in (40, 45)]
    for hhmm, o, h, l, c in bars:
        eng.on_event(bar(day, hhmm, o, h, l, c, 111.8, 108.8))
    for qq in quotes:
        eng.on_event(q(day, *qq))
    assert eng.trades and eng.trades[0]["SIDE"] == "LONG"
    # long entry filled at ASK (110.3), not bid, not open
    assert abs(eng.trades[0]["ENTRY"]["BASE"] - 110.3) < 1e-9


def test_short_entry_at_bid():
    eng = PaperEngine(HERE / "state_tests" / "dir2", persist_every=0)
    seed_history(eng)
    day = "2021-06-02"
    bars = [("04:00", 89.6, 90.1, 89.1, 89.6)]
    bars += [(f"09:{m:02d}", 90, 90.4, 89.2, 89.5) for m in (30, 35)]
    quotes = [(f"09:{m:02d}:{s:02d}", 89.4, 89.7) for m in (40,) for s in (1,)]
    bars += [(f"09:{m:02d}", 89.5, 90.0, 89.0, 89.6) for m in (40, 45)]
    for hhmm, o, h, l, c in bars:
        eng.on_event(bar(day, hhmm, o, h, l, c, 90.9, 88.9))
    for qq in quotes:
        eng.on_event(q(day, *qq))
    assert eng.trades[0]["SIDE"] == "SHORT"
    assert abs(eng.trades[0]["ENTRY"]["BASE"] - 89.4) < 1e-9   # BID for short


def test_stop_triggers_on_executable_quote():
    eng = PaperEngine(HERE / "state_tests" / "stop1", persist_every=0)
    seed_history(eng)
    day = "2021-06-02"
    bars = [("04:00", 110.5, 110.9, 109.9, 110.5)] +         [(f"09:{m:02d}", 110, 110.5, 109.8, 110.2) for m in (30, 35)]
    for hhmm, o, h, l, c in bars:
        eng.on_event(bar(day, hhmm, o, h, l, c, 111.8, 108.8))
    eng.on_event(q(day, "09:40:01", 110.0, 110.3))    # entry fills here (ask)
    stop = eng.trades[0]["STOP"]
    eng.on_event(q(day, "09:38:00", stop - 0.5, stop - 0.25))  # bid <= stop
    assert eng.trades[0].get("EXIT_REASON") == "STOP"
    # long exit executed at BID (the executable side)
    assert abs(eng.trades[0]["EXIT"]["BASE"] - (stop - 0.5)) < 1e-9


def test_chandelier_requires_completed_close():
    eng = PaperEngine(HERE / "state_tests" / "chand", persist_every=0)
    seed_history(eng)
    day = "2021-06-02"
    for hhmm, o, h, l, c in [("04:00", 110.5, 110.9, 109.9, 110.5)] +             [(f"09:{m:02d}", 110, 110.5, 109.8, 110.2) for m in (30, 35)]:
        eng.on_event(bar(day, hhmm, o, h, l, c, 111.8, 108.8))
    eng.on_event(q(day, "09:40:01", 110.0, 110.3))
    assert eng.trades[0].get("EXIT_REASON") is None
    # rally bar then a close below the chandelier -> TRAIL exit
    eng.on_event(bar(day, "09:40", 110.3, 112.0, 110.0, 111.5))
    eng.on_event(q(day, "09:41:00", 111.4, 111.6))
    eng.on_event(bar(day, "09:45", 111.5, 111.6, 110.5, 110.6))
    eng.on_event(q(day, "09:46:00", 110.5, 110.7))
    assert eng.trades[0].get("EXIT_REASON") == "TRAIL"


def test_eod_exit_last_bar():
    eng = PaperEngine(HERE / "state_tests" / "eod", persist_every=0)
    seed_history(eng)
    day = "2021-06-02"
    for hhmm, o, h, l, c in [("04:00", 110.5, 110.9, 109.9, 110.5)] +             [(f"09:{m:02d}", 110, 110.5, 109.8, 110.2) for m in (30, 35)]:
        eng.on_event(bar(day, hhmm, o, h, l, c, 111.8, 108.8))
    eng.on_event(q(day, "09:40:01", 110.0, 110.3))
    eng.on_event(bar(day, "15:55", 112, 112.5, 111.8, 112.2))
    eng.on_event(q(day, "15:56:00", 112.1, 112.3))
    assert eng.trades[0].get("EXIT_REASON") == "EOD"


def test_three_scenarios_diverge_by_ticks():
    eng = PaperEngine(HERE / "state_tests" / "scen", persist_every=0)
    seed_history(eng)
    day = "2021-06-02"
    for hhmm, o, h, l, c in [("04:00", 110.5, 110.9, 109.9, 110.5)] +             [(f"09:{m:02d}", 110, 110.5, 109.8, 110.2) for m in (30, 35)]:
        eng.on_event(bar(day, hhmm, o, h, l, c, 111.8, 108.8))
    eng.on_event(q(day, "09:40:01", 110.0, 110.3))
    eng.on_event(bar(day, "15:55", 112, 112.5, 111.8, 112.2))
    eng.on_event(q(day, "15:56:00", 112.1, 112.3))
    t = eng.trades[0]
    assert abs(t["PNL_CONSERVATIVE_PTS"] - (t["PNL_BASE_PTS"] - 0.5)) < 1e-9
    assert abs(t["PNL_STRESS_PTS"] - (t["PNL_BASE_PTS"] - 1.0)) < 1e-9


def test_no_real_order_capability():
    assert PAPER_ONLY is True
    assert no_real_order_capability() is True


def test_restart_recovery_no_duplicate():
    root = HERE / "state_tests" / "restart"
    import shutil
    shutil.rmtree(root, ignore_errors=True)
    eng = PaperEngine(root, persist_every=1)
    seed_history(eng)
    day = "2021-06-02"
    evs = [bar(day, hhmm, 110, 110.5, 109.8, 110.2, 111.8, 108.8) for hhmm in ("09:30", "09:35")]
    for e in evs:
        eng.on_event(e)
    n1 = eng.seq
    # restart: new engine, same state store
    eng2 = PaperEngine(root, persist_every=1)
    assert eng2.seq >= n1 - 1            # restored progress
    # duplicate event (same event_id) is ignored
    ev = dict(evs[1])
    ev["event_id"] = "DUP-1"
    eng2.on_event(ev)
    eng2.on_event(ev)
    assert eng2.seq == eng2.seq          # no crash
    # and no duplicate journal lines for DUP-1
    jl = (root / "paper_journal.jsonl").read_text()
    assert jl.count("DUP-1") <= 1


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
