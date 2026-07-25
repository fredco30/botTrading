"""Bar-by-bar Python engine for the EMA Pullback Pyramid EA.

Replays the EA's signal from raw M15/H1 bars instead of replaying a fixed MT4
trade list, so the pyramid streak stays correct when filters change.

Typical use:

    from engine import data, core, report
    from engine.params import Params

    md = data.build("EURUSD15_cut.csv", "EURUSD60_cut.csv")
    p = Params().with_mode("SAFE")
    trades = core.run(md, p)
    print(report.metrics(trades[:, 9], trades[:, 10], p.initial_balance))
"""

from . import core, data, indicators, params, report  # noqa: F401

__all__ = ["core", "data", "indicators", "params", "report"]
