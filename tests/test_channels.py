"""Verrouille l'equivalence entre la version numpy pure et la version numba.

Le bot live utilise engine.channels, le backtest engine.trend. S'ils divergent,
le bot ne trade plus la strategie qui a ete validee - et rien ne le signalerait.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.channels import donchian as np_donchian, wilder_atr as np_atr
from engine.trend import donchian as nb_donchian, wilder_atr as nb_atr

CASES = [(3000, 55), (20000, 720), (50000, 1440), (170000, 2880), (1000, 999)]


def test_identical():
    rng = np.random.default_rng(7)
    for n, p in CASES:
        high = np.cumsum(rng.normal(size=n)) + 1000
        low = high - rng.random(n) * 3
        close = high - rng.random(n) * 1.5

        h1, l1 = nb_donchian(high, low, p)
        h2, l2 = np_donchian(high, low, p)
        assert np.array_equal(h1, h2, equal_nan=True), f"donchian high n={n} p={p}"
        assert np.array_equal(l1, l2, equal_nan=True), f"donchian low n={n} p={p}"

        a1 = nb_atr(high, low, close, 14)
        a2 = np_atr(high, low, close, 14)
        assert np.nanmax(np.abs(a1 - a2)) == 0.0, f"atr n={n} p={p}"
    print(f"OK : {len(CASES)} cas, donchian et ATR bit-identiques")


if __name__ == "__main__":
    test_identical()
