"""Donchian et ATR en numpy pur, sans numba.

Le backtest a besoin de numba : il rejoue des centaines de milliers de barres
des centaines de fois. Le bot live n'en a pas besoin - il traite 1 459 barres
une fois toutes les cinq minutes, ce qui coute 0.06 ms en numpy.

Numba represente pourtant 68 Mo de RSS (21 Mo a l'import, 47 de plus a la
compilation JIT). Sur un petit VPS c'est la moitie de l'empreinte du bot,
depensee pour un gain nul. Ce module existe pour que `live/` puisse importer les
indicateurs sans tirer numba.

Les deux implementations sont verifiees identiques par `tests/test_channels.py`.
"""

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


def donchian(high, low, period):
    """Canal de Donchian sur les `period` barres finissant a chaque indice."""
    high = np.ascontiguousarray(high, dtype=np.float64)
    low = np.ascontiguousarray(low, dtype=np.float64)
    n = high.size
    hi = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    if n <= period:
        return hi, lo
    hi[period - 1:] = sliding_window_view(high, period).max(axis=1)
    lo[period - 1:] = sliding_window_view(low, period).min(axis=1)
    return hi, lo


def wilder_atr(high, low, close, period):
    """ATR lisse a la Wilder.

    Boucle explicite plutot qu'une forme fermee : la recursion est un filtre IIR
    qu'on pourrait resoudre analytiquement, mais a**n sous-deborde vers zero des
    quelques milliers de barres et la division par ce zero produit des infinis.
    A 1 459 barres la boucle coute moins d'une milliseconde.
    """
    high = np.asarray(high, dtype=np.float64)
    low = np.asarray(low, dtype=np.float64)
    close = np.asarray(close, dtype=np.float64)
    n = high.size
    out = np.full(n, np.nan)
    if n <= period:
        return out

    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    prev = close[:-1]
    tr[1:] = np.maximum(high[1:], prev) - np.minimum(low[1:], prev)

    val = tr[:period].mean()
    out[period - 1] = val
    for i in range(period, n):
        val = (val * (period - 1) + tr[i]) / period
        out[i] = val
    return out
