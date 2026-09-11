#!/usr/bin/env python3
"""PHASE 2 — causal phenomena beyond plain OHLC patterns (mission H).

Ten families, DISCOVERY-window only, via the central validation gate
(gate.window). No V1/V2 access before an explicit, logged authorization.

Causality conventions (inherited from p000_lib / repo engine):
  * a signal using information finalized at the close of bar i is executable
    at the open of bar i+1 (first price at/after the decision);
  * follower/forward returns are measured from the follower's open at/after
    the leader's information is complete;
  * no forward window crosses the Discovery end;
  * rates/data availability uses a conservative +1 day lag (announcement /
    publication mechanics) — documented per family.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta

import numpy as np
import pandas as pd

import gate
import p000_lib as P

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OFFICIAL = os.path.join(ROOT, "data_raw", "official")

DISC = gate.window("DISCOVERY")          # (2010-01-01, 2019-01-01) UTC

PIP = P.PIP

_CACHE = {}


def load(sym):
    if sym not in _CACHE:
        df = P.load_5m(sym)
        _CACHE[sym] = df
    return _CACHE[sym]


def discovery(df):
    return df[(df.index >= DISC[0]) & (df.index < DISC[1])]


def ev_stats(rets_df, scale=1.0):
    st = P.event_stats(rets_df, unit_scale=scale)
    keep = {k: st.get(k) for k in ("N", "MEAN", "MEDIAN", "WIN_RATE",
                                   "N_LONG", "N_SHORT", "MEAN_BEST1_REMOVED",
                                   "MEAN_BEST5_REMOVED", "BOOT_CI_LO",
                                   "BOOT_CI_HI", "BOOT_P")}
    return keep


def follower_returns(df_f, leader_ts, leader_side, horizons, pip):
    """Follower forward returns executable at the first follower open at/after
    the leader's information moment (bar after the leader's closing bar)."""
    o = df_f["open"]
    pos = df_f.index.get_indexer(leader_ts)
    rows = []
    for i0, s in zip(pos, leader_side):
        if i0 < 0 or i0 + 1 >= len(df_f):
            continue
        base = float(o.iloc[i0 + 1])
        for hh in horizons:
            j = i0 + 1 + hh
            if j >= len(df_f):
                continue
            rows.append({"entry_ts": df_f.index[i0 + 1], "side": s, "h": hh,
                         "ret": s * (float(o.iloc[j]) - base) / pip})
    return pd.DataFrame(rows)


def rolling_z(x, win=8640):
    mu = pd.Series(x).rolling(win, min_periods=2000).mean()
    sd = pd.Series(x).rolling(win, min_periods=2000).std()
    return (pd.Series(x) - mu) / sd


# ---------------------------------------------------------------------------
# P010 — cross-pair lead/lag + triangular residual
# ---------------------------------------------------------------------------
def p010_cross_pair(tri, horizons=(1, 3, 6, 12), z_gate=2.0):
    """tri = (base, quote, cross) with base/quote/cross symbols s.t.
    base/quote = cross * arithmetic identity in logs:
    ln(base) - ln(quote) = ln(cross). e.g. (EURUSD, GBPUSD, EURGBP),
    (EURUSD, USDJPY, EURJPY), (GBPUSD, USDJPY, GBPJPY)."""
    a, b, c = (discovery(load(s)) for s in tri)
    common = a.index.intersection(b.index).intersection(c.index)
    a, b, c = a.loc[common], b.loc[common], c.loc[common]
    out = {}
    # leader abnormal 30-min move -> follower catch-up
    pip_c = 0.01 if "JPY" in tri[2] else 0.0001
    leaders = {tri[0]: (a, PIP[tri[0]]), tri[1]: (b, PIP[tri[1]]),
               tri[2]: (c, pip_c)}
    for name, (df_l, pip_l) in leaders.items():
        r30 = (df_l["close"] - df_l["open"].shift(6)) / pip_l   # 30-min move
        z = rolling_z(r30.to_numpy())
        m = (np.abs(z) > z_gate).to_numpy() if isinstance(z, pd.Series) else np.abs(z) > z_gate
        m[:9000] = False
        m &= (m != np.roll(m, 1))          # first bar entering the zone only
        ts_l = df_l.index[m]
        side_l = [int(np.sign(z[i])) for i in np.where(m)[0]]
        for fname, (df_f, pip_f) in leaders.items():
            if fname == name:
                continue
            rets = follower_returns(df_f, ts_l, side_l, horizons, pip_f)
            out[f"LEADER_{name}_FOLLOWER_{fname}"] = {
                f"h{hh*5}m": ev_stats(rets[rets["h"] == hh]) for hh in horizons}
    # triangular residual (log identity), SECOND-ORDER (no tradable claim)
    lr = (np.log(a["close"]) - np.log(b["close"]) - np.log(c["close"]))
    zr = (lr - lr.rolling(8640, min_periods=2000).mean()) / \
        lr.rolling(8640, min_periods=2000).std()
    resid = zr.to_numpy()
    m = np.abs(resid) > 2.0
    m[:9000] = False
    m &= (m != np.roll(m, 1))
    rows = []
    for i in np.where(m)[0]:
        for hh in horizons:
            j = i + hh
            if j >= len(lr):
                continue
            d = resid[j] - resid[i]          # residual change in sigma units
            rows.append({"entry_ts": lr.index[i], "side": -int(np.sign(resid[i])),
                         "h": hh, "ret": -int(np.sign(resid[i])) * d})
    rd = pd.DataFrame(rows)
    out["TRIANGULAR_RESIDUAL_SIGMA"] = {
        f"h{hh*5}m": ev_stats(rd[rd["h"] == hh]) for hh in horizons}
    out["NOTE"] = ("residual measured in sigma units; NOT an arbitrage claim "
                   "(no synchronous quotes / no costs model)")
    return out


# ---------------------------------------------------------------------------
# P026 — US 2Y yield change -> USDJPY next day
# ---------------------------------------------------------------------------
def _daily_close(sym):
    df = discovery(load(sym))
    return df["close"].resample("1D").last().dropna()


def _dgs2():
    d = pd.read_csv(os.path.join(OFFICIAL, "DGS2.csv"))
    d.index = pd.to_datetime(d["observation_date"])
    s = pd.to_numeric(d["DGS2"], errors="coerce").dropna()
    s.index = s.index.tz_localize("UTC")
    return s[s.index < DISC[1]]


def p026_us2y(shock_bp=3.0):
    """DGS2(t) is published after 16:00 ET on day t -> usable from day t+1.
    Signal: delta2y(t); reaction: USDJPY close(t+1) -> close(t+1+H)."""
    s = _dgs2()
    d2 = s.diff().dropna()
    px = _daily_close("USDJPY")
    rows = []
    for t, dv in d2.items():
        # decision usable at the open of the NEXT trading day after t;
        # skip if the FX series does not actually cover that day (e.g. rate
        # history predates the FX data)
        nxt = px.index[px.index > t + pd.Timedelta(days=1)]
        if not len(nxt) or (nxt[0] - t).days > 7:
            continue
        t_exec = nxt[0]
        for H, hh in ((1, 1), (5, 5)):
            tgt = px.index[px.index >= t_exec + pd.Timedelta(days=H)]
            if not len(tgt):
                continue
            rows.append({"entry_ts": t_exec, "side": int(np.sign(dv)),
                         "h": hh,
                         "ret": int(np.sign(dv)) * (px[tgt[0]] - px[t_exec])})
    rd = pd.DataFrame(rows)
    out = {}
    for hh in (1, 5):
        sub = rd[rd["h"] == hh]
        out[f"ALL_h{hh}d"] = ev_stats(sub, 1.0)          # % not pips: scale via /pip below
    # scale to JPY pips for readability
    for hh in (1, 5):
        sub = rd[rd["h"] == hh].copy()
        sub["ret"] = sub["ret"] / 0.01
        out[f"PIPS_h{hh}d"] = ev_stats(sub)
        shk = sub[sub["ret"].abs() > 0].copy()
        dmap = {t: dv for t, dv in d2.items()}
        sub["d2"] = [dmap.get(t - pd.Timedelta(days=1), dmap.get(t - pd.Timedelta(days=2), np.nan))
                     for t in sub["entry_ts"]]
        strong = sub[sub["d2"].abs() >= shock_bp / 100.0]   # DGS2 is in %
        out[f"SHOCK{shock_bp:.0f}bp_h{hh}d"] = ev_stats(strong)
    return out


# ---------------------------------------------------------------------------
# P025 — carry / rate differential (official rates, +1 day availability)
# ---------------------------------------------------------------------------
def _fred_series(fname, col):
    d = pd.read_csv(os.path.join(OFFICIAL, fname))
    d.index = pd.to_datetime(d["observation_date"])
    s = pd.to_numeric(d[col], errors="coerce").dropna()
    s.index = s.index.tz_localize("UTC")
    return s[s.index < DISC[1]]


BOJ_STEPS = [  # official BoJ policy decisions (announcement dates); ASSUMPTION: proxy = complementary/deposit policy rate
    ("2010-10-05", 0.10), ("2016-01-29", -0.10), ("2024-03-19", 0.10),
    ("2024-07-31", 0.25), ("2025-01-24", 0.50),
]


def _boj():
    idx = pd.date_range("2010-01-01", DISC[1].date() - timedelta(days=1),
                        freq="D")
    s = pd.Series(0.10, index=idx.tz_localize("UTC"))
    for d, v in BOJ_STEPS:
        ts = pd.Timestamp(d, tz="UTC") + pd.Timedelta(days=1)  # +1 day availability
        s[s.index >= ts] = v
    return s


def p025_carry(sym_pair, diff_series, horizons=(1, 5, 20)):
    """diff_series: policy-rate differential (high-yield currency = base).
    Signal variants (<=3 configs): sign(diff); sign(delta20(diff));
    carry+momentum alignment. Reaction: FX close-to-close forward returns."""
    px = _daily_close(sym_pair)
    diff = diff_series.reindex(px.index).ffill()
    if diff.index.tz is None:
        diff.index = diff.index.tz_localize("UTC")
    diff = diff.shift(1)                      # +1 day availability lag
    rets = px.diff()
    mom20 = px.diff(20)
    rows = []
    for t in px.index[21:]:
        dv = diff.get(t, np.nan)
        mom = mom20.get(t, np.nan)
        if np.isnan(dv) or np.isnan(mom):
            continue
        for H in horizons:
            j = px.index.get_indexer([t])[0] + H
            if j >= len(px):
                continue
            dv_prev = diff.get(px.index[max(0, j - H - 21)], np.nan)
            fwd = float(px.iloc[j] - px.iloc[j - H])
            rows.append({"entry_ts": t, "h": H, "side": int(np.sign(dv)),
                         "s_level": int(np.sign(dv)) * fwd,
                         "s_delta": (int(np.sign(dv - dv_prev)) * fwd
                                     if not np.isnan(dv_prev) else 0.0),
                         "s_carrymom": (int(np.sign(dv)) if np.sign(dv) ==
                                        np.sign(float(mom)) else
                                        -int(np.sign(dv))) * fwd})
    rd = pd.DataFrame(rows)
    pip = PIP[sym_pair]
    out = {}
    for key in ("s_level", "s_delta", "s_carrymom"):
        for H in horizons:
            sub = rd[rd["h"] == H].copy()
            sub["ret"] = sub[key] / pip
            out[f"{key}_h{H}d"] = ev_stats(sub)
    return out


# ---------------------------------------------------------------------------
# P027 — gold shock <-> USDJPY (price discovery direction)
# ---------------------------------------------------------------------------
def p027_gold_jpy(z_gate=2.0, horizons=(1, 3, 6, 12)):
    g = discovery(load("XAUUSD"))
    j = discovery(load("USDJPY"))
    common = g.index.intersection(j.index)
    g, j = g.loc[common], j.loc[common]
    out = {}
    # gold shock -> JPY (co-movement / risk-off test)
    r30 = (g["close"] - g["open"].shift(6))          # USD move of gold
    z = rolling_z(r30.to_numpy())
    m = np.abs(z) > z_gate
    m[:9000] = False
    m &= (m != np.roll(m, 1))
    ts = g.index[m]
    sd = [int(np.sign(z[i])) for i in np.where(m)[0]]
    rets = follower_returns(j, ts, sd, horizons, PIP["USDJPY"])
    out["GOLD_SHOCK_TO_USDJPY"] = {f"h{hh*5}m": ev_stats(rets[rets["h"] == hh])
                                   for hh in horizons}
    # JPY shock -> gold (reverse price discovery)
    r30j = (j["close"] - j["open"].shift(6)) / PIP["USDJPY"]
    zj = rolling_z(r30j.to_numpy())
    mj = np.abs(zj) > z_gate
    mj[:9000] = False
    mj &= (mj != np.roll(mj, 1))
    tsj = j.index[mj]
    sdj = [int(np.sign(zj[i])) for i in np.where(mj)[0]]
    retsj = follower_returns(g, tsj, sdj, horizons, 1.0)
    out["USDJPY_SHOCK_TO_GOLD"] = {f"h{hh*5}m": ev_stats(retsj[retsj["h"] == hh])
                                   for hh in horizons}
    return out


# ---------------------------------------------------------------------------
# P020 — London 16:00 fix (pre-drift / post-reversal / month-end amplification)
# ---------------------------------------------------------------------------
def p020_london_fix(sym="EURUSD"):
    df = discovery(load(sym))
    lon = df.index.tz_convert("Europe/London")
    hm = np.asarray(lon.hour * 100 + lon.minute)
    day = np.asarray(lon.date)
    c = df["close"].to_numpy()
    month_last2 = _month_last2_days(set(day))
    rows = []
    for d in np.unique(day):
        m = day == d
        i1300 = np.where(m & (hm == 1300))[0]
        i1600 = np.where(m & (hm == 1600))[0]
        i1800 = np.where(m & (hm == 1800))[0]
        if not (len(i1300) and len(i1600) and len(i1800)):
            continue
        pre = float(c[i1600[0]] - c[i1300[0]])
        post = float(c[i1800[0]] - c[i1600[0]])
        rows.append({"day": d, "pre": pre, "post_signed": post,
                     "post_fade": (-np.sign(pre) if pre != 0 else 0) * post,
                     "month_end": d in month_last2})
    rd = pd.DataFrame(rows)
    rd["pip"] = rd["pre"] / PIP[sym]
    rd["post_fade_pip"] = rd["post_fade"] / PIP[sym]
    rd["post_signed_pip"] = rd["post_signed"] / PIP[sym]
    out = {
        "PRE_FIX_DRIFT_ONLY": {"N": int(len(rd)),
                               "MEAN_PIPS": float(rd["pip"].mean())},
        "POST_FADE_ALL": {"N": int(len(rd)),
                          "MEAN_PIPS": float(rd["post_fade_pip"].mean()),
                          "WR": float((rd["post_fade_pip"] > 0).mean())},
    }
    me = rd[rd["month_end"]]
    no = rd[~rd["month_end"]]
    out["POST_FADE_MONTH_END"] = {"N": int(len(me)),
                                  "MEAN_PIPS": float(me["post_fade_pip"].mean()),
                                  "WR": float((me["post_fade_pip"] > 0).mean())}
    out["POST_FADE_NORMAL"] = {"N": int(len(no)),
                               "MEAN_PIPS": float(no["post_fade_pip"].mean()),
                               "WR": float((no["post_fade_pip"] > 0).mean())}
    out["PRE_ME_vs_NORMAL_pips"] = {
        "MONTH_END": float(me["pip"].mean()), "NORMAL": float(no["pip"].mean()),
        "N_ME": int(len(me)), "N_NORMAL": int(len(no))}
    return out


def _month_last2_days(all_days):
    """Month-end = last TWO trading days of each calendar month (defined a
    priori, no calendar mining)."""
    s = pd.Series(sorted(all_days))
    out = set()
    for _, g in s.groupby([pd.to_datetime(s).dt.year, pd.to_datetime(s).dt.month]):
        for d in list(g)[-2:]:
            out.add(d)
    return out


# ---------------------------------------------------------------------------
# P013 — month-end rebalancing (daily effects, definition a priori)
# ---------------------------------------------------------------------------
def p013_month_end(sym="EURUSD"):
    df = discovery(load(sym))
    px = df["close"].resample("1D").last().dropna()
    day = np.asarray(px.index.tz_convert("UTC").date)
    last2 = _month_last2_days(set(day))
    r1 = px.diff()
    rows = []
    for i in range(1, len(px)):
        d = day[i]
        in_me = d in last2
        for H in (1, 3):
            if i + H < len(px):
                fwd = float(px.iloc[i + H] - px.iloc[i]) / PIP[sym]
                rows.append({"entry_ts": px.index[i], "h": H, "ret": fwd,
                             "me": in_me})
    rd = pd.DataFrame(rows)
    out = {}
    for H in (1, 3):
        sub = rd[rd["h"] == H]
        me = sub[sub["me"]]
        no = sub[~sub["me"]]
        out[f"h{H}d"] = {
            "MONTH_END": {"N": int(len(me)), "MEAN_PIPS": float(me["ret"].mean())},
            "NORMAL": {"N": int(len(no)), "MEAN_PIPS": float(no["ret"].mean())},
        }
    return out


# ---------------------------------------------------------------------------
# P032 — post-FOMC (exact release timestamps from the Fed pages)
# ---------------------------------------------------------------------------
def p032_fomc(syms=("EURUSD", "USDJPY", "GBPUSD")):
    path = os.path.join(OFFICIAL, "fomc_decisions.json")
    evs = json.load(open(path))
    out = {}
    for sym in syms:
        df = discovery(load(sym))
        o = df["open"]
        c = df["close"]
        et = df.index.tz_convert("America/New_York")
        rows = []
        for e in evs:
            if not e.get("release_time"):
                continue
            h, m = e["release_time"].split(":")
            tz = e.get("tz") or "EST"
            rel = pd.Timestamp(f"{e['date']} {h}:{m}", tz="EST").tz_convert("UTC")
            if not (DISC[0] <= rel < DISC[1]):
                continue
            pos = df.index.searchsorted(rel)
            if pos == 0 or pos + 24 >= len(df):
                continue
            def px(k):
                return float(c.iloc[k])
            p0 = px(pos)
            i30 = min(pos + 6, len(df) - 1)
            i120 = min(pos + 24, len(df) - 1)
            rows.append({"release": rel,
                         "r0_30m": (px(i30) - p0),
                         "r30_120m": (px(i120) - px(i30)),
                         "r_nextday": float(c.iloc[min(pos + 288, len(df) - 1)] - p0)})
        rd = pd.DataFrame(rows)
        pip = PIP[sym]
        out[sym] = {
            "N": int(len(rd)),
            "R0_30M_PIPS": float(rd["r0_30m"].mean() / pip) if len(rd) else None,
            "R30_120M_PIPS": float(rd["r30_120m"].mean() / pip) if len(rd) else None,
            "R_NEXTDAY_PIPS": float(rd["r_nextday"].mean() / pip) if len(rd) else None,
            "CONTINUATION_s0_30_to_30_120": float(
                (np.sign(rd["r0_30m"]) * rd["r30_120m"]).mean() / pip) if len(rd) else None,
            "ABS_R0_30M_PIPS": float(rd["r0_30m"].abs().mean() / pip) if len(rd) else None,
        }
    out["_NOTE"] = ("release times parsed from official Fed press-release pages "
                    "('For release at ...'); no surprise data; event-time study only")
    return out


# ---------------------------------------------------------------------------
# P004 — previous day high/low (first touch / break / failed break / reclaim)
# ---------------------------------------------------------------------------
def p004_pdh_pdl(sym="EURUSD", back_inside_bars=6):
    df = discovery(load(sym))
    day_num = np.asarray(df.index.view("int64") // 86_400_000_000_000)
    uniq, first = np.unique(day_num, return_index=True)
    order = np.argsort(first)
    uniq, first = uniq[order], first[order]
    day_slice = {int(d): (int(f), int(f + np.sum(day_num == d)))
                 for d, f in zip(uniq, first)}
    c = df["close"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    hm = np.asarray(df.index.hour * 100 + df.index.minute)
    sess = (hm >= 700) & (hm < 2000)
    events = []
    for d, (i_s, i_e) in day_slice.items():
        if (d - 1) not in day_slice:
            continue
        j_s, j_e = day_slice[d - 1]
        prev_slice = slice(j_s, j_e)
        if j_e - j_s < 24:
            continue
        pdh = float(h[prev_slice].max())
        pdl = float(l[prev_slice].min())
        fired = set()
        above = below = False
        above_bar = below_bar = -10**9
        failed_up = failed_dn = False
        for i in range(i_s, i_e):
            if not sess[i]:
                continue
            if "touch_PDH" not in fired and h[i] >= pdh:
                fired.add("touch_PDH"); events.append((df.index[i], -1, "touch_PDH"))
            if "touch_PDL" not in fired and l[i] <= pdl:
                fired.add("touch_PDL"); events.append((df.index[i], 1, "touch_PDL"))
            if not above and c[i] > pdh:
                above = True; above_bar = i
                if "break_PDH" not in fired:
                    fired.add("break_PDH"); events.append((df.index[i], 1, "break_PDH"))
            elif above and c[i] < pdh and i > above_bar:
                if not failed_up and "break_PDH" in fired and                         "failed_PDH" not in fired and i - above_bar <= back_inside_bars:
                    failed_up = True
                    fired.add("failed_PDH"); events.append((df.index[i], -1, "failed_PDH"))
                elif failed_up and "reclaim_PDH" not in fired:
                    fired.add("reclaim_PDH"); events.append((df.index[i], 1, "reclaim_PDH"))
                above = False
            if not below and c[i] < pdl:
                below = True; below_bar = i
                if "break_PDL" not in fired:
                    fired.add("break_PDL"); events.append((df.index[i], -1, "break_PDL"))
            elif below and c[i] > pdl and i > below_bar:
                if not failed_dn and "break_PDL" in fired and                         "failed_PDL" not in fired and i - below_bar <= back_inside_bars:
                    failed_dn = True
                    fired.add("failed_PDL"); events.append((df.index[i], 1, "failed_PDL"))
                elif failed_dn and "reclaim_PDL" not in fired:
                    fired.add("reclaim_PDL"); events.append((df.index[i], -1, "reclaim_PDL"))
                below = False
    o = df["open"].to_numpy()
    res = {}
    by_kind = {}
    for ts, side, kind in events:
        by_kind.setdefault(kind, []).append((ts, side))
    for kind, evs in by_kind.items():
        rows = []
        for ts, s in evs:
            i0 = df.index.get_indexer([ts])[0]
            for hh in (3, 12):
                j = i0 + 1 + hh
                if j < len(df) and df.index[j] < DISC[1]:
                    rows.append({"entry_ts": ts, "side": s, "h": hh,
                                 "ret": s * (o[j] - o[i0 + 1]) / PIP[sym]})
        rd = pd.DataFrame(rows)
        res[kind] = {f"h{hh*5}m": ev_stats(rd[rd["h"] == hh]) for hh in (3, 12)}
    return res


# ---------------------------------------------------------------------------
# P006 — London move before NY open -> continuation/reversal in NY overlap
# ---------------------------------------------------------------------------
def p006_ny_overlap(sym="EURUSD"):
    df = discovery(load(sym))
    lon = df.index.tz_convert("Europe/London")
    nyc = df.index.tz_convert("America/New_York")
    lon_hm = np.asarray(lon.hour * 100 + lon.minute)
    ny_hm = np.asarray(nyc.hour * 100 + nyc.minute)
    ny_day = np.asarray(nyc.date)
    lon_day = np.asarray(lon.date)
    c = df["close"].to_numpy()
    rows = []
    for d in np.unique(ny_day):
        same_ny = ny_day == d
        i_ny_open = np.where(same_ny & (ny_hm == 930))[0]
        if not len(i_ny_open):
            continue
        i0 = i_ny_open[0]
        # London open bar of the SAME London calendar day (works even when
        # DST changes are not synchronized across the Atlantic)
        d_lon = lon_day[i0]
        i_lon = np.where(lon_day == d_lon)[0]
        i_lon_open = i_lon[lon_hm[i_lon] == 800]
        if not len(i_lon_open) or i_lon_open[0] >= i0:
            continue
        iL = i_lon_open[0]
        move = float(c[i0 - 1] - c[iL])          # London move known BEFORE NY open
        if abs(move) < 5 * PIP[sym]:
            continue
        s = np.sign(move)
        for hh, name in ((12, "NY_1H"), (24, "NY_2H"), (48, "NY_4H")):
            j = i0 + hh
            if j < len(df):
                rows.append({"entry_ts": df.index[i0], "h": hh,
                             "cont": s * (c[j] - c[i0]) / PIP[sym],
                             "fade": -s * (c[j] - c[i0]) / PIP[sym]})
    rd = pd.DataFrame(rows)
    out = {}
    for hh, name in ((12, "NY_1H"), (24, "NY_2H"), (48, "NY_4H")):
        sub = rd[rd["h"] == hh]
        out[name] = {"CONTINUATION_PIPS": float(sub["cont"].mean()),
                     "FADE_PIPS": float(sub["fade"].mean()),
                     "WR_CONT": float((sub["cont"] > 0).mean()),
                     "N": int(len(sub))}
    return out


# ---------------------------------------------------------------------------
# P034 — range compression -> forward volatility expansion (SECOND ORDER)
# ---------------------------------------------------------------------------
def p034_compression(sym="EURUSD", ratios=(0.6, 0.7)):
    df = discovery(load(sym))
    hi12 = df["high"].rolling(144).max() - df["low"].rolling(144).min()
    med = hi12.rolling(30 * 288, min_periods=5000).median()
    comp = hi12 / med
    fwd_range = (df["high"].shift(-144) - df["low"].shift(-144))
    base_med = float(np.nanmedian(fwd_range))
    out = {"BASELINE_FWD_12H_RANGE_PIPS": base_med / PIP[sym]}
    for r in ratios:
        m = (comp < r).to_numpy()
        m[:5000] = False
        prev = np.concatenate(([False], m[:-1]))
        m &= ~prev
        vals = fwd_range[m] / PIP[sym]
        out[f"COMP<{r:.2f}"] = {
            "N": int(m.sum()),
            "FWD_RANGE_PIPS_MEDIAN": float(np.nanmedian(vals)) if m.sum() else None,
            "RATIO_VS_BASELINE": (float(np.nanmedian(vals) / (base_med / PIP[sym]))
                                  if m.sum() else None),
        }
    return out
