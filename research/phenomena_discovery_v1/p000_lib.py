#!/usr/bin/env python3
"""P000 — video strategy research library (phenomena-discovery-v1).

Reconstructs the PBInvesting "one trade per day" pre-market breakout strategy
(video_strategy_spec.md) and implements:

  * P000A / P000_VIDEO_CORE_V1 — pre-market high/low breakout + 5m close
    confirmation + retest entry with momentum trigger, close-based stop,
    trim at new extreme of day, EMA8 trail after first trim (day ends flat);
  * P000B — VWAP-retest variant (level = session VWAP when VWAP beyond the
    pre-market level at confirmation);
  * P000C / P000_TRANSFER — session transposition on FX: Asia range ->
    London/NY breakout + retest (UTC, DST-safe).

CAUSALITY
  5m bars carry their bucket-START timestamp ts; a bar is fully known only
  at ts+5min. All decisions use information available at decision time:
  the pre-market levels are usable only from the first session bar; the
  running day extreme for the trim is the shifted cummax/cummin (known
  before the bar); EMA8/BE/level stops are evaluated on closes.
  Entry is a stop order at the tap-bar extreme (fills at that level, or at
  the worse open when a later bar gaps past it). The trim is a limit at the
  running extreme (fills only if the bar reaches it). The untrimmed stop is
  CLOSE-based through the level (video rule). Same-bar conflicts resolve to
  the worse compatible issue. Forward returns start at the actual fill and
  never cross a split boundary (enforced by passing `split`). No OOS data
  is ever loaded (defensive check).

COSTS (SYNTHETIC, parametric — never claimed realistic): round-trip
{LOW,NORMAL,STRESS} in instrument units, half adverse at entry, half at exit.
US index = index points; FX = pips.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARQUET = os.path.join(ROOT, "data_raw", "parquet")

ET = "America/New_York"

DATA_END = pd.Timestamp("2026-04-09 00:00", tz="UTC")     # exclusive — PROTECTED
OOS_START = pd.Timestamp("2026-04-09 00:00", tz="UTC")    # PROTECTED window
OOS_STOP = pd.Timestamp("2026-07-24 23:59", tz="UTC")     # inclusive — PROTECTED

SPLITS = {
    "DISCOVERY": (pd.Timestamp("2010-01-01", tz="UTC"), pd.Timestamp("2019-01-01", tz="UTC")),
    "V1": (pd.Timestamp("2019-01-01", tz="UTC"), pd.Timestamp("2023-01-01", tz="UTC")),
    "V2": (pd.Timestamp("2023-01-01", tz="UTC"), DATA_END),
}

US_COSTS = {"LOW": 0.5, "NORMAL": 1.0, "STRESS": 2.5}     # index points, RT
FX_COSTS = {"LOW": 1.0, "NORMAL": 2.0, "STRESS": 3.5}     # pips, RT
PIP = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01}

PM_START_ET = (4, 0)
RTH_START_ET = (9, 30)
RTH_END_ET = (16, 0)

FX_RANGE_START_UTC = (23, 0)
FX_RANGE_END_UTC = (7, 0)
FX_SESSION_END_UTC = (16, 0)

MIN_PM_BARS = 12


def load_5m(sym):
    df = pd.read_parquet(os.path.join(PARQUET, f"{sym}_5m.parquet"))
    df.index = pd.DatetimeIndex(df.index).tz_convert("UTC")
    bad = int(((df.index >= OOS_START) & (df.index <= OOS_STOP)).sum())
    if bad:
        raise ValueError(f"{bad} OOS bars present — refusing")
    return df[df.index < DATA_END]


# ---------------------------------------------------------------------------
# Levels (causal: only usable once the defining window has ended)
# ---------------------------------------------------------------------------
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
    """RTH-anchored expanding session VWAP per ET day (volume-weighted when
    the day has positive volume, else typical-price TWAP — documented)."""
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
    """Per-day running extremes known BEFORE each bar (shifted cummax/cummin
    within the day in `tz`). Causal at any moment inside the bar.

    The shift is applied WITHIN each day group: the first bar of a new day
    never inherits the previous day's extreme (NaN until the day has
    its own history)."""
    key = pd.Series(df.index.tz_convert(tz).date, index=df.index)
    hi = df["high"].groupby(key).cummax()
    lo = df["low"].groupby(key).cummin()
    hi = hi.groupby(key).shift(1)
    lo = lo.groupby(key).shift(1)
    return hi, lo


# ---------------------------------------------------------------------------
# Generic confirmation -> tap -> entry walk
# ---------------------------------------------------------------------------
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
    """Split positions into maximal runs of equal int day ids (UTC- or ET-day
    numbers). Integer ids avoid object-dtype pitfalls with np.diff."""
    day_ids = np.asarray(day_ids)
    pos = np.arange(len(day_ids))
    boundaries = np.where(np.diff(day_ids) != 0)[0]
    return np.split(pos, boundaries + 1)


def _et_day_ids(index):
    """int64 day ids of ET calendar days for a UTC DatetimeIndex."""
    naive = index.tz_convert(ET).tz_localize(None)
    # ET day number = UTC ns of naive ET midnight floor; shift by 86400s from epoch is irrelevant
    return (naive.view("int64") // 86_400_000_000_000)


def _walk_day(g, o, h, l, c, idx, upper, lower, dyn_level, dyn_name, day):
    """One-day state machine. dyn_level(pos, level) -> new level or the same
    (None = static levels). Returns 0 or 1 events (first setup of the day)."""
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
                # video rule: trade the VWAP retest only when VWAP is already
                # beyond the broken level at confirmation
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
                return None     # closed back through before any tap
            touched = (l[pos] <= level) if side == 1 else (h[pos] >= level)
            if touched:
                tap_extreme = h[pos] if side == 1 else l[pos]
                tap_i = pos
                state = "WAIT_ENTRY"
        elif state == "WAIT_ENTRY":
            if (side == 1 and c[pos] < level) or (side == -1 and c[pos] > level):
                return None     # closed back through before entry
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
    """P000A (LEVEL) / P000B (VWAP) events on US 5m bars, session = RTH."""
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


def detect_fx_events(df):
    """P000C: Asia range [23:00,07:00) UTC -> session [07:00,16:00) UTC."""
    hm = (df.index.hour * 100 + df.index.minute).to_numpy()
    day_num = (df.index.view("int64") // 86_400_000_000_000)   # fast UTC day id
    utc_dates = df.index.date
    sess = ((hm >= FX_RANGE_END_UTC[0] * 100 + FX_RANGE_END_UTC[1]) &
            (hm < FX_SESSION_END_UTC[0] * 100 + FX_SESSION_END_UTC[1]))
    sess_pos = np.where(sess)[0]
    if len(sess_pos) == 0:
        return []
    groups = _consecutive_day_groups(day_num[sess_pos])
    rng_start = FX_RANGE_START_UTC[0] * 100
    rng_end = FX_RANGE_END_UTC[0] * 100 + FX_RANGE_END_UTC[1]

    o = df["open"].to_numpy()
    h = df["high"].to_numpy()
    l = df["low"].to_numpy()
    c = df["close"].to_numpy()
    idx = df.index
    hi_all = df["high"].to_numpy()
    lo_all = df["low"].to_numpy()
    ev = []
    for g in groups:
        day = utc_dates[sess_pos[g[0]]]
        dnum = day_num[sess_pos[g[0]]]
        same_day = (day_num == dnum) & (hm < rng_end)
        prev_mask = (day_num == dnum - 1) & (hm >= rng_start)
        rng_mask = same_day | prev_mask
        if rng_mask.sum() < MIN_PM_BARS:
            continue
        r_hi = float(hi_all[rng_mask].max())
        r_lo = float(lo_all[rng_mask].min())
        if not (r_hi > r_lo):
            continue
        e = _walk_day(sess_pos[g], o, h, l, c, idx, r_hi, r_lo,
                      None, "LEVEL", day)
        if e is not None:
            ev.append(e)
    return ev


# ---------------------------------------------------------------------------
# Forward returns for the raw signal
# ---------------------------------------------------------------------------
def raw_forward_returns(df, events, horizons=(1, 3, 6, 12, 24), split=None):
    """Signed open-forward returns (instrument units) from the fill.

    Target = OPEN of the bar `h` bars after the entry bar (causal, known at
    that bar's open). With `split=(lo,hi)`, events whose horizon end exits
    the window are dropped (no boundary contamination).
    """
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


# ---------------------------------------------------------------------------
# Statistics (mission measures; moving-block bootstrap for overlapping-free
# one-event-per-day samples)
# ---------------------------------------------------------------------------
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
    """tz-aware or naive DatetimeIndex -> ET (naive treated as UTC-naive label)."""
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
    hrs = _to_et(rets_df["entry_ts"]).hour
    out["BY_HOUR_ET"] = {int(x): round(float(np.mean(r[np.asarray(hrs == x)])), 5)
                         for x in sorted(set(hrs))}
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


# ---------------------------------------------------------------------------
# Strategy simulation (conservative; day ends flat; no pyramiding)
# ---------------------------------------------------------------------------
@dataclass
class Trade:
    day: object
    side: int
    variant: str
    entry_ts: object
    fill: float
    exit_ts: object
    gross: float
    net: float
    exit_reason: str
    n_bars: int


def simulate_strategy(df, events, cost_rt, tz, sess_end_hm,
                      trim_frac=0.5, ema_n=8):
    """Entry stop-fill -> close-based level stop while untrimmed -> trim at
    first new running day extreme (limit fill at the extreme; stop moves to
    BE) -> runner exits on gap-aware BE floor or CLOSE through EMA8 -> flat
    at the last session bar of the day."""
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
    half = cost_rt / 2.0
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
                # worse issue first: close-based invalidation through level
                # (evaluated on every bar, including the day's last one)
                if (side == 1 and c[i] < e.level) or \
                   (side == -1 and c[i] > e.level):
                    gross += remaining * side * (float(c[i]) - fill)
                    exit_reason = "LEVEL_STOP"
                    remaining = 0.0
                    last_i = i
                    break
                hit = (h[i] >= tgt) if side == 1 else (l[i] <= tgt)
                if hit:
                    # GUARD: a trim never executes worse than the fill. If the
                    # entry gapped beyond the pre-entry day extreme (long entry
                    # above the old HOD, short below the old LOD), the "new
                    # extreme" condition is already met at entry; conservative
                    # interpretation = trim AT FILL (0 PnL on that fraction),
                    # never a synthetic loss at a level the trade never had.
                    trim_price = max(tgt, fill) if side == 1 else min(tgt, fill)
                    gross += trim_frac * side * (trim_price - fill)  # limit fill
                    remaining -= trim_frac
                    trimmed = True   # trail/BE active from next bar
            else:
                # BE floor, gap-aware (worse of open / floor)
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
                            idx[last_i], gross, gross - cost_rt,
                            exit_reason, last_i - i0 + 1))
    return trades


def trades_frame(trades):
    return pd.DataFrame([t.__dict__ for t in trades])


def split_events_by_entry(events, split_name):
    lo, hi = SPLITS[split_name]
    return [e for e in events if lo <= e.entry_ts < hi]
