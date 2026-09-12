#!/usr/bin/env python3
"""Discovery-window phenomena screening (P001+).

Every screen is event-based, causal, and evaluated on the DISCOVERY window
only. Outputs phenomena_screen.csv/.json. No V1/V2 access here — a candidate
must be frozen before those windows open.

Gross = instrument-native units scaled to pips (FX) / index points (US).
Anti-edge screens report GROSS expectancy (cost-free) per mission protocol.
"""
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import p000_lib as P  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
H1H4_DIR = os.path.abspath(os.path.join(HERE, "..", "autonomous_h1_h4_2026_09"))
if H1H4_DIR not in sys.path:
    sys.path.insert(0, H1H4_DIR)

FX = ["EURUSD", "GBPUSD", "USDJPY"]
US = ["USA500IDXUSD"]
PIP = P.PIP

DATA = {}


def load(sym):
    if sym not in DATA:
        df = P.load_5m(sym)
        DATA[sym] = df
    return DATA[sym]


def discovery(df):
    lo, hi = P.SPLITS["DISCOVERY"]
    return df[(df.index >= lo) & (df.index < hi)]


def fwd_from_events(df, ts_list, sides, horizons=(1, 6, 12, 24), scale=1.0):
    """Open-to-open forward returns for (ts, side) events on df.

    CAUSAL CONVENTION: the event is marked at the bar whose data (usually its
    close) triggers the condition; that information is only actionable at the
    OPEN of the NEXT bar. Base = open[pos+1]; target = open[pos+1+h].
    (Measuring from open[pos] would include the event bar's own move —
    lookahead.)
    """
    o = df["open"]
    n = len(df)
    rows = []
    for ts, s in zip(ts_list, sides):
        pos = df.index.get_indexer([ts])[0]
        if pos < 0 or pos + 1 >= n:
            continue
        base = float(o.iloc[pos + 1])
        for hh in horizons:
            j = pos + 1 + hh
            if j >= n:
                continue
            rows.append({"entry_ts": ts, "side": s, "h": hh,
                         "ret": s * (float(o.iloc[j]) - base) * scale})
    return pd.DataFrame(rows)


def stat_block(rets):
    st = P.event_stats(rets)
    keep = {k: st.get(k) for k in ("N", "MEAN", "MEDIAN", "WIN_RATE",
                                   "N_LONG", "N_SHORT", "MEAN_LONG",
                                   "MEAN_SHORT", "MEAN_BEST1_REMOVED",
                                   "MEAN_BEST5_REMOVED", "BOOT_CI_LO",
                                   "BOOT_CI_HI", "BOOT_P")}
    return keep


def atr(df, n=96):
    tr = pd.concat([df["high"] - df["low"],
                    (df["high"] - df["close"].shift()).abs(),
                    (df["low"] - df["close"].shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()



def causal_exec_returns(df, ex_side, horizons, pip, split=None):
    """Causal execution returns for a shifted signal array (to_executable_side
    convention: ex_side[i] != 0 means EXECUTION at the open of bar i).

    * pip scaling via the instrument pip size (USDJPY = 0.01, not 0.0001);
    * entry_ts = df.index[i] (the real execution bar), target = df.index[i+h];
    * split=(lo,hi): execution must satisfy lo <= entry_ts < hi AND the
      future_ts = df.index[i+h] must be strictly < hi (no 2019 price may feed
      a Discovery candidate).
    """
    o = df["open"].to_numpy()
    n = len(df)
    rows = []
    for hh in horizons:
        last = n - 1 - hh
        if last < 1:
            continue
        idx = np.where(ex_side[:last + 1] != 0)[0]
        for i in idx:
            if split is not None:
                if not (split[0] <= df.index[i] < split[1]):
                    continue
                if not (df.index[i + hh] < split[1]):
                    continue
            rows.append({"entry_ts": df.index[i],
                         "side": int(np.sign(ex_side[i])),
                         "h": hh,
                         "ret": ex_side[i] * (o[i + hh] - o[i]) / pip})
    return pd.DataFrame(rows)


def naive_split(name):
    """Discovery bounds as naive timestamps (repo M15 data is naive)."""
    lo, hi = P.SPLITS[name]
    return lo.tz_localize(None), hi.tz_localize(None)


# ---------------------------------------------------------------------------
# Screens
# ---------------------------------------------------------------------------
def screen_asia_range_breakout(df, sym, pip):
    """P001: first 5m close outside Asia range [23:00,07:00) in [07:00,16:00)."""
    hm = np.asarray(df.index.hour * 100 + df.index.minute)
    c = df["close"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    day_num = np.asarray(df.index.view("int64") // 86_400_000_000_000)
    sess = (hm >= 700) & (hm < 1600)
    pos = np.where(sess)[0]
    groups = P._consecutive_day_groups(day_num[pos])
    ts_l, sd = [], []
    for g in groups:
        dnum = day_num[pos[g[0]]]
        rng = ((day_num == dnum) & (hm < 700)) | \
              ((day_num == dnum - 1) & (hm >= 2300))
        if rng.sum() < 24:
            continue
        r_hi, r_lo = h[rng].max(), l[rng].min()
        fired = False
        for i in pos[g]:
            if not fired and (c[i] > r_hi or c[i] < r_lo):
                ts_l.append(df.index[i])
                sd.append(1 if c[i] > r_hi else -1)
                fired = True
    rets = fwd_from_events(df, ts_l, sd, (6, 12, 24), 1.0 / pip)
    return {f"h{hh*5}m": stat_block(rets[rets["h"] == hh])
            for hh in (6, 12, 24)}


def screen_false_breakout(df, sym, pip):
    """P003: breakout of Asia range that closes back inside within 60 min ->
    fade (opposite side) forward returns."""
    hm = np.asarray(df.index.hour * 100 + df.index.minute)
    c = df["close"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    day_num = np.asarray(df.index.view("int64") // 86_400_000_000_000)
    sess = (hm >= 700) & (hm < 1600)
    pos = np.where(sess)[0]
    groups = P._consecutive_day_groups(day_num[pos])
    ts_l, sd = [], []
    for g in groups:
        dnum = day_num[pos[g[0]]]
        rng = ((day_num == dnum) & (hm < 700)) | \
              ((day_num == dnum - 1) & (hm >= 2300))
        if rng.sum() < 24:
            continue
        r_hi, r_lo = h[rng].max(), l[rng].min()
        t0 = None
        d0 = 0
        for i in pos[g]:
            if t0 is None:
                if c[i] > r_hi:
                    t0, d0 = i, 1
                elif c[i] < r_lo:
                    t0, d0 = i, -1
            else:
                if (i - t0) * 5 <= 60 and \
                   ((d0 == 1 and c[i] < r_hi) or (d0 == -1 and c[i] > r_lo)):
                    ts_l.append(df.index[i])
                    sd.append(-d0)          # fade the failed breakout
                    break
                if i - t0 > 12:
                    break
    rets = fwd_from_events(df, ts_l, sd, (6, 12, 24), 1.0 / pip)
    return {f"h{hh*5}m": stat_block(rets[rets["h"] == hh])
            for hh in (6, 12, 24)}


def screen_london_first_hour(df, sym, pip):
    """P005: direction of first 30 min after London open -> continuation."""
    hm = np.asarray(df.index.hour * 100 + df.index.minute)
    o = df["open"].to_numpy()
    c = df["close"].to_numpy()
    day_num = np.asarray(df.index.view("int64") // 86_400_000_000_000)
    ts_l, sd = [], []
    for dnum in np.unique(day_num):
        i0 = np.where((day_num == dnum) & (hm == 700))[0]
        i1 = np.where((day_num == dnum) & (hm == 730))[0]
        if len(i0) and len(i1):
            mv = float(c[i1[0]] - o[i0[0]])
            if abs(mv) > 5 * pip:
                ts_l.append(df.index[i1[0]])
                sd.append(1 if mv > 0 else -1)
    rets = fwd_from_events(df, ts_l, sd, (12, 24, 48), 1.0 / pip)
    return {f"h{hh*5}m": stat_block(rets[rets["h"] == hh])
            for hh in (12, 24, 48)}


def screen_round_numbers(df, sym, pip):
    """P007: 5m close crossing a round multiple of 100 pips -> continuation."""
    c = df["close"].to_numpy()
    step = 100 * pip          # 100-pip round levels (1.00 for JPY pairs)
    prev = c - (c % step)
    # robust vectorized: level index of close now vs previous close
    li = np.floor(c / step).astype(np.int64)
    li_prev = np.concatenate(([li[0]], li[:-1]))
    up = li > li_prev
    dn = li < li_prev
    hm = np.asarray(df.index.hour * 100 + df.index.minute)
    valid = (hm >= 700) & (hm < 1700)
    ts_l = list(df.index[up & valid]) + list(df.index[dn & valid])
    sd = [1] * int((up & valid).sum()) + [-1] * int((dn & valid).sum())
    rets = fwd_from_events(df, ts_l, sd, (3, 6, 12), 1.0 / pip)
    return {f"h{hh*5}m": stat_block(rets[rets["h"] == hh])
            for hh in (3, 6, 12)}


def screen_vol_shock(df, sym, pip):
    """P008/P009: |ret| > 3 ATR -> continuation + forward vol response."""
    with np.errstate(invalid="ignore", divide="ignore"):
        a = atr(df).to_numpy()
        r = df["close"].to_numpy() - df["open"].to_numpy()
        z = np.where(a > 0, r / a, 0.0)
    z = np.nan_to_num(z, nan=0.0, posinf=0.0, neginf=0.0)
    m = np.abs(z) > 3.0
    m[:100] = False
    hm = np.asarray(df.index.hour * 100 + df.index.minute)
    m &= (hm >= 700) & (hm < 1900)
    ts_l = list(df.index[m])
    sd = [int(np.sign(x)) for x in z[m]]
    rets = fwd_from_events(df, ts_l, sd, (1, 6, 12), 1.0 / pip)
    out = {f"h{hh*5}m": stat_block(rets[rets["h"] == hh]) for hh in (1, 6, 12)}
    # forward realized vol (|sum of next 12 5m rets| vs baseline) - second order
    rr = df["close"].diff().abs().to_numpy()
    fwd_vol = pd.Series(rr).rolling(12).sum().shift(-12).to_numpy()
    base = np.nanmedian(fwd_vol)
    ev_vol = np.nanmedian(fwd_vol[m])
    out["SECOND_ORDER"] = {"FORWARD_VOL_EVENT": float(ev_vol / pip),
                           "FORWARD_VOL_BASELINE": float(base / pip),
                           "RATIO": float(ev_vol / base) if base else None}
    return out


def screen_runs(df, sym, pip):
    """P021: 4 consecutive same-sign 5m closes -> continuation."""
    r = np.sign(df["close"].diff().to_numpy())
    same = (r == np.roll(r, 1)) & (r == np.roll(r, 2)) & (r == np.roll(r, 3)) & (r != 0)
    prev_same = np.concatenate(([False], same[:-1]))
    ev = same & ~prev_same
    hm = np.asarray(df.index.hour * 100 + df.index.minute)
    ev &= (hm >= 700) & (hm < 1900)
    ts_l = list(df.index[ev])
    sd = [int(x) for x in r[ev]]
    rets = fwd_from_events(df, ts_l, sd, (1, 3, 6), 1.0 / pip)
    return {f"h{hh*5}m": stat_block(rets[rets["h"] == hh]) for hh in (1, 3, 6)}


def screen_asia_fade(df, sym, pip):
    """P014: directional Asia session -> fade at London open 07:00."""
    hm = np.asarray(df.index.hour * 100 + df.index.minute)
    o = df["open"].to_numpy()
    c = df["close"].to_numpy()
    day_num = np.asarray(df.index.view("int64") // 86_400_000_000_000)
    ts_l, sd = [], []
    for dnum in np.unique(day_num):
        i7 = np.where((day_num == dnum) & (hm == 700))[0]
        if not len(i7):
            continue
        rng = ((day_num == dnum) & (hm < 700)) | \
              ((day_num == dnum - 1) & (hm >= 2300))
        if rng.sum() < 24:
            continue
        mv = float(c[i7[0]] - o[rng][0])
        if abs(mv) > 10 * pip:
            ts_l.append(df.index[i7[0]])
            sd.append(-1 if mv > 0 else 1)
    rets = fwd_from_events(df, ts_l, sd, (12, 24, 48), 1.0 / pip)
    return {f"h{hh*5}m": stat_block(rets[rets["h"] == hh])
            for hh in (12, 24, 48)}


def screen_weekend_gap(df, sym, pip):
    """P011: Sunday reopen gap > 15 pips -> partial fade forward."""
    o = df["open"].to_numpy()
    c = df["close"].to_numpy()
    hm = np.asarray(df.index.hour * 100 + df.index.minute)
    dow = np.asarray(df.index.dayofweek)
    ts_l, sd = [], []
    sun_first = np.where((dow == 6) & (hm >= 2100))[0]
    if len(sun_first):
        fri_close = pd.Series(c).shift(1)
        for i in sun_first:
            # find previous Friday close (last bar with dow==4 before i)
            j = i - 1
            while j > 0 and dow[j] != 4:
                j -= 1
            gap = float(o[i] - c[j])
            if abs(gap) > 15 * pip:
                ts_l.append(df.index[i])
                sd.append(-1 if gap > 0 else 1)
    rets = fwd_from_events(df, ts_l, sd, (12, 24, 48), 1.0 / pip)
    if rets.empty:
        return {"NOTE": "no Sunday session in Dukascopy FX feed (opens Mon 00:00 UTC)",
                "N": 0}
    return {f"h{hh*5}m": stat_block(rets[rets["h"] == hh])
            for hh in (12, 24, 48)}


def screen_vwap_reversion_us(df, sym, pip):
    """P016: extreme deviation from RTH VWAP -> reversion toward VWAP."""
    et = df.index.tz_convert(P.ET)
    et_hm = np.asarray(et.hour * 100 + et.minute)
    vwap = P.vwap_rth(df).to_numpy()
    a = atr(df).to_numpy()
    dev = df["close"].to_numpy() - vwap
    z = np.where(a > 0, dev / a, 0.0)
    m = np.abs(z) > 1.5
    m[:100] = False
    m &= (et_hm >= 1000) & (et_hm <= 1500)
    prev = np.concatenate(([False], m[:-1]))
    m &= ~prev  # first bar entering the zone only
    ts_l = list(df.index[m])
    sd = [-int(np.sign(x)) for x in z[m]]
    rets = fwd_from_events(df, ts_l, sd, (6, 12, 24), 1.0)
    return {f"h{hh*5}m": stat_block(rets[rets["h"] == hh])
            for hh in (6, 12, 24)}


def screen_gap_fill_us(df, sym, pip):
    """P018: RTH open gap vs prior RTH close -> trade toward the fill."""
    et = df.index.tz_convert(P.ET)
    et_hm = np.asarray(et.hour * 100 + et.minute)
    o = df["open"].to_numpy()
    c = df["close"].to_numpy()
    a = atr(df).to_numpy()
    groups = P._consecutive_day_groups(np.asarray(et.date))
    ts_l, sd = [], []
    for gi, g in enumerate(groups):
        rth_bars = [i for i in g if 930 <= et_hm[i] < 1600]
        if not rth_bars:
            continue
        i0 = rth_bars[0]
        if gi == 0:
            continue
        prev_rth = [i for i in groups[gi - 1] if 930 <= et_hm[i] < 1600]
        if not prev_rth:
            continue
        prev_close = c[prev_rth[-1]]
        gap = float(o[i0] - prev_close)
        if not np.isnan(a[i0]) and abs(gap) > 0.25 * a[i0] and abs(gap) > 0.1:
            ts_l.append(df.index[i0])
            sd.append(-1 if gap > 0 else 1)
    rets = fwd_from_events(df, ts_l, sd, (12, 24, 48), 1.0)
    return {f"h{hh*5}m": stat_block(rets[rets["h"] == hh])
            for hh in (12, 24, 48)}


# ---------------------------------------------------------------------------
# M15 anti-edge screens (repo data, MT4 server time — no session logic used)
# ---------------------------------------------------------------------------
def load_m15(sym):
    from research_engine import load_bars_csv
    import h1h4_lib as H  # repo lib (previous mission conventions)
    # EURUSD15.csv in the worktree is a 2020+ cut; the full 1971-2026 export
    # lives at git snapshot 3cd12c3 (extracted to data_raw/, gitignored).
    local = os.path.join(ROOT, "data_raw", f"{sym}15_full.csv")
    path = local if os.path.exists(local) else os.path.join(ROOT, f"{sym}15.csv")
    bars = H.filter_window(load_bars_csv(path))
    return H.bars_to_frame(bars)


def screen_anti_edge_ma_cross(sym):
    """P028: EMA5/EMA20 cross M15 -> GROSS forward expectancy (anti-edge)."""
    import h1h4_lib as H
    df = load_m15(sym)
    ef = H.ema(df["close"], 5)
    es = H.ema(df["close"], 20)
    up = (ef > es) & (ef.shift() <= es.shift())
    dn = (ef < es) & (ef.shift() >= es.shift())
    side = np.where(up, 1, np.where(dn, -1, 0)).astype(np.int8)
    ex = H.to_executable_side(side)  # causal: execute at next bar open
    rets = causal_exec_returns(df, ex, (4, 8, 16), P.PIP[sym],
                               split=naive_split("DISCOVERY"))
    return {f"h{hh*15}m": stat_block(rets[rets["h"] == hh]) for hh in (4, 8, 16)}


def screen_anti_edge_donchian(sym):
    """P029: Donchian 48 M15 cross -> GROSS forward expectancy (anti-edge)."""
    import h1h4_lib as H
    df = load_m15(sym)
    side = H.f2_donchian(df, 48)
    ex = H.to_executable_side(side)
    rets = causal_exec_returns(df, ex, (8, 16, 32), P.PIP[sym],
                               split=naive_split("DISCOVERY"))
    return {f"h{hh*15}m": stat_block(rets[rets["h"] == hh]) for hh in (8, 16, 32)}


# ---------------------------------------------------------------------------
def main():
    results = {}

    def run(name, sym, fn, pip):
        df = discovery(load(sym))
        res = fn(df, sym, pip)
        results[f"{name}_{sym}"] = res
        n = res.get("h30m", res.get("h60m", {})).get("N", "?")
        print(f"  {name} {sym}: N={n}")

    for sym in FX:
        pip = PIP[sym]
        run("P001_ASIA_BREAKOUT", sym, screen_asia_range_breakout, pip)
        run("P003_FALSE_BREAKOUT", sym, screen_false_breakout, pip)
        run("P005_LONDON_FIRST_HOUR", sym, screen_london_first_hour, pip)
        run("P007_ROUND_NUMBERS", sym, screen_round_numbers, pip)
        run("P008_VOL_SHOCK", sym, screen_vol_shock, pip)
        run("P021_RUNS", sym, screen_runs, pip)
        run("P014_ASIA_FADE", sym, screen_asia_fade, pip)
        run("P011_WEEKEND_GAP", sym, screen_weekend_gap, pip)

    for sym in US:
        run("P016_VWAP_REVERSION", sym, screen_vwap_reversion_us, 1.0)
        run("P018_GAP_FILL", sym, screen_gap_fill_us, 1.0)

    for sym in ["EURUSD", "GBPUSD", "USDJPY"]:
        results[f"P028_ANTI_MA_CROSS_{sym}"] = screen_anti_edge_ma_cross(sym)
        results[f"P029_ANTI_DONCHIAN_{sym}"] = screen_anti_edge_donchian(sym)
        print(f"  P028/P029 {sym}")

    # second-order descriptive (P034/P035)
    for sym in FX:
        df = discovery(load(sym))
        r5 = df["close"].diff().abs()
        r1h = r5.rolling(12).sum()
        dow = df.index.dayofweek
        by_dow = {int(d): round(float(r1h[dow == d].mean()) / PIP[sym], 2)
                  for d in range(5)}
        results[f"P035_VOL_BY_DOW_{sym}"] = by_dow

    with open(os.path.join(HERE, "phenomena_screen.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1, default=str)

    # CSV summary at the primary horizon
    rows = []
    for key, res in results.items():
        if not isinstance(res, dict):
            continue
        best = None
        for k, v in res.items():
            if isinstance(v, dict) and "MEAN" in v:
                if best is None:
                    best = v | {"HORIZON": k}
        if best:
            rows.append({"SCREEN": key, **{kk: best.get(kk) for kk in
                         ("HORIZON", "N", "MEAN", "MEDIAN", "WIN_RATE",
                          "N_LONG", "N_SHORT", "BOOT_P")}})
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "phenomena_screen.csv"), index=False)
    print("WROTE phenomena_screen.json/.csv")


if __name__ == "__main__":
    main()
