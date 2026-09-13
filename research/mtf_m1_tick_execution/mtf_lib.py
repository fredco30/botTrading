#!/usr/bin/env python3
"""MTF-M1 library: causal M15/H1/H4 mid bars from monthly tick parquet +
tick-accurate BID/ASK execution for the three frozen strategies of
`MTF_M1_FROZEN_SPEC.md` (commit 7dd5a02, which froze every rule used here).

Design mirrors TICK-M1: month-partitioned processing, 2019+ partitions are
never opened (hard guard), nothing holds the full 9 years in RAM.

Units: timestamps are int64 nanoseconds UTC; prices float64; 1 pip = 1e-4.
"""
import os
from collections import OrderedDict

import numpy as np
import pandas as pd

NS = 1_000_000_000
PIP = 1e-4
TF_NS = {"M15": 900 * NS, "H1": 3600 * NS, "H4": 14400 * NS}

LATENCY_NS = 250 * 1_000_000          # frozen: 250 ms
NO_FILL_WINDOW_NS = 3600 * NS         # frozen: entry search bound 1 hour
GAP_NS = 3600 * NS                    # frozen: data-gap threshold 1 hour
# Implementation precision for the frozen INVALID_STOP rule ("stop not beyond
# entry in the correct direction"): prices live on a 1e-5 grid and mid stops
# on a 5e-6 grid, so the smallest geometric entry-stop distance is 0.05 pip.
# Anything below that is floating-point noise on the SAME price, not a stop.
MIN_RISK_PIPS = 0.05
DISCOVERY_START_NS = int(pd.Timestamp("2010-01-01T00:00:00Z").value)
DISCOVERY_END_NS = int(pd.Timestamp("2019-01-01T00:00:00Z").value)  # HARD CUT
YEARS = list(range(2010, 2019))       # 9 discovery years

# frozen weekend window: every week [Fri 21:59:00Z, Sun 22:01:00Z)
WEEKEND_START_S = 21 * 3600 + 59 * 60                 # Friday 00:00 -> 21:59:00
WEEKEND_LEN_S = (2 * 24 * 3600) + (2 * 60)            # -> Sunday 22:01:00
DAY_NS = 86400 * NS


# ------------------------------------------------------------------ guards

def assert_month_in_discovery(year, month):
    """Hard guard: no partition outside 2010-01..2018-12 may ever be opened."""
    if not (2010 <= year <= 2018 and 1 <= month <= 12):
        raise ValueError(f"month {year}-{month:02d} outside DISCOVERY window "
                         f"(2010-01 .. 2018-12); 2019+ is forbidden")


def month_range_ns(year, month):
    start = int(pd.Timestamp(f"{year:04d}-{month:02d}-01T00:00:00Z").value)
    end = int((pd.Timestamp(f"{year:04d}-{month:02d}-01T00:00:00Z")
               + pd.offsets.MonthBegin(1)).value)
    return start, end


# ------------------------------------------------------- weekend / gaps

def weekend_windows(t1, t2):
    """Weekend windows [Fri 21:59:00Z, Sun 22:01:00Z) overlapping [t1, t2)."""
    dow = ((t1 // DAY_NS) + 3) % 7          # epoch Thu; Mon=0 .. Sun=6
    days_since_fri = (dow - 4) % 7
    friday0 = (t1 // DAY_NS) * DAY_NS - days_since_fri * DAY_NS
    out = []
    for k in (-1, 0, 1, 2):
        ws = friday0 + k * 7 * DAY_NS + WEEKEND_START_S * NS
        we = ws + WEEKEND_LEN_S * NS
        if we > t1 and ws < t2:
            out.append((ws, we))
    return sorted(out)


def non_weekend_duration(t1, t2):
    """Portion of [t1, t2) lying outside the frozen weekend windows."""
    segs = [(t1, t2)]
    for ws, we in weekend_windows(t1, t2):
        nxt = []
        for a, b in segs:
            if we <= a or ws >= b:
                nxt.append((a, b))
                continue
            if a < ws:
                nxt.append((a, min(ws, b)))
            if b > we:
                nxt.append((max(we, a), b))
        segs = nxt
    return sum(b - a for a, b in segs)


def is_data_gap(t1, t2):
    """Frozen rule: inter-tick delta whose non-weekend portion exceeds 1 h."""
    return (t2 - t1) > GAP_NS and non_weekend_duration(t1, t2) > GAP_NS


def detect_gaps(month_ts_iter):
    """GAP LIST from an ordered iterable of per-month sorted tick timestamps
    (ns arrays); one tick of context is carried across month boundaries."""
    gaps = []
    prev_last = None
    for ts in month_ts_iter:
        if len(ts) == 0:
            continue
        if prev_last is not None and is_data_gap(int(prev_last), int(ts[0])):
            gaps.append((int(prev_last), int(ts[0])))
        d = np.diff(ts)
        for i in np.flatnonzero(d > GAP_NS):
            t1, t2 = int(ts[i]), int(ts[i + 1])
            if is_data_gap(t1, t2):
                gaps.append((t1, t2))
        prev_last = ts[-1]
    return gaps


def gap_starts_array(gaps):
    return np.array([g[0] for g in gaps], dtype=np.int64) if gaps else \
        np.array([], dtype=np.int64)


def mark_gap_bars(bar_start, tf_ns, gaps):
    """Frozen gap-affected-bar rule: bar [t, t+TF) invalid iff a gap (g1,g2)
    has g1 < t+TF and g2 > t. Returns boolean array."""
    flags = np.zeros(len(bar_start), dtype=bool)
    if len(bar_start) == 0:
        return flags
    bar_end = bar_start + tf_ns
    for g1, g2 in gaps:
        lo = int(np.searchsorted(bar_end, g1, side="right"))
        hi = int(np.searchsorted(bar_start, g2, side="left"))
        if hi > lo:
            flags[lo:hi] = True
    return flags


# ------------------------------------------------------------- bar build

def bars_from_ticks(ts, mid, tf_ns):
    """Left-labelled bars [t, t+TF) on the UTC grid, from sorted ticks."""
    if len(ts) == 0:
        z = np.array([], dtype=np.int64)
        return {"start": z, "open": np.array([]), "high": np.array([]),
                "low": np.array([]), "close": np.array([]),
                "n_ticks": z.astype(np.int64)}
    ids = ts // tf_ns
    bounds = np.flatnonzero(np.diff(ids)) + 1
    starts_idx = np.concatenate(([0], bounds))
    ends_idx = np.concatenate((bounds, [len(ts)]))
    return {
        "start": (ids[starts_idx] * tf_ns).astype(np.int64),
        "open": mid[starts_idx],
        "high": np.maximum.reduceat(mid, starts_idx),
        "low": np.minimum.reduceat(mid, starts_idx),
        "close": mid[ends_idx - 1],
        "n_ticks": (ends_idx - starts_idx).astype(np.int64),
    }


# ----------------------------------------------------------- indicators

def ema(x, period):
    """Frozen EMA: e_1 = x_1, e_t = e_{t-1} + (2/(p+1))(x_t - e_{t-1})."""
    return pd.Series(x).ewm(alpha=2.0 / (period + 1), adjust=False).mean().to_numpy()


def atr14(high, low, close):
    """Frozen Wilder ATR14: first ATR = mean TR_1..TR_14, then
    ATR_t = (13*ATR_{t-1} + TR_t)/14. NaN until the 14th bar."""
    return _wilder_smooth_trailing(atr14_components(high, low, close), 14)


def atr14_components(high, low, close):
    """True-range series; TR_1 = H-L."""
    n = len(high)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    prev_c = close[:-1]
    tr[1:] = np.maximum.reduce([
        (high - low)[1:],
        np.abs(high[1:] - prev_c),
        np.abs(low[1:] - prev_c)])
    return tr


def _wilder_smooth_trailing(x, period):
    """RMA: seed = simple mean of the first `period` VALUES (leading NaNs are
    skipped, e.g. DX is only defined from the 14th bar), placed at the index
    of that last seed value; then s_t = (s_{t-1}*(period-1) + x_t)/period."""
    n = len(x)
    out = np.full(n, np.nan)
    finite = np.flatnonzero(np.isfinite(x))
    if len(finite) < period:
        return out
    f = int(finite[0])
    a = float(np.mean(x[f:f + period]))
    out[f + period - 1] = a
    for i in range(f + period, n):
        a = (a * (period - 1) + x[i]) / period
        out[i] = a
    return out


def adx14(high, low, close):
    """Frozen Wilder ADX14. NaN until the 27th bar."""
    n = len(high)
    up = np.zeros(n)
    dn = np.zeros(n)
    up[1:] = high[1:] - high[:-1]
    dn[1:] = low[:-1] - low[1:]
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr = _wilder_smooth_trailing(atr14_components(high, low, close), 14)
    s_plus = _wilder_smooth_trailing(plus_dm, 14)
    s_minus = _wilder_smooth_trailing(minus_dm, 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * s_plus / atr
        minus_di = 100.0 * s_minus / atr
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    dx = np.where(np.isfinite(dx), dx, np.nan)
    return _wilder_smooth_trailing(dx, 14)


def bollinger(close, period=20, num=2.0):
    """Frozen Bollinger: SMA20 +/- 2 * population std (ddof=0), window
    includes the current bar. NaN until `period` bars."""
    s = pd.Series(close)
    mid = s.rolling(period).mean()
    sd = s.rolling(period).std(ddof=0)
    return (mid.to_numpy(), (mid - num * sd).to_numpy(), (mid + num * sd).to_numpy())


# -------------------------------------------------------------- loading

def read_month_ticks(pdir, symbol, year, month, columns=None):
    assert_month_in_discovery(year, month)
    f = os.path.join(pdir, symbol, f"year={year:04d}", f"month={month:02d}",
                     "ticks.parquet")
    if not os.path.exists(f):
        return None
    if columns is None:
        columns = ["timestamp_utc", "bid", "ask"]
    df = pd.read_parquet(f, columns=columns)
    return df


def iter_month_tick_ts(pdir, symbol):
    for y in range(2010, 2019):
        for m in range(1, 13):
            df = read_month_ticks(pdir, symbol, y, m, columns=["timestamp_utc"])
            if df is None:
                continue
            yield df["timestamp_utc"].astype("int64").to_numpy()


class TickStore:
    """LRU month-partition tick access; never holds the full history and
    never opens 2019+ partitions. Serves time-sliced numpy ranges."""

    def __init__(self, pdir, symbol="EURUSD", max_months=4):
        self.pdir = pdir
        self.symbol = symbol
        self.max_months = max_months
        self._cache = OrderedDict()

    def _month_arrays(self, year, month):
        key = (year, month)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        assert_month_in_discovery(year, month)
        df = read_month_ticks(self.pdir, self.symbol, year, month)
        if df is None:
            a = (np.array([], dtype=np.int64), np.array([]), np.array([]))
        else:
            a = (df["timestamp_utc"].astype("int64").to_numpy(),
                 df["bid"].to_numpy(np.float64),
                 df["ask"].to_numpy(np.float64))
        self._cache[key] = a
        while len(self._cache) > self.max_months:
            self._cache.popitem(last=False)
        return a

    def get_range(self, t_from, t_to):
        """Ticks with t_from <= ts < t_to, clipped to 2010-01..2018-12."""
        ts_parts, bid_parts, ask_parts = [], [], []
        y, m = 2010, 1
        # skip to the month containing t_from
        while y < 2019:
            ms, me = month_range_ns(y, m)
            if t_from < me:
                break
            m += 1
            if m == 13:
                y, m = y + 1, 1
        while y < 2019:
            ms, me = month_range_ns(y, m)
            if ms >= t_to:
                break
            arr = self._month_arrays(y, m)
            if len(arr[0]):
                a = max(ms, t_from)
                b = min(me, t_to)
                if b > a:
                    i0 = int(np.searchsorted(arr[0], a, side="left"))
                    i1 = int(np.searchsorted(arr[0], b, side="left"))
                    if i1 > i0:
                        ts_parts.append(arr[0][i0:i1])
                        bid_parts.append(arr[1][i0:i1])
                        ask_parts.append(arr[2][i0:i1])
            m += 1
            if m == 13:
                y, m = y + 1, 1
        if not ts_parts:
            return (np.array([], dtype=np.int64), np.array([]), np.array([]))
        return (np.concatenate(ts_parts), np.concatenate(bid_parts),
                np.concatenate(ask_parts))


# ------------------------------------------------------------- strategies

def h4_regime_at(h4_close_ts, ema50_h4, ema200_h4, when_ns):
    """Frozen A/B regime on the latest COMPLETED H4 bar at `when`:
    +1 long if EMA50>EMA200 and EMA50 rising over 3 bars; -1 mirror;
    0 otherwise / undefined."""
    idx = int(np.searchsorted(h4_close_ts, when_ns, side="right")) - 1
    if idx < 3:
        return 0
    e50, e200 = ema50_h4[idx], ema200_h4[idx]
    if np.isnan(e50) or np.isnan(e200) or np.isnan(ema50_h4[idx - 3]):
        return 0
    if e50 > e200 and e50 > ema50_h4[idx - 3]:
        return 1
    if e50 < e200 and e50 < ema50_h4[idx - 3]:
        return -1
    return 0


def strategy_A_events(h4_close_ts, h1, m15, ema20_h1, ema50_h1,
                      ema50_h4, ema200_h4):
    """Frozen Strategy A state machine. Returns trigger events:
    dict(decision_ns, side, stop_price, kind='A')."""
    h1_close = h1["start"] + TF_NS["H1"]
    m15_close = m15["start"] + TF_NS["M15"]
    events = []
    active = None
    j = 0
    n15 = len(m15_close)
    for i in range(len(h1_close)):
        t = int(h1_close[i])
        while j < n15 and m15_close[j] <= t:
            if active is not None:
                if j >= active["w_end"]:
                    active = None                      # window expired
                elif j >= active["i0"]:
                    side = active["side"]
                    trig = (side == 1 and m15["close"][j] > m15["high"][j - 1]) \
                        if j >= 1 else False
                    trig = trig or (side == -1 and j >= 1
                                    and m15["close"][j] < m15["low"][j - 1])
                    if trig:
                        events.append({"decision_ns": int(m15_close[j]),
                                       "side": int(side),
                                       "stop_price": active["stop"],
                                       "r_mult": 2.0, "T_ns": 24 * 3600 * NS,
                                       "kind": "A"})
                        active = None                  # setup consumed
            j += 1
        if np.isnan(ema20_h1[i]) or np.isnan(ema50_h1[i]):
            continue
        reg = h4_regime_at(h4_close_ts, ema50_h4, ema200_h4, t)
        c, lo, hi, e20, e50 = (h1["close"][i], h1["low"][i], h1["high"][i],
                               ema20_h1[i], ema50_h1[i])
        if reg == 1 and lo <= e20 and c > e20 and c > e50:
            w0 = int(np.searchsorted(m15_close, t, side="right"))
            active = {"side": 1, "stop": float(lo), "i0": w0, "w_end": w0 + 4}
        elif reg == -1 and hi >= e20 and c < e20 and c < e50:
            w0 = int(np.searchsorted(m15_close, t, side="right"))
            active = {"side": -1, "stop": float(hi), "i0": w0, "w_end": w0 + 4}
    return events


def strategy_B_events(h4_close_ts, h1, ema50_h4, ema200_h4, atr_h1, lookback=20):
    """Frozen Strategy B: completed H1 close beyond the extreme of the
    PREVIOUS 20 completed H1 bars (current bar excluded), in the A/B regime."""
    h1_close = h1["start"] + TF_NS["H1"]
    ref_high = pd.Series(h1["high"]).rolling(lookback).max().shift(1).to_numpy()
    ref_low = pd.Series(h1["low"]).rolling(lookback).min().shift(1).to_numpy()
    events = []
    for i in range(len(h1_close)):
        if np.isnan(ref_high[i]):
            continue
        t = int(h1_close[i])
        reg = h4_regime_at(h4_close_ts, ema50_h4, ema200_h4, t)
        if reg == 1 and h1["close"][i] > ref_high[i]:
            events.append({"decision_ns": t, "side": 1,
                           "atr": float(atr_h1[i]), "sl_mult": 1.5,
                           "r_mult": 2.0, "T_ns": 48 * 3600 * NS, "kind": "B"})
        elif reg == -1 and h1["close"][i] < ref_low[i]:
            events.append({"decision_ns": t, "side": -1,
                           "atr": float(atr_h1[i]), "sl_mult": 1.5,
                           "r_mult": 2.0, "T_ns": 48 * 3600 * NS, "kind": "B"})
    return events


def strategy_C_events(h4_close_ts, h1, adx_h4, bb_mid, bb_lo, bb_hi, atr_h1,
                      adx_max=20.0):
    """Frozen Strategy C: latest completed H4 ADX14 < 20 and H1 Bollinger
    pierce-and-close-back. Target = SMA20_H1 frozen at signal close."""
    h1_close = h1["start"] + TF_NS["H1"]
    events = []
    for i in range(len(h1_close)):
        if np.isnan(bb_mid[i]) or np.isnan(atr_h1[i]):
            continue
        t = int(h1_close[i])
        idx4 = int(np.searchsorted(h4_close_ts, t, side="right")) - 1
        if idx4 < 0 or np.isnan(adx_h4[idx4]) or adx_h4[idx4] >= adx_max:
            continue
        if h1["low"][i] < bb_lo[i] and h1["close"][i] > bb_lo[i]:
            events.append({"decision_ns": t, "side": 1, "atr": float(atr_h1[i]),
                           "sl_mult": 1.0, "target_price": float(bb_mid[i]),
                           "T_ns": 12 * 3600 * NS, "kind": "C"})
        elif h1["high"][i] > bb_hi[i] and h1["close"][i] < bb_hi[i]:
            events.append({"decision_ns": t, "side": -1, "atr": float(atr_h1[i]),
                           "sl_mult": 1.0, "target_price": float(bb_mid[i]),
                           "T_ns": 12 * 3600 * NS, "kind": "C"})
    return events


# -------------------------------------------------------------- execution

def _first_true_idx(mask):
    idx = np.flatnonzero(mask)
    return int(idx[0]) if len(idx) else None


def resolve_entry(ts, bid, ask, decision_ns, side, gap_starts):
    """Frozen entry: first tick at/after decision+250ms (search bound 1 h).
    `ts` must start at or before decision+250ms. Statuses:
    FILLED / NO_FILL / NO_FILL_GAP / SKIPPED_HARD_END."""
    t0 = decision_ns + LATENCY_NS
    i0 = int(np.searchsorted(ts, t0, side="left"))
    if i0 >= len(ts) or ts[i0] > decision_ns + NO_FILL_WINDOW_NS:
        return {"status": "NO_FILL"}
    fill_ts = int(ts[i0])
    if fill_ts >= DISCOVERY_END_NS:
        return {"status": "SKIPPED_HARD_END"}
    gi = int(np.searchsorted(gap_starts, decision_ns, side="right"))
    if gi < len(gap_starts) and gap_starts[gi] < fill_ts:
        return {"status": "NO_FILL_GAP"}
    return {"status": "FILLED", "idx": i0, "fill_ts": fill_ts,
            "price": float(ask[i0] if side == 1 else bid[i0])}


def resolve_trade(ts, bid, ask, side, entry_idx, entry_ts, stop, target,
                  time_exit_ns, gap_starts, last_tick=None):
    """Frozen post-entry evaluation on ticks strictly after the entry tick;
    first event wins. Returns status STOP/TARGET/TIME/DATA_GAP_INVALID/
    UNRESOLVED with exit_ts, exit_price, exit_idx."""
    n = len(ts)
    lo = entry_idx + 1
    if side == 1:
        j_stop = _first_true_idx(bid[lo:] <= stop)
        j_tgt = _first_true_idx(bid[lo:] >= target)
    else:
        j_stop = _first_true_idx(ask[lo:] >= stop)
        j_tgt = _first_true_idx(ask[lo:] <= target)
    e_stop = int(ts[lo + j_stop]) if j_stop is not None else np.inf
    e_tgt = int(ts[lo + j_tgt]) if j_tgt is not None else np.inf
    j_time = int(np.searchsorted(ts, time_exit_ns, side="left"))
    e_time = int(ts[j_time]) if j_time < n else np.inf
    gi = int(np.searchsorted(gap_starts, int(entry_ts), side="right"))
    e_gap = int(gap_starts[gi]) if gi < len(gap_starts) else np.inf

    resolved = min(e_stop, e_tgt, e_time)
    if e_gap < resolved:
        return {"status": "DATA_GAP_INVALID", "gap_ts": e_gap}
    if not np.isfinite(resolved):
        # only possible at the dataset tail: frozen fallback = last tick
        if last_tick is None:
            return {"status": "UNRESOLVED"}
        lt_ts, lt_bid, lt_ask = last_tick
        return {"status": "TIME", "exit_ts": int(lt_ts),
                "exit_price": float(lt_bid if side == 1 else lt_ask),
                "exit_idx": None}
    if e_stop <= min(e_tgt, e_time):
        k = lo + j_stop
        px = float(bid[k]) if side == 1 else float(ask[k])
        return {"status": "STOP", "exit_ts": e_stop, "exit_price": px,
                "exit_idx": k}
    if e_tgt <= e_time:
        k = lo + j_tgt
        mid_at = float((bid[k] + ask[k]) / 2.0)
        return {"status": "TARGET", "exit_ts": e_tgt, "exit_price": float(target),
                "exit_idx": k, "exit_tick_mid": mid_at}
    mid_at = float((bid[j_time] + ask[j_time]) / 2.0)
    return {"status": "TIME", "exit_ts": e_time,
            "exit_price": float(bid[j_time] if side == 1 else ask[j_time]),
            "exit_idx": j_time, "exit_tick_mid": mid_at}


def run_discovery_pass(all_events, store, gap_starts,
                       discovery_end_ns=DISCOVERY_END_NS):
    """Chronological sweep with one-open-position occupancy per strategy.
    Trades execute independently; a kept trade occupies its strategy from
    entry fill until resolution. Returns (trades, setup_counts)."""
    events = sorted(all_events, key=lambda e: (e["decision_ns"], e["kind"]))
    last_exit = {}
    trades = []
    counts = {k: {"NO_FILL": 0, "NO_FILL_GAP": 0, "INVALID_STOP": 0,
                  "NO_TRADE_TARGET_CROSSED": 0, "SKIPPED_HARD_END": 0,
                  "UNRESOLVED": 0, "IGNORED_WHILE_OPEN": 0}
              for k in ("A", "B", "C")}
    for ev in events:
        kind = ev["kind"]
        d = ev["decision_ns"]
        if d >= discovery_end_ns or d < DISCOVERY_START_NS:
            continue
        if kind in last_exit and d < last_exit[kind]:
            counts[kind]["IGNORED_WHILE_OPEN"] += 1
            continue                      # frozen: ignore signals while open
        side = ev["side"]
        ts, bid, ask = store.get_range(d + LATENCY_NS,
                                       d + NO_FILL_WINDOW_NS + 1)
        rr = resolve_entry(ts, bid, ask, d, side, gap_starts)
        if rr["status"] != "FILLED":
            counts[kind][rr["status"]] += 1
            continue
        entry_ts = rr["fill_ts"]
        entry = rr["price"]
        T = ev["T_ns"]
        if entry_ts + T >= discovery_end_ns:
            counts[kind]["SKIPPED_HARD_END"] += 1
            continue
        if kind == "A":
            stop = ev["stop_price"]
            if (side == 1 and stop >= entry) or (side == -1 and stop <= entry):
                counts[kind]["INVALID_STOP"] += 1
                continue
            risk = abs(entry - stop)
            target = entry + side * ev["r_mult"] * risk
        elif kind == "B":
            atr = ev["atr"]
            if not atr > 0:
                counts[kind]["INVALID_STOP"] += 1
                continue
            risk = ev["sl_mult"] * atr
            stop = entry - side * risk
            target = entry + side * ev["r_mult"] * risk
        else:  # C
            atr = ev["atr"]
            if not atr > 0:
                counts[kind]["INVALID_STOP"] += 1
                continue
            risk = ev["sl_mult"] * atr
            stop = entry - side * risk
            target = ev["target_price"]
            if (side == 1 and entry >= target) or (side == -1 and entry <= target):
                counts[kind]["NO_TRADE_TARGET_CROSSED"] += 1
                continue
        if risk / PIP < MIN_RISK_PIPS:
            counts[kind]["INVALID_STOP"] += 1   # stop at entry price ± fp noise
            continue
        # The tick window MUST extend past the time-exit timestamp: if the
        # market is closed exactly at entry+T (weekend / holiday), the first
        # tick at/after it lies further ahead, and the TIME exit must find it.
        # 4 days covers weekend + longest known gap; grow if ever needed.
        pad = 4 * 86400 * NS
        while True:
            end_bound = min(entry_ts + T + NS + pad, discovery_end_ns)
            ts, bid, ask = store.get_range(entry_ts, end_bound)
            k = int(np.searchsorted(ts, entry_ts, side="left"))
            j_time = int(np.searchsorted(ts, entry_ts + T, side="left"))
            if j_time < len(ts) or end_bound >= discovery_end_ns:
                break
            pad *= 4
        if k >= len(ts) or ts[k] != entry_ts:
            counts[kind]["UNRESOLVED"] += 1
            continue
        entry_mid = float((bid[k] + ask[k]) / 2.0)
        last_tick = (int(ts[-1]), float(bid[-1]), float(ask[-1]))
        res = resolve_trade(ts, bid, ask, side, k, entry_ts, stop, target,
                            entry_ts + T, gap_starts, last_tick)
        if res["status"] == "UNRESOLVED":
            counts[kind]["UNRESOLVED"] += 1
            continue
        if res["status"] == "DATA_GAP_INVALID":
            # excluded from all main metrics; occupancy ends at gap onset
            trades.append({
                "kind": kind, "side": int(side), "decision_ns": int(d),
                "entry_ts": int(entry_ts), "entry": float(entry),
                "exit_ts": int(res["gap_ts"]), "exit_reason": "DATA_GAP_INVALID",
                "exit_price": float("nan"), "stop": float(stop),
                "target": float(target), "risk_pips": float(risk / PIP),
                "net_pips": float("nan"), "gross_mid_pips": float("nan"),
                "year": int(pd.Timestamp(entry_ts, tz="UTC").year)})
            last_exit[kind] = int(res["gap_ts"])
            continue
        exit_px = res["exit_price"]
        if "exit_idx" in res and res["exit_idx"] is not None:
            exit_mid = float((bid[res["exit_idx"]] + ask[res["exit_idx"]]) / 2.0)
        else:
            exit_mid = exit_px
        net = ((exit_px - entry) if side == 1 else (entry - exit_px)) / PIP
        gross = side * (exit_mid - entry_mid) / PIP
        trades.append({
            "kind": kind, "side": int(side), "decision_ns": int(d),
            "entry_ts": int(entry_ts), "entry": float(entry),
            "exit_ts": int(res["exit_ts"]), "exit_reason": res["status"],
            "exit_price": float(exit_px), "stop": float(stop),
            "target": float(target), "risk_pips": float(risk / PIP),
            "net_pips": float(net), "gross_mid_pips": float(gross),
            "year": int(pd.Timestamp(entry_ts, tz="UTC").year)})
        last_exit[kind] = int(res["exit_ts"])
    return trades, counts


# ---------------------------------------------------------------- metrics

def remove_best_1pct(net):
    n = len(net)
    if n == 0:
        return float("nan")
    k = max(1, int(np.ceil(0.01 * n)))
    if k >= n:
        return float("nan")
    s = np.sort(net)
    return float(s[:n - k].mean())


def bootstrap_ci95(net, n_res=2000, seed=42):
    rng = np.random.default_rng(seed)
    x = np.asarray(net, dtype=np.float64)
    n = len(x)
    if n == 0:
        return (float("nan"), float("nan"))
    means = np.empty(n_res, dtype=np.float64)
    for i in range(n_res):
        means[i] = x[rng.integers(0, n, n)].mean()
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def strategy_metrics(trades, counts):
    """Frozen metric set. DATA_GAP_INVALID trades are excluded from main
    metrics and only counted."""
    valid = [t for t in trades if t["exit_reason"] != "DATA_GAP_INVALID"]
    gap_invalid = [t for t in trades if t["exit_reason"] == "DATA_GAP_INVALID"]
    out = {"n_trades": len(valid), "n_gap_invalid": len(gap_invalid),
           "setup_counts": dict(counts)}
    if not valid:
        out["verdict"] = "REJECT"
        return out
    net = np.array([t["net_pips"] for t in valid])
    gross = np.array([t["gross_mid_pips"] for t in valid])
    wins = net[net > 0]
    losses = net[net < 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 \
        else float("inf")
    risk = np.array([t["risk_pips"] for t in valid])
    exp_r = float(np.mean(net / risk))
    years = np.array([t["year"] for t in valid])
    by_year = {}
    pos_years = 0
    for y in YEARS:
        m = years == y
        if not m.any():
            by_year[str(y)] = None
            continue
        ynet = float(net[m].sum())
        yw = net[m][net[m] > 0]
        yl = net[m][net[m] < 0]
        ypf = float(yw.sum() / abs(yl.sum())) if len(yl) and yl.sum() != 0 else float("inf")
        by_year[str(y)] = {"n": int(m.sum()),
                           "mean_net": round(float(net[m].mean()), 4),
                           "total_net": round(ynet, 4),
                           "pf": round(min(ypf, 1e9), 4)}
        if ynet > 0:
            pos_years += 1
    order = np.argsort([t["entry_ts"] for t in valid], kind="stable")
    net_chron = net[order]
    cum = np.cumsum(net_chron)
    peak = np.maximum.accumulate(cum)
    max_dd = float((peak - cum).max()) if len(cum) else 0.0
    streak = best = 0
    for v in net_chron:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    ci_lo, ci_hi = bootstrap_ci95(net)
    mean_net = float(net.mean())
    out.update({
        "trades_per_year": round(len(valid) / 9.0, 2),
        "gross_mid_move_mean_pips": round(float(gross.mean()), 4),
        "net_mean_pips": round(mean_net, 4),
        "net_median_pips": round(float(np.median(net)), 4),
        "total_net_pips": round(float(net.sum()), 4),
        "stress_010_mean": round(mean_net - 0.20, 4),
        "stress_025_mean": round(mean_net - 0.50, 4),
        "win_rate": round(float((net > 0).mean()), 4),
        "avg_win": round(float(wins.mean()), 4) if len(wins) else 0.0,
        "avg_loss": round(float(losses.mean()), 4) if len(losses) else 0.0,
        "profit_factor": round(min(pf, 1e9), 4),
        "expectancy_r": round(exp_r, 4),
        "max_drawdown_pips": round(max_dd, 4),
        "max_consecutive_losses": int(best),
        "positive_years": pos_years,
        "by_year": by_year,
        "remove_best_1pct_mean": round(remove_best_1pct(net), 4),
        "ci95_lo": round(ci_lo, 4), "ci95_hi": round(ci_hi, 4),
        "exits": {r: int(sum(1 for t in valid if t["exit_reason"] == r))
                  for r in ("STOP", "TARGET", "TIME")},
    })
    out["verdict"] = gate_verdict(out)
    return out


def gate_verdict(m):
    """Frozen §11 gate, then frozen §12 fail-fast."""
    if (m["net_mean_pips"] >= 2.0 and m["profit_factor"] >= 1.20
            and m["expectancy_r"] > 0.10 and m["positive_years"] >= 6
            and m["remove_best_1pct_mean"] > 0 and m["stress_010_mean"] > 0
            and m["n_trades"] >= 150 and m["total_net_pips"] > 0):
        return "MTF_DISCOVERY_PROMISING"
    if (m["net_mean_pips"] <= 0 or m["profit_factor"] <= 1.0
            or m["remove_best_1pct_mean"] <= 0):
        return "REJECT"
    return "FAIL_GATE"
