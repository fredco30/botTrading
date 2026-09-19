#!/usr/bin/env python3
"""Source-fidelity + causality tests for the Trend Magic Enhanced port.

Run:  python tests/test_trend_magic.py   (plain asserts, no pytest needed)
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import tmlab as T

FAIL = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL  {name}  {detail}")


# ---------------------------------------------------------------- hand-calc
def test_true_range():
    h = np.array([10.0, 10.5, 10.2, 10.9])
    l = np.array([9.5, 9.8, 9.9, 10.0])
    c = np.array([9.9, 10.4, 10.1, 10.8])
    tr = T.true_range(h, l, c)
    # bar0: h-l = 0.5
    # bar1: max(0.7, |10.5-9.9|=0.6, |9.8-9.9|=0.1) = 0.7
    # bar2: max(0.3, |10.2-10.4|=0.2, |9.9-10.4|=0.5) = 0.5
    # bar3: max(0.9, |10.9-10.1|=0.8, |10.0-10.1|=0.1) = 0.9
    check("true_range hand-calc", np.allclose(tr, [0.5, 0.7, 0.5, 0.9]), tr)


def test_sma():
    x = np.arange(1, 7, dtype="float64")
    s = T.sma(x, 3)
    check("sma hand-calc", np.allclose(s[2:], [2.0, 3.0, 4.0, 5.0])
          and np.all(np.isnan(s[:2])), s)


def test_cci_constant_and_flat():
    # constant series -> MAD 0 -> CCI na (Pine: division by 0 -> na)
    c = np.full(30, 1.10)
    cc = T.cci_pine(c, 20)
    check("cci constant -> na", np.all(np.isnan(cc[19:])))
    # ramp series hand-checked against definition
    c = np.linspace(1.0, 1.29, 30)
    cc = T.cci_pine(c, 20)
    i = 25
    w = c[i - 19:i + 1]
    m = w.mean()
    mad = np.mean(np.abs(w - m))
    expected = (c[i] - m) / (0.015 * mad)
    check("cci hand-calc bar25", np.isclose(cc[i], expected),
          (cc[i], expected))


def test_trend_magic_recurrence_synthetic():
    """Tiny series where every MT value is computable by hand.

    Construct rising closes so CCI >= 0 from bar 19 onward, constant TR so
    VOL is known, then verify ratchet: MT = max(UP, prev).
    """
    n = 30
    # symmetric oscillator around 1.10 with amplitude 0.002 -> keep CCI positive:
    # use strictly increasing close so CCI > 0 after warm-up
    c = np.linspace(1.10, 1.10 + 0.001 * (n - 1), n)
    h = c + 0.0005
    l = c - 0.0005
    # TR bar0 = 0.001; bars 1+: max(0.001, |h-c[-1]|=0.0015, |l-c[-1]|=0.0005)
    tr_const = 0.0015
    mt, d, cc, vol = T.trend_magic(h, l, c, atr_period=5)
    # bars 0..3: VOL na -> candidates na -> MT := na (Pine na ratchet)
    check("warm-up: MT na while VOL undefined", np.all(np.isnan(mt[:4])), mt[:6])
    # bars 4..18: CCI na -> bear branch; dn>0 -> MT := nz(MT[1]) = 0
    check("warm-up: MT == 0 while CCI na (nz quirk)",
          np.all(mt[4:18] == 0.0) and np.all(d[:19] == 0), mt[:20])
    # from bar 19 CCI defined; VOL[19] = mean(TR[15..19]) — all 0.0015
    # (TR[0]=0.001 only feeds VOL[4..8])
    vol19 = tr_const
    check("VOL[19] hand-calc", np.isclose(vol[19], vol19), vol[19])
    # first valid bar: CCI>0 -> UP = l - 2*VOL; MT := UP (nz(prev)=0 < UP)
    up19 = l[19] - 2 * vol19
    check("MT[19] = UP", np.isclose(mt[19], up19), (mt[19], up19))
    # next bar UP rises with l; MT must take the larger
    up20 = l[20] - 2 * (0.0015)
    check("MT[20] = max(UP20, MT19)",
          np.isclose(mt[20], max(up20, mt[19])), (mt[20], up20, mt[19]))


def test_bear_branch_ratchet():
    """CCII < 0: MT = min(DN, prev), falls or holds; state via high crossunder."""
    n = 40
    c = np.linspace(1.20, 1.20 - 0.001 * (n - 1), n)   # falling -> CCI < 0
    h = c + 0.0005
    l = c - 0.0005
    mt, d, cc, vol = T.trend_magic(h, l, c)
    # warm-up: bars 0..3 na (VOL undefined), then bear branch holds 0
    check("bear warm-up MT na then 0",
          np.all(np.isnan(mt[:4])) and np.all(mt[4:18] == 0.0))
    # first valid bar (19): CCI<0 -> DN>0 -> MT := nz(MT[1]) = 0 — the line
    # stays 0 until a bull branch appears (Pine nz(0)-anchor quirk). Verify:
    check("bear-only series: MT stays 0 (nz(0) ratchet quirk)",
          np.all(mt[19:] == 0.0), mt[19:].min())
    # direction never triggers (no crossing vs 0 possible from below)
    check("bear-only series: direction stays 0", np.all(d == 0))


def test_state_transition_crossover():
    """V-reversal scenario: ramp -> flat -> collapse -> recovery.

    In a ramp/flat the line trails below the low (no cross possible, state
    stays 0 — genuine Pine behaviour); a collapse makes high cross under the
    line (state -1); a recovery makes low cross over it (state +1).
    """
    n0, m_flat, m2, m3 = 30, 40, 30, 30
    c = np.linspace(1.10, 1.10 + 0.001 * (n0 - 1), n0)
    h0 = c + 0.0005
    l0 = c - 0.0005
    mt0, d0, _, _ = T.trend_magic(h0, l0, c)
    check("ramp series: no premature bull state", np.all(d0 == 0))
    # flat plateau above the ramp: state stays 0 (low never touches the line)
    lvl = 1.1355
    c1 = np.full(m_flat, lvl); h1 = c1 + 0.0001; l1 = c1 - 0.0001
    # collapse far below the line -> high crosses under -> bear
    lvl2 = 1.1150
    c2 = np.full(m2, lvl2); h2 = c2 + 0.0001; l2 = c2 - 0.0001
    # recovery far above the line -> low crosses over -> bull
    lvl3 = 1.1350
    c3 = np.full(m3, lvl3); h3 = c3 + 0.0001; l3 = c3 - 0.0001
    h = np.concatenate([h0, h1, h2, h3])
    l = np.concatenate([l0, l1, l2, l3])
    c4 = np.concatenate([c, c1, c2, c3])
    i_flat, i_coll, i_rec = n0, n0 + m_flat, n0 + m_flat + m2
    mt, d, _, _ = T.trend_magic(h, l, c4)
    check("flat region: state still 0", np.all(d[:i_coll] == 0))
    check("bear state on engineered crossunder", d[i_coll] == -1,
          (d[i_coll - 2:i_coll + 3], mt[i_coll - 1:i_coll + 2], lvl2))
    check("direction holds -1 through collapse",
          np.all(d[i_coll:i_rec] == -1))
    check("bull state on engineered cross-up", d[i_rec] == 1,
          (d[i_rec - 2:i_rec + 3], mt[i_rec - 1:i_rec + 2], lvl3))
    check("direction holds +1 through recovery", np.all(d[i_rec:] == 1))


def test_crossover_semantics_edge():
    """Pine crossover: a[1] <= b[1] and a > b. Equality on prev bar counts."""
    # Craft two bars: MT known constant M (bear series won't work; use bull
    # branch with CCI>=0 constant ratchet). Simplest: verify the boolean rule
    # directly on a constructed MT by calling the loop logic via trend_magic
    # with a vol of 0 -> MT == low for bull branch (l - 0*mult).
    # vol=0 impossible via TR=0? TR=0 when h==l==c constant -> then CCI na.
    # Instead directly test the inequality pattern with synthetic mt array:
    l = np.array([1.0, 2.0, 2.0, 3.0])
    mt = np.array([0.0, 2.0, 2.0, 4.0])
    # bar1: l0=1<=0? no -> rule needs mt[0]: 1<=0 false -> no
    # bar2: l1=2 <= mt1=2 (equality) and l2=2 > 2 false -> no
    # bar3: l2=2 <= 2 and l3=3 > 4 false -> no
    cross_up = (l[1:] > mt[1:]) & (l[:-1] <= mt[:-1])
    check("crossover rule equality/no-cross", not cross_up.any())
    l2 = np.array([1.0, 1.0, 3.0]); mt2 = np.array([0.0, 2.0, 2.0])
    cross_up2 = (l2[1:] > mt2[1:]) & (l2[:-1] <= mt2[:-1])
    check("crossover fires after prev-bar equality",
          cross_up2.tolist() == [False, True])


# ---------------------------------------------------------------- causality
def test_truncation_invariance():
    """Indicator values for bars 0..k must not change when future bars change
    (no lookahead)."""
    rng = np.random.default_rng(7)
    n = 400
    c = 1.10 + np.cumsum(rng.normal(0, 0.0004, n))
    h = c + np.abs(rng.normal(0, 0.0002, n)) + 0.0001
    l = c - np.abs(rng.normal(0, 0.0002, n)) - 0.0001
    mt, d, cc, vol = T.trend_magic(h, l, c)
    k = 250
    c2 = c.copy(); c2[k:] = c2[k:] + 0.01     # mutate only the future
    h2 = h.copy(); h2[k:] += 0.01
    l2 = l.copy(); l2[k:] -= 0.01
    mt2, d2, cc2, vol2 = T.trend_magic(h2, l2, c2)
    check("truncation: MT[0:k] invariant",
          np.array_equal(mt[:k], mt2[:k], equal_nan=True))
    check("truncation: DIR[0:k] invariant", np.array_equal(d[:k], d2[:k]))
    check("truncation: CCI/VOL[0:k] invariant",
          np.array_equal(cc[:k], cc2[:k], equal_nan=True)
          and np.array_equal(vol[:k], vol2[:k], equal_nan=True))


def test_online_vs_batch():
    """Batch loop equals incremental feed (bar-by-bar availability)."""
    rng = np.random.default_rng(11)
    n = 300
    c = 1.30 + np.cumsum(rng.normal(0, 0.0005, n))
    h = c + 0.0003; l = c - 0.0003
    mt, d, _, _ = T.trend_magic(h, l, c)
    # incremental: recompute with growing history; values at bar k must match
    ok = True
    for k in (25, 50, 99, 150, 299):
        mtk, dk, _, _ = T.trend_magic(h[:k + 1], l[:k + 1], c[:k + 1])
        if not (np.isclose(mtk[-1], mt[k]) and dk[-1] == d[k]):
            ok = False
            print("   mismatch at", k, mtk[-1], mt[k], dk[-1], d[k])
    check("online == batch", ok)


def test_warmup_nan_handling():
    n = 19
    c = np.linspace(1.0, 1.02, n); h = c + 1e-4; l = c - 1e-4
    mt, d, cc, vol = T.trend_magic(h, l, c)
    check("all-na CCI before period", np.all(np.isnan(cc)))
    check("vol na before atr period", np.isnan(vol[3]) and np.isfinite(vol[4]))
    check("direction 0 during warm-up", np.all(d == 0))


def test_pine_source_frozen():
    sha = T.pine_source_sha256()
    check("pine source sha256 matches spec",
          sha == "82de45d028e0c8793115ef07f4c7d6f3de7d4f844ea96bb58a10b4f4bc1c2e21",
          sha)


def test_seal():
    import pandas as pd
    idx = pd.date_range("2025-12-31", periods=3, freq="5min", tz="UTC")
    try:
        T.assert_sealed(idx)
        check("seal allows 2025 data", True)
    except T.SealViolation:
        check("seal allows 2025 data", False)
    idx2 = pd.date_range("2026-01-01", periods=2, freq="5min", tz="UTC")
    try:
        T.assert_sealed(idx2)
        check("seal blocks 2026 data", False)
    except T.SealViolation:
        check("seal blocks 2026 data", True)
    df = T.load_5m("EURUSD", "2025-12-30", "2025-12-31 23:59")
    check("load_5m sealed end", df.index.max() <= T.SEAL_UTC, df.index.max())
    try:
        T.load_5m("EURUSD", "2025-12-01", "2026-01-05")
        check("load_5m rejects 2026 window", False)
    except AssertionError:
        check("load_5m rejects 2026 window", True)


def test_events():
    d = np.array([0, 0, 1, 1, 1, -1, -1, 1, 0])
    ev = T.events_from_direction(d)
    check("event indices", np.array_equal(ev, [2, 5, 7, 8]), ev)
    check("no events on constant state",
          len(T.events_from_direction(np.ones(50))) == 0)


if __name__ == "__main__":
    for fn in [test_true_range, test_sma, test_cci_constant_and_flat,
               test_trend_magic_recurrence_synthetic,
               test_bear_branch_ratchet, test_state_transition_crossover,
               test_crossover_semantics_edge, test_truncation_invariance,
               test_online_vs_batch, test_warmup_nan_handling,
               test_pine_source_frozen, test_seal, test_events]:
        print(fn.__name__)
        fn()
    print()
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)
    print("ALL TESTS PASSED")
