"""S001 — GBPUSD London / Asian-range breakout — causal backtest library.

Frozen spec: S001_FROZEN_SPEC.md (commit 1 of research/s001-gbpusd-london-breakout).
Discovery window 2010-01-01 (incl) -> 2019-01-01 (excl), Europe/London hours,
causal 5m OHLC execution, stop-first on same-bar ambiguity, costs 2/4 pips.
"""

import numpy as np
import pandas as pd

PIP = 0.0001
COST_NORMAL = 2.0
COST_STRESS = 4.0
TP_R_MULT = 1.5
ASIAN_END_MIN = 7 * 60        # [00:00, 07:00) London
SIGNAL_START_MIN = 8 * 60     # signal bars: open time in [08:00, 11:00) London
SIGNAL_END_MIN = 11 * 60
TIME_EXIT_MIN = 12 * 60       # exit at open of first bar >= 12:00 London
DISCOVERY_START = pd.Timestamp("2010-01-01", tz="UTC")
DISCOVERY_END = pd.Timestamp("2019-01-01", tz="UTC")
N_DISCOVERY_YEARS = 9
SEED = 42
N_BOOT = 2000

# Reasons
R_TARGET = "TARGET"
R_STOP = "STOP"
R_STOP_FIRST = "STOP_FIRST"
R_STOP_GAP = "STOP_GAP"
R_TIME_1200 = "TIME_1200"
R_TIME_FALLBACK = "TIME_FALLBACK_LAST_CLOSE"

LOSS_REASONS = {R_STOP, R_STOP_FIRST, R_STOP_GAP}


def load_discovery_bars(parquet_path):
    """Load 5m parquet and slice to the Discovery window immediately.

    Guarantees no 2019+ price ever enters the pipeline.
    """
    bars = pd.read_parquet(parquet_path)
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("parquet index must be a DatetimeIndex")
    bars = bars.sort_index()
    bars = bars.loc[(bars.index >= DISCOVERY_START) & (bars.index < DISCOVERY_END)]
    if bars.index.max() >= DISCOVERY_END or bars.index.min() < DISCOVERY_START:
        raise AssertionError("discovery window contamination")
    return bars[["open", "high", "low", "close"]].copy()


def _day_frame(bars):
    """Precompute London-date ordinals and London minutes-of-day."""
    ldn = bars.index.tz_convert("Europe/London")
    day_ord = ldn.tz_localize(None).values.astype("datetime64[D]")
    time_min = np.asarray(ldn.hour * 60 + ldn.minute, dtype=np.int64)
    return day_ord, time_min


def run_backtest(bars):
    """Run the frozen S001 rule over a UTC-indexed OHLC frame.

    Returns (trades, meta). Trades are chronological dicts, one max per
    London day.
    """
    o = bars["open"].to_numpy(dtype=float)
    h = bars["high"].to_numpy(dtype=float)
    l = bars["low"].to_numpy(dtype=float)
    c = bars["close"].to_numpy(dtype=float)
    idx = bars.index
    day_ord, time_min = _day_frame(bars)

    unique_days = np.unique(day_ord)
    bounds = np.searchsorted(day_ord, unique_days)
    bounds = np.append(bounds, len(day_ord))

    trades = []
    n_days_with_range = 0
    n_time_fallback = 0

    for k in range(len(unique_days)):
        i0, i1 = bounds[k], bounds[k + 1]
        d = unique_days[k]

        asian = (time_min[i0:i1] >= 0) & (time_min[i0:i1] < ASIAN_END_MIN)
        if not asian.any():
            continue
        asian_idx = i0 + np.flatnonzero(asian)
        asian_high = h[asian_idx].max()
        asian_low = l[asian_idx].min()
        n_days_with_range += 1

        sig_win = (time_min[i0:i1] >= SIGNAL_START_MIN) & (
            time_min[i0:i1] < SIGNAL_END_MIN
        )
        sig_rel = np.flatnonzero(sig_win)
        if sig_rel.size == 0:
            continue

        sig_i = None
        direction = None
        for rel in sig_rel:
            j = i0 + rel
            if c[j] > asian_high:
                sig_i, direction = j, "LONG"
                break
            if c[j] < asian_low:
                sig_i, direction = j, "SHORT"
                break
        if sig_i is None:
            continue

        e = sig_i + 1
        if e >= i1:  # entry bar must exist within the same London day
            continue
        entry = o[e]
        if direction == "LONG":
            stop = asian_low
            risk = entry - stop
        else:
            stop = asian_high
            risk = stop - entry
        risk_pips = risk / PIP
        if not np.isfinite(risk_pips) or risk_pips <= 0:
            continue
        if direction == "LONG":
            target = entry + TP_R_MULT * risk
        else:
            target = entry - TP_R_MULT * risk

        exit_px = None
        reason = None
        for j in range(e, i1):
            if time_min[j] >= TIME_EXIT_MIN:
                exit_px, reason = o[j], R_TIME_1200
                break
            if direction == "LONG":
                if o[j] <= stop:
                    exit_px, reason = o[j], R_STOP_GAP
                    break
                if o[j] >= target:
                    exit_px, reason = target, R_TARGET
                    break
                if l[j] <= stop and h[j] >= target:
                    exit_px, reason = stop, R_STOP_FIRST
                    break
                if l[j] <= stop:
                    exit_px, reason = stop, R_STOP
                    break
                if h[j] >= target:
                    exit_px, reason = target, R_TARGET
                    break
            else:
                if o[j] >= stop:
                    exit_px, reason = o[j], R_STOP_GAP
                    break
                if o[j] <= target:
                    exit_px, reason = target, R_TARGET
                    break
                if h[j] >= stop and l[j] <= target:
                    exit_px, reason = stop, R_STOP_FIRST
                    break
                if h[j] >= stop:
                    exit_px, reason = stop, R_STOP
                    break
                if l[j] <= target:
                    exit_px, reason = target, R_TARGET
                    break
        if exit_px is None:  # degenerate: day data ends before 12:00 London
            exit_px, reason = c[i1 - 1], R_TIME_FALLBACK
            n_time_fallback += 1

        if direction == "LONG":
            gross_pips = (exit_px - entry) / PIP
        else:
            gross_pips = (entry - exit_px) / PIP

        entry_ts = idx[e]
        trades.append(
            {
                "date": str(np.datetime64(d, "D")),
                "year": int(pd.Timestamp(d).year),
                "direction": direction,
                "entry_ts": entry_ts,
                "entry": entry,
                "exit_ts": idx[j],
                "exit": exit_px,
                "stop": stop,
                "target": target,
                "risk_pips": risk_pips,
                "gross_pips": gross_pips,
                "net_normal": gross_pips - COST_NORMAL,
                "net_stress": gross_pips - COST_STRESS,
                "r_multiple": (gross_pips - COST_NORMAL) / risk_pips,
                "reason": reason,
            }
        )

    meta = {
        "n_days_with_range": n_days_with_range,
        "n_time_fallback": n_time_fallback,
        "first_bar": str(idx.min()),
        "last_bar": str(idx.max()),
        "n_bars": int(len(bars)),
    }
    return trades, meta


def _profit_factor(net):
    wins = net[net > 0].sum()
    losses = -net[net < 0].sum()
    if losses == 0:
        return float("inf") if wins > 0 else float("nan")
    return float(wins / losses)


def _max_consecutive_losses(net):
    best = cur = 0
    for x in net:
        if x < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _max_drawdown(net):
    eq = np.cumsum(net)
    peak = np.maximum.accumulate(np.append(0.0, eq))[:-1]
    dd = peak - eq
    return float(dd.max()) if len(dd) else 0.0


def remove_best_1_percent(x):
    """Repo convention (P042): mean after dropping floor(N*1%) best trades."""
    x = np.sort(np.asarray(x, dtype=float))
    k = int(np.floor(len(x) * 0.01))
    return float(x[: len(x) - k].mean()) if 0 < len(x) - k else float("nan")


def ci95_mean(x, n_boot=N_BOOT, seed=SEED):
    rng = np.random.default_rng(seed)
    x = np.asarray(x, dtype=float)
    means = [rng.choice(x, size=len(x), replace=True).mean() for _ in range(n_boot)]
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def compute_metrics(trades, meta):
    if not trades:
        return {"n_trades": 0, "classification": "S001_DISCOVERY_REJECT", **meta}

    df = pd.DataFrame(trades)
    net = df["net_normal"].to_numpy(dtype=float)
    gross = df["gross_pips"].to_numpy(dtype=float)
    stress = df["net_stress"].to_numpy(dtype=float)
    risk = df["risk_pips"].to_numpy(dtype=float)

    winners = net > 0
    years_expected = list(range(2010, 2019))
    by_year = []
    for y in years_expected:
        sub = df[df["year"] == y]
        if len(sub):
            by_year.append(
                {
                    "year": y,
                    "n": int(len(sub)),
                    "net_pips": round(float(sub["net_normal"].sum()), 2),
                    "mean_net": round(float(sub["net_normal"].mean()), 4),
                    "profit_factor": round(_profit_factor(sub["net_normal"].to_numpy()), 4),
                }
            )
        else:
            by_year.append({"year": y, "n": 0, "net_pips": 0.0, "mean_net": 0.0,
                            "profit_factor": float("nan")})

    positive_years = sum(1 for r in by_year if r["net_pips"] > 0)
    mean_net = float(net.mean())
    pf_normal = _profit_factor(net)
    rm1 = remove_best_1_percent(net)
    ci_lo, ci_hi = ci95_mean(net)

    m = {
        **meta,
        "n_trades": int(len(df)),
        "trades_per_year": round(len(df) / N_DISCOVERY_YEARS, 2),
        "gross_mean_pips": round(gross.mean(), 4),
        "net_normal_mean_pips": round(mean_net, 4),
        "net_stress_mean_pips": round(stress.mean(), 4),
        "median_net_pips": round(float(np.median(net)), 4),
        "win_rate": round(float(winners.mean()), 4),
        "avg_win_pips": round(float(net[winners].mean()), 4) if winners.any() else 0.0,
        "avg_loss_pips": round(float(net[~winners].mean()), 4) if (~winners).any() else 0.0,
        "profit_factor_normal": None if np.isnan(pf_normal) else round(pf_normal, 4),
        "expectancy_r_normal": round(float((net / risk).mean()), 4),
        "total_net_pips": round(float(net.sum()), 2),
        "max_drawdown_pips": round(_max_drawdown(net), 2),
        "max_consecutive_losses": _max_consecutive_losses(net),
        "positive_years": positive_years,
        "n_years": N_DISCOVERY_YEARS,
        "by_year": by_year,
        "remove_best_1_percent_net_mean": round(rm1, 4),
        "ci95_mean_net_normal": [round(ci_lo, 4), round(ci_hi, 4)],
        "reason_counts": df["reason"].value_counts().to_dict(),
        "direction_counts": df["direction"].value_counts().to_dict(),
    }

    criteria = {
        "c1_mean_gt_2": mean_net > 2.0,
        "c2_pf_ge_1_20": bool(np.isfinite(pf_normal) and pf_normal >= 1.20),
        "c3_expectancy_gt_0_10R": m["expectancy_r_normal"] > 0.10,
        "c4_positive_years_ge_6": positive_years >= 6,
        "c5_remove_best_gt_0": rm1 > 0,
        "c6_total_net_gt_0": m["total_net_pips"] > 0,
    }
    m["criteria"] = {k: bool(v) for k, v in criteria.items()}
    m["classification"] = (
        "S001_DISCOVERY_PROMISING" if all(criteria.values())
        else "S001_DISCOVERY_REJECT"
    )
    return m


def run_discovery(parquet_path):
    bars = load_discovery_bars(parquet_path)
    trades, meta = run_backtest(bars)
    return compute_metrics(trades, meta), trades
