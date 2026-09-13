#!/usr/bin/env python3
"""TICK-M1 microstructure research library.

Implements the FROZEN definitions of
`research/tick_m1_microstructure/TICK_M1_FROZEN_HYPOTHESES.md` exactly:

- month-partitioned parquet loading with <=15-min causal/future context padding
  (context months are always inside the Discovery window; year>=2019 is NEVER
  opened),
- causal feature primitives F1..F8 at every decision tick,
- frozen event filters (gap<=60s, rollover exclusion [21:00,21:05) UTC,
  discovery boundary),
- greedy chronological non-overlap suppression per horizon,
- bid/ask execution (LONG: ask in, bid out; SHORT: bid in, ask out), real
  spread charged by construction, adverse-only slippage stress,
- frozen metric set incl. remove-best-1%, bootstrap CI95, stress, direction
  balance, time-of-day distribution.

Processing is chunked by month; nothing here ever holds the full 9 years.
"""
import os

import numpy as np
import pandas as pd

NS = 1_000_000_000
S10, S30, S60 = 10 * NS, 30 * NS, 60 * NS
S600 = 600 * NS
GAP_MAX_NS = 60 * NS
PAD_NS = 900 * NS  # 15-min context padding on each side of a month

DISCOVERY_START_NS = int(pd.Timestamp("2010-01-01T00:00:00Z").value)
DISCOVERY_END_NS = int(pd.Timestamp("2019-01-01T00:00:00Z").value)  # exclusive, HARD CUT
YEARS = list(range(2010, 2019))  # 9 discovery years

PIPS = 1e-4


# ---------------------------------------------------------------- loading

def assert_month_in_discovery(year, month):
    """Hard guard: no partition outside 2010-01..2018-12 may ever be opened."""
    if not (2010 <= year <= 2018 and 1 <= month <= 12):
        raise ValueError(f"month {year}-{month:02d} outside DISCOVERY window "
                         f"(2010-01 .. 2018-12); 2019+ is forbidden")


def _read_partition(pdir, symbol, year, month):
    assert_month_in_discovery(year, month)
    f = os.path.join(pdir, symbol, f"year={year:04d}", f"month={month:02d}", "ticks.parquet")
    if not os.path.exists(f):
        return None
    df = pd.read_parquet(f, columns=["timestamp_utc", "bid", "ask", "mid",
                                     "spread_pips", "bid_volume", "ask_volume"])
    return df


def load_month_padded(pdir, symbol, year, month):
    """Arrays for [month_start - PAD, month_end + PAD). Next-month pad is
    skipped for 2018-12 (never reads 2019). Decision ticks are restricted to
    the month itself by the caller via `month_mask`."""
    assert_month_in_discovery(year, month)
    start = int(pd.Timestamp(f"{year:04d}-{month:02d}-01T00:00:00Z").value)
    end = int((pd.Timestamp(f"{year:04d}-{month:02d}-01T00:00:00Z")
               + pd.offsets.MonthBegin(1)).value)  # first day of next month
    parts = []
    # previous-month tail (context for causal features); none exists for the
    # very first discovery month (2009-12 is outside the window and never read)
    has_prev = not (year == 2010 and month == 1)
    if has_prev:
        if month == 1:
            assert_month_in_discovery(year - 1, 12)
            prev = _read_partition(pdir, symbol, year - 1, 12)
        else:
            prev = _read_partition(pdir, symbol, year, month - 1)
        if prev is not None:
            prev = prev[prev["timestamp_utc"].astype("int64") >= start - PAD_NS]
            parts.append(prev)
    cur = _read_partition(pdir, symbol, year, month)
    if cur is not None:
        parts.append(cur)
    # next-month head (ONLY for exit fills of events decided inside the month)
    if not (year == 2018 and month == 12):
        if month == 12:
            nxt = _read_partition(pdir, symbol, year + 1, 1)
        else:
            nxt = _read_partition(pdir, symbol, year, month + 1)
        if nxt is not None:
            nxt = nxt[nxt["timestamp_utc"].astype("int64") < end + PAD_NS]
            parts.append(nxt)
    if not parts:
        z = np.array([], dtype=np.int64)
        return {"ts": z, "bid": np.array([]), "ask": np.array([]), "mid": np.array([]),
                "spread": np.array([]), "bv": np.array([]), "av": np.array([]),
                "month_start": start, "month_end": end}
    df = pd.concat(parts, ignore_index=True)
    df = df.sort_values("timestamp_utc", kind="stable")
    ts = df["timestamp_utc"].astype("int64").to_numpy()
    return {"ts": ts,
            "bid": df["bid"].to_numpy(np.float64),
            "ask": df["ask"].to_numpy(np.float64),
            "mid": df["mid"].to_numpy(np.float64),
            "spread": df["spread_pips"].to_numpy(np.float64),
            "bv": df["bid_volume"].to_numpy(np.float64),
            "av": df["ask_volume"].to_numpy(np.float64),
            "month_start": start, "month_end": end}


# ---------------------------------------------------------------- features

def compute_features(d):
    """Frozen primitives F1..F8 at every tick of the padded arrays.
    NaN/False = undefined (such ticks can never become events)."""
    ts = d["ts"]
    n = len(ts)
    out = {"n": n}
    if n == 0:
        return out
    t10 = ts - S10
    t600 = ts - S600
    lo10 = np.searchsorted(ts, t10, side="left")
    lo600 = np.searchsorted(ts, t600, side="left")
    idx = np.arange(n, dtype=np.int64)

    # F1: ticks in [t-10s, t]
    f1 = idx - lo10 + 1
    # F2: ticks in [t-600s, t-10s) / 59
    f2 = (lo10 - lo600) / 59.0
    with np.errstate(divide="ignore", invalid="ignore"):
        f3 = np.where(f2 > 0, f1 / f2, np.nan)
    out["f1"], out["f3"] = f1.astype(np.float64), f3

    # F4: r10 = mid(t) - mid(last tick <= t-10s), pips
    r_idx = np.searchsorted(ts, t10, side="right") - 1
    ok = r_idx >= 0
    r10 = np.full(n, np.nan)
    r10[ok] = (d["mid"][ok] - d["mid"][r_idx[ok]]) / PIPS
    out["f4"] = r10

    # F5: median of per-minute median spread over the 10 complete minutes
    # before the minute of t; >=8 of 10 must exist.
    minute = (ts // (60 * NS)).astype(np.int64)
    sp = pd.Series(d["spread"])
    grp = sp.groupby(pd.Series(minute)).median()
    if len(grp):
        full = pd.RangeIndex(int(minute.min()), int(minute.max()) + 1)
        s = grp.reindex(full)
        base = s.shift(1).rolling(10, min_periods=8).median()
        f5 = base.reindex(pd.Series(minute)).to_numpy()
    else:
        f5 = np.full(n, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        out["f6"] = np.where(f5 > 0, d["spread"] / f5, np.nan)

    # F7: imb30 over [t-30s, t]
    lo30 = np.searchsorted(ts, ts - S30, side="left")
    cbv = np.concatenate([[0.0], np.cumsum(d["bv"])])
    cav = np.concatenate([[0.0], np.cumsum(d["av"])])
    BV = cbv[idx + 1] - cbv[lo30]
    AV = cav[idx + 1] - cav[lo30]
    tot = BV + AV
    n30 = (idx - lo30 + 1).astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        f7 = np.where(tot > 0, (BV - AV) / tot, np.nan)
    f7 = np.where(n30 >= 5, f7, np.nan)
    out["f7"] = f7

    # F8: qdir30 — consecutive-pair quote moves with later tick in [t-30s, t]
    if n >= 2:
        db = np.zeros(n)
        da = np.zeros(n)
        db[1:] = d["bid"][1:] - d["bid"][:-1]
        da[1:] = d["ask"][1:] - d["ask"][:-1]
        upb = np.zeros(n)
        upa = np.zeros(n)
        dnb = np.zeros(n)
        dna = np.zeros(n)
        upb[1:] = (db[1:] > 0).astype(np.float64)
        upa[1:] = (da[1:] > 0).astype(np.float64)
        dnb[1:] = (db[1:] < 0).astype(np.float64)
        dna[1:] = (da[1:] < 0).astype(np.float64)
        C = lambda a: np.concatenate([[0.0], np.cumsum(a)])
        cub, cua = C(upb), C(upa)
        cdnb, cdna = C(dnb), C(dna)
        CU = (cub[idx + 1] - cub[lo30]) + (cua[idx + 1] - cua[lo30])
        DN = (cdnb[idx + 1] - cdnb[lo30]) + (cdna[idx + 1] - cdna[lo30])
        moves = CU + DN
        with np.errstate(divide="ignore", invalid="ignore"):
            f8 = np.where(moves > 0, (CU - DN) / moves, np.nan)
        f8 = np.where(moves >= 8, f8, np.nan)
    else:
        f8 = np.full(n, np.nan)
    out["f8"] = f8

    # frozen validity filters
    gap_prev = np.full(n, np.inf)
    gap_prev[1:] = ts[1:] - ts[:-1]
    minute_of_day = ((ts // (60 * NS)) % 1440).astype(np.int64)
    rollover = (minute_of_day >= 21 * 60) & (minute_of_day < 21 * 60 + 5)
    out["valid_base"] = ((gap_prev <= GAP_MAX_NS) & (~rollover)
                         & (ts >= d["month_start"]) & (ts < d["month_end"]))
    years = pd.DatetimeIndex(pd.to_datetime(ts, utc=True)).year.to_numpy()
    out["year"] = years
    tod_hour = ((ts // (3600 * NS)) % 24).astype(np.int64)
    out["tod_bucket"] = (tod_hour // 4).astype(np.int8)
    return out


# ---------------------------------------------------------------- events

def build_events(feat, d, cfg):
    """Vectorized trigger + greedy chronological overlap suppression +
    frozen execution. Returns dict with per-event arrays."""
    ts, n = d["ts"], feat["n"]
    if n == 0:
        return None
    base = feat["valid_base"]
    trig = np.zeros(n, dtype=bool)
    k = cfg["kind"]
    if k == "H1":
        trig = base & (feat["f3"] >= 3.0) & (feat["f1"] >= 10) & (np.abs(feat["f4"]) >= 0.20)
        direction = np.sign(feat["f4"])
    elif k == "H2":
        trig = base & (feat["f6"] <= 0.8) & (feat["f3"] >= 2.0) & (np.abs(feat["f4"]) >= 0.20)
        direction = np.sign(feat["f4"])
    elif k == "H3":
        trig = base & (feat["f6"] >= 2.0) & (d["spread"] >= 1.0) & (np.abs(feat["f4"]) >= 0.20)
        direction = -np.sign(feat["f4"])
    elif k == "H4":
        trig = base & ((feat["f7"] >= 0.30) | (feat["f7"] <= -0.30))
        direction = np.sign(feat["f7"])
    elif k == "H5":
        trig = base & ((feat["f8"] >= 0.30) | (feat["f8"] <= -0.30))
        direction = np.sign(feat["f8"])
    elif k == "H6":
        trig = (base & (feat["f3"] >= 3.0) & (feat["f1"] >= 10)
                & (np.abs(feat["f4"]) >= 0.20)
                & (np.abs(feat["f7"]) >= 0.10)
                & (np.sign(feat["f7"]) == np.sign(feat["f4"])))
        direction = np.sign(feat["f4"])
    else:
        raise ValueError(k)

    H = cfg["horizon_ns"]
    cand = np.flatnonzero(trig & (direction != 0))
    if len(cand) == 0:
        return {"n_raw": 0, "n_nonoverlap": 0, "n_skipped_no_exit": 0}
    cand_ts = ts[cand]
    # greedy chronological: accept, then first candidate strictly after t+H
    pos = np.searchsorted(cand_ts, ts[cand] + H, side="right")
    accepted = []
    i = 0
    while i < len(cand):
        accepted.append(i)
        i = pos[i]
    acc = cand[np.array(accepted, dtype=np.int64)]
    acc_ts = ts[acc]

    # exit: last tick <= t+H, strictly after decision, and t+H inside discovery
    e_idx = np.searchsorted(ts, acc_ts + H, side="right") - 1
    ok_exit = (e_idx > acc) & ((acc_ts + H) < DISCOVERY_END_NS)
    acc, acc_ts, e_idx = acc[ok_exit], acc_ts[ok_exit], e_idx[ok_exit]
    n_skipped = int((~ok_exit).sum())

    direction = direction[acc]
    long = direction > 0
    net = np.where(long,
                   (d["bid"][e_idx] - d["ask"][acc]) / PIPS,
                   (d["ask"][e_idx] - d["bid"][acc]) / PIPS)
    gross = direction * (d["mid"][e_idx] - d["mid"][acc]) / PIPS
    return {
        "n_raw": int(trig.sum()),
        "n_nonoverlap": int(len(acc)),
        "n_skipped_no_exit": n_skipped,
        "net": net,
        "gross": gross,
        "year": feat["year"][acc],
        "tod": feat["tod_bucket"][acc],
        "is_long": long,
    }


# ---------------------------------------------------------------- metrics

def remove_best_1pct(net):
    k = int(np.ceil(0.01 * len(net)))
    if k >= len(net):
        return float("nan")
    s = np.sort(net)
    return float(s[:len(s) - k].mean())


def bootstrap_ci95(net, n_res=2000, seed=42, cap=200_000):
    """Percentile bootstrap of the mean; deterministic (seed 42). For very
    large N a deterministic stride subsample (<=cap) is used first, per the
    frozen spec."""
    rng = np.random.default_rng(seed)
    x = net
    if len(x) > cap:
        stride = int(np.ceil(len(x) / cap))
        x = x[::stride]
    n = len(x)
    if n == 0:
        return (float("nan"), float("nan"))
    means = np.empty(n_res, dtype=np.float64)
    for i in range(n_res):
        means[i] = x[rng.integers(0, n, n)].mean()
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def one_sided_p(net):
    if len(net) < 2:
        return 1.0
    se = net.std(ddof=1) / np.sqrt(len(net))
    if se == 0:
        return 1.0 if net.mean() <= 0 else 0.0
    from math import erf, sqrt
    z = net.mean() / se
    return 0.5 * (1.0 + erf(-z / sqrt(2.0)))


def bh_fdr(pvals):
    """Benjamini-Hochberg adjusted q-values."""
    p = np.asarray(pvals, dtype=np.float64)
    m = len(p)
    order = np.argsort(p)
    ranked = p[order] * m / (np.arange(1, m + 1))
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(m)
    out[order] = np.minimum(q, 1.0)
    return out


def config_metrics(name, cfg, ev):
    if ev is None or ev["n_nonoverlap"] == 0:
        return {"config": name, **cfg_lite(cfg), "n_raw": ev["n_raw"] if ev else 0,
                "n_nonoverlap": 0, "n_skipped_no_exit": ev["n_skipped_no_exit"] if ev else 0,
                "pass_gate": False}
    net = ev["net"]
    year = ev["year"]
    year_means = {}
    for y in YEARS:
        m = year == y
        year_means[str(y)] = round(float(net[m].mean()), 4) if m.any() else None
    pos_years = sum(1 for v in year_means.values() if v is not None and v > 0)
    ci_lo, ci_hi = bootstrap_ci95(net)
    mean_net = float(net.mean())
    stress01 = mean_net - 0.20
    stress025 = mean_net - 0.50
    res = {
        "config": name,
        **cfg_lite(cfg),
        "n_raw": ev["n_raw"],
        "n_nonoverlap": ev["n_nonoverlap"],
        "n_skipped_no_exit": ev["n_skipped_no_exit"],
        "mean_net_pips": round(mean_net, 4),
        "median_net_pips": round(float(np.median(net)), 4),
        "win_rate": round(float((net > 0).mean()), 4),
        "mean_gross_mid_pips": (round(float(ev["gross"].mean()), 4)
                                if ev.get("gross") is not None else None),
        "positive_years": pos_years,
        "year_means": year_means,
        "remove_best_1pct_mean": round(remove_best_1pct(net), 4),
        "ci95_lo": round(ci_lo, 4),
        "ci95_hi": round(ci_hi, 4),
        "stress_net_010_per_side": round(stress01, 4),
        "stress_net_025_per_side": round(stress025, 4),
        "pct_long": round(float(ev["is_long"].mean()), 4),
        "tod_counts_4h_utc": {f"h{h:02d}-{h+4:02d}": int((ev["tod"] == b).sum())
                              for b, h in enumerate(range(0, 24, 4))},
        "one_sided_p": float(one_sided_p(net)),
    }
    res["pass_gate"] = bool(
        res["mean_net_pips"] >= 0.30 and pos_years >= 6
        and res["remove_best_1pct_mean"] > 0
        and res["stress_net_010_per_side"] > 0
        and res["n_nonoverlap"] >= 500)
    return res


def cfg_lite(cfg):
    return {"hyp": cfg["kind"], "horizon_s": cfg["horizon_ns"] // NS}
