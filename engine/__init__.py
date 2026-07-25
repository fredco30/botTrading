"""Moteur de backtest et indicateurs.

Les sous-modules sont importes paresseusement (PEP 562). `engine.core` et
`engine.trend` tirent numba, qui coute 68 Mo de RSS ; le bot live n'a besoin que
de `engine.channels`, en numpy pur. Un import eager du paquet lui imposerait
numba sans aucun usage - la moitie de son empreinte sur un petit VPS.

    from engine import core, data, report     # backtest : numba charge
    from engine.channels import donchian      # live : numba jamais importe
"""

import importlib

__all__ = ["channels", "core", "data", "debug", "indicators", "instruments",
           "params", "portfolio", "report", "trend"]


def __getattr__(name):
    if name in __all__:
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} n'a pas d'attribut {name!r}")


def __dir__():
    return sorted(__all__)
