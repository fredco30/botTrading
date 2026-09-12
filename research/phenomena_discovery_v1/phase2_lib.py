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

    Audit fix: signal day = FIRST FX MARKET DAY with index >= t + 1 calendar
    day (the old `> t + 1 day` skipped the eligible day, e.g. Monday -> 
    Wednesday). d2_change is stored on each event at construction (no
    retroactive -1/-2 day lookup)."""
    s = _dgs2()
    d2 = s.diff().dropna()
    px = _daily_close("USDJPY")
    rd = us2y_events(d2, px)
    out = {}
    for hh in (1, 5):
        sub = rd[rd["h"] == hh].copy()
        sub["ret"] = sub["ret"] / 0.01          # JPY pips
        out[f"PIPS_h{hh}d"] = ev_stats(sub)
        strong = sub[sub["d2_change"].abs() >= shock_bp / 100.0]   # DGS2 is in %
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

    Signal definitions (audit fix):
      s_level:     every day, direction = sign(differential);
      s_delta:     EVENT ONLY when the differential actually changed after the
                   causal lag (delta != 0), direction = sign(delta);
      s_carrymom:  EVENT ONLY when sign(carry) == sign(20d momentum), direction
                   = carry side; no alignment -> NO EVENT.
    Reaction: FX close-to-close forward returns (1d/5d/20d)."""
    px = _daily_close(sym_pair)
    diff = diff_series.reindex(px.index).ffill()
    if diff.index.tz is None:
        diff.index = diff.index.tz_localize("UTC")
    diff = diff.shift(1)                      # +1 day availability lag
    mom20 = px.diff(20)
    events = {"s_level": [], "s_delta": [], "s_carrymom": []}
    idx = px.index
    for k in range(21, len(px)):
        t = idx[k]
        dv = diff.get(t, np.nan)
        mom = mom20.get(t, np.nan)
        if np.isnan(dv) or np.isnan(mom):
            continue
        for H in horizons:
            j = k + H
            if j >= len(px):
                continue
            fwd = float(px.iloc[j] - px.iloc[j - H])
            events["s_level"].append((t, H, int(np.sign(dv)), fwd))
            dv_prev = diff.get(idx[k - 1], np.nan)
            delta = dv - dv_prev
            if not np.isnan(delta) and delta != 0:
                events["s_delta"].append((t, H, int(np.sign(delta)), fwd))
            if np.sign(dv) == np.sign(mom):
                events["s_carrymom"].append((t, H, int(np.sign(dv)), fwd))
    pip = PIP[sym_pair]
    out = {}
    for key, evs in events.items():
        for H in horizons:
            rows = [{"entry_ts": t, "side": s, "ret": s * fwd / pip}
                    for t, hh, s, fwd in evs if hh == H]
            rd = pd.DataFrame(rows)
            out[f"{key}_h{H}d"] = ev_stats(rd)
            out[f"{key}_h{H}d"]["N_EVENTS_DAYS"] = int(len({r["entry_ts"] for r in rows}))
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
    """London 16:00 fix study (convention documented — audit fix):

    a 5m bar labelled 16:00 covers [16:00, 16:05); its CLOSE is the 16:05
    price. Boundary prices are therefore taken as the OPEN of the bar whose
    label equals the boundary time (= last executable price at/before the
    boundary). pre-fix = open(13:00) -> open(16:00) ; post-fix =
    open(16:00) -> open(18:00). Fixed windows a priori, no retuning."""
    df = discovery(load(sym))
    lon = df.index.tz_convert("Europe/London")
    hm = np.asarray(lon.hour * 100 + lon.minute)
    day = np.asarray(lon.date)
    o = df["open"].to_numpy()
    month_last2 = _month_last2_days(set(day))
    rows = []
    for d in np.unique(day):
        m = day == d
        i1300 = np.where(m & (hm == 1300))[0]
        i1600 = np.where(m & (hm == 1600))[0]
        i1800 = np.where(m & (hm == 1800))[0]
        if not (len(i1300) and len(i1600) and len(i1800)):
            continue
        pre = float(o[i1600[0]] - o[i1300[0]])
        post = float(o[i1800[0]] - o[i1600[0]])
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
def fed_tz_offset(tz_name):
    """'EST' -> '-05:00', 'EDT' -> '-04:00' (fixed offsets; pytz rejects the
    DST names). Anything else raises."""
    return {"EST": "-05:00", "EDT": "-04:00"}[tz_name]


def p032_fomc(syms=("EURUSD", "USDJPY", "GBPUSD")):
    """Post-FOMC event study with EXACT published release timestamps.

    Audit fixes: (1) the parsed tz field (EST/EDT) is honored — a 14:00 EDT
    release is 18:00 UTC, not 19:00; (2) ENTRY = the first bar OPEN whose
    timestamp >= release_ts (executable price; the old code used the CLOSE of
    the reaction bar). R0_30 = open(t+30m) - entry_open ;
    R30_120 = open(t+120m) - open(t+30m) ; NEXTDAY = open(t+24h) - entry_open.
    Events without an official release time are never fabricated."""
    path = os.path.join(OFFICIAL, "fomc_decisions.json")
    evs = json.load(open(path))
    out = {}
    for sym in syms:
        df = discovery(load(sym))
        o = df["open"].to_numpy()
        rows = []
        years_used = set()
        for e in evs:
            if not e.get("release_time"):
                continue
            h, m = e["release_time"].split(":")
            tz_name = e.get("tz") or "EST"
            rel = pd.Timestamp(f"{e['date']} {h}:{m}",
                               tz=fed_tz_offset(tz_name)).tz_convert("UTC")
            if not (DISC[0] <= rel < DISC[1]):
                continue
            pos = int(df.index.searchsorted(rel))   # first bar open >= release
            if pos == 0 or pos + 288 >= len(df):
                continue
            rows.append({"release": rel,
                         "r0_30": float(o[pos + 6] - o[pos]),
                         "r30_120": float(o[pos + 24] - o[pos + 6]),
                         "r_nextday": float(o[pos + 288] - o[pos])})
            years_used.add(e["date"][:4])
        rd = pd.DataFrame(rows)
        pip = PIP[sym]
        out[sym] = {
            "N": int(len(rd)),
            "PERIOD": f"{min(years_used)}-{max(years_used)}" if years_used else "n/a",
            "R0_30M_PIPS": float(rd["r0_30"].mean() / pip) if len(rd) else None,
            "R30_120M_PIPS": float(rd["r30_120"].mean() / pip) if len(rd) else None,
            "R_NEXTDAY_PIPS": float(rd["r_nextday"].mean() / pip) if len(rd) else None,
            "CONTINUATION_s0_30_to_30_120": float(
                (np.sign(rd["r0_30"]) * rd["r30_120"]).mean() / pip) if len(rd) else None,
            "ABS_R0_30M_PIPS": float(rd["r0_30"].abs().mean() / pip) if len(rd) else None,
        }
    out["_NOTE"] = ("release times parsed from official Fed press-release pages "
                    "('For release at ... EST/EDT', tz honored); entry = first "
                    "bar OPEN at/after release; exact times exist only from "
                    "2016 onward (pre-2015 statements say 'For immediate "
                    "release'); event-time study, no surprise data")
    return out


# ---------------------------------------------------------------------------
# P004 — previous day high/low (first touch / break / failed break / reclaim)
# ---------------------------------------------------------------------------
def p004_pdh_pdl(sym="EURUSD", back_inside_bars=6):
    """Previous-day H/L state machine (audit fix — explicit states):

    BREAK_PDH:   first close > PDH                     -> event side +1
    FAILED_PDH:  after BREAK, close < PDH within
                 `back_inside_bars` of the break bar   -> event side -1
    RECLAIM_PDH: after FAILED, first close > PDH again -> event side +1 (LONG)
    Symmetric for PDL (BREAK -1 / FAILED +1 / RECLAIM -1 SHORT).
    One event per type per day."""
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
        if j_e - j_s < 24:
            continue
        pdh = float(h[j_s:j_e].max())
        pdl = float(l[j_s:j_e].min())
        events += pdh_pdl_walk(i_s, i_e, c, h, l, sess, pdh, pdl,
                               back_inside_bars, df.index)
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
def future_rolling_range(high, low, fwd_bars):
    """TRUE forward range: for each i, max(high[i+1 : i+1+fwd_bars]) -
    min(low[i+1 : i+1+fwd_bars]) (the whole FUTURE window, not the single bar
    fwd_bars later). Last fwd_bars rows are NaN."""
    fhigh = high.rolling(fwd_bars).max().shift(-fwd_bars)
    flow = low.rolling(fwd_bars).min().shift(-fwd_bars)
    return fhigh - flow


def us2y_events(d2, px):
    """Pure mapping: DGS2 diff day t -> first FX market day >= t+1 calendar
    day, with d2_change stored on the event."""
    px_pos = {ts: i for i, ts in enumerate(px.index)}
    rows = []
    for t, dv in d2.items():
        elig = px.index[px.index >= t + pd.Timedelta(days=1)]
        if not len(elig) or (elig[0] - t).days > 7:
            continue
        t_exec = elig[0]
        k = px_pos[t_exec]
        for H in (1, 5):
            j = k + H
            if j >= len(px):
                continue
            rows.append({"entry_ts": t_exec, "side": int(np.sign(dv)),
                         "h": H, "d2_change": float(dv),
                         "ret": int(np.sign(dv)) * (px.iloc[j] - px.iloc[k])})
    return pd.DataFrame(rows)


def pdh_pdl_walk(i_s, i_e, c, h, l, sess, pdh, pdl, back, idx):
    """One-day PDH/PDL state machine (pure): NONE -> BROKEN -> FAILED ->
    RECLAIMED per side. Events: break (+1 PDH / -1 PDL), failed (-1 PDH /
    +1 PDL), reclaim (+1 PDH LONG / -1 PDL SHORT)."""
    events = []
    st_up = st_dn = "NONE"
    brk_up = brk_dn = -10**9
    for i in range(i_s, i_e):
        if not sess[i]:
            continue
        if st_up != "RECLAIMED":
            if c[i] > pdh:
                if st_up == "NONE":
                    st_up = "BROKEN"; brk_up = i
                    events.append((idx[i], 1, "break_PDH"))
                elif st_up == "FAILED":
                    st_up = "RECLAIMED"
                    events.append((idx[i], 1, "reclaim_PDH"))
            elif c[i] < pdh and st_up == "BROKEN" and i - brk_up <= back:
                st_up = "FAILED"
                events.append((idx[i], -1, "failed_PDH"))
        if st_dn != "RECLAIMED":
            if c[i] < pdl:
                if st_dn == "NONE":
                    st_dn = "BROKEN"; brk_dn = i
                    events.append((idx[i], -1, "break_PDL"))
                elif st_dn == "FAILED":
                    st_dn = "RECLAIMED"
                    events.append((idx[i], -1, "reclaim_PDL"))
            elif c[i] > pdl and st_dn == "BROKEN" and i - brk_dn <= back:
                st_dn = "FAILED"
                events.append((idx[i], 1, "failed_PDL"))
    return events



def paired_bootstrap_means(event_matrix, n_boot=2000, seed=42):
    """FAMILY-INFERENCE bootstrap for a common event table.

    event_matrix: ndarray (n_events, n_pairs) — one ROW per common event,
    one COLUMN per instrument. Each draw resamples whole ROWS (events), so
    the cross-pair dependence structure is preserved exactly. Returns the
    array of bootstrap means of the equal-weight pooled series.
    (The previous per-pair independent resampling is superseded — it
    understates uncertainty when pairs are correlated.)"""
    m = np.asarray(event_matrix, dtype=float)
    n = m.shape[0]
    pooled = m.mean(axis=1)
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for b in range(n_boot):
        sel = rng.integers(0, n, n)
        out[b] = pooled[sel].mean()
    return out


def _year_block_sample_mean(pooled, years, pick):
    """Mean of the CONCATENATED blocks for one draw. A year drawn k times
    contributes k copies of its events (the old boolean-mask implementation
    deduplicated repeats and lost the multiplicity — bug fixed)."""
    blocks = [pooled[years == y] for y in pick]
    return float(np.concatenate(blocks).mean())


def year_block_bootstrap_means(event_matrix, year_ids, n_boot=2000, seed=42):
    """Year-block bootstrap: resample CALENDAR YEARS as blocks (all their
    month-end events, all pairs together) to preserve regimes, cross-pair
    correlation and temporal structure. Years are drawn WITH replacement and
    repeated draws genuinely repeat the block (no mask deduplication)."""
    m = np.asarray(event_matrix, dtype=float)
    years = np.asarray(year_ids)
    uniq = np.unique(years)
    pooled = m if m.ndim == 1 else m.mean(axis=1)
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for b in range(n_boot):
        pick = rng.choice(uniq, size=len(uniq), replace=True)
        out[b] = _year_block_sample_mean(pooled, years, pick)
    return out

def p034_compression(sym="EURUSD", ratios=(0.6, 0.7), fwd_bars=144):
    """Forward 12h range = max(high[i+1:i+1+fwd_bars]) - min(low[i+1:i+1+fwd_bars]):
    the TRUE rolling future window (audit fix: the old shift(-144) measured the
    range of the single bar 12h later). The whole future window must stay
    inside Discovery (events near the window end are dropped)."""
    df = discovery(load(sym))
    hi12 = df["high"].rolling(144).max() - df["low"].rolling(144).min()
    med = hi12.rolling(30 * 288, min_periods=5000).median()
    comp = hi12 / med
    fwd_range = future_rolling_range(df["high"], df["low"], fwd_bars)
    n = len(df)
    base_med = float(np.nanmedian(fwd_range[: n - fwd_bars]))
    out = {"BASELINE_FWD_12H_RANGE_PIPS": base_med / PIP[sym]}
    for r in ratios:
        m = (comp < r).to_numpy()
        m[:5000] = False
        m[n - fwd_bars:] = False          # future window must stay in Discovery
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
