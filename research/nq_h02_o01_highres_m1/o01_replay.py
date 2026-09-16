#!/usr/bin/env python3
"""O01 BBO-1s execution replay (all-marketable candidate, frozen decisions).

Entry  = MARKET at the fill-bar open: LONG at ASK / SHORT at BID, first
         sample with ts_recv >= activation (= fill bar start).
STOP   = touch stop live since entry: LONG triggers when BID <= stop (market
         sell at BID), SHORT when ASK >= stop (market buy at ASK); replay
         scans from the frozen exit bar START.
TRAIL  = chandelier close-cross (frozen bar-based level): MARKET at the exit
         bar END (LONG at BID / SHORT at ASK).
EOD    = MARKET at the last bar end.
Costs: OBSERVED spread (in bid/ask) + FIXED_FEES residual (NORMAL 1.0 /
STRESS 2.5 pts RT) + scenario slippage (0 / 1 / 2 adverse ticks per
marketable execution). 1 pt = USD 20 = 4 ticks.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from databento import DBNStore

TICK = 0.25
FIXED_FEES_RT = {"NORMAL": 1.0, "STRESS": 2.5}
SLIP_TICKS = {"L1_BASE": 0, "L1_CONSERVATIVE": 1, "L1_STRESS": 2}
NS = 10 ** 9


class BboWindow:
    def __init__(self, path: Path):
        df = DBNStore.from_file(str(path)).to_df()
        self.ts = df.index.asi8.copy()
        self.bid = df["bid_px_00"].to_numpy(float)
        self.ask = df["ask_px_00"].to_numpy(float)

    def first_idx_ge(self, ts):
        k = np.searchsorted(self.ts, int(pd.Timestamp(ts).value), side="left")
        return k if k < len(self.ts) else None


def replay_o01(t: dict, w: BboWindow, scenario: str, tier: str):
    """t: frozen ledger row (entry_ts/exit_ts/level/side/fill/exit_px/...)."""
    side = 1 if t["SIDE"] == "LONG" else -1
    amb = []
    act = pd.Timestamp(t["ORDER_ACTIVATION_TIMESTAMP"])
    exit_bar_ts = pd.Timestamp(t["MODELED_FINAL_EXIT_TIMESTAMP"])
    reason = t["MODELED_EXIT_REASON"]

    # ---- entry: market at activation, LONG at ASK / SHORT at BID
    e_i = w.first_idx_ge(act)
    if e_i is None:
        amb.append("NO_QUOTE_60S_ENTRY")
        entry_exec = float(t["MODELED_ENTRY"])
        entry_bid = entry_ask = np.nan
    else:
        if w.ts[e_i] - int(act.value) > 60 * NS:
            amb.append("NO_QUOTE_60S_ENTRY")
        entry_bid = float(w.bid[e_i])
        entry_ask = float(w.ask[e_i])
        entry_exec = w.ask[e_i] if side == 1 else w.bid[e_i]

    # ---- exit: frozen trigger semantics
    if reason == "STOP":
        dec_ts = exit_bar_ts                       # touch stop live since entry
        stop = float(t["INITIAL_STOP"])
        k1 = w.first_idx_ge(dec_ts)
        while k1 is not None and k1 < len(w.ts):
            hit = (side == 1 and w.bid[k1] <= stop) or \
                  (side == -1 and w.ask[k1] >= stop)
            if hit:
                break
            k1 += 1
        if k1 is None or k1 >= len(w.ts):
            amb.append("STOP_NEVER_TOUCHED_BBO")
            exit_exec = float(t["MODELED_FINAL_EXIT"])
            exit_bid = exit_ask = np.nan
        else:
            exit_exec = w.bid[k1] if side == 1 else w.ask[k1]
            exit_bid, exit_ask = float(w.bid[k1]), float(w.ask[k1])
    else:                                          # TRAIL / EOD: close-based
        dec_ts = exit_bar_ts + pd.Timedelta(5, "min")
        k1 = w.first_idx_ge(dec_ts)
        if k1 is None or k1 >= len(w.ts):
            amb.append("NO_QUOTE_60S_EXIT")
            exit_exec = float(t["MODELED_FINAL_EXIT"])
            exit_bid = exit_ask = np.nan
        else:
            if w.ts[k1] - int(dec_ts.value) > 60 * NS:
                amb.append("NO_QUOTE_60S_EXIT")
            exit_exec = w.bid[k1] if side == 1 else w.ask[k1]
            exit_bid, exit_ask = float(w.bid[k1]), float(w.ask[k1])

    # ---- PnL (adverse slippage: entry pays more, exit receives less)
    slip = SLIP_TICKS[scenario] * TICK
    entry_adverse = entry_exec + slip * side
    exit_adverse = exit_exec - slip * side
    slip_paid = 2 * slip                            # two marketable legs
    gross = side * (exit_adverse - entry_adverse)
    fees = FIXED_FEES_RT[tier]
    net = gross - fees
    return {
        "flag": "OK" if not amb else "AMBIGUOUS:" + ";".join(amb),
        "ambiguity": ";".join(amb),
        "entry_exec": entry_exec, "entry_bid": entry_bid, "entry_ask": entry_ask,
        "entry_spread": entry_ask - entry_bid if entry_bid == entry_bid else np.nan,
        "exit_exec": exit_exec, "exit_bid": exit_bid, "exit_ask": exit_ask,
        "exit_spread": exit_ask - exit_bid if exit_bid == exit_bid else np.nan,
        "gross": gross, "fees": fees, "slippage": slip_paid, "net": net,
    }
