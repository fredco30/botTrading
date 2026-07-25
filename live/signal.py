"""Calcul du signal, strictement identique au backtest.

Les indicateurs viennent de `engine.channels`, pas d'une reimplementation
locale : une copie reste fidele jusqu'a ce qu'un seul des deux cotes bouge, et
l'ecart ne se voit qu'en production.

`engine.channels` est la version numpy pure, bit-identique a la version numba de
`engine.trend` (verifie par tests/test_channels.py). Le bot evite ainsi
d'importer numba, qui coute 68 Mo de RSS pour un gain nul : 1 459 barres toutes
les cinq minutes se calculent en 0.6 ms.
"""

from dataclasses import dataclass

import numpy as np

from engine.channels import donchian, wilder_atr


@dataclass
class Decision:
    action: str        # "open", "close", "trail", "hold"
    side: int = 0      # +1 long, -1 short
    stop: float = 0.0
    level: float = 0.0     # niveau de cassure (prix d'entree theorique)
    atr: float = 0.0
    reason: str = ""


def indicators(ohlcv, cfg):
    """Renvoie (don_hi, don_lo, exit_hi, exit_lo, atr) sur les barres closes."""
    h, l, c = ohlcv[:, 2], ohlcv[:, 3], ohlcv[:, 4]
    don_hi, don_lo = donchian(h, l, cfg.entry_period)
    ex_hi, ex_lo = donchian(h, l, cfg.exit_period)
    atr = wilder_atr(h, l, c, cfg.atr_period)
    return don_hi, don_lo, ex_hi, ex_lo, atr


def decide(ohlcv, cfg, pos):
    """Decision sur la derniere barre close.

    `pos` est le dict d'etat de la position en cours, ou None.

    Le backtest entre au niveau du canal via un ordre stop, pas a l'ouverture de
    la barre suivante. En live la fidelite vient d'un ordre stop reel laisse sur
    le marche ; ici on se contente de detecter que le niveau a ete franchi sur
    la barre close, ce qui est legerement en retard mais jamais en avance.
    """
    if len(ohlcv) < cfg.entry_period + cfg.atr_period + 2:
        return Decision("hold", reason="historique insuffisant")

    don_hi, don_lo, ex_hi, ex_lo, atr = indicators(ohlcv, cfg)
    i = len(ohlcv) - 1                 # derniere barre close
    hi, lo, close = ohlcv[i, 2], ohlcv[i, 3], ohlcv[i, 4]
    a = atr[i - 1]
    if not np.isfinite(a) or a <= 0:
        return Decision("hold", reason="ATR indisponible")

    if pos:
        side = pos["side"]
        stop = pos["stop"]
        ext = pos["extreme"]

        if side == 1:
            if lo <= stop:
                return Decision("close", side, reason=f"stop touche a {stop:.6g}")
            if np.isfinite(ex_lo[i - 1]) and lo <= ex_lo[i - 1]:
                return Decision("close", side, reason="canal de sortie oppose")
            new_ext = max(ext, hi)
            new_stop = max(stop, new_ext - cfg.atr_trail_mult * a)
            if new_stop > stop or new_ext > ext:
                return Decision("trail", side, stop=new_stop, level=new_ext, atr=a)
        else:
            if hi >= stop:
                return Decision("close", side, reason=f"stop touche a {stop:.6g}")
            if np.isfinite(ex_hi[i - 1]) and hi >= ex_hi[i - 1]:
                return Decision("close", side, reason="canal de sortie oppose")
            new_ext = min(ext, lo)
            new_stop = min(stop, new_ext + cfg.atr_trail_mult * a)
            if new_stop < stop or new_ext < ext:
                return Decision("trail", side, stop=new_stop, level=new_ext, atr=a)
        return Decision("hold", side)

    if cfg.allow_long and np.isfinite(don_hi[i - 1]) and hi >= don_hi[i - 1]:
        lvl = don_hi[i - 1]
        return Decision("open", 1, stop=lvl - cfg.atr_stop_mult * a, level=lvl,
                        atr=a, reason=f"cassure haussiere de {lvl:.6g}")
    if cfg.allow_short and np.isfinite(don_lo[i - 1]) and lo <= don_lo[i - 1]:
        lvl = don_lo[i - 1]
        return Decision("open", -1, stop=lvl + cfg.atr_stop_mult * a, level=lvl,
                        atr=a, reason=f"cassure baissiere de {lvl:.6g}")
    return Decision("hold")


def size_position(equity, entry, stop, cfg, market=None):
    """Taille en unites : risque_pct de l'equity divise par la distance au stop."""
    risk_price = abs(entry - stop)
    if risk_price <= 0 or entry <= 0:
        return 0.0
    units = (equity * cfg.risk_pct / 100.0) / risk_price

    cap = equity * cfg.max_position_notional_pct / 100.0 / entry
    units = min(units, cap)
    lev_cap = equity * cfg.max_leverage / entry
    units = min(units, lev_cap)

    if market:
        prec = (market.get("precision") or {}).get("amount")
        if isinstance(prec, int) and prec >= 0:
            units = float(np.floor(units * 10 ** prec) / 10 ** prec)
        step = ((market.get("limits") or {}).get("amount") or {}).get("min")
        if step and units < step:
            return 0.0
    if units * entry < cfg.min_order_value:
        return 0.0
    return units
