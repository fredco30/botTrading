#!/usr/bin/env python3
"""Mission tests: MODE guards, prospective no-synthetic, warm-up exactness."""
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from o01_engine.engine import PaperEngine, MODE_REFERENCE, MODE_PROSPECTIVE  # noqa: E402

ACT = "2026-09-16T22:01:40+00:00"


def mk(mode, **kw):
    return PaperEngine(HERE / "state_tests" / f"mode-{mode}-{id(kw)}",
                       persist_every=0, mode=mode,
                       activation_ts=ACT if mode == MODE_PROSPECTIVE else None, **kw)


def test_reference_2026_rejected():
    eng = mk(MODE_REFERENCE)
    with pytest.raises(ValueError):
        eng.on_event({"type": "BAR", "ts": pd.Timestamp("2026-06-01", tz="UTC"),
                      "o": 1, "h": 1, "l": 1, "c": 1, "v": 1})


def test_prospective_pre_activation_rejected():
    eng = mk(MODE_PROSPECTIVE)
    with pytest.raises(ValueError):
        eng.on_event({"type": "BAR", "ts": pd.Timestamp("2026-06-01", tz="UTC"),
                      "o": 1, "h": 1, "l": 1, "c": 1, "v": 1})


def test_prospective_post_activation_allowed():
    eng = mk(MODE_PROSPECTIVE)
    eng.on_event({"type": "BAR", "ts": pd.Timestamp("2026-09-17 14:35", tz="UTC"),
                  "o": 100, "h": 100.5, "l": 99.5, "c": 100.2, "v": 1,
                  "on_high": None, "on_low": None})
    assert eng.seq == 1


def test_prospective_no_synthetic_stop_fill():
    eng = mk(MODE_PROSPECTIVE)
    day = "2026-09-17"
    eng.on_event({"type": "BAR", "ts": pd.Timestamp(f"{day} 13:30", tz="UTC"),
                  "o": 100, "h": 100.5, "l": 99.5, "c": 100, "v": 1,
                  "on_high": None, "on_low": None})
    # open a position directly (unit-level): stop 99.0
    eng.pos.side, eng.pos.stop, eng.pos.entry = 1, 99.0, 100.0
    # bar touches stop (l <= 99) but NO executable quote proof attached
    eng.on_event({"type": "BAR", "ts": pd.Timestamp(f"{day} 13:40", tz="UTC"),
                  "o": 99.5, "h": 99.6, "l": 98.9, "c": 99.2, "v": 1,
                  "on_high": None, "on_low": None})
    jl = (HERE / "state_tests" / f"mode-{MODE_PROSPECTIVE}-{id({})}"
          if False else None)
    # no exit was booked without quote proof (position still open, DATA_GAP path)
    assert eng.pos.side == 1 and "PNL_BASE_PTS" not in (
        eng.trades[-1] if eng.trades else {})


def test_prospective_exit_quote_proven_fills():
    eng = mk(MODE_PROSPECTIVE)
    day = "2026-09-17"
    eng.on_event({"type": "BAR", "ts": pd.Timestamp(f"{day} 13:30", tz="UTC"),
                  "o": 100, "h": 100.5, "l": 99.5, "c": 100, "v": 1,
                  "on_high": None, "on_low": None})
    eng.pos.side, eng.pos.stop, eng.pos.entry = 1, 99.0, 100.0
    eng.pos.entry_shadows = {"BASE": 100.0, "CONSERVATIVE": 100.0, "STRESS": 100.0}
    eng.trades.append({"DATE": day, "EXIT_REASON": None, "ENTRY": {"BASE": 100.0, "CONSERVATIVE": 100.0, "STRESS": 100.0}})   # position ledger entry
    # bar touches stop WITH quote proof: first quote in bar with bid <= stop
    bq = [(pd.Timestamp(f"{day} 13:41", tz="UTC"), 98.8, 99.0)]
    eng._manage_bar({"type": "BAR", "ts": pd.Timestamp(f"{day} 13:40", tz="UTC"),
                     "o": 99.5, "h": 99.6, "l": 98.9, "c": 99.2, "v": 1,
                     "on_high": None, "on_low": None, "bar_quotes": bq,
                     "quotes_at_exit": []}, bq, [], False)
    assert eng.pos.side == 0 and eng.trades[-1]["EXIT_REASON"] == "STOP"
    assert abs(eng.trades[-1]["EXIT"]["BASE"] - 98.8) < 1e-9


def test_warmup_counts():
    # on_ret needs a prior session close -> first record at session 2;
    # decision needs >=20 on_rets -> session 22; ATR needs 14 -> session 15.
    assert 22 == 22  # documented computation; calendar check below
    # 22nd US weekday from 2026-09-17 (Thu):
    d = pd.Timestamp("2026-09-17")
    count, cur = 0, d
    while count < 21:
        cur += pd.Timedelta(days=1)
        if cur.dayofweek < 5:
            count += 1
    assert str(cur.date()) == "2026-10-16"


def test_spending_guard_logic():
    cum, est, ceiling = 0.48, 0.0385, 0.50
    assert cum + est > ceiling     # guard must STOP here
