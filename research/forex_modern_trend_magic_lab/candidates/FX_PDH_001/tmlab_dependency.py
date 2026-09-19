#!/usr/bin/env python3
"""FOREX_MODERN_TREND_MAGIC_LAB_M1 core library.

Source-faithful, causal Python translation of Trend Magic Enhanced
[AlgoAlpha] (see TREND_MAGIC_SOURCE_SPEC.md) + data layer with a hard
2026 seal.

Conventions (inherited from prior audited FX campaigns):
  * data_raw/parquet/<SYM>_5m.parquet holds 5m BID OHLCV, UTC-indexed,
    left-labelled bars; bar [t, t+5m) CLOSES at t+5m.
  * decisions only on bar close; features read bars closing <= T;
    forward returns start at the event bar's close.
  * HARD SEAL: no bar with end time > 2025-12-31 23:59:59 UTC may be
    returned by any loader (2026_ACCESSED=NO).
"""
from __future__ import annotations

import hashlib
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PARQUET_DIR = os.path.join(REPO, "data_raw", "parquet")
PINE_PATH = os.path.join(HERE, "TREND_MAGIC_PINE_ORIGINAL.pine")

# ---------------------------------------------------------------- seals / const
SEAL_UTC = pd.Timestamp("2025-12-31 23:59:59", tz="UTC")   # 2026 sealed
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "USDJPY": 1e-2}
PAIRS = ("EURUSD", "GBPUSD", "USDJPY")

# measured/conservative Dukascopy spread medians (pips), from prior campaign
SPREAD_PIPS = {"EURUSD": 0.6, "GBPUSD": 1.0, "USDJPY": 0.9}
SLIP_STRESS_PIPS = 0.5          # per side, stress scenario


class SealViolation(RuntimeError):
    pass


def assert_sealed(idx: pd.DatetimeIndex) -> None:
    """Hard guard: reject any data whose timestamps enter 2026."""
    if len(idx) and idx.max() > SEAL_UTC:
        raise SealViolation(f"2026 seal violated: last timestamp {idx.max()}")


def load_5m(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Load 5m BID bars with start <= bar_start <= end, hard-sealed at 2026.

    start/end are ISO strings interpreted as UTC bar-start labels.
    """
    path = os.path.join(PARQUET_DIR, f"{symbol}_5m.parquet")
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"{symbol}: parquet index is not a DatetimeIndex")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")
    df = df[~df.index.duplicated(keep="last")].sort_index()
    a = pd.Timestamp(start, tz="UTC")
    b = pd.Timestamp(end, tz="UTC")
    assert b <= SEAL_UTC + pd.Timedelta(minutes=5), "end must not enter 2026"
    df = df.loc[(df.index >= a) & (df.index <= b)]
    assert_sealed(df.index)             # seal the returned window
    return df[["open", "high", "low", "close", "volume"]].astype("float64")


def resample_ohlcv(df5: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Causal OHLCV resample: left-labelled, left-closed; bar closes at
    label + rule. Only complete bars are kept (empties dropped)."""
    out = df5.resample(rule, label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"))
    return out.dropna(subset=["open", "high", "low", "close"])


# ---------------------------------------------------------------- indicator
def true_range(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
    """Pine ta.tr(true): max(h-l, |h-c[-1]|, |l-c[-1]|); first bar h-l."""
    n = len(h)
    tr = np.empty(n)
    if n == 0:
        return tr
    tr[0] = h[0] - l[0]
    pc = c[:-1]
    tr[1:] = np.maximum.reduce([
        h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    return tr


def sma(x: np.ndarray, n: int) -> np.ndarray:
    """Rolling mean, min_periods=n (na until n bars)."""
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        cs = np.cumsum(np.insert(x.astype("float64"), 0, 0.0))
        out[n - 1:] = (cs[n:] - cs[:-n]) / n
    return out


def cci_pine(src: np.ndarray, n: int) -> np.ndarray:
    """Pine ta.cci: (src - SMA(src,n)) / (0.015 * MAD(src,n)),
    MAD = rolling mean absolute deviation about the same SMA (population)."""
    m = sma(src, n)
    out = np.full(len(src), np.nan)
    for i in range(n - 1, len(src)):
        w = src[i - n + 1:i + 1]
        mad = np.mean(np.abs(w - m[i]))
        if mad > 1e-12:      # constant window -> Pine division-by-0 -> na
            out[i] = (src[i] - m[i]) / (0.015 * mad)
    return out


def trend_magic(h: np.ndarray, l: np.ndarray, c: np.ndarray,
                cci_period: int = 20, atr_multiplier: float = 2.0,
                atr_period: int = 5, smooth_len: int = 14,
                smooth_type: str = "SMA", smoothing: bool = False,
                src: np.ndarray | None = None):
    """Full Trend Magic Enhanced computation (single causal pass).

    Returns (mt, direction, cci, vol):
      mt        ratcheted Trend Magic line (post-smoothing if enabled)
      direction trend state per bar in {-1, 0, +1} (0 = warm-up/undecided)
      cci, vol  raw CCI and SMA-of-TR volatility (pre-smoothing diagnostics)
    """
    h = np.asarray(h, "float64"); l = np.asarray(l, "float64")
    c = np.asarray(c, "float64")
    s = c if src is None else np.asarray(src, "float64")
    vol = sma(true_range(h, l, c), atr_period)
    cc = cci_pine(s, cci_period)

    n = len(c)
    mt = np.full(n, np.nan)             # Pine: na until VOL defined
    direction = np.zeros(n)             # Pine: var trendDirection = 0
    prev_dir = 0
    for i in range(n):
        prev_mt = 0.0 if i == 0 or np.isnan(mt[i - 1]) else mt[i - 1]
        if np.isnan(vol[i]):
            up = dn = np.nan
        else:
            up = l[i] - vol[i] * atr_multiplier
            dn = h[i] + vol[i] * atr_multiplier
        # Pine ternary semantics: na condition -> false branch.
        # bull: MT := (up < nz(MT[1])) ? nz(MT[1]) : up
        # bear: MT := (dn > nz(MT[1])) ? nz(MT[1]) : dn
        # if CCI na -> `cci >= 0` false -> bear branch (Pine quirk).
        if not np.isnan(cc[i]) and cc[i] >= 0:
            mt[i] = prev_mt if (not np.isnan(up) and up < prev_mt) else up
        else:
            mt[i] = prev_mt if (not np.isnan(dn) and dn > prev_mt) else dn
        # Pine crossover/crossunder vs the prior bar's line value; na -> false
        cross_up = i > 0 and l[i - 1] <= mt[i - 1] and l[i] > mt[i]
        cross_dn = i > 0 and h[i - 1] >= mt[i - 1] and h[i] < mt[i]
        if cross_up:
            prev_dir = 1
        elif cross_dn:
            prev_dir = -1
        direction[i] = prev_dir

    if smoothing:
        if smooth_type == "SMA":
            mt_s = sma(mt, smooth_len)
        elif smooth_type == "EMA":
            mt_s = _ema(mt, smooth_len)
        elif smooth_type == "SMMA (RMA)":
            mt_s = _rma(mt, smooth_len)
        else:
            raise NotImplementedError(f"smoothing {smooth_type} not needed "
                                      "(default OFF); only SMA/EMA/RMA wired")
        mt = mt_s
    return mt, direction.astype("int64"), cc, vol


def _ema(x: np.ndarray, n: int) -> np.ndarray:
    a = 2.0 / (n + 1.0)
    out = np.full(len(x), np.nan)
    acc = np.nan
    for i, v in enumerate(x):
        if np.isnan(v):
            continue
        acc = v if np.isnan(acc) else a * v + (1 - a) * acc
        out[i] = acc
    return out


def _rma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    acc = np.nan
    cnt = 0
    s = 0.0
    for i, v in enumerate(x):
        if np.isnan(v):
            continue
        if np.isnan(acc):
            s += v
            cnt += 1
            if cnt == n:
                acc = s / n
        else:
            acc = (acc * (n - 1) + v) / n
        out[i] = acc
    return out


def events_from_direction(direction: np.ndarray) -> np.ndarray:
    """Indices where the state changes. direction[0] is always 0 in a fresh
    computation (crossings need a prior bar), so every returned index is a
    genuine change; 0 -> ±1 counts (matches the script's alert semantics).
    """
    d = np.asarray(direction)
    if len(d) == 0:
        return np.array([], "int64")
    return np.nonzero(d[1:] != d[:-1])[0] + 1


# ---------------------------------------------------------------- event study
def forward_returns(close: np.ndarray, ev_idx: np.ndarray,
                    horizons: list[int]) -> dict[int, np.ndarray]:
    """Causal forward log-returns of close over `horizons` bars.

    ret[k] = close[i+h] - close[i] in *price* units is returned as
    log-return *sign-agnostic*; caller applies the signal direction.
    NA when the horizon runs past the end of the array.
    """
    c = np.asarray(close, "float64")
    out = {}
    for hz in horizons:
        r = np.full(len(ev_idx), np.nan)
        j = ev_idx[ev_idx + hz < len(c)]
        r[:len(j)] = np.log(c[j + hz] / c[j])
        out[hz] = r
    return out


def excursions(h: np.ndarray, l: np.ndarray, close: np.ndarray,
               ev_idx: np.ndarray, horizons: list[int],
               sign: np.ndarray) -> tuple[dict, dict]:
    """MFE/MAE (price units) within each horizon window, in signal direction.

    MFE_k[i] = max favourable move between event close (exclusive) and
    bar i+k (inclusive); MAE analogously adverse. Direction-adjusted so
    positive MFE = price moved in the trade's favour.
    """
    hh = np.asarray(h, "float64"); ll = np.asarray(l, "float64")
    c = np.asarray(close, "float64")
    mfe_all, mae_all = {}, {}
    for k, hz in enumerate(horizons):
        f = np.full(len(ev_idx), np.nan)
        a = np.full(len(ev_idx), np.nan)
        for m, i in enumerate(ev_idx):
            j = i + hz
            if j >= len(c):
                continue
            s = sign[m]
            best = np.max(hh[i + 1:j + 1] if s > 0 else ll[i + 1:j + 1])
            worst = np.min(ll[i + 1:j + 1] if s > 0 else hh[i + 1:j + 1])
            f[m] = s * (best - c[i])
            a[m] = s * (worst - c[i])      # <= 0 when adverse
        mfe_all[hz] = f
        mae_all[hz] = a
    return mfe_all, mae_all


def stats_bucket(ret: np.ndarray, price: np.ndarray,
                 pip: float) -> dict:
    """Mean/median/win-rate/SE/bootstrap CI + remove-best-1% for a bucket.

    `ret` log-returns, `price` price at event (same length), `pip` size.
    Returns stats in PIPS.
    """
    m = np.isfinite(ret)
    r = ret[m]
    p = price[m]
    n = len(r)
    if n == 0:
        return {"n": 0}
    pipsr = r * p / pip
    mean = float(np.mean(pipsr))
    med = float(np.median(pipsr))
    win = float(np.mean(pipsr > 0))
    se = float(np.std(pipsr, ddof=1) / np.sqrt(n)) if n > 1 else np.nan
    # bootstrap CI of the mean (2000 resamples, seeded)
    rng = np.random.default_rng(42)
    if n >= 30:
        idx = rng.integers(0, n, size=(2000, n))
        bm = pipsr[idx].mean(axis=1)
        lo, hi = np.percentile(bm, [2.5, 97.5])
        ci = [float(lo), float(hi)]
    else:
        ci = [np.nan, np.nan]
    # remove-best 1% (at least 1 event) at this bucket level
    k = max(1, int(round(0.01 * n)))
    part = np.sort(pipsr)[:-k] if n - k > 0 else pipsr
    rb1 = float(np.mean(part)) if len(part) else np.nan
    return {"n": int(n), "mean_pips": mean, "median_pips": med,
            "win_rate": win, "se_pips": se, "ci95": ci, "rm_best1pct": rb1}


def pine_source_sha256() -> str:
    with open(PINE_PATH, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
