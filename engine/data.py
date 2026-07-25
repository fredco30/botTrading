"""Market data loading and H1 <-> M15 alignment.

The whole point of this module is to reproduce what the EA actually *sees* at
the instant a new M15 bar opens. That is subtler than it looks, because
`EMA_Pullback_pyramid.mq4` reads several H1 values at shift 0 - the H1 bar that
is still forming:

    iMA(Symbol(), PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE, 0)
    iClose(Symbol(), PERIOD_H1, 0)
    iATR(Symbol(), PERIOD_H1, 14, 0)

At the first tick of M15 bar `i`, that forming H1 bar has:
    close = the current price          -> open of M15 bar i (bid)
    high  = max(highs of the M15 sub-bars already closed this hour, open_i)
    low   = min(lows  of the M15 sub-bars already closed this hour, open_i)

Same story on M15: `iMA(..., PERIOD_M15, 20, ..., 0)` is the EMA including the
forming bar whose close is the current price. Ignoring this shifts the EMA20 by
one bar and changes which pullbacks qualify.
"""

from dataclasses import dataclass, field

import numpy as np

from . import indicators as ind

SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400


def load_mt4_csv(path):
    """Load an MT4 'Export bars' CSV: date,time,open,high,low,close,volume."""
    dt_list = []
    ohlcv = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) < 6:
                continue
            date_part, time_part = parts[0], parts[1]
            try:
                y, mo, d = (int(x) for x in date_part.split("."))
                hh, mm = (int(x) for x in time_part.split(":"))
                row = [float(x) for x in parts[2:6]]
            except ValueError:
                continue  # header or malformed line
            dt_list.append(
                np.datetime64(
                    f"{y:04d}-{mo:02d}-{d:02d}T{hh:02d}:{mm:02d}:00", "s"
                )
            )
            ohlcv.append(row)

    dt = np.array(dt_list, dtype="datetime64[s]")
    arr = np.asarray(ohlcv, dtype=np.float64)
    order = np.argsort(dt, kind="stable")
    dt = dt[order]
    arr = arr[order]
    return dt, arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]


def derive_h1(m15_dt, m_o, m_h, m_l, m_c):
    """Aggregate M15 bars into H1 bars.

    MT4's own H1 export is reproducible from the M15 series to the point:
    checked against EURUSD60.csv over 175,992 bars, open/high/low match 100%
    exactly and close matches everywhere except the final, still-forming bar.

    This exists so a pair only needs its M15 export. Asking for both timeframes
    doubles the manual work in the terminal and, in practice, is where the H1
    file ends up covering a different span than the M15 one.
    """
    ts = m15_dt.astype("int64")
    bucket = ts // SECONDS_PER_HOUR
    starts = np.concatenate(([0], np.flatnonzero(np.diff(bucket)) + 1))
    ends = np.concatenate((starts[1:], [ts.size]))

    h1_dt = (bucket[starts] * SECONDS_PER_HOUR).astype("datetime64[s]")
    h_o = m_o[starts]
    h_c = m_c[ends - 1]
    h_h = np.maximum.reduceat(m_h, starts)
    h_l = np.minimum.reduceat(m_l, starts)
    return h1_dt, h_o, h_h, h_l, h_c


@dataclass
class MarketData:
    """Everything the backtest core needs, pre-aligned to the M15 index."""

    # M15 series
    ts: np.ndarray           # int64 epoch seconds, bar open time
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    hour: np.ndarray         # int32, server time
    dow: np.ndarray          # int32, MT4 convention: 0=Sunday .. 5=Friday
    day_id: np.ndarray       # int64, ts // 86400 (matches the EA's daily reset)

    # M15 indicators on closed bars
    ema_entry_closed: np.ndarray   # EMA(EntryEMA_Period) at bar i (closed)
    rsi_closed: np.ndarray         # RSI(RSI_Period) at bar i (closed)

    # H1 state seen from each M15 bar
    h1_valid: np.ndarray           # bool: forming H1 bar resolved and warmed up
    h1_ema_now: np.ndarray         # EMA50 including the forming H1 bar
    h1_ema_prev: np.ndarray        # EMA50 at shift = TrendBars (closed bar)
    h1_close_now: np.ndarray       # iClose(H1, 0) == open of the M15 bar
    h1_atr_now: np.ndarray         # iATR(H1, period, 0), price units

    # Swap accounting. roll_cum is indexed by (day_id - day0), not by bar, so
    # the number of rollovers a trade crossed is a single subtraction:
    #   roll_cum[day_exit - day0] - roll_cum[day_entry - day0]
    roll_cum: np.ndarray = field(default_factory=lambda: np.zeros(1))
    day0: int = 0

    n_unaligned: int = 0           # M15 bars with no matching H1 bar


def build(
    m15_path,
    h1_path,
    entry_ema_period=20,
    rsi_period=14,
    trend_ema_period=50,
    trend_bars=5,
    atr_period=14,
):
    """Load both timeframes and produce the M15-aligned view the EA sees."""
    m15_dt, m_o, m_h, m_l, m_c = load_mt4_csv(m15_path)
    if h1_path in (None, "auto"):
        h1_dt, h_o, h_h, h_l, h_c = derive_h1(m15_dt, m_o, m_h, m_l, m_c)
    else:
        h1_dt, h_o, h_h, h_l, h_c = load_mt4_csv(h1_path)

    ts = m15_dt.astype("int64")
    h1_ts = h1_dt.astype("int64")
    n = ts.size

    # --- calendar fields (MT4 semantics) ---
    hour = ((ts % SECONDS_PER_DAY) // SECONDS_PER_HOUR).astype(np.int32)
    # 1970-01-01 was a Thursday -> day 0 maps to MT4 dow 4
    dow = (((ts // SECONDS_PER_DAY) + 4) % 7).astype(np.int32)
    day_id = (ts // SECONDS_PER_DAY).astype(np.int64)

    # --- M15 indicators on closed bars ---
    ema_entry_closed = ind.ema(m_c, entry_ema_period)
    rsi_closed = ind.rsi(m_c, rsi_period)

    # --- H1 indicators on closed bars ---
    h1_ema_closed = ind.ema(h_c, trend_ema_period)
    h1_tr = ind.true_range(h_h, h_l, h_c)
    h1_tr_cum = np.concatenate(([0.0], np.cumsum(h1_tr)))

    # --- map each M15 bar onto the H1 bar that contains it ---
    k = np.searchsorted(h1_ts, ts, side="right") - 1
    aligned = (k >= 0) & (ts - h1_ts[np.clip(k, 0, None)] < SECONDS_PER_HOUR)
    n_unaligned = int((~aligned).sum())

    # --- partial H1 high/low built from the already-closed M15 sub-bars ---
    # part_hi[i] / part_lo[i] cover only bars strictly before i inside the same
    # H1 bucket; NaN when bar i is the first sub-bar of its H1 bar.
    part_hi = np.full(n, np.nan)
    part_lo = np.full(n, np.nan)
    run_hi = np.nan
    run_lo = np.nan
    prev_k = -1
    for i in range(n):
        ki = k[i]
        if ki != prev_k:
            run_hi = np.nan
            run_lo = np.nan
            prev_k = ki
        part_hi[i] = run_hi
        part_lo[i] = run_lo
        run_hi = m_h[i] if np.isnan(run_hi) else max(run_hi, m_h[i])
        run_lo = m_l[i] if np.isnan(run_lo) else min(run_lo, m_l[i])

    # --- fold the forming H1 bar into EMA50 / ATR, exactly like shift 0 ---
    h1_close_now = m_o.copy()  # iClose(H1, 0) == current price == M15 open

    warm = aligned & (k >= max(trend_bars, atr_period))
    kk = np.clip(k, 1, None)

    prev_ema = h1_ema_closed[kk - 1]
    h1_ema_now = np.where(
        warm, ind.ema_step(prev_ema, h1_close_now, trend_ema_period), np.nan
    )
    h1_ema_prev = np.where(warm, h1_ema_closed[np.clip(k - trend_bars, 0, None)], np.nan)

    prev_close = h_c[kk - 1]
    hi_now = np.where(np.isnan(part_hi), h1_close_now, np.fmax(part_hi, h1_close_now))
    lo_now = np.where(np.isnan(part_lo), h1_close_now, np.fmin(part_lo, h1_close_now))
    tr_now = np.maximum(hi_now, prev_close) - np.minimum(lo_now, prev_close)

    # ATR(period) with the forming bar as the most recent sample:
    #   (tr_now + sum of the previous period-1 closed TRs) / period
    lo_idx = np.clip(k - (atr_period - 1), 0, None)
    tr_tail = h1_tr_cum[np.clip(k, 0, None)] - h1_tr_cum[lo_idx]
    h1_atr_now = np.where(warm, (tr_now + tr_tail) / atr_period, np.nan)

    # --- rollover weights: 0 on Sat/Sun, 3 on Thursday, 1 otherwise ---
    day0 = int(day_id[0])
    n_days = int(day_id[-1]) - day0 + 2
    days = np.arange(day0, day0 + n_days)
    day_dow = (days + 4) % 7           # MT4 convention, 0 = Sunday
    weight = np.ones(n_days)
    weight[(day_dow == 0) | (day_dow == 6)] = 0.0   # weekend: no rollover
    weight[day_dow == 4] = 3.0                      # Thursday 00:00 = triple
    roll_cum = np.cumsum(weight)

    return MarketData(
        ts=ts,
        open=m_o,
        high=m_h,
        low=m_l,
        close=m_c,
        hour=hour,
        dow=dow,
        day_id=day_id,
        ema_entry_closed=ema_entry_closed,
        rsi_closed=rsi_closed,
        h1_valid=warm,
        h1_ema_now=h1_ema_now,
        h1_ema_prev=h1_ema_prev,
        h1_close_now=h1_close_now,
        h1_atr_now=h1_atr_now,
        roll_cum=roll_cum,
        day0=day0,
        n_unaligned=n_unaligned,
    )


def slice_period(md, start=None, end=None):
    """Restrict a MarketData to [start, end] (inclusive) 'YYYY.MM.DD' strings.

    Indicator warmup is already baked into the arrays, so slicing afterwards is
    safe - unlike slicing the raw CSV, which would reset every EMA seed.
    """
    mask = np.ones(md.ts.size, dtype=bool)
    if start is not None:
        mask &= md.ts >= np.datetime64(start.replace(".", "-"), "s").astype("int64")
    if end is not None:
        end_ts = np.datetime64(end.replace(".", "-"), "s").astype("int64") + SECONDS_PER_DAY
        mask &= md.ts < end_ts
    idx = np.flatnonzero(mask)
    if idx.size == 0:
        raise ValueError("empty period after slicing")
    lo, hi = idx[0], idx[-1] + 1

    n_bars = md.ts.size
    fields = {}
    for name, value in md.__dict__.items():
        # Only per-bar arrays get sliced; roll_cum is indexed by day offset.
        if isinstance(value, np.ndarray) and value.size == n_bars:
            fields[name] = value[lo:hi]
        else:
            fields[name] = value
    return MarketData(**fields)
