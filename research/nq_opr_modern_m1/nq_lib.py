#!/usr/bin/env python3
"""NQ OPR MODERN M1 — engine (frozen p000 semantics on real CME NQ data).

PORT PROVENANCE: every strategy-bearing function below is a faithful port of
research/phenomena_discovery_v1/p000_lib.py @ 3122f1ea64aafb2c8952cc01189f9af63ff62f63
(walk state machine, retest/entry rules, close-based level stop, 50% trim at new
running day extreme + breakeven, EMA8 runner, RTH EOD flatten, one trade/day,
VWAP variant, forward-return horizons). Only these deltas exist:
  * data source = locally built 5m bars from real NQ ohlcv-1m (E: drive);
  * hard 2026 seal at 2026-01-01 UTC exclusive;
  * NQ preregistered costs (points RT): LOW 0.75 / NORMAL 1.5 / STRESS 3.0;
  * ADDITIVE measurement helpers (MFE/MAE, R-multiples, drawdown, frequency,
    regime variables) that never alter decisions.

CAUSALITY (unchanged): 5m bars carry bucket-START labels; a bar is fully known
only at label+5min. Levels usable only after their window; running extremes are
shifted cummax/cummin; entries are stop orders at the tap-bar extreme (or worse
open on a gap-through); exits evaluate closes; forward returns target strictly
later bar opens.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARQUET = "E:/ResearchData/botTrading/nq/databento/parquet"

ET = "America/New_York"

# 2026 SEALED — hard guard, refuse any bar at/after this instant
DATA_END = pd.Timestamp("2026-01-01 00:00", tz="UTC")

# Internal temporal blocks (NOT pristine OOS — see lab protocol)
FOLDS = {
    "DISCOVERY": (pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC")),
    "VALIDATION": (pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2024-01-01", tz="UTC")),
    "REPLICATION": (pd.Timestamp("2024-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC")),
}

# Preregistered NQ frictions, ROUND TRIP, index points; 1 pt = 5.00 USD
NQ_COSTS = {"LOW": 0.75, "NORMAL": 1.5, "STRESS": 3.0}
POINT_VALUE_USD = 5.0
TICK_SIZE = 0.25
TICK_VALUE_USD = 5.0

PM_START_ET = (4, 0)
RTH_START_ET = (9, 30)
RTH_END_ET = (16, 0)
MIN_PM_BARS = 12


def load_5m():
    """Local 5m parquet (2020-2025). Refuses any 2026 row — hard seal."""
    df = pd.read_parquet(os.path.join(PARQUET, "nq_5m_2020_2025.parquet"))
    idx = pd.DatetimeIndex(pd.to_datetime(df["ts"], utc=True))
    bad = int((idx >= DATA_END).sum())
    if bad:
        raise ValueError(f"{bad} SEALED 2026 bars present — refusing")
    df = df.set_index(idx).drop(columns=["ts"])
    return df[df.index < DATA_END]


# --- frozen: levels ---------------------------------------------------------
def premarket_levels(df):
    """Per ET-day (pmh, pml, n_bars) from [04:00, 09:30) ET."""
    et = df.index.tz_convert(ET)
    et_hm = et.hour * 100 + et.minute
    mask = (et_hm >= PM_START_ET[0] * 100 + PM_START_ET[1]) & \
           (et_hm < RTH_START_ET[0] * 100 + RTH_START_ET[1])
    pm = df[mask]
    out = {}
    for d, g in pm.groupby(et[mask].date):
        out[d] = (float(g["high"].max()), float(g["low"].min()), len(g))
    return out


def vwap_rth(df):
    """RTH-anchored expanding session VWAP per ET day (volume-weighted; NQ has
    real volume so the historical TWAP fallback is normally not used)."""
    et = df.index.tz_convert(ET)
    et_hm = et.hour * 100 + et.minute
    rth = (et_hm >= RTH_START_ET[0] * 100 + RTH_START_ET[1]) & \
          (et_hm < RTH_END_ET[0] * 100 + RTH_END_ET[1])
    tp = ((df["high"] + df["low"] + df["close"]) / 3.0).to_numpy()
    vol = df["volume"].to_numpy(dtype=float)
    out = np.full(len(df), np.nan)
    pos = np.arange(len(df))
    rth_pos = pos[np.asarray(rth)]
    dates = df.index.tz_convert(ET).date
    for day in sorted(set(dates[rth_pos])):
        sel = rth_pos[dates[rth_pos] == day]
        v, tp_s = vol[sel], tp[sel]
        if v.sum() > 0:
            out[sel] = np.cumsum(tp_s * v) / np.cumsum(v)
        else:
            out[sel] = np.cumsum(tp_s) / np.arange(1, len(sel) + 1)
    return pd.Series(out, index=df.index)


def running_day_extremes(df, tz):
    """Per-day running extremes known BEFORE each bar (shifted cummax/cummin)."""
    key = pd.Series(df.index.tz_convert(tz).date, index=df.index)
    hi = df["high"].groupby(key).cummax().shift(1)
    lo = df["low"].groupby(key).cummin().shift(1)
    return hi, lo


# --- frozen: event walk -----------------------------------------------------
@dataclass
class RawEvent:
    day: object
    side: int
    level: float
    confirm_ts: pd.Timestamp
    tap_ts: pd.Timestamp
    entry_ts: pd.Timestamp
    fill: float
    variant: str


def _consecutive_day_groups(day_ids):
    day_ids = np.asarray(day_ids)
    pos = np.arange(len(day_ids))
    boundaries = np.where(np.diff(day_ids) != 0)[0]
    return np.split(pos, boundaries + 1)


def _et_day_ids(index):
    naive = index.tz_convert(ET).tz_localize(None)
    return (naive.view("int64") // 86_400_000_000_000)


def _walk_day(g, o, h, l, c, idx, upper, lower, dyn_level, dyn_name, day):
    """One-day state machine (frozen). Returns 0 or 1 events (first of day)."""
    side = 0
    level = np.nan
    confirm_i = tap_i = -1
    tap_extreme = np.nan
    state = "WAIT_CONFIRM"
    for pos in g:
        if state == "WAIT_CONFIRM":
            if c[pos] > upper:
                side, level = 1, upper
            elif c[pos] < lower:
                side, level = -1, lower
            else:
                continue
            if dyn_level is not None:
                new_lv = dyn_level(pos)
                if np.isnan(new_lv) or not ((side == 1 and new_lv > level) or
                                            (side == -1 and new_lv < level)):
                    return None
                level = float(new_lv)
            confirm_i = pos
            state = "WAIT_TAP"
        elif state == "WAIT_TAP":
            if dyn_level is not None:
                level = float(dyn_level(pos))
            if (side == 1 and c[pos] < level) or (side == -1 and c[pos] > level):
                return None
            touched = (l[pos] <= level) if side == 1 else (h[pos] >= level)
            if touched:
                tap_extreme = h[pos] if side == 1 else l[pos]
                tap_i = pos
                state = "WAIT_ENTRY"
        elif state == "WAIT_ENTRY":
            if (side == 1 and c[pos] < level) or (side == -1 and c[pos] > level):
                return None
            if side == 1 and (o[pos] >= tap_extreme or h[pos] >= tap_extreme):
                fill = float(o[pos]) if o[pos] >= tap_extreme else float(tap_extreme)
                return RawEvent(day, 1, float(level), idx[confirm_i],
                                idx[tap_i], idx[pos], fill, dyn_name)
            if side == -1 and (o[pos] <= tap_extreme or l[pos] <= tap_extreme):
                fill = float(o[pos]) if o[pos] <= tap_extreme else float(tap_extreme)
                return RawEvent(day, -1, float(level), idx[confirm_i],
                                idx[tap_i], idx[pos], fill, dyn_name)
    return None


def detect_us_events(df, variant="LEVEL"):
    """P000A (LEVEL) / P000B (VWAP) events on NQ 5m bars, session = RTH (frozen)."""
    levels = premarket_levels(df)
    et_idx = df.index.tz_convert(ET)
    et_dates = et_idx.date
    et_ids = _et_day_ids(df.index)
    sess_hm = np.asarray(et_idx.hour * 100 + et_idx.minute)
    sess = ((sess_hm >= RTH_START_ET[0] * 100 + RTH_START_ET[1]) &
            (sess_hm < RTH_END_ET[0] * 100 + RTH_END_ET[1]))
    sess_pos = np.where(sess)[0]
    if len(sess_pos) == 0:
        return []
    groups = _consecutive_day_groups(et_ids[sess_pos])

    dyn_level = None
    dyn_name = "LEVEL"
    if variant == "VWAP":
        vw = vwap_rth(df).to_numpy()
        dyn_level = lambda pos: vw[pos]  # noqa: E731
        dyn_name = "VWAP"

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    idx = df.index
    ev = []
    for g in groups:
        day = et_dates[sess_pos[g[0]]]
        lv = levels.get(day)
        if lv is None or lv[2] < MIN_PM_BARS or not (lv[0] > lv[1]):
            continue
        e = _walk_day(sess_pos[g], o, h, l, c, idx, lv[0], lv[1],
                      dyn_level, dyn_name, day)
        if e is not None:
            ev.append(e)
    return ev


# --- frozen: raw forward returns --------------------------------------------
def raw_forward_returns(df, events, horizons=(1, 3, 6, 12, 24), split=None):
    """Signed forward returns (points) from the fill to bar opens h bars later."""
    o = df["open"].to_numpy()
    pos_of = {ts: i for i, ts in enumerate(df.index)}
    rows = []
    for e in events:
        i = pos_of.get(e.entry_ts)
        if i is None:
            continue
        for hh in horizons:
            j = i + hh
            if j >= len(df):
                continue
            if split is not None and not (split[0] <= df.index[j] < split[1]):
                continue
            rows.append({"day": e.day, "side": e.side, "variant": e.variant,
                         "entry_ts": e.entry_ts, "confirm_ts": e.confirm_ts,
                         "fill": e.fill, "h": hh,
                         "ret": e.side * (float(o[j]) - e.fill)})
    return pd.DataFrame(rows)


# --- frozen: statistics -----------------------------------------------------
def block_bootstrap_mean(x, block=20, n_boot=2000, seed=42):
    rng = np.random.default_rng(seed)
    n = len(x)
    if n < 30:
        return None, None, None
    block = max(2, min(block, n // 5))
    nb = int(np.ceil(n / block))
    means = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n - block + 1, size=nb)
        sel = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        means[b] = np.mean(x[sel])
    lo, hi = np.percentile(means, [2.5, 97.5])
    p = 2 * min(float(np.mean(means <= 0)), float(np.mean(means >= 0)))
    return float(lo), float(hi), min(p, 1.0)


def _to_et(ts_like):
    di = pd.DatetimeIndex(ts_like)
    if di.tz is None:
        di = di.tz_localize("UTC")
    return di.tz_convert(ET)


def event_stats(rets_df, unit_scale=1.0):
    out = {"N": 0} if rets_df is None or rets_df.empty else {}
    if out:
        return out
    r = rets_df["ret"].to_numpy() * unit_scale
    out["N"] = int(len(r))
    out["MEAN"] = float(np.mean(r))
    out["MEDIAN"] = float(np.median(r))
    out["WIN_RATE"] = float(np.mean(r > 0))
    out["STD"] = float(np.std(r, ddof=1)) if len(r) > 1 else 0.0
    lm = (rets_df["side"] == 1).to_numpy()
    out["N_LONG"] = int(lm.sum())
    out["N_SHORT"] = int((~lm).sum())
    out["MEAN_LONG"] = float(np.mean(r[lm])) if lm.any() else None
    out["MEAN_SHORT"] = float(np.mean(r[~lm])) if (~lm).any() else None
    sr = np.sort(r)[::-1]
    out["MEAN_BEST1_REMOVED"] = float(np.mean(sr[1:]))
    out["MEAN_BEST5_REMOVED"] = float(np.mean(sr[5:])) if len(sr) > 5 else None
    top = max(1, int(round(0.01 * len(r))))
    out["MEAN_TOP1PCT_REMOVED"] = float(np.mean(sr[top:]))
    lo, hi, p = block_bootstrap_mean(r)
    out["BOOT_CI_LO"], out["BOOT_CI_HI"], out["BOOT_P"] = lo, hi, p
    yrs = _to_et(rets_df["entry_ts"]).year
    out["BY_YEAR"] = {int(y): round(float(np.mean(r[np.asarray(yrs == y)])), 5)
                      for y in sorted(set(yrs))}
    return out


def summarize_trades(tf, unit_scale=1.0, use="net"):
    if tf is None or tf.empty:
        return {"N": 0}
    r = tf[use].to_numpy() * unit_scale
    g = tf["gross"].to_numpy() * unit_scale
    pos_sum = r[r > 0].sum()
    neg_sum = -r[r < 0].sum()
    lm = (tf["side"] == 1).to_numpy()
    out = {
        "N": int(len(r)),
        "MEAN_NET": float(np.mean(r)),
        "MEDIAN_NET": float(np.median(r)),
        "MEAN_GROSS": float(np.mean(g)),
        "WIN_RATE": float(np.mean(r > 0)),
        "PROFIT_FACTOR": float(pos_sum / neg_sum) if neg_sum > 0 else None,
        "MEAN_LONG": float(np.mean(r[lm])) if lm.any() else None,
        "MEAN_SHORT": float(np.mean(r[~lm])) if (~lm).any() else None,
        "EXIT_REASONS": {k: int(v) for k, v in tf["exit_reason"].value_counts().items()},
    }
    lo, hi, p = block_bootstrap_mean(r)
    out["BOOT_CI_LO"], out["BOOT_CI_HI"], out["BOOT_P"] = lo, hi, p
    yrs = _to_et(tf["entry_ts"]).year
    out["BY_YEAR"] = {int(y): round(float(np.mean(r[np.asarray(yrs == y)])), 5)
                      for y in sorted(set(yrs))}
    return out


# --- frozen: strategy simulation --------------------------------------------
@dataclass
class Trade:
    day: object
    side: int
    variant: str
    entry_ts: object
    fill: float
    level: float
    exit_ts: object
    gross: float
    net: float
    exit_reason: str
    n_bars: int


def simulate_strategy(df, events, cost_rt, tz, sess_end_hm,
                      trim_frac=0.5, ema_n=8):
    """Frozen mechanics: stop-entry fill -> close-based level stop (untrimmed)
    -> 50% trim at first new running day extreme + BE -> runner: gap-aware BE
    floor or CLOSE through EMA8 -> flat at last session bar of the day."""
    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    idx = df.index
    local = idx.tz_convert(tz)
    hm = (local.hour * 100 + local.minute).to_numpy()
    ldate = local.date

    run_hi, run_lo = running_day_extremes(df, tz)
    run_hi = run_hi.to_numpy()
    run_lo = run_lo.to_numpy()
    ema = df["close"].ewm(span=ema_n, adjust=False).mean().to_numpy()

    pos_of = {ts: i for i, ts in enumerate(idx)}
    half = cost_rt / 2.0  # noqa: F841 (kept for provenance parity)
    n = len(df)
    trades = []
    for e in events:
        side = e.side
        i0 = pos_of.get(e.entry_ts)
        if i0 is None:
            continue
        fill = e.fill
        tgt = run_hi[i0] if side == 1 else run_lo[i0]
        if np.isnan(tgt):
            tgt = fill
        trimmed = False
        remaining = 1.0
        gross = 0.0
        exit_reason = ""
        last_i = i0
        for i in range(i0, n):
            same_day_next = (i + 1 < n) and (ldate[i + 1] == ldate[i]) and \
                            (hm[i + 1] < sess_end_hm)
            if not trimmed:
                if (side == 1 and c[i] < e.level) or \
                   (side == -1 and c[i] > e.level):
                    gross += remaining * side * (float(c[i]) - fill)
                    exit_reason = "LEVEL_STOP"
                    remaining = 0.0
                    last_i = i
                    break
                hit = (h[i] >= tgt) if side == 1 else (l[i] <= tgt)
                if hit:
                    gross += trim_frac * side * (tgt - fill)
                    remaining -= trim_frac
                    trimmed = True
            else:
                if (side == 1 and o[i] < fill) or (side == -1 and o[i] > fill):
                    px = float(o[i])
                elif (side == 1 and c[i] < fill) or (side == -1 and c[i] > fill):
                    px = float(fill)
                else:
                    px = None
                if px is not None:
                    gross += remaining * side * (px - fill)
                    exit_reason = "BE_STOP"
                    remaining = 0.0
                    last_i = i
                    break
                e8 = ema[i]
                if (side == 1 and c[i] < e8) or (side == -1 and c[i] > e8):
                    gross += remaining * side * (float(c[i]) - fill)
                    exit_reason = "EMA8"
                    remaining = 0.0
                    last_i = i
                    break
            if not same_day_next:
                gross += remaining * side * (float(c[i]) - fill)
                exit_reason = exit_reason or "EOD"
                remaining = 0.0
                last_i = i
                break
            last_i = i
        if remaining > 0:
            gross += remaining * side * (float(c[last_i]) - fill)
            exit_reason = exit_reason or "FORCED"
        trades.append(Trade(e.day, side, e.variant, e.entry_ts, fill,
                            e.level, idx[last_i], gross, gross - cost_rt,
                            exit_reason, last_i - i0 + 1))
    return trades


def trades_frame(trades):
    return pd.DataFrame([t.__dict__ for t in trades])


def split_events_by_entry(events, split_name):
    lo, hi = FOLDS[split_name]
    return [e for e in events if lo <= e.entry_ts < hi]


# --- ADDITIVE measurement helpers (never alter decisions) -------------------
def trade_measurements(df, tf):
    """MFE/MAE (points), R multiples, hold minutes — from 5m bars."""
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    idx = df.index
    pos_of = {ts: i for i, ts in enumerate(idx)}
    mfe, mae, r0, hold_min = [], [], [], []
    for _, t in tf.iterrows():
        i0 = pos_of[t["entry_ts"]]
        i1 = pos_of[t["exit_ts"]]
        side = int(t["side"])
        fill = float(t["fill"])
        fav = np.maximum(side * (h[i0:i1 + 1] - fill),
                         side * (l[i0:i1 + 1] - fill))
        adv = np.maximum(side * (fill - h[i0:i1 + 1]),
                         side * (fill - l[i0:i1 + 1]))
        mfe.append(float(fav.max()))
        mae.append(float(adv.max()))
        r0.append(abs(fill - float(t["level"])))
        hold_min.append((t["exit_ts"] - t["entry_ts"]) / np.timedelta64(1, "m"))
    out = tf.copy()
    out["MFE"] = mfe
    out["MAE"] = mae
    out["R0"] = r0
    out["R_MULT"] = out["net"] / out["R0"].replace(0.0, np.nan)
    out["HOLD_MIN"] = hold_min
    return out


def drawdown_metrics(net_points: np.ndarray):
    """Max drawdown on the chronological per-trade cumulative net (points)."""
    eq = np.cumsum(net_points)
    peak = np.maximum.accumulate(np.concatenate([[0.0], eq]))
    dd = np.concatenate([[0.0], eq]) - peak
    return float(dd.min()), float(eq[-1])


def frequency_metrics(df, events, tf, fold_lo, fold_hi):
    """Eligible / breakout / retest-session counts and trades per week."""
    local = df.index.tz_convert(ET)
    in_fold = (df.index >= fold_lo) & (df.index < fold_hi)
    days = pd.Series(local[in_fold].date).drop_duplicates()
    elig = premarket_days = 0
    lv = premarket_levels(df[in_fold])
    for d, (_, _, nb) in lv.items():
        if nb >= MIN_PM_BARS:
            elig += 1
    breakout_days = len(set(e.day for e in events))
    trade_days = len(set(t.day for _, t in tf.iterrows())) if not tf.empty else 0
    weeks = max(len(days) / 5.0, 1e-9)
    return {"ELIGIBLE_SESSIONS": elig,
            "BREAKOUT_SESSIONS": breakout_days,
            "RETEST_TRADE_SESSIONS": trade_days,
            "TRADES": int(len(tf)),
            "TRADES_PER_WEEK": float(len(tf) / weeks)}


def regime_variables(df):
    """Diagnostic regime table per ET day (NO filtering use in this mission)."""
    local = df.index.tz_convert(ET)
    d = pd.Series(local.date, index=df.index)
    hm = local.hour * 100 + local.minute
    rows = {}
    rth = (hm >= 930) & (hm < 1600)
    pm = (hm >= 400) & (hm < 930)
    for day, g in df[rth].groupby(d[rth]):
        gpm = df[pm][d[pm] == day]
        if len(g) < 60:
            continue
        o = float(g["open"].iloc[0]); c = float(g["close"].iloc[-1])
        hi = float(g["high"].max()); lo = float(g["low"].min())
        prev_close = None
        prev = df[rth][d[rth] < day]
        if len(prev):
            prev_close = float(prev["close"].iloc[-1])
        rows[str(day)] = {
            "RTH_RANGE": hi - lo,
            "RTH_NET": c - o,
            "PM_RANGE": (float(gpm["high"].max()) - float(gpm["low"].min()))
                        if len(gpm) else np.nan,
            "GAP_FROM_PRIOR_RTH_CLOSE": (o - prev_close) if prev_close else np.nan,
            "RET_1D": c / o - 1.0,
        }
    return pd.DataFrame(rows).T
