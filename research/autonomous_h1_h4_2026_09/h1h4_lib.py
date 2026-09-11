#!/usr/bin/env python3
"""Autonomous H1/H4 multi-pair research library.

Causal building blocks:
  * strict date filtering BEFORE any strategic use (OOS cutoff enforced);
  * calendar-bucket aggregation M15 -> H1 -> H4 (open=first, high=max,
    low=min, close=last); no bucket is fabricated from zero bars;
  * vectorized indicators on CLOSED bars only (all feature index <= i-1
    for a decision taken at the open of bar i);
  * open-to-open forward-return event study with synthetic round-trip
    costs (LOW 1.0 / NORMAL 2.0 / STRESS 3.5 pips).

No OOS data ever enters this module: callers must pass already-filtered
bars; `filter_window` enforces the cutoff defensively.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from research_engine import Bar, load_bars_csv  # noqa: E402

DATA_START = pd.Timestamp("2010-01-01 00:00")
DATA_END = pd.Timestamp("2026-04-09 00:00")      # exclusive — OOS PROTECTED
CUTOFF = DATA_END

COSTS = {"LOW": 1.0, "NORMAL": 2.0, "STRESS": 3.5}   # round-trip pips, SYNTHETIC

PIP_SIZE = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def filter_window(bars):
    """Strict defensive filter to [2010-01-01, 2026-04-09)."""
    out = [b for b in bars if DATA_START <= pd.Timestamp(b.dt) < DATA_END]
    if not out:
        raise ValueError("no bars inside the allowed window")
    return out


def load_pair_csv(csv_path):
    return filter_window(load_bars_csv(csv_path))


def bars_to_frame(bars):
    df = pd.DataFrame(
        {"open": [b.open for b in bars], "high": [b.high for b in bars],
         "low": [b.low for b in bars], "close": [b.close for b in bars]},
        index=pd.DatetimeIndex([b.dt for b in bars]),
    )
    return df


def aggregate(df_m15, rule):
    """Causal calendar-bucket aggregation (rule='1h' or '4h').

    open=first, high=max, low=min, close=last.  Buckets with zero bars do
    not exist; partially-filled buckets (market open/close hours) are kept
    as-is — they are real market bars, not fabricated ones.  Bucket label =
    bucket START; the bucket is only known at its END.
    """
    o = df_m15["open"].resample(rule).first()
    h = df_m15["high"].resample(rule).max()
    l = df_m15["low"].resample(rule).min()
    c = df_m15["close"].resample(rule).last()
    out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c}).dropna()
    return out


# ---------------------------------------------------------------------------
# Indicators (closed bars; value at index i uses data up to i inclusive)
# ---------------------------------------------------------------------------
def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"] - df["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


# ---------------------------------------------------------------------------
# Event study
# ---------------------------------------------------------------------------
@dataclass
class StudyResult:
    n: int
    mean: float
    median: float
    win_rate: float
    std: float
    mean_long: float
    mean_short: float
    n_long: int
    n_short: int

    def as_row(self):
        return {
            "N": self.n, "MEAN_PIPS": round(self.mean, 4),
            "MEDIAN_PIPS": round(self.median, 4),
            "WIN_RATE": round(self.win_rate, 4), "STD_PIPS": round(self.std, 3),
            "MEAN_LONG": round(self.mean_long, 4),
            "MEAN_SHORT": round(self.mean_short, 4),
            "N_LONG": self.n_long, "N_SHORT": self.n_short,
        }


def forward_returns(opens: np.ndarray, side: np.ndarray, horizons,
                    pip_size: float):
    """Signed open-to-open returns (pips) per horizon.

    side[i] != 0 marks an event decided at the OPEN of bar i (features from
    closed bars <= i-1).  Returns dict horizon -> raw pips array.
    """
    out = {}
    for h in horizons:
        if len(opens) <= h:
            out[h] = np.array([])
            continue
        base = opens[:-h]
        fwd = opens[h:]
        r = np.sign(side[:len(base)]) * (fwd - base) / pip_size
        ev = side[:len(base)] != 0
        out[h] = r[ev]
    return out


def summarize(raw: np.ndarray, side_at_events: np.ndarray):
    if len(raw) == 0:
        return StudyResult(0, float("nan"), float("nan"), float("nan"),
                           float("nan"), float("nan"), float("nan"), 0, 0)
    longs = raw[side_at_events > 0]
    shorts = raw[side_at_events < 0]
    return StudyResult(
        n=len(raw), mean=float(np.mean(raw)), median=float(np.median(raw)),
        win_rate=float(np.mean(raw > 0)), std=float(np.std(raw, ddof=1)) if len(raw) > 1 else 0.0,
        mean_long=float(np.mean(longs)) if len(longs) else float("nan"),
        mean_short=float(np.mean(shorts)) if len(shorts) else float("nan"),
        n_long=len(longs), n_short=len(shorts),
    )


# ---------------------------------------------------------------------------
# Signal families F1..F8 (all causal: features end at bar i-1)
# Each generator returns an int8 array side ∈ {-1,0,+1} of EVENT decisions
# (transitions only — no continuous re-firing).
# ---------------------------------------------------------------------------
def _cross(bool_series: np.ndarray) -> np.ndarray:
    """True where condition became True (False->True transition)."""
    prev = np.concatenate(([False], bool_series[:-1]))
    return bool_series & ~prev


def to_executable_side(side: np.ndarray) -> np.ndarray:
    """Shift signal side by one bar for causal execution.

    Family generators mark an event at the bar whose CLOSE makes the
    condition true.  That close is only known at the END of that bar, so
    the decision is executable at the OPEN of the NEXT bar.  Without this
    shift, forward returns would include the signal bar's own body
    (lookahead).  Muting bar 0 (no previous bar) keeps the array causal.
    """
    out = np.zeros(len(side), dtype=np.int8)
    out[1:] = side[:-1]
    return out


def f1_tsmom(df: pd.DataFrame, lookback: int) -> np.ndarray:
    c = df["close"].values
    mom = np.full(len(c), np.nan)
    mom[lookback:] = c[lookback:] - c[:-lookback]
    state = np.zeros(len(c), dtype=np.int8)
    with np.errstate(invalid="ignore"):
        state[mom > 0] = 1
        state[mom < 0] = -1
    prev_state = np.concatenate(([0], state[:-1]))
    return np.where((state != 0) & (state != prev_state), state, 0).astype(np.int8)


def f2_donchian(df: pd.DataFrame, lookback: int) -> np.ndarray:
    hi, lo, c = df["high"].values, df["low"].values, df["close"].values
    n = len(c)
    side = np.zeros(n, dtype=np.int8)
    # features strictly from bars <= i-2; decision bar close = i-1
    roll_hi = pd.Series(hi).shift(1).rolling(lookback).max().values
    roll_lo = pd.Series(lo).shift(1).rolling(lookback).min().values
    up_prev = c > roll_hi
    up = np.zeros(n, dtype=bool)
    up[1:] = up_prev[1:] & ~up_prev[:-1]          # crossing event
    dn_prev = c < roll_lo
    dn = np.zeros(n, dtype=bool)
    dn[1:] = dn_prev[1:] & ~dn_prev[:-1]
    side[up] = 1
    side[dn] = -1
    side[np.isnan(roll_hi) | np.isnan(roll_lo)] = 0
    return side


def f3_trend_pullback(df: pd.DataFrame, fast: int, slow: int, k: int = 3,
                      tol_atr: float = 0.25) -> np.ndarray:
    """Trend = close vs slow EMA + slow-EMA slope; entry = pullback into the
    fast EMA zone (normalized by ATR) then resumption in trend direction."""
    c = df["close"].values
    ef = ema(df["close"], fast).values
    es = ema(df["close"], slow).values
    a = atr(df).values
    lo_roll = pd.Series(df["low"].values).rolling(k).min().shift(1).values
    hi_roll = pd.Series(df["high"].values).rolling(k).max().shift(1).values
    es_prev = np.concatenate(([np.nan], es[:-1]))
    with np.errstate(invalid="ignore"):
        up_trend = (c > es) & (es >= es_prev)
        dn_trend = (c < es) & (es <= es_prev)
        up_cond = up_trend & (lo_roll <= ef + tol_atr * a) & (c > ef) & \
            ~np.isnan(lo_roll)
        dn_cond = dn_trend & (hi_roll >= ef - tol_atr * a) & (c < ef) & \
            ~np.isnan(hi_roll)
    side = np.zeros(len(c), dtype=np.int8)
    up_ev = np.zeros(len(c), dtype=bool)
    up_ev[1:] = up_cond[1:] & ~up_cond[:-1]
    dn_ev = np.zeros(len(c), dtype=bool)
    dn_ev[1:] = dn_cond[1:] & ~dn_cond[:-1]
    side[up_ev] = 1
    side[dn_ev] = -1
    return side


def f4_h4_trend_h1_entry(h1: pd.DataFrame, h4: pd.DataFrame, ema_h4: int = 50,
                         fast_h1: int = 20, k: int = 3,
                         tol_atr: float = 0.25) -> np.ndarray:
    """H4 trend (last CLOSED H4 bucket) + H1 pullback/resume entry."""
    c = h1["close"].values
    ef = ema(h1["close"], fast_h1).values
    a = atr(h1).values
    lo_roll = pd.Series(h1["low"].values).rolling(k).min().shift(1).values

    h4c = h4["close"].values
    h4e = ema(h4["close"], ema_h4).values
    # map each H1 bar to the last H4 bucket CLOSED at or before its open
    h4_end = h4.index + pd.Timedelta(hours=4)
    idx = np.searchsorted(h4_end.values, h1.index.values, side="right") - 1
    valid = idx >= 1                      # need one previous bucket for slope
    trend_up = np.zeros(len(c), dtype=bool)
    trend_dn = np.zeros(len(c), dtype=bool)
    vm = valid & ~np.isnan(h4e[idx]) & ~np.isnan(h4e[np.maximum(idx - 1, 0)])
    trend_up[vm] = h4c[idx[vm]] > h4e[idx[vm]]
    trend_dn[vm] = h4c[idx[vm]] < h4e[idx[vm]]

    ok = ~np.isnan(lo_roll) & ~np.isnan(a) & ~np.isnan(ef)
    touch = lo_roll <= ef + tol_atr * a
    resume = c > ef
    cond_up = trend_up & ok & touch & resume
    ev_up = np.zeros(len(c), dtype=bool)
    ev_up[1:] = cond_up[1:] & ~cond_up[:-1]
    hi_roll = pd.Series(h1["high"].values).rolling(k).max().shift(1).values
    touch_dn = hi_roll >= ef - tol_atr * a
    resume_dn = c < ef
    cond_dn = trend_dn & ok & touch_dn & resume_dn
    ev_dn = np.zeros(len(c), dtype=bool)
    ev_dn[1:] = cond_dn[1:] & ~cond_dn[:-1]

    side = np.zeros(len(c), dtype=np.int8)
    side[ev_up] = 1
    side[ev_dn] = -1
    return side


def f5_vol_compress_breakout(df: pd.DataFrame, lookback: int,
                             ratio: float, atr_c: int = 12,
                             atr_l: int = 48) -> np.ndarray:
    """Breakout crossing that follows a volatility compression."""
    base = f2_donchian(df, lookback)
    a_c = atr(df, atr_c).values
    a_l = atr(df, atr_l).values
    compress = (a_c / a_l) <= ratio
    compress &= ~np.isnan(a_l)
    side = base.copy()
    side[~compress] = 0
    return side


def f6_mean_reversion(df: pd.DataFrame, sma_len: int, z: float,
                      atr_n: int = 14) -> np.ndarray:
    """Event = first bar entering the extreme zone (|z| >= threshold)."""
    c = df["close"].values
    m = sma(df["close"], sma_len).values
    a = atr(df, atr_n).values
    zz = (c - m) / a
    long_zone = zz < -z
    short_zone = zz > z
    long_zone[np.isnan(zz)] = False
    short_zone[np.isnan(zz)] = False
    side = np.zeros(len(c), dtype=np.int8)
    side[_cross(long_zone)] = 1
    side[_cross(short_zone)] = -1
    return side


def f7_trend_strength(df: pd.DataFrame, fast: int, slow: int,
                      band: float) -> np.ndarray:
    c = df["close"].values
    ef = ema(df["close"], fast).values
    es = ema(df["close"], slow).values
    a = atr(df).values
    strength = np.abs(c - es) / a
    up = (c > es) & (ef > es) & (strength >= band)
    dn = (c < es) & (ef < es) & (strength >= band)
    up[np.isnan(strength)] = False
    dn[np.isnan(strength)] = False
    side = np.zeros(len(c), dtype=np.int8)
    side[_cross(up)] = 1
    side[_cross(dn)] = -1
    return side


def f8_breakout_expansion(df: pd.DataFrame, lookback: int,
                          ratio: float, atr_c: int = 12,
                          atr_l: int = 48) -> np.ndarray:
    """Breakout crossing occurring while volatility is already expanding."""
    base = f2_donchian(df, lookback)
    a_c = atr(df, atr_c).values
    a_l = atr(df, atr_l).values
    expand = (a_c / a_l) >= ratio
    expand &= ~np.isnan(a_l)
    side = base.copy()
    side[~expand] = 0
    return side
