#!/usr/bin/env python3
"""S003 minimal tests (frozen-spec section 17). Run: python test_s003.py"""
import numpy as np
import pandas as pd

import s003_strategy as S


def mk5(prices, start="2011-06-01"):
    """Flat 5m series from a price path (one price per 5m bar, flat OHLC)."""
    idx = pd.date_range(start, periods=len(prices), freq="5min", tz="UTC")
    p = np.asarray(prices, dtype=float)
    return pd.DataFrame({"open": p, "high": p, "low": p, "close": p,
                         "n": 1}, index=idx)


BASE_DAYS = 40  # > 5000 5m bars: P034 warmup + 30d median


def synth(compressed_bars, breakout_bars, tail_bars=0, tail_price=1.1020,
          breakout_price=1.1020):
    """40d of +-30 pip oscillation (hi12 ~ 60 pips) -> 13h compressed
    oscillation (hi12 ~ 0.4 pips, comp ~ 0.007) -> breakout -> tail."""
    prices = [1.1015, 1.0985] * (BASE_DAYS * 288 // 2)
    prices += [1.10002, 1.09998] * (compressed_bars // 2)
    prices += [breakout_price] * breakout_bars
    prices += [tail_price] * tail_bars
    return mk5(prices)


def events_and_h1(df5):
    hi12, comp = S.p034_compression_5m(df5)
    h1 = S.h1_bars(df5)
    return S.compression_events(df5, hi12, comp), h1


def test_p034_compression_identical_to_original():
    """hi12/med/event rule reproduce phase2_lib.p034_compression on the same
    5m discovery slice."""
    import os, sys
    sys.path.insert(0, os.path.join(S.ROOT, "research", "phenomena_discovery_v1"))
    import phase2_lib as P2
    df5 = S.load_5m_discovery()
    disc = P2.discovery(df5)
    hi12 = disc["high"].rolling(144).max() - disc["low"].rolling(144).min()
    med = hi12.rolling(30 * 288, min_periods=5000).median()
    ref = (hi12 / med < 0.60).to_numpy()
    ref[:5000] = False
    ref &= ~np.concatenate(([False], ref[:-1]))
    _, comp = S.p034_compression_5m(df5)
    got = (comp.reindex(disc.index) < 0.60).to_numpy()
    got[:5000] = False
    got &= ~np.concatenate(([False], got[:-1]))
    assert (ref == got).all(), "P034 compression flag differs from original"
    # baseline forward-range check vs published figure (62.5 pips)
    fwd = P2.future_rolling_range(disc["high"], disc["low"], 144)
    base = float(np.nanmedian(fwd[: len(disc) - 144])) / S.PIP
    assert abs(base - 62.5) < 0.1, f"baseline {base} != 62.5"
    # P034_5M_EVENT_IDENTITY: raw run-start events must match exactly
    raw_ref = int(ref.sum())
    hi12, comp = S.p034_compression_5m(df5)
    ev = S.compression_events(df5, hi12, comp)
    assert len(ev) == raw_ref, (len(ev), raw_ref)
    for kt, ch, cl, i5 in ev[:50] + ev[-50:]:
        j0 = i5 - 144 + 1
        assert df5.index[i5] + pd.Timedelta(minutes=5) == kt
        assert ch == df5["high"].iloc[j0:i5 + 1].max()
        assert cl == df5["low"].iloc[j0:i5 + 1].min()
    print(f"ok P034_5M_EVENT_IDENTITY: {len(ev)} 5m run-start events == original {raw_ref}")


def test_h1_causal_and_signal_timing():
    df5 = synth(13 * 12, 12, tail_bars=12)
    ev, h1 = events_and_h1(df5)
    assert ev, "no compression event generated"
    T, chigh, clow = ev[-1][0], ev[-1][1], ev[-1][2]
    assert chigh > 1.10 and clow < 1.10  # frozen range spans the oscillation
    trades, _ = S.simulate(ev, h1)
    assert len(trades) == 1
    tr = trades[0]
    assert tr["side"] == 1
    sig = h1.index[h1.close > chigh][0]  # first H1 close above the range
    assert tr["entry_ts"] == sig + pd.Timedelta(hours=1)  # next H1 open
    print("ok H1 causal, signal after close, entry next H1 open (LONG)")


def test_short_stop_target_timeexit_stopfirst_gap():
    # entry ~1.0980 area; risk ~ stop(=chigh) - entry
    # price segments after the 1.0980 signal bar: entry = first segment open
    cases = [("stop", [(6, 1.0990), (6, 1.1010)]),          # rally -> stop
             ("target", [(6, 1.0980), (6, 1.0930)]),        # drop -> 1.5R
             ("time", [(200, 1.0985)])]                      # nowhere -> time
    for kind, segs in cases:
        n_flat = 2 * 288
        prices = [1.1015, 1.0985] * (40 * 288 // 2)
        prices += [1.10002, 1.09998] * (13 * 12 // 2)
        prices += [1.0980] * 12
        for nbars, px in segs:
            prices += [px] * nbars
        ev, h1 = events_and_h1(mk5(prices))
        trades, _ = S.simulate(ev, h1)
        last = [t for t in trades if t["comp_known"] == ev[0][0]][0]
        assert last["side"] == -1
        assert last["reason"] == kind.upper(), (kind, last)
        if kind == "stop":
            assert abs(last["gross_pips"] + last["risk_pips"]) < 1e-9  # stop = -1R
        if kind == "target":
            assert abs(last["gross_pips"] - 1.5 * last["risk_pips"]) < 1e-9
        print(f"ok SHORT {kind} exit")


def test_stop_first_and_gap_through_stop():
    # LONG: signal 1.1020 -> entry 1.1025 (open), stop 1.0985, risk 40p,
    # target 1.1085. Exit bar touches BOTH (high 1.1065 then low 1.0990):
    # STOP-FIRST must win despite the target also being hit.
    prices = [1.1015, 1.0985] * (40 * 288 // 2)
    prices += [1.10002, 1.09998] * (13 * 12 // 2)
    prices += [1.1020] * 12        # signal bar
    prices += [1.1025] * 12        # entry bar
    prices += [1.1090] * 6 + [1.0980] * 6   # target touched, then stop
    ev, h1 = events_and_h1(mk5(prices))
    trades, _ = S.simulate(ev, h1)
    tr = [t for t in trades if t["comp_known"] == ev[0][0]][0]
    assert tr["reason"] == "STOP" and tr["gross_pips"] < 0, tr

    # adverse gap: exit bar OPENS below the LONG stop -> fill at real open,
    # worse than -1R
    prices2 = prices.copy()
    prices2[-12:] = [1.0950] * 12
    ev2, h1b = events_and_h1(mk5(prices2))
    trb = [t for t in S.simulate(ev2, h1b)[0] if t["comp_known"] == ev2[0][0]][0]
    assert trb["reason"] == "STOP" and trb["gross_pips"] < -trb["risk_pips"], trb
    print("ok stop-first same-bar priority + adverse gap at real open")


def test_one_position_and_costs():
    df5 = synth(13 * 12, 12, tail_bars=36 * 12, tail_price=1.1021)
    ev, h1 = events_and_h1(df5)
    trades, skipped = S.simulate(ev, h1)
    for a, b in zip(trades, trades[1:]):
        assert b["entry_ts"] > a["exit_ts"]  # never overlapping
    tr = [t for t in trades if t["reason"] == "TIME"]
    assert tr and tr[0]["net_stress"] == tr[0]["gross_pips"] - S.COST_STRESS
    assert tr[0]["net_normal"] == tr[0]["gross_pips"] - S.COST_NORMAL
    print(f"ok single position (skipped overlap events: {skipped}), costs 2/4")


def test_discovery_frontier():
    df5 = S.load_5m_discovery()
    assert df5.index.max() < pd.Timestamp("2019-01-01", tz="UTC")
    print("ok 2019+ never accessed; discovery frontier enforced at load")


if __name__ == "__main__":
    test_p034_compression_identical_to_original()
    test_h1_causal_and_signal_timing()
    test_short_stop_target_timeexit_stopfirst_gap()
    test_stop_first_and_gap_through_stop()
    test_one_position_and_costs()
    test_discovery_frontier()
    print("ALL S003 TESTS PASSED")
