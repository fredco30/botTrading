#!/usr/bin/env python3
"""TRI-TICK-M0 library: multi-symbol tick decode, causal synchronization,
triangular mid residual and executable cycle diagnostics.

Reuses the validated TICK-M0 20-byte big-endian record decode:
  uint32 ms-in-hour, uint32 ask, uint32 bid, float32 ask_vol, float32 bid_vol.
Per-symbol point scaling is validated empirically (candidates below), never
assumed blindly (Dukascopy FX pairs here are expected 1e5 but proven first).

Quotes convention (price of 1 unit of BASE in QUOTE currency):
  EURUSD = USD per EUR, GBPUSD = USD per GBP, EURGBP = GBP per EUR.

Executable conversion sides (buy base -> use ASK of that pair;
sell base -> use BID of that pair):
  USD->GBP : buy GBP  => divide by ASK(GBPUSD)     [GBPUSD = USD/GBP]
  GBP->USD : sell GBP => multiply by BID(GBPUSD)
  USD->EUR : buy EUR  => divide by ASK(EURUSD)     [EURUSD = USD/EUR]
  EUR->USD : sell EUR => multiply by BID(EURUSD)
  GBP->EUR : buy EUR  => divide by ASK(EURGBP)     [EURGBP = GBP/EUR]
  EUR->GBP : sell EUR => multiply by BID(EURGBP)

Cycle A (USD -> GBP -> EUR -> USD):
  1 USD / ASK(GBPUSD) = x GBP ; x GBP / ASK(EURGBP) = y EUR ; y EUR * BID(EURUSD)
  A = BID(EURUSD) / (ASK(GBPUSD) * ASK(EURGBP))

Cycle B (USD -> EUR -> GBP -> USD):
  1 USD / ASK(EURUSD) = e EUR ; e EUR * BID(EURGBP) = g GBP ; g GBP * BID(GBPUSD)
  B = BID(EURGBP) * BID(GBPUSD) / ASK(EURUSD)

Perfect internally-consistent triangle with zero spread => A == B == 1.
With mids consistent and realistic positive spreads => A <= 1 and B <= 1.
"""
import lzma
import os
import struct
from datetime import datetime

import numpy as np

RECORD_SIZE = 20
REC_DTYPE = [("ms", ">u4"), ("a", ">u4"), ("b", ">u4"), ("av", ">f4"), ("bv", ">f4")]
POINT_CANDIDATES = [1e5, 1e3, 1.0]
MS = 1_000_000  # ns per ms
NS = 1
SEC = 1_000_000_000
HOUR_NS = 3_600 * SEC
PIP = 1e-4  # all three pairs are 5-decimal FX pairs; 1 pip = 1e-4

SYMBOLS = ("EURUSD", "GBPUSD", "EURGBP")
PLAUSIBLE = {"EURUSD": (0.5, 2.5), "GBPUSD": (0.5, 2.5), "EURGBP": (0.3, 1.5)}


# ---------------------------------------------------------------- decode ----
def decompress_file(path):
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) == 0:
        return b""  # 0-byte marker: hour with no ticks
    return lzma.decompress(raw, format=lzma.FORMAT_ALONE)


def hour_start_ns(y, m, d, h):
    dt = datetime(y, m, d, h, tzinfo=None).replace(tzinfo=None)
    return int((datetime(y, m, d, h) - datetime(1970, 1, 1)).total_seconds()) * SEC


def decode_buf(buf, base_ns, point, lo=0.0, hi=np.inf, strict=False):
    """Decode one hour buffer to arrays. Prices scaled by `point`."""
    if len(buf) % RECORD_SIZE != 0:
        raise ValueError(f"buffer {len(buf)} bytes not divisible by {RECORD_SIZE}")
    if len(buf) == 0:
        return {k: np.array([], dtype=np.float64)
                for k in ("timestamp_ns", "ask", "bid", "ask_volume", "bid_volume")}
    recs = np.frombuffer(buf, dtype=REC_DTYPE)
    ts = base_ns + recs["ms"].astype(np.int64) * MS
    out = {
        "timestamp_ns": ts,
        "ask": recs["a"].astype(np.float64) / point,
        "bid": recs["b"].astype(np.float64) / point,
        "ask_volume": recs["av"].astype(np.float64),
        "bid_volume": recs["bv"].astype(np.float64),
    }
    if strict:
        errs = validate_arrays(out, base_ns, lo, hi)
        if errs:
            raise ValueError("; ".join(errs))
    return out


def validate_arrays(t, base_ns, lo, hi):
    errs = []
    ts = t["timestamp_ns"]
    if len(ts) and np.any(np.diff(ts) < 0):
        errs.append("non-monotone timestamps")
    if len(ts) and (ts.min() < base_ns or ts.max() >= base_ns + HOUR_NS):
        errs.append("timestamps outside hour bounds")
    if np.any(t["ask"] < t["bid"]):
        errs.append("ASK < BID present")
    if np.any(t["ask_volume"] < 0) or np.any(t["bid_volume"] < 0):
        errs.append("negative volumes")
    if len(t["bid"]) and (t["bid"].min() < lo or t["bid"].max() > hi):
        errs.append(f"price outside plausible range [{lo},{hi}]")
    return errs


def pick_scaling(buf, base_ns, plausible):
    """Empirically pick point scaling: fewest validation errors wins."""
    best = None
    for p in POINT_CANDIDATES:
        try:
            t = decode_buf(buf, base_ns, p)
        except ValueError:
            return None, ["record size mismatch"]
        errs = validate_arrays(t, base_ns, plausible[0], plausible[1])
        if best is None or len(errs) < len(best[1]):
            best = (p, errs)
        if not errs:
            break
    return best


def load_symbol_week(raw_root, symbol, days, point=None):
    """Load a week of hourly .bi5 into concatenated arrays.

    days: list of (y, m, d). Returns (arrays dict, per-hour audit list).
    Hour audit entry: dict(y,m,d,h,status in ok/empty/missing/corrupt,n_ticks).
    """
    raw_dir = os.path.join(raw_root, "raw", symbol)
    frames = []
    audit = []
    chosen_point = point
    for (y, m, d) in days:
        day_dir = os.path.join(raw_dir, f"{y:04d}{m:02d}{d:02d}")
        for h in range(24):
            p = os.path.join(day_dir, f"{h:02d}h_ticks.bi5")
            entry = {"y": y, "m": m, "d": d, "h": h, "n_ticks": 0, "status": "ok"}
            if not os.path.exists(p):
                entry["status"] = "missing"
                audit.append(entry)
                continue
            try:
                buf = decompress_file(p)
            except Exception:
                entry["status"] = "corrupt"
                audit.append(entry)
                continue
            if len(buf) == 0:
                entry["status"] = "empty"
                audit.append(entry)
                continue
            base_ns = hour_start_ns(y, m, d, h)
            if chosen_point is None:
                pt, errs = pick_scaling(buf, base_ns, PLAUSIBLE[symbol])
                if pt is None or errs:
                    entry["status"] = "corrupt"
                    audit.append(entry)
                    continue
                chosen_point = pt
            try:
                t = decode_buf(buf, base_ns, chosen_point, *PLAUSIBLE[symbol], strict=True)
            except ValueError:
                entry["status"] = "corrupt"
                audit.append(entry)
                continue
            entry["n_ticks"] = len(t["timestamp_ns"])
            frames.append(t)
            audit.append(entry)
    if frames:
        out = {k: np.concatenate([f[k] for f in frames]) for k in frames[0]}
    else:
        out = {k: np.array([], dtype=np.float64) for k in frames[0]} if frames else {
            k: np.array([], dtype=np.float64)
            for k in ("timestamp_ns", "ask", "bid", "ask_volume", "bid_volume")}
    audit.sort(key=lambda e: (e["y"], e["m"], e["d"], e["h"]))
    return out, audit, chosen_point


# ----------------------------------------------------------------- sync -----
def causal_snapshot(sym_ts, sym_bid, sym_ask, grid_ns):
    """Latest quote with quote_ts <= grid_t, per grid point. No future quotes.

    Returns (idx, ts_quote, bid, ask). idx == -1 where no prior quote exists
    (grid start before first tick); those rows are dropped by the caller.
    """
    idx = np.searchsorted(sym_ts, grid_ns, side="right") - 1
    valid = idx >= 0
    return (idx,
            np.where(valid, sym_ts[np.clip(idx, 0, None)], -1),
            sym_bid[np.clip(idx, 0, None)],
            sym_ask[np.clip(idx, 0, None)])


def build_snapshots(feeds, grid_ns):
    """feeds: {sym: arrays}. Returns dict with merged snapshot arrays
    (only grid points where all three pairs have a prior quote)."""
    parts = {}
    for sym, t in feeds.items():
        idx, qts, bid, ask = causal_snapshot(t["timestamp_ns"], t["bid"], t["ask"], grid_ns)
        parts[sym] = (idx, qts, bid, ask)
    ok = np.ones(len(grid_ns), dtype=bool)
    for sym in parts:
        ok &= parts[sym][0] >= 0
    g = grid_ns[ok]
    out = {"grid_ns": g}
    for sym in parts:
        idx, qts, bid, ask = parts[sym]
        out[f"ts_{sym}"] = qts[ok]
        out[f"bid_{sym}"] = bid[ok]
        out[f"ask_{sym}"] = ask[ok]
        out[f"age_{sym}_ms"] = (g - qts[ok]) / MS
    out["max_age_ms"] = np.max(np.stack([out[f"age_{s}_ms"] for s in parts]), axis=0)
    for s in parts:
        out[f"mid_{s}"] = (out[f"bid_{s}"] + out[f"ask_{s}"]) / 2.0
    if set(parts) == set(SYMBOLS):
        out["synth_mid"] = out["mid_EURGBP"] * out["mid_GBPUSD"]
        out["resid_pips"] = (out["mid_EURUSD"] - out["synth_mid"]) / PIP
        out["cycle_A"] = out["bid_EURUSD"] / (out["ask_GBPUSD"] * out["ask_EURGBP"])
        out["cycle_B"] = (out["bid_EURGBP"] * out["bid_GBPUSD"]) / out["ask_EURUSD"]
    return out


def grid_series(start_ns, end_ns, step_ms):
    return np.arange(start_ns, end_ns, step_ms * MS, dtype=np.int64)


# ------------------------------------------------------------- episodes -----
def positive_episode_durations_ns(cycle_vals, grid_ns):
    pos = cycle_vals > 1.0
    if not pos.any():
        return np.array([], dtype=np.int64)
    step = grid_ns[1] - grid_ns[0] if len(grid_ns) > 1 else 0
    starts = np.flatnonzero(np.r_[pos[0], np.diff(pos.astype(int)) == 1])
    ends = np.flatnonzero(np.r_[np.diff(pos.astype(int)) == -1, pos[-1]])
    return grid_ns[ends] - grid_ns[starts] + step


# ------------------------------------------------------------ lead/lag ------
def lead_lag_corr(a, b, lags_ms, step_ms):
    """corr(a[t], b[t+lag]) for each lag. lag<0 => b leads a.

    Series are uniform-grid (NaN where snapshots missing, e.g. market closed);
    correlations use pairwise-complete observations.
    """
    step = step_ms
    out = []
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    for lag in lags_ms:
        k = int(lag // step)
        if k >= 0:
            x, y = a[:len(a) - k if k else None], b[k:]
        else:
            k = -k
            x, y = a[k:], b[:len(b) - k]
        m = np.isfinite(x) & np.isfinite(y)
        if m.sum() < 100:
            out.append((lag, np.nan, int(m.sum())))
            continue
        xs, ys = x[m], y[m]
        if xs.std() == 0 or ys.std() == 0:
            out.append((lag, np.nan, int(m.sum())))
            continue
        c = float(np.corrcoef(xs, ys)[0, 1])
        out.append((lag, c, int(m.sum())))
    return out


def pct(a, q):
    return float(np.percentile(a, q)) if len(a) else float("nan")


def spread_stats_pips(bid, ask):
    sp = (ask - bid) / PIP
    return {
        "median": pct(sp, 50), "p95": pct(sp, 95), "p99": pct(sp, 99),
        "max": float(sp.max()) if len(sp) else float("nan"),
    }


def ticks_per_min_stats(ts):
    if len(ts) == 0:
        return {"median": float("nan"), "p95": float("nan")}
    mins = ts // (60 * SEC)
    uniq, counts = np.unique(mins, return_counts=True)
    return {"median": pct(counts, 50), "p95": pct(counts, 95)}


def resid_stats_pips(resid, mask=None):
    x = resid if mask is None else resid[mask]
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return {"n": 0}
    return {
        "n": int(len(x)), "mean": float(x.mean()), "median": pct(x, 50),
        "std": float(x.std()), "p01": pct(x, 1), "p05": pct(x, 5),
        "p95": pct(x, 95), "p99": pct(x, 99), "min": float(x.min()),
        "max": float(x.max()), "mean_abs": float(np.abs(x).mean()),
        "p95_abs": pct(np.abs(x), 95),
    }


def cycle_stats_bp(cycle_vals, mask=None):
    x = cycle_vals if mask is None else cycle_vals[mask]
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return {"n": 0}
    r = (x - 1.0) * 1e4  # bp
    return {
        "n": int(len(x)),
        "mean_bp": float(r.mean()), "median_bp": pct(r, 50),
        "p95_bp": pct(r, 95), "p99_bp": pct(r, 99), "max_bp": float(r.max()),
        "count_gt_0": int((r > 0).sum()),
        "count_gt_0_5bp": int((r > 0.5).sum()),
        "count_gt_1bp": int((r > 1.0).sum()),
    }
