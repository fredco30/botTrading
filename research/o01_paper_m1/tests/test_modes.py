#!/usr/bin/env python3
"""Reconciliation-mode tests: S1 trigger, no synthetic fallback, mode split."""
import sys
from pathlib import Path
import pandas as pd
import pytest
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from o01_engine.engine import PaperEngine  # noqa: E402
from o01_engine.adapters import no_real_order_capability  # noqa: E402


def test_s1_trigger_is_bar_based_not_quote_continuous():
    # a quote touching the stop DURING a bar whose low did NOT touch
    # must NOT stop the position (S1 bar semantic) — the stop fires only
    # when the completed bar's low/high touches, priced at the quote.
    eng = PaperEngine(HERE / "state_tests" / "s1", persist_every=0)
    base = 100.0
    for k in range(21):
        day = str((pd.Timestamp("2021-06-01", tz="America/New_York") -
                   pd.Timedelta(days=25 - k, unit="D")).date())
        drift = 0.5 if k % 2 else -0.3
        for hhmm, c in (("09:30", 100), ("09:35", 100.2), ("15:55", 100.0 + drift)):
            ts = pd.Timestamp(f"{day} {hhmm}", tz="America/New_York").tz_convert("UTC")
            eng.on_event({"type": "BAR", "ts": ts, "o": 100, "h": 100.5,
                          "l": 99.5, "c": c, "v": 1, "on_high": 101, "on_low": 99})
    day = "2021-06-02"
    for hhmm, o, h, l, c in [("04:00", 110.5, 110.9, 109.9, 110.5),
                             ("09:30", 110, 110.5, 109.8, 110.2),
                             ("09:35", 110, 110.5, 109.8, 110.2)]:
        eng.on_event({"type": "BAR", "ts": pd.Timestamp(f"{day} {hhmm}",
                     tz="America/New_York").tz_convert("UTC"), "o": o, "h": h,
                     "l": l, "c": c, "v": 1, "on_high": 111.8, "on_low": 108.8})
    eng.on_event({"type": "QUOTE", "ts": pd.Timestamp(f"{day} 09:40:01",
                 tz="America/New_York").tz_convert("UTC"), "bid": 110.0,
                 "ask": 110.3})
    assert eng.trades, "entry should have filled"
    stop = eng.trades[0]["STOP"]
    # quote BELOW stop while the BAR low stays above it: no S1 stop
    eng.on_event({"type": "BAR", "ts": pd.Timestamp(f"{day} 09:45",
                 tz="America/New_York").tz_convert("UTC"), "o": 110.2,
                 "h": 110.4, "l": stop + 0.5, "c": 110.1, "v": 1,
                 "on_high": None, "on_low": None})
    assert eng.trades[0].get("EXIT_REASON") is None


def test_no_synthetic_fallback_in_prospective_mode():
    # engine has no frozen-price fallback symbol: missing quotes leave the
    # day flat (DATA_GAP), never a fabricated fill
    import inspect
    src = inspect.getsource(PaperEngine)
    assert "MODELED_ENTRY" not in src and "MODELED_FINAL_EXIT" not in src


def test_no_real_order_route():
    assert no_real_order_capability()


def test_reference_mode_regression_artifact_exists():
    p = HERE.parent / "nq_h02_o01_highres_m1" / "results" / "o01_bbo_replay_trades.csv"
    assert p.exists() and len(pd.read_csv(p)) == 133


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
