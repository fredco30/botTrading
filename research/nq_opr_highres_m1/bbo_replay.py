#!/usr/bin/env python3
"""BBO-1s execution replay for the FROZEN P000 trade list.

Replays ONLY execution (frozen decisions are taken as given):
  entry  = buy/sell STOP at the tap-bar extreme (long triggers on ASK >= level,
           short on BID <= level), first sample STRICTLY AFTER activation;
  trim   = PASSIVE limit at the running extreme, fills only if BID (long) /
           ASK (short) is proven to reach the level inside the trim bar
           interval, else QUEUE_UNCERTAIN (trade replays UNTRIMMED);
  exits  = market orders at the frozen decision instants (long at BID,
           short at ASK); BE keeps the frozen close/gap trigger times.
Costs: OBSERVED spread (embedded in bid/ask) + FIXED_FEES residual
(NORMAL 1.0 pt RT, STRESS 2.5 pt RT, pro-rata by size) + scenario slippage
(L1_BASE 0 / L1_CONSERVATIVE 1 tick / L1_STRESS 2 ticks per MARKETABLE exec).
Ambiguity flags are conservative and never resolved in the strategy's favor.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from databento import DBNStore

HERE = Path(__file__).parent
BBO_DIR = Path(r"E:\ResearchData\botTrading\nq\databento\highres\bbo_1s")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nq_opr_modern_m1"))
import nq_lib as N  # noqa: E402

TICK = 0.25
FIXED_FEES_RT = {"NORMAL": 1.0, "STRESS": 2.5}   # index points, residual after
#                                                  spread is observed on BBO
SLIP_TICKS = {"L1_BASE": 0, "L1_CONSERVATIVE": 1, "L1_STRESS": 2}
NS = 10 ** 9


class BboWindow:
    def __init__(self, path: Path):
        df = DBNStore.from_file(str(path)).to_df()
        self.ts = df.index.asi8.copy()
        self.bid = df["bid_px_00"].to_numpy(float)
        self.ask = df["ask_px_00"].to_numpy(float)

    def first_idx_after(self, ts, inclusive=False):
        """First sample with ts_recv > ts (or >= when inclusive)."""
        k = np.searchsorted(self.ts, int(ts.value), side="left" if inclusive else "right")
        return k if k < len(self.ts) else None

    def spread_check(self, i):
        return self.ask[i] - self.bid[i]


def _scan_trigger(w: BboWindow, start_i, side, level):
    """First sample at/after start_i where a stop at `level` is marketable.
    LONG buy-stop triggers on ASK >= level; SHORT sell-stop on BID <= level."""
    k = start_i
    while k is not None and k < len(w.ts):
        if side == 1 and w.ask[k] >= level:
            return k
        if side == -1 and w.bid[k] <= level:
            return k
        k += 1
    return None


def _scan_market(w: BboWindow, start_i, side):
    """First sample at/after start_i for a market order (long exits at BID,
    short exits at ASK). Returns (idx, exec_price)."""
    k = start_i
    while k is not None and k < len(w.ts):
        px = w.bid[k] if side == 1 else w.ask[k]
        return k, float(px)
    return None, None


def _scan_passive_trim(w: BboWindow, lo_ts, hi_ts, side, level):
    """Passive limit: filled only if the resting side is proven to reach the
    level inside [lo_ts, hi_ts]: long sell-limit needs BID >= level."""
    lo, hi = int(lo_ts.value), int(hi_ts.value)
    a = np.searchsorted(w.ts, lo, side="left")
    b = np.searchsorted(w.ts, hi, side="left")
    seg_b = w.bid[a:b]
    seg_a = w.ask[a:b]
    if side == 1:
        hit = np.where(seg_b >= level)[0]
    else:
        hit = np.where(seg_a <= level)[0]
    return (a + int(hit[0])) if len(hit) else None


def replay_trade(t: dict, df: pd.DataFrame, w: BboWindow, scenario: str,
                 tier: str):
    """Replay one frozen trade. Returns dict of execution results."""
    side = 1 if t["SIDE"] == "LONG" else -1
    amb = []
    pos_of = {ts: k for k, ts in enumerate(df.index)}
    tap_i = pos_of[pd.Timestamp(t["RETEST_TIMESTAMP"])]
    entry_bar_i = pos_of[pd.Timestamp(t["ORDER_ACTIVATION_TIMESTAMP"])]
    exit_bar_i = pos_of[pd.Timestamp(t["MODELED_FINAL_EXIT_TIMESTAMP"])]
    trig = float(df["high"].iloc[tap_i]) if side == 1 else float(df["low"].iloc[tap_i])
    act = pd.Timestamp(t["ORDER_ACTIVATION_TIMESTAMP"])

    # ---- entry: stop trigger on the correct side, strictly after activation
    k0 = w.first_idx_after(act, inclusive=False)
    if k0 is None:
        return {"flag": "NO_QUOTES"}
    # causality fallback check: first sample must be within 60s of activation
    if w.ts[k0] - int(act.value) > 60 * NS:
        amb.append("NO_QUOTE_60S_ENTRY")
    e_i = _scan_trigger(w, k0, side, trig)
    if e_i is None:
        amb.append("ENTRY_NEVER_MARKETABLE")
        entry_exec = float(t["MODELED_ENTRY"])
        entry_i_used = None
    else:
        entry_exec = w.ask[e_i] if side == 1 else w.bid[e_i]
        entry_i_used = e_i
    entry_bid = float(w.bid[e_i]) if e_i is not None else np.nan
    entry_ask = float(w.ask[e_i]) if e_i is not None else np.nan

    # ---- lifecycle decisions (frozen) ----
    trimmed_frozen = bool(t["TRIM_TRIGGERED"])
    tgt = float(t["TRIM_LEVEL"])
    reason = t["MODELED_EXIT_REASON"]
    size = 1.0
    legs = []           # (size_fraction, exit_price, kind)
    # trim replay (only if frozen trimmed)
    trim_exec = np.nan
    if trimmed_frozen:
        trim_bar_start = df.index[entry_bar_i]
        # frozen trim fired on first bar >= entry with high>=tgt: replicate the
        # search from entry bar to exit bar for the FIRST qualifying bar
        hi_arr = df["high"].to_numpy()
        lo_arr = df["low"].to_numpy()
        tb = None
        for k in range(entry_bar_i, exit_bar_i + 1):
            if (side == 1 and hi_arr[k] >= tgt) or (side == -1 and lo_arr[k] <= tgt):
                tb = k
                break
        if tb is not None:
            lo_ts = df.index[tb]
            hi_ts = lo_ts + pd.Timedelta(5, "min")
            pt = _scan_passive_trim(w, lo_ts, hi_ts, side, tgt)
            if pt is not None:
                trim_exec = float(tgt)   # passive limit, no slippage
                legs.append((0.5, trim_exec, "TRIM"))
                size = 0.5
            else:
                amb.append("TRIM_QUEUE_UNCERTAIN")
        else:
            amb.append("TRIM_BAR_NOT_FOUND")
        if size == 1.0:
            # trim NOT proven -> frozen BE/EMA8 arms are void; the position
            # exits at the frozen exit timestamp as a MARKET order (full size)
            legs.append((1.0, None, "MARKET_AT_FROZEN_EXIT"))
    else:
        legs.append((1.0, None, "MARKET_AT_FROZEN_EXIT"))

    # market exit legs at the frozen decision instant(s)
    exit_exec = np.nan
    exit_bid = exit_ask = np.nan
    if size > 0:
        if reason in ("BE_STOP",) and size == 0.5:
            # BE floor: frozen trigger = gap-open at exit bar start, else close
            gap = (side == 1 and df["open"].iloc[exit_bar_i] < float(t["INITIAL_STOP"])) or \
                  (side == -1 and df["open"].iloc[exit_bar_i] > float(t["INITIAL_STOP"]))
            dec_ts = df.index[exit_bar_i] if gap else \
                df.index[exit_bar_i] + pd.Timedelta(5, "min")
        elif reason == "LEVEL_STOP" or reason == "EMA8" or reason == "BE_STOP":
            dec_ts = df.index[exit_bar_i] + pd.Timedelta(5, "min")
        else:  # EOD / FORCED
            dec_ts = df.index[exit_bar_i] + pd.Timedelta(5, "min")
        k1 = w.first_idx_after(dec_ts, inclusive=True)
        if k1 is None:
            amb.append("NO_QUOTE_60S_EXIT")
            exit_exec = float(t["MODELED_FINAL_EXIT"])
        else:
            if w.ts[k1] - int(dec_ts.value) > 60 * NS:
                amb.append("NO_QUOTE_60S_EXIT")
            exit_i = k1
            exit_exec = w.bid[exit_i] if side == 1 else w.ask[exit_i]
            exit_bid = float(w.bid[exit_i])
            exit_ask = float(w.ask[exit_i])
        legs = [(sz, exit_exec, "MARKET") if kind != "TRIM" else (sz, px, "TRIM")
                for (sz, px, kind) in legs]

    # ---- PnL ----
    slip = SLIP_TICKS[scenario] * TICK
    # adverse entry slippage: pay more in the trade direction
    entry_adverse = entry_exec + slip * side
    slip_paid = 1.0 * slip            # entry is always a marketable execution
    gross = 0.0
    legs = []
    if size == 0.5:
        legs.append((0.5, trim_exec, "TRIM"))          # passive: no slippage
    mkt_size = size
    legs.append((mkt_size, exit_exec, "MARKET"))
    for (sz, px, kind) in legs:
        p = px
        if kind == "MARKET":
            p = px - slip * side     # adverse exit slippage: receive less
            slip_paid += sz * slip
        gross += sz * side * (p - entry_adverse)
    fees = FIXED_FEES_RT[tier]          # RT on the full round trip
    net = gross - fees                  # slippage embedded in executed prices
    return {
        "flag": "OK" if not amb else "AMBIGUOUS:" + ";".join(amb),
        "entry_exec": entry_exec, "entry_bid": entry_bid, "entry_ask": entry_ask,
        "entry_spread": (entry_ask - entry_bid) if entry_bid == entry_bid else np.nan,
        "exit_exec": exit_exec, "exit_bid": exit_bid, "exit_ask": exit_ask,
        "exit_spread": (exit_ask - exit_bid) if exit_bid == exit_bid else np.nan,
        "trim_exec": trim_exec, "gross": gross, "fees": fees,
        "slippage": slip_paid, "net": net, "ambiguity": ";".join(amb),
    }
