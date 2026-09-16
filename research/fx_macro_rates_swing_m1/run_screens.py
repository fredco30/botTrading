#!/usr/bin/env python3
"""FX_MACRO_RATES_SWING_M1 — Phase B cheap causal gross/net screens.

Families (mission §12) — each mechanism requires rates/macro information to
materially define the signal. Execution: swing_lib.bar_replay on 5m BID with
per-side spread model (EURUSD 0.6 / GBPUSD 1.0 pip) = MODELED_EXECUTION.

Screen promote bar: N>=50, PF>=1.15, expR>=+0.04, both pairs net>=0
(or one pair clearly dominant -> note §19 concentration), multi-year.
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mrlib as MR
import swing_lib as SW

PIP = SW.PIP
OUT = os.path.join(HERE, "cache", "screens.json")
RESULTS = {}


def mask_valid(side, bars, p, sym):
    """Zero out decisions whose ATR stop distance is 0/NaN (degenerate bar
    windows, e.g. data-poor 2010 stretches or the first n ATR bars)."""
    tf = p["tf"]
    a = SW.atr(sym, bars[f"{tf}_high"], bars[f"{tf}_low"],
               bars[f"{tf}_close"], 14)
    bad = ~np.isfinite(a) | (a <= 0)
    if bad.any():
        side = side.copy()
        side[bad] = 0
    return side


def ATRdist(tf, n=14, mult=2.5):
    def stop_fn(bars, i, sym, params):
        return float(SW.atr(sym, bars[f"{tf}_high"], bars[f"{tf}_low"],
                            bars[f"{tf}_close"], n)[i] * mult)
    return stop_fn


def tp_mult(mult=1.0):
    def tp_fn(bars, i, sym, params):
        return float(SW.atr(sym, bars[f"{params['tf']}_high"],
                            bars[f"{params['tf']}_low"],
                            bars[f"{params['tf']}_close"], 14)[i]
                     * params["stop_mult"] * mult)
    return tp_fn


def run(family, mech, signal_fn, params, hold_hours, pairs=SW.DISCOVERY_PAIRS,
        rr=1.0, budget_note=""):
    """One experiment: pooled replay + metrics + stress + ledger entry."""
    MR.register_family(family)
    stop_fn = ATRdist(params["tf"], mult=params["stop_mult"])
    tp_fn = tp_mult(rr)
    trades = SW.run_pooled(signal_fn, params, stop_fn, tp_fn, hold_hours,
                           pairs=pairs)
    stress = SW.run_pooled(signal_fn, params, stop_fn, tp_fn, hold_hours,
                           pairs=pairs, stress=True)
    m = SW.pooled_metrics(trades, f"{family}/{mech}")
    ms = SW.pooled_metrics(stress, f"{family}/{mech}+stress")
    per_pair = {}
    for sym in pairs:
        mt = SW.pooled_metrics([t for t in trades if t["sym"] == sym], sym)
        per_pair[sym] = {k: mt[k] for k in ("N", "mean_pips", "PF",
                                            "expectancy_r", "pos_years")}
    promote = promote_check(trades, per_pair)
    eid = MR.log(family, mech, "PENDING_GATE",
                 {**params, "hold_hours": hold_hours, "rr": rr},
                 N=m.get("N"), mean_pips=m.get("mean_pips"), PF=m.get("PF"),
                 expectancy_r=m.get("expectancy_r"),
                 stress_pips=ms.get("mean_pips"),
                 remove_best_pips=m.get("remove_best"),
                 status="PROMOTE" if promote else "screen_reject",
                 reason=reason_str(m, per_pair))
    RESULTS[eid] = {"metrics": m, "stress_mean": ms.get("mean_pips"),
                    "per_pair": per_pair, "promote": promote,
                    "years": SW.year_table(trades), "note": budget_note}
    print(f"{eid} {family}/{mech} N={m.get('N')} mean={m.get('mean_pips')} "
          f"PF={m.get('PF')} expR={m.get('expectancy_r')} "
          f"stress={ms.get('mean_pips')} -> "
          f"{'PROMOTE' if promote else 'reject'}")
    return eid, m, trades


def promote_check(trades, per_pair):
    m = SW.pooled_metrics(trades, "chk")
    n = m.get("N", 0)
    if n < 50:
        return False
    if not (m.get("PF", 0) >= 1.15 and m.get("expectancy_r", 0) >= 0.04):
        return False
    pairs_pos = [v["mean_pips"] >= 0 for v in per_pair.values()]
    if sum(pairs_pos) < len(pairs_pos) - 1:      # at most one pair negative
        return False
    yr = m.get("yearly_pips", {})
    vals = sorted(yr.values())
    if vals and vals[-1] > 2.5 * max(1, sum(v for v in vals if v > 0)):
        return False                              # one year dominates
    return True


def reason_str(m, per_pair):
    if m.get("N", 0) == 0:
        return "NO_TRADES"
    bits = []
    if m.get("PF", 0) < 1.15:
        bits.append(f"PF<1.15 ({m.get('PF')})")
    if m.get("expectancy_r", 0) < 0.04:
        bits.append(f"expR<0.04 ({m.get('expectancy_r')})")
    if m.get("N", 0) < 50:
        bits.append(f"N<50 ({m.get('N')})")
    if m.get("remove_best", 1) <= 0:
        bits.append("remove_best<=0")
    return "; ".join(bits) or "promoted"


# ---------------------------------------------------------------- families

def sig_rate_impulse(bars, sym, p):
    """A: big 4h rates move + FX underreaction -> follow rates direction."""
    ct = bars[f"{p['tf']}_close_time"]
    z = MR.rz(ct, p["rates_sym"], 4)
    c = bars[f"{p['tf']}_close"]
    a = SW.atr(sym, bars[f"{p['tf']}_high"], bars[f"{p['tf']}_low"], c, 14)
    lh = 4 if p["tf"] == "H1" else 1
    fx = np.zeros(len(c))
    fx[lh:] = np.log(c[lh:] / c[:-lh]) / np.maximum(a[lh:] * PIP[sym], 1e-9)
    side = np.zeros(len(c), dtype=int)
    side[(z >= p["thr"]) & (fx <= p["cap"])] = -1    # USD up -> short EURUSD
    side[(z <= -p["thr"]) & (fx >= -p["cap"])] = 1
    return mask_valid(side, bars, p, sym)


def sig_rate_fx_divergence(bars, sym, p):
    """B: 24h rates vs 24h FX disagreement -> align FX to rates."""
    ct = bars[f"{p['tf']}_close_time"]
    z = MR.rz(ct, p.get("rates_sym", "ZN"), 24)
    c = bars[f"{p['tf']}_close"]
    a = SW.atr(sym, bars[f"{p['tf']}_high"], bars[f"{p['tf']}_low"], c, 14)
    lh = 6 if p["tf"] == "H4" else 1
    fx = np.zeros(len(c))
    fx[lh:] = np.log(c[lh:] / c[:-lh]) / np.maximum(a[lh:] * PIP[sym], 1e-9)
    side = np.zeros(len(c), dtype=int)
    usd_dir = np.where(z > p["thr"], -1, np.where(z < -p["thr"], 1, 0))
    # only when FX has NOT followed (fx*usd_dir >= -cap means flat/opposed)
    take = (usd_dir != 0) & (fx * usd_dir <= p["cap"])
    side[take] = usd_dir[take]
    return mask_valid(side, bars, p, sym)


def sig_curve_regime(bars, sym, p):
    """C: 5d balanced curve change z conditions USD direction."""
    ct = bars[f"{p['tf']}_close_time"]
    cz = MR.curve_z(ct, "ZN", "ZT", 120)
    side = np.zeros(len(ct), dtype=int)
    if p["variant"] == "flat_short_usd":       # long-end outperforms -> USD up
        side[cz >= p["thr"]] = 1
        side[cz <= -p["thr"]] = -1
    else:                                       # front-end outperforms -> USD down
        side[cz >= p["thr"]] = -1
        side[cz <= -p["thr"]] = 1
    return mask_valid(side, bars, p, sym)


def sig_rate_vol_regime(bars, sym, p):
    """E: rates vol regime jump -> next-day FX momentum w/ rates direction."""
    ct = bars[f"{p['tf']}_close_time"]
    z = MR.rz(ct, "ZN", 24)
    g = MR._grid("ZN")
    hs = g["hsum"][1]
    v_short = np.sqrt(pd_roll_var(hs, 5 * 24))
    v_long = np.sqrt(pd_roll_var(hs, 60 * 24))
    ratio = v_short / np.maximum(v_long, 1e-12)
    e = np.searchsorted(g["ct"], ct, side="right") - 1
    r = np.full(len(ct), np.nan)
    ok = e >= 0
    r[ok] = ratio[e[ok]]
    jump = r >= p["ratio_thr"]
    prev = np.zeros(len(ct), dtype=bool)
    prev[1:] = jump[:-1]
    fresh = jump & ~prev                        # first H4 with elevated regime
    side = np.zeros(len(ct), dtype=int)
    side[fresh & (z > 0)] = -1                  # follow last-24h rates dir
    side[fresh & (z < 0)] = 1
    return mask_valid(side, bars, p, sym)


def pd_roll_var(x, n):
    import pandas as pd
    return pd.Series(x).rolling(n).var(ddof=0).to_numpy()


def sig_surprise(bars, sym, p):
    """H: causal NFP/CPI surprise -> USD direction, held multi-hour/day."""
    ct = bars[f"{p['tf']}_close_time"]
    side = np.zeros(len(ct), dtype=int)
    ev = MR.events()
    ev = ev[(ev["family"].isin(p.get("fams", ["NFP", "CPI"])))
            & (ev["surprise_z"].notna())
            & (ev["surprise_z"].abs() >= p["sz"])]
    for _, row in ev.iterrows():
        k = int(np.searchsorted(ct, row["release_ns"] + 300 * MR.NS))
        if k < len(ct):
            side[k] = -1 if row["surprise_z"] > 0 else 1   # hot -> USD up
    return mask_valid(side, bars, p, sym)


def sig_event_fx_follow(bars, sym, p):
    """G: first-hour FX reaction to NFP/CPI -> follow or fade at 4-48h."""
    ct = bars[f"{p['tf']}_close_time"]
    c = bars[f"{p['tf']}_close"]
    side = np.zeros(len(ct), dtype=int)
    ev = MR.events()
    ev = ev[ev["family"].isin(["NFP", "CPI"])]
    for _, row in ev.iterrows():
        k = int(np.searchsorted(ct, row["release_ns"] + 300 * MR.NS))
        if k < len(ct) and k >= 1:
            move = c[k] - c[k - 1]
            side[k] = (1 if move > 0 else -1) * p["follow"]
    return mask_valid(side, bars, p, sym)


def sig_rate_trend_pullback(bars, sym, p):
    """D: 5d rates trend + opposing 3d FX move -> join rates-implied USD."""
    ct = bars[f"{p['tf']}_close_time"]
    z = MR.rz(ct, "ZN", 120)
    c = bars[f"{p['tf']}_close"]
    lh = 3 if p["tf"] == "D1" else 18
    fx = np.zeros(len(c))
    fx[lh:] = c[lh:] / c[:-lh] - 1.0
    side = np.zeros(len(ct), dtype=int)
    side[(z >= p["thr"]) & (fx < 0)] = 1         # rates rally + USD dip -> buy USD
    side[(z <= -p["thr"]) & (fx > 0)] = -1
    return mask_valid(side, bars, p, sym)


def sig_cross_confirm(bars, sym, p):
    """I: ZN AND ZF 4h impulse agree (both >= thr) + FX regime filter."""
    ct = bars[f"{p['tf']}_close_time"]
    z1 = MR.rz(ct, "ZN", 4)
    z2 = MR.rz(ct, "ZF", 4)
    c = bars[f"{p['tf']}_close"]
    a = SW.atr(sym, bars[f"{p['tf']}_high"], bars[f"{p['tf']}_low"], c, 14)
    lh = 4 if p["tf"] == "H1" else 1
    fx = np.zeros(len(c))
    fx[lh:] = np.log(c[lh:] / c[:-lh]) / np.maximum(a[lh:] * PIP[sym], 1e-9)
    side = np.zeros(len(ct), dtype=int)
    up = (z1 >= p["thr"]) & (z2 >= p["thr"])
    dn = (z1 <= -p["thr"]) & (z2 <= -p["thr"])
    if p.get("adx_max"):
        adxv = SW.adx(bars[f"{p['tf']}_high"], bars[f"{p['tf']}_low"], c, 14)
        calm = adxv <= p["adx_max"]
        up &= calm
        dn &= calm
    side[up & (fx <= p["cap"])] = -1
    side[dn & (fx >= -p["cap"])] = 1
    return mask_valid(side, bars, p, sym)


def sig_regime_machine(bars, sym, p):
    """K: rates 20d trend sign gates H4/D1 donchian breakout direction."""
    ct = bars[f"{p['tf']}_close_time"]
    z = MR.rz(ct, "ZN", 120)
    c = bars[f"{p['tf']}_close"]
    n = p["don"]
    hi = SW.donhi(c, n)
    lo = SW.donlo(c, n)
    side = np.zeros(len(ct), dtype=int)
    side[(z >= p["thr"]) & (c > hi)] = 1
    side[(z <= -p["thr"]) & (c < lo)] = -1
    return mask_valid(side, bars, p, sym)


# ------------------------------------------------------------------ main

def main():
    sig_rate_impulse.signal_tf = "H1"
    sig_rate_fx_divergence.signal_tf = "H4"
    sig_curve_regime.signal_tf = "D1"
    sig_rate_vol_regime.signal_tf = "H4"
    sig_surprise.signal_tf = "H1"
    sig_event_fx_follow.signal_tf = "H1"
    sig_rate_trend_pullback.signal_tf = "D1"
    sig_cross_confirm.signal_tf = "H1"
    sig_regime_machine.signal_tf = "H4"

    plan = [
        # A — rate impulse + FX underreaction (H1)
        ("A", "impulse_z1.5_cap0.5_h24", sig_rate_impulse,
         {"tf": "H1", "rates_sym": "ZN", "thr": 1.5, "cap": 0.5,
          "stop_mult": 2.5}, 24),
        ("A", "impulse_z2.0_cap0.5_h24", sig_rate_impulse,
         {"tf": "H1", "rates_sym": "ZN", "thr": 2.0, "cap": 0.5,
          "stop_mult": 2.5}, 24),
        # B — 24h rate/FX divergence (H4)
        ("B", "div_z1.5_h48", sig_rate_fx_divergence,
         {"tf": "H4", "thr": 1.5, "cap": 0.0, "stop_mult": 2.5}, 48),
        ("B", "div_z2.0_h48", sig_rate_fx_divergence,
         {"tf": "H4", "thr": 2.0, "cap": 0.0, "stop_mult": 2.5}, 48),
        # C — curve regime (D1)
        ("C", "curve_flat_usdup_thr1_h5d", sig_curve_regime,
         {"tf": "D1", "thr": 1.0, "variant": "flat_short_usd",
          "stop_mult": 2.0}, 120),
        ("C", "curve_steep_usddn_thr1_h5d", sig_curve_regime,
         {"tf": "D1", "thr": 1.0, "variant": "steep_short_usd",
          "stop_mult": 2.0}, 120),
        # E — rates vol regime jump (H4)
        ("E", "volregime_1.5_h24", sig_rate_vol_regime,
         {"tf": "H4", "ratio_thr": 1.5, "stop_mult": 2.5}, 24),
        # H — causal surprise -> USD (H1)
        ("H", "surprise_z1.0_h24", sig_surprise,
         {"tf": "H1", "sz": 1.0, "stop_mult": 2.5}, 24),
        ("H", "surprise_z1.0_h120", sig_surprise,
         {"tf": "H1", "sz": 1.0, "stop_mult": 2.5}, 120),
        # G — first-hour FX reaction continuation/fade after NFP/CPI (H1)
        ("G", "evfx_follow_h24", sig_event_fx_follow,
         {"tf": "H1", "follow": 1, "stop_mult": 2.5}, 24),
        ("G", "evfx_fade_h24", sig_event_fx_follow,
         {"tf": "H1", "follow": -1, "stop_mult": 2.5}, 24),
        # D — rates trend + FX pullback (D1)
        ("D", "trendpb_thr1.0_h5d", sig_rate_trend_pullback,
         {"tf": "D1", "thr": 1.0, "stop_mult": 2.0}, 120),
        ("D", "trendpb_thr2.0_h5d", sig_rate_trend_pullback,
         {"tf": "D1", "thr": 2.0, "stop_mult": 2.0}, 120),
        # I — ZN+ZF cross-maturity confirm (H1)
        ("I", "xmat_z1.5_cap0.5_h24", sig_cross_confirm,
         {"tf": "H1", "thr": 1.5, "cap": 0.5, "stop_mult": 2.5}, 24),
        ("I", "xmat_z1.5_cap0.5_adx25_h24", sig_cross_confirm,
         {"tf": "H1", "thr": 1.5, "cap": 0.5, "adx_max": 25,
          "stop_mult": 2.5}, 24),
        # K — rates-regime gated breakout (H4)
        ("K", "regime_don20_z1.0_h48", sig_regime_machine,
         {"tf": "H4", "don": 30, "thr": 1.0, "stop_mult": 2.5}, 48),
    ]
    for fam, mech, fn, params, hold in plan:
        run(fam, mech, fn, params, hold)
    json.dump(RESULTS, open(OUT, "w"), indent=1, default=str)
    print(f"\nEXPERIMENTS_USED={MR.experiments_used()} "
          f"FAMILIES_USED={MR.families_used()}")


if __name__ == "__main__":
    main()
