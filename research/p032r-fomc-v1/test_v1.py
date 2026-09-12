"""Tests minimaux P032R V1 (pytest). Données synthétiques uniquement."""
import pandas as pd
import numpy as np

import lib_v1 as L


def bars_from(opens, start="2020-01-01", freq="5min"):
    idx = pd.date_range(start, periods=len(opens), freq=freq, tz="UTC")
    df = pd.DataFrame({"open": opens}, index=idx)
    for c in ["high", "low", "close", "volume", "n"]:
        df[c] = 0.0
    return df


# --- timing causal T0/T30/T120 -------------------------------------------
def test_timing_causal():
    # release 14:00 EST = 19:00 UTC; T0 = première barre >= 19:00
    bars = bars_from([1.0 + 0.0001 * i for i in range(40)],
                     start="2020-01-01 18:50")
    r = L.measure_event_pair(bars, pd.Timestamp("2020-01-01 19:00", tz="UTC"),
                             "EURUSD")
    assert r["T0"] == pd.Timestamp("2020-01-01 19:00", tz="UTC")
    assert r["T30"] == pd.Timestamp("2020-01-01 19:30", tz="UTC")
    assert r["T120"] == pd.Timestamp("2020-01-01 21:00", tz="UTC")
    assert r["T0"] < r["T30"] < r["T120"]


def test_t0_rounds_up_to_next_bar():
    # release 19:02 → T0 = barre 19:05 (OPEN >= release)
    bars = bars_from([1.0] * 40, start="2020-01-01 18:50")
    r = L.measure_event_pair(bars, pd.Timestamp("2020-01-01 19:02", tz="UTC"),
                             "EURUSD")
    assert r["T0"] == pd.Timestamp("2020-01-01 19:05", tz="UTC")


# --- direction connue à T30, P&L = signe * (T120 - T30) -------------------
def test_direction_known_at_t30_and_pnl():
    def make(t30_px, end_px):
        opens = [1.0] * 32         # barres 18:35 → 21:55
        opens[11] = t30_px         # T30 = barre 19:30 (index 11)
        opens[29] = end_px         # T120 = barre 21:00 (index 29)
        return bars_from(opens, start="2020-01-01 18:35")

    # initial +10 pips → LONG; T120 = T30 + 20 pips
    r = L.measure_event_pair(make(1.0010, 1.0030),
                             pd.Timestamp("2020-01-01 19:00", tz="UTC"),
                             "EURUSD")
    assert abs(r["INITIAL_MOVE_PIPS"] - 10.0) < 1e-9
    assert abs(r["CONT_30_120_PIPS"] - 20.0) < 1e-9
    # SHORT symétrique: initial -10 pips; mouvement prix T120-T30 = -20 pips
    # (P&L SHORT = +20 pips, appliqué via direction dans build_table)
    r2 = L.measure_event_pair(make(0.9990, 0.9970),
                              pd.Timestamp("2020-01-01 19:00", tz="UTC"),
                              "EURUSD")
    assert abs(r2["INITIAL_MOVE_PIPS"] + 10.0) < 1e-9
    assert abs(r2["CONT_30_120_PIPS"] + 20.0) < 1e-9


# --- V1 boundary: entrée/sortie dans V1 uniquement ------------------------
def test_v1_boundary_exit_outside_rejected():
    # événement 2022-12-14 19:00 UTC → T120 le 14/12; OK.
    # Ici: barres s'arrêtent avant T120 → None (pas de sortie dans V1)
    opens = [1.0] * 10
    bars = bars_from(opens, start="2022-12-14 18:55")
    assert L.measure_event_pair(
        bars, pd.Timestamp("2022-12-14 19:00", tz="UTC"), "EURUSD") is None


def test_v1_boundary_uses_synthetic_out_of_window():
    # release avant V1 → None
    bars = bars_from([1.0] * 40, start="2018-12-31 18:50")
    assert L.measure_event_pair(
        bars, pd.Timestamp("2018-12-31 19:00", tz="UTC"), "EURUSD") is None


# --- V2/OOS non accessibles ------------------------------------------------
def test_no_v2_oos_access():
    assert L.V1_END == pd.Timestamp("2023-01-01", tz="UTC")
    bars = bars_from([1.0] * 40, start="2023-01-01 00:00")
    assert L.measure_event_pair(
        bars, pd.Timestamp("2023-01-01 00:00", tz="UTC"), "EURUSD") is None


# --- événements appariés conservés ensemble --------------------------------
def test_paired_event_kept_together():
    t = pd.DataFrame({
        "YEAR": ["2020"] * 3,
        "POOLED_NET_NORMAL": [10.0, -4.0, 2.0],
        "POOLED_GROSS": [12.0, -2.0, 4.0],
        "POOLED_NET_STRESS": [8.0, -6.0, 0.0],
        "EURUSD_NET_NORMAL": [1.0] * 3, "USDJPY_NET_NORMAL": [1.0] * 3,
        "GBPUSD_NET_NORMAL": [1.0] * 3})
    lo, hi = L.paired_bootstrap_ci(t["POOLED_NET_NORMAL"], n=2000, seed=42)
    rng = np.random.default_rng(42)
    x = t["POOLED_NET_NORMAL"].values
    expect = rng.choice(x, size=(2000, x.size), replace=True).mean(axis=1)
    assert lo == float(np.percentile(expect, 2.5))
    assert hi == float(np.percentile(expect, 97.5))


# --- remove-best = vraie moyenne après retrait ------------------------------
def test_remove_best_true_mean_after_removal():
    t = pd.DataFrame({"YEAR": ["2020", "2020", "2020"],
                      "POOLED_NET_NORMAL": [100.0, 2.0, 4.0],
                      "POOLED_GROSS": [0, 0, 0],
                      "POOLED_NET_STRESS": [0, 0, 0],
                      "EURUSD_NET_NORMAL": [0] * 3,
                      "USDJPY_NET_NORMAL": [0] * 3,
                      "GBPUSD_NET_NORMAL": [0] * 3})
    res = L.classify(t)
    assert abs(res["REMOVE_BEST_EVENT_NET_NORMAL"] - 3.0) < 1e-12
