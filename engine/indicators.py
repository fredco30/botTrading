"""MT4-faithful indicator implementations.

Every function here reproduces the exact recursion used by the MetaTrader 4
built-in indicators, including their seeding rules. Matching the seeding
matters: a pandas `ewm` with the wrong initial value drifts for the first few
hundred bars and silently shifts early entries.

Reference behaviour:
  * iMA(MODE_EMA)  -> ExponentialMAOnBuffer: buf[0] = price[0], then recursion
  * iRSI           -> Wilder smoothing seeded with a simple average
  * iATR           -> SMA of True Range (MT4 uses SMA, *not* Wilder smoothing)
"""

import numpy as np


def ema(values, period):
    """MT4 ExponentialMAOnBuffer. Returns array of same length as `values`.

    out[i] is the EMA value on the *closed* bar i.
    """
    values = np.asarray(values, dtype=np.float64)
    out = np.empty_like(values)
    if values.size == 0:
        return out
    k = 2.0 / (period + 1.0)
    out[0] = values[0]
    for i in range(1, values.size):
        out[i] = values[i] * k + out[i - 1] * (1.0 - k)
    return out


def ema_step(prev_ema, price, period):
    """One EMA step. Used to fold a still-forming bar into a closed-bar EMA."""
    k = 2.0 / (period + 1.0)
    return price * k + prev_ema * (1.0 - k)


def rsi(closes, period):
    """MT4 iRSI (Wilder). out[i] is the RSI on closed bar i.

    Bars before `period` are filled with NaN, exactly like MT4's empty buffer
    values, so the caller can refuse to trade during warmup.
    """
    closes = np.asarray(closes, dtype=np.float64)
    n = closes.size
    out = np.full(n, np.nan)
    if n <= period:
        return out

    pos = 0.0
    neg = 0.0
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            pos += diff
        else:
            neg -= diff
    pos /= period
    neg /= period
    out[period] = 100.0 - 100.0 / (1.0 + pos / neg) if neg != 0 else 100.0

    for i in range(period + 1, n):
        diff = closes[i] - closes[i - 1]
        gain = diff if diff > 0 else 0.0
        loss = -diff if diff < 0 else 0.0
        pos = (pos * (period - 1) + gain) / period
        neg = (neg * (period - 1) + loss) / period
        out[i] = 100.0 - 100.0 / (1.0 + pos / neg) if neg != 0 else 100.0

    return out


def true_range(high, low, close):
    """MT4 True Range buffer. tr[0] = high[0] - low[0]."""
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)
    tr = np.empty_like(high)
    if high.size == 0:
        return tr
    tr[0] = high[0] - low[0]
    prev_close = close[:-1]
    tr[1:] = np.maximum(high[1:], prev_close) - np.minimum(low[1:], prev_close)
    return tr


def sma_of(values, period):
    """Simple moving average, NaN during warmup. Matches iMAOnArray(MODE_SMA)."""
    values = np.asarray(values, dtype=np.float64)
    n = values.size
    out = np.full(n, np.nan)
    if n < period:
        return out
    csum = np.cumsum(values)
    out[period - 1] = csum[period - 1] / period
    out[period:] = (csum[period:] - csum[:-period]) / period
    return out
