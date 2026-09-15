#!/usr/bin/env python3
"""Parameter plateau for the G08 candidate (mission 21). The FROZEN config
is k=20, eff>=0.45, hold=120h, stop=2.5xATR14 — fixed before these runs.
Plateau cells vary ONE axis at a time; a candidate needs broad coarse
plateaus, not razor-thin winners."""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import swing_lib as S
import families_sw as F
from run_deepen import stop_atr, no_tp, run_config


def main():
    fn = F.g08_efficiency
    cells = [
        ({"k": 10, "eff": 0.45}, 120, 2.5),   # k- neighbor
        ({"k": 30, "eff": 0.45}, 120, 2.5),   # k+ neighbor
        ({"k": 20, "eff": 0.50}, 120, 2.5),   # threshold+ neighbor
        ({"k": 20, "eff": 0.40}, 120, 2.5),   # threshold- neighbor
        ({"k": 20, "eff": 0.45}, 72, 2.5),    # hold- neighbor
        ({"k": 20, "eff": 0.45}, 168, 2.5),   # hold+ neighbor
    ]
    for p, hold, stop in cells:
        run_config("G08", "plateau", fn, p, hold_hours=hold, stop_mult=stop)


if __name__ == "__main__":
    main()
