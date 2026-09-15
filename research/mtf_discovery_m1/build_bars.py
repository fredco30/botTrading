#!/usr/bin/env python3
"""Build + cache M1/M5/M15/H1/H4 bars for every discovery year (2010-2017)."""
import sys
import numpy as np

import m3lib as L

for y in L.DISCOVERY_YEARS:
    bars = L.build_year(y)
    h1 = {k[len("H1_"):]: bars[f"H1_{k[len('H1_'):]}"] for k in bars if k.startswith("H1_")}
    print(f"{y}: M1={len(bars['m1_close'])} M5={len(bars['M5_close'])} "
          f"M15={len(bars['M15_close'])} H1={len(bars['H1_close'])} "
          f"H4={len(bars['H4_close'])} "
          f"first_H1_close={h1['close_time'][0] // L.NS} "
          f"last_H1_close={h1['close_time'][-1] // L.NS}")
