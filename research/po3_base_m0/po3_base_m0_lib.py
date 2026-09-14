"""PO3-BASE-M0 core library: Asia-range sweep -> reintegration -> reversal engine.

Pure functions only — no network, no filesystem. All market timestamps are int64
nanoseconds UTC. Session times use Europe/London via the real IANA database
(zoneinfo). Implements exactly PO3_BASE_M0_FROZEN_SPEC.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

LONDON = ZoneInfo("Europe/London")
UTC = timezone.utc

PIP = 1e-4
MINUTE_NS = 60_000_000_000

# Frozen constants (spec section 20).
SWEEP_FRAC = 0.20
REINTEGRATION_LIMIT_NS = 900 * 1_000_000_000
ENTRY_DELAY_BASE_NS = 5 * 1_000_000_000
ENTRY_DELAY_STRESS_NS = 30 * 1_000_000_000
FILL_BOUND_NS = 30 * 1_000_000_000
TIME_EXIT_BOUND_NS = 60 * 1_000_000_000
TARGET_R = 2.0
SLIP_PER_SIDE_PIPS = 0.50
MIN_ASIA_TICKS = 3600
MAX_ASIA_GAP_S = 300.0
PF_CAP = 999.0
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42

# Discovery window (Europe/London dates) and hard UTC data guard.
DISCOVERY_FIRST = date(2010, 1, 4)
DISCOVERY_LAST = date(2018, 12, 31)
UTC_GUARD_START_NS = 1262304000_000000000   # 2010-01-01T00:00:00Z
UTC_GUARD_END_NS = 1546300800_000000000     # 2019-01-01T00:00:00Z

# Day outcome statuses.
NO_SWEEP = "NO_SWEEP"
NO_REINTEGRATION = "NO_REINTEGRATION"
DOUBLE_SWEEP_INVALID = "DOUBLE_SWEEP_INVALID"
NO_FILL = "NO_FILL"
INVALID_RISK = "INVALID_RISK"
TRADE = "TRADE"
NO_TIME_EXIT_DATA = "NO_TIME_EXIT_DATA"


class OutOfWindowError(RuntimeError):
    """Requested data escapes the Discovery guard (2019+ / protected OOS)."""


def assert_utc_range(start_ns: int, end_ns: int) -> None:
    if start_ns < UTC_GUARD_START_NS or end_ns > UTC_GUARD_END_NS:
        raise OutOfWindowError(
            f"range [{start_ns}, {end_ns}) escapes UTC guard "
            f"[{UTC_GUARD_START_NS}, {UTC_GUARD_END_NS})")


def assert_discovery_date(d: date) -> None:
    if not (DISCOVERY_FIRST <= d <= DISCOVERY_LAST):
        raise OutOfWindowError(f"date {d} escapes Discovery window")


def guard_partition_path(path: str) -> tuple[int, int]:
    """Refuse any parquet partition outside year=2010..2018 (2019+ FORBIDDEN)."""
    parts = dict(p.split("=", 1) for p in Path(path).parts if "=" in p)
    year, month = int(parts["year"]), int(parts["month"])
    if not (2010 <= year <= 2018):
        raise OutOfWindowError(f"forbidden partition: {path}")
    return year, month


def _london_ns(d: date, hour: int, minute: int) -> int:
    dt = datetime(d.year, d.month, d.day, hour, minute, tzinfo=LONDON)
    return int(dt.astimezone(UTC).timestamp()) * 1_000_000_000


@dataclass(frozen=True)
class DayBounds:
    day: date
    asia_start: int    # inclusive
    asia_end: int      # exclusive
    obs_start: int     # inclusive (07:00 London)
    obs_end: int       # exclusive (10:00 London)
    time_exit: int     # inclusive (12:00 London)
    slice_end: int     # inclusive data-slice end (12:36 London)


def day_bounds(d: date) -> DayBounds:
    """Frozen London wall-clock windows for one trading day, resolved via IANA tz."""
    assert_discovery_date(d)
    return DayBounds(
        day=d,
        asia_start=_london_ns(d, 0, 0), asia_end=_london_ns(d, 7, 0),
        obs_start=_london_ns(d, 7, 0), obs_end=_london_ns(d, 10, 0),
        time_exit=_london_ns(d, 12, 0), slice_end=_london_ns(d, 12, 36),
    )


def discovery_dates() -> list[date]:
    out, d = [], DISCOVERY_FIRST
    while d <= DISCOVERY_LAST:
        if d.weekday() < 5:  # Mon-Fri Europe/London
            out.append(d)
        d += timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# Asian range + eligibility
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AsianRange:
    high: float
    low: float
    range_: float
    n_ticks: int
    max_gap_s: float

    @property
    def eligible(self) -> bool:
        return (self.n_ticks >= MIN_ASIA_TICKS
                and self.max_gap_s <= MAX_ASIA_GAP_S
                and self.range_ > 0.0)


def asian_range(ts: np.ndarray, mid: np.ndarray, b: DayBounds) -> AsianRange:
    """MID extremes over [asia_start, asia_end); coverage with boundary pads."""
    i0 = int(np.searchsorted(ts, b.asia_start, side="left"))
    i1 = int(np.searchsorted(ts, b.asia_end, side="left"))
    seg_ts = ts[i0:i1]
    seg_mid = mid[i0:i1]
    n = len(seg_ts)
    if n == 0:
        return AsianRange(float("nan"), float("nan"), 0.0, 0, float("inf"))
    gaps = np.diff(np.concatenate(([b.asia_start], seg_ts, [b.asia_end]))).astype(np.float64) / 1e9
    return AsianRange(float(seg_mid.max()), float(seg_mid.min()),
                      float(seg_mid.max() - seg_mid.min()), n, float(gaps.max()))


# ---------------------------------------------------------------------------
# Setup detection: sweep -> reintegration decision (spec 6-8)
# ---------------------------------------------------------------------------

@dataclass
class Setup:
    status: str
    side: int = 0              # +1 upper sweep (SHORT trade), -1 lower sweep (LONG trade)
    sweep_ts: int = 0
    sweep_extreme: float = float("nan")   # stop level (MID)
    decision_ts: int = 0
    close_price: float = float("nan")
    sweep_latency_min: float = float("nan")  # 07:00 -> sweep_ts


def detect_setup(ts: np.ndarray, mid: np.ndarray, b: DayBounds,
                 rng: AsianRange) -> Setup:
    upper_thr = rng.high + SWEEP_FRAC * rng.range_
    lower_thr = rng.low - SWEEP_FRAC * rng.range_

    i = int(np.searchsorted(ts, b.obs_start, side="left"))
    i_end = int(np.searchsorted(ts, b.obs_end, side="left"))
    if i >= i_end:
        return Setup(status=NO_SWEEP)
    seg = mid[i:i_end]
    up_hit = seg >= upper_thr
    lo_hit = seg <= lower_thr
    both = up_hit | lo_hit
    if not both.any():
        return Setup(status=NO_SWEEP)
    k = int(np.argmax(both))
    sweep_i = i + k
    side = 1 if up_hit[k] else -1
    sweep_ts = int(ts[sweep_i])
    extreme = float(seg[k])
    limit = sweep_ts + REINTEGRATION_LIMIT_NS

    # Event loop: candle completions (bucket ends) precede ticks at >= bucket end.
    pending_bucket = sweep_ts // MINUTE_NS
    decision_ts = 0
    close_price = float("nan")
    status = ""
    j = sweep_i + 1
    n = len(ts)
    while True:
        if j >= n:
            # Final candle completes as a wall-clock event, no later tick needed.
            end = (pending_bucket + 1) * MINUTE_NS
            if end <= limit:
                close = float(mid[j - 1])
                if (close < rng.high) if side > 0 else (close > rng.low):
                    decision_ts, close_price, status = end, close, "OK"
            break
        tj = int(ts[j])
        t_bucket = tj // MINUTE_NS
        if t_bucket > pending_bucket:
            end = (pending_bucket + 1) * MINUTE_NS
            if end > limit:
                status = NO_REINTEGRATION
                break
            close = float(mid[j - 1])  # last tick of pending bucket
            if (close < rng.high) if side > 0 else (close > rng.low):
                decision_ts, close_price, status = end, close, "OK"
                break
            pending_bucket = t_bucket
        if side > 0:
            extreme = max(extreme, float(mid[j]))
            if mid[j] <= lower_thr:
                status = DOUBLE_SWEEP_INVALID
                break
        else:
            extreme = min(extreme, float(mid[j]))
            if mid[j] >= upper_thr:
                status = DOUBLE_SWEEP_INVALID
                break
        j += 1

    if status == "OK":
        return Setup(status=TRADE, side=side, sweep_ts=sweep_ts,
                     sweep_extreme=extreme, decision_ts=decision_ts,
                     close_price=close_price,
                     sweep_latency_min=(sweep_ts - b.obs_start) / 60e9)
    if status == "":
        status = NO_REINTEGRATION
    return Setup(status=status, side=side, sweep_ts=sweep_ts,
                 sweep_extreme=extreme,
                 sweep_latency_min=(sweep_ts - b.obs_start) / 60e9)


# ---------------------------------------------------------------------------
# Execution (spec 9-12): side-accurate, tick-chronological
# ---------------------------------------------------------------------------

@dataclass
class Execution:
    status: str                 # TRADE / NO_FILL / INVALID_RISK / NO_TIME_EXIT_DATA
    entry_ts: int = 0
    entry_px: float = float("nan")
    stop: float = float("nan")
    target: float = float("nan")
    r: float = float("nan")
    exit_type: str = ""         # STOP / TARGET / TIME
    exit_ts: int = 0
    exit_px: float = float("nan")
    net_pips: float = float("nan")
    stop_gap_pips: float = 0.0  # adverse gap beyond stop level at stop exit
    entry_idx: int = -1
    time_idx: int = -1          # index of first tick at/after 12:00 (diagnostics)


def execute(ts: np.ndarray, bid: np.ndarray, ask: np.ndarray,
            direction: int, stop: float, decision_ts: int,
            delay_ns: int, time_exit_ns: int) -> Execution:
    """First executable tick at/after decision+delay; frozen stop/target/time exits.

    LONG (+1): entry ASK, stop/target/time on BID. SHORT (-1): entry BID, exits ASK.
    """
    ref = decision_ts + delay_ns
    i = int(np.searchsorted(ts, ref, side="left"))
    if i >= len(ts) or ts[i] > ref + FILL_BOUND_NS:
        return Execution(status=NO_FILL)
    entry_px = float(ask[i] if direction > 0 else bid[i])
    if direction > 0 and entry_px <= stop:
        return Execution(status=INVALID_RISK)
    if direction < 0 and entry_px >= stop:
        return Execution(status=INVALID_RISK)
    r = abs(entry_px - stop)
    target = entry_px + TARGET_R * r if direction > 0 else entry_px - TARGET_R * r

    exit_side = bid if direction > 0 else ask
    if direction > 0:
        stop_hits = np.nonzero(exit_side[i:] <= stop)[0]
        tgt_hits = np.nonzero(exit_side[i:] >= target)[0]
    else:
        stop_hits = np.nonzero(exit_side[i:] >= stop)[0]
        tgt_hits = np.nonzero(exit_side[i:] <= target)[0]

    t_rel = int(np.searchsorted(ts[i:], time_exit_ns, side="left"))
    time_i = i + t_rel
    has_time = time_i < len(ts)
    if has_time and ts[time_i] >= time_exit_ns + TIME_EXIT_BOUND_NS:
        has_time = False  # quote bound: no tick within [12:00, 12:01) London

    events = []
    if len(stop_hits):
        events.append((i + int(stop_hits[0]), 0))   # priority 0: stop
    if len(tgt_hits):
        events.append((i + int(tgt_hits[0]), 1))    # priority 1: target
    if has_time:
        events.append((time_i, 2))
    if not events:
        return Execution(status=NO_TIME_EXIT_DATA, entry_ts=int(ts[i]),
                         entry_px=entry_px, stop=stop, target=target, r=r,
                         entry_idx=i)
    events.sort(key=lambda e: (e[0], e[1]))
    win_i, kind = events[0]
    if kind == 0:
        exit_px = float(exit_side[win_i])
        exit_type = "STOP"
        gap = (stop - exit_px) * direction / PIP
    elif kind == 1:
        exit_px = float(target)  # favorable overshoot capped at target
        exit_type = "TARGET"
        gap = 0.0
    else:
        exit_px = float(exit_side[win_i])
        exit_type = "TIME"
        gap = 0.0
    net_pips = (exit_px - entry_px) * direction / PIP
    return Execution(status=TRADE, entry_ts=int(ts[i]), entry_px=entry_px,
                     stop=stop, target=target, r=r, exit_type=exit_type,
                     exit_ts=int(ts[win_i]), exit_px=exit_px, net_pips=net_pips,
                     stop_gap_pips=float(gap), entry_idx=i, time_idx=time_i)


# ---------------------------------------------------------------------------
# Diagnostics (spec 14) — descriptive only
# ---------------------------------------------------------------------------

def mfe_r(ts: np.ndarray, bid: np.ndarray, ask: np.ndarray, ex: Execution,
          direction: int, horizon_min: float) -> float:
    """Max favorable excursion in R within [entry, entry+X], capped at time exit."""
    if ex.status != TRADE or ex.time_idx < 0 or ex.entry_idx < 0:
        return float("nan")
    end = ex.entry_ts + int(horizon_min * 60 * 1e9)
    j = min(int(np.searchsorted(ts, end, side="right")), ex.time_idx + 1)
    seg = (bid if direction > 0 else ask)[ex.entry_idx:j]
    if len(seg) == 0:
        return float("nan")
    best = float(seg.max()) if direction > 0 else float(seg.min())
    return (best - ex.entry_px) * direction / ex.r


def reaches_kr_before_stop(ts: np.ndarray, bid: np.ndarray, ask: np.ndarray,
                           ex: Execution, direction: int, k: float) -> bool:
    """True iff the exit-side price reaches entry+k*R before the stop event
    (scan capped at the time-exit tick; tie -> stop)."""
    if ex.status != TRADE or ex.time_idx < 0 or ex.entry_idx < 0:
        return False
    side = bid if direction > 0 else ask
    level = ex.entry_px + k * ex.r if direction > 0 else ex.entry_px - k * ex.r
    hit = np.nonzero(side[ex.entry_idx:ex.time_idx + 1] >= level)[0] \
        if direction > 0 else \
        np.nonzero(side[ex.entry_idx:ex.time_idx + 1] <= level)[0]
    stop_hit = np.nonzero(side[ex.entry_idx:ex.time_idx + 1] <= ex.stop)[0] \
        if direction > 0 else \
        np.nonzero(side[ex.entry_idx:ex.time_idx + 1] >= ex.stop)[0]
    i_hit = int(hit[0]) if len(hit) else math.inf
    i_stop = int(stop_hit[0]) if len(stop_hit) else math.inf
    return i_hit < i_stop  # tie -> stop wins (defensive; exit-side conditions are
    # mutually exclusive at a single tick, so a true tie cannot occur)


# ---------------------------------------------------------------------------
# Metrics (spec 13)
# ---------------------------------------------------------------------------

def profit_factor(nets: np.ndarray) -> float:
    wins = float(nets[nets > 0].sum())
    losses = float(-nets[nets < 0].sum())
    return PF_CAP if losses == 0 else wins / losses


def remove_best_1pct_mean(vals: np.ndarray) -> float:
    v = np.sort(np.asarray(vals, dtype=np.float64))
    n = len(v)
    if n == 0:
        return float("nan")
    k = max(1, int(math.ceil(0.01 * n)))
    return float(v[: n - k].mean())


def bootstrap_ci95_mean(vals: np.ndarray, n_resamples: int = BOOTSTRAP_N,
                        seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    v = np.asarray(vals, dtype=np.float64)
    n = len(v)
    if n == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_resamples, n))
    means = v[idx].mean(axis=1)
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def max_drawdown_r(r_mults: np.ndarray) -> float:
    eq = np.cumsum(np.asarray(r_mults, dtype=np.float64))
    if len(eq) == 0:
        return 0.0
    peaks = np.maximum.accumulate(np.concatenate(([0.0], eq)))
    dd = np.concatenate(([0.0], eq)) - peaks
    return float(-dd.min())


def max_consecutive_losses(nets: np.ndarray) -> int:
    best = cur = 0
    for x in nets:
        if x < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def positive_years(entry_ts_ns: np.ndarray, nets: np.ndarray) -> tuple[int, int]:
    yrs = (entry_ts_ns.astype("datetime64[ns]").astype("datetime64[Y]").astype(np.int64)
           + 1970)
    eligible = sorted(set(int(v) for v in yrs))
    positive = sum(1 for yr in eligible if float(nets[yrs == yr].sum()) > 0)
    return positive, len(eligible)
