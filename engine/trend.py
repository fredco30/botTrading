"""Donchian breakout trend-following core.

Written after the EMA-pullback post-mortem, and shaped by what that showed:

  * that signal is PF 0.89-1.19 on raw data depending only on the era, so its
    edge was never robust enough to carry leverage
  * every context filter that looked decisive (blocked hours, toxic hour x day
    combos, ATR bands) had been fitted on a 3-year window and added nothing
    once 16+ years were available
  * a per-pair parameter set is a fit, not an edge

So this deliberately goes the other way: a breakout archetype with four
parameters, no calendar filters at all, and - the important constraint - the
*same* parameters across every instrument. A configuration only counts if one
setting works on EUR, GBP, JPY and gold at once, across three decades.

Execution model is stop-order semantics, which is what a breakout actually is:
the order rests at the Donchian level and fills there, not at the next bar's
open. Slippage is charged on top of the spread because breakouts fill in fast
markets.
"""

import numpy as np
from numba import njit

R_ENTRY_IDX = 0
R_EXIT_IDX = 1
R_DIR = 2
R_UNITS = 3
R_ENTRY = 4
R_STOP0 = 5
R_EXIT = 6
R_PNL = 7
R_EQUITY = 8
R_RISK = 9      # intended risk in account currency at entry
R_BARS = 10     # holding period in bars
R_COLS = 11


@njit(cache=True)
def _run_trend(
    ts, o, h, l, c, atr, don_hi, don_lo, exit_hi, exit_lo, roll_w,
    # instrument
    initial_equity, spread, slippage, spread_bps, slippage_bps,
    contract_size, inverse_quote,
    min_lot, max_lot, lot_step, tick_size, tick_value,
    swap_long, swap_short, financing_bps_day, use_swap,
    # strategy
    risk_pct, atr_stop_mult, atr_trail_mult, use_trailing,
    allow_long, allow_short, max_risk_units,
    max_units, add_step_atr,
    out,
):
    n = ts.size
    k = 0
    equity = initial_equity

    in_pos = False
    p_dir = 0
    p_units = 0.0
    p_entry = 0.0
    p_stop = 0.0
    p_stop0 = 0.0
    p_idx = 0
    p_ext = 0.0        # best price reached since entry, for the trailing stop
    p_risk = 0.0
    p_rollw = 0.0

    # Unit pyramiding. Trend following has a long right tail - the best trade in
    # this sample is +22R - so the payoff comes from a handful of runs, not from
    # the median trade. Adding units as a run extends is how that tail gets
    # exploited. This is the same anti-martingale idea as the EMA-pullback
    # pyramid, applied where the payoff distribution actually supports it:
    # there it amplified a marginal clustering effect, here it scales into a
    # move that has already proven itself.
    u_entry = np.zeros(8)
    u_units = np.zeros(8)
    n_units = 0
    p_next_add = 0.0

    for i in range(1, n):
        if np.isnan(atr[i - 1]) or atr[i - 1] <= 0.0:
            continue
        if np.isnan(don_hi[i - 1]) or np.isnan(don_lo[i - 1]):
            continue

        bar_h = h[i]
        bar_l = l[i]
        # Absolute plus proportional costs. A fixed spread is meaningless on an
        # instrument whose price moves two orders of magnitude - BTC went from
        # $1k to $120k in this sample - so crypto is quoted in basis points and
        # FX keeps its measured absolute spread.
        px = c[i - 1]
        eff_spread = spread + px * spread_bps * 1e-4
        eff_slip = slippage + px * slippage_bps * 1e-4

        if in_pos:
            p_rollw += roll_w[i]
            exit_price = np.nan

            if p_dir == 1:
                if bar_l <= p_stop:
                    exit_price = p_stop - eff_slip
                elif not np.isnan(exit_lo[i - 1]) and bar_l <= exit_lo[i - 1]:
                    # Opposite Donchian: a resting stop at that level.
                    lvl = exit_lo[i - 1]
                    exit_price = (lvl if lvl < p_stop else lvl) - eff_slip
                else:
                    if bar_h > p_ext:
                        p_ext = bar_h
                    if use_trailing:
                        trail = p_ext - atr_trail_mult * atr[i - 1]
                        if trail > p_stop:
                            p_stop = trail
                    while (n_units < max_units and p_next_add > 0.0
                           and bar_h >= p_next_add):
                        add_at = p_next_add + eff_spread + eff_slip
                        rp = atr_stop_mult * atr[i - 1]
                        vpp = contract_size / add_at if inverse_quote else contract_size
                        add_u = (equity * risk_pct / 100.0) / (rp * vpp)
                        add_u = np.floor(add_u / lot_step) * lot_step
                        if add_u < min_lot:
                            break
                        u_entry[n_units] = add_at
                        u_units[n_units] = add_u
                        n_units += 1
                        p_units += add_u
                        p_risk += rp * vpp * add_u
                        p_next_add = add_at + add_step_atr * atr[i - 1]
            else:
                if bar_h + eff_spread >= p_stop:
                    exit_price = p_stop + eff_slip
                elif not np.isnan(exit_hi[i - 1]) and bar_h + eff_spread >= exit_hi[i - 1]:
                    exit_price = exit_hi[i - 1] + eff_slip
                else:
                    if bar_l < p_ext:
                        p_ext = bar_l
                    if use_trailing:
                        trail = p_ext + atr_trail_mult * atr[i - 1]
                        if trail < p_stop:
                            p_stop = trail
                    while (n_units < max_units and p_next_add > 0.0
                           and bar_l <= p_next_add):
                        add_at = p_next_add - eff_slip
                        rp = atr_stop_mult * atr[i - 1]
                        vpp = contract_size / add_at if inverse_quote else contract_size
                        add_u = (equity * risk_pct / 100.0) / (rp * vpp)
                        add_u = np.floor(add_u / lot_step) * lot_step
                        if add_u < min_lot:
                            break
                        u_entry[n_units] = add_at
                        u_units[n_units] = add_u
                        n_units += 1
                        p_units += add_u
                        p_risk += rp * vpp * add_u
                        p_next_add = add_at - add_step_atr * atr[i - 1]

            if not np.isnan(exit_price):
                pnl = 0.0
                for u in range(n_units):
                    leg = (exit_price - u_entry[u]) * p_dir * u_units[u] * contract_size
                    if inverse_quote:
                        leg /= exit_price
                    pnl += leg
                if use_swap and p_rollw > 0.0:
                    if financing_bps_day > 0.0:
                        # Crypto CFDs charge a percentage of notional per day,
                        # always against the holder, long or short.
                        notional = p_units * contract_size * exit_price
                        pnl -= p_rollw * notional * financing_bps_day * 1e-4
                    else:
                        rate = swap_long if p_dir == 1 else swap_short
                        pnl += p_rollw * p_units * rate
                equity += pnl

                out[k, R_ENTRY_IDX] = p_idx
                out[k, R_EXIT_IDX] = i
                out[k, R_DIR] = p_dir
                out[k, R_UNITS] = p_units
                out[k, R_ENTRY] = p_entry
                out[k, R_STOP0] = p_stop0
                out[k, R_EXIT] = exit_price
                out[k, R_PNL] = pnl
                out[k, R_EQUITY] = equity
                out[k, R_RISK] = p_risk
                out[k, R_BARS] = i - p_idx
                k += 1
                if k >= out.shape[0]:
                    return k
                in_pos = False
            continue

        if equity <= 0.0:
            break

        # --- breakout entries, filled at the level the stop order rests on ---
        direction = 0
        level = 0.0
        if allow_long and bar_h >= don_hi[i - 1]:
            direction = 1
            level = don_hi[i - 1]
        elif allow_short and bar_l <= don_lo[i - 1]:
            direction = -1
            level = don_lo[i - 1]
        if direction == 0:
            continue

        # A gap through the level fills at the open, not at the level.
        if direction == 1:
            entry = o[i] if o[i] > level else level
            entry += eff_spread + eff_slip
            stop = entry - atr_stop_mult * atr[i - 1]
        else:
            entry = o[i] if o[i] < level else level
            entry -= eff_slip
            stop = entry + atr_stop_mult * atr[i - 1]

        risk_price = abs(entry - stop)
        if risk_price <= 0.0:
            continue

        risk_money = equity * risk_pct / 100.0
        value_per_price = contract_size
        if inverse_quote:
            value_per_price = contract_size / entry
        units = risk_money / (risk_price * value_per_price)
        units = np.floor(units / lot_step) * lot_step
        if units < min_lot:
            units = min_lot
        if units > max_lot:
            units = max_lot
        # Refuse a trade whose real risk overshoots the intended risk, which
        # happens when the minimum lot is already too big for the account.
        if risk_price * value_per_price * units > risk_money * max_risk_units:
            continue

        in_pos = True
        p_dir = direction
        p_units = units
        p_entry = entry
        p_stop = stop
        p_stop0 = stop
        p_idx = i
        p_ext = entry
        p_risk = risk_price * value_per_price * units
        p_rollw = 0.0
        u_entry[0] = entry
        u_units[0] = units
        n_units = 1
        if max_units > 1:
            p_next_add = entry + direction * add_step_atr * atr[i - 1]
        else:
            p_next_add = 0.0

    return k


@njit(cache=True)
def _rolling_extreme(values, period, out, want_max):
    """Rolling max or min via a monotonic deque: O(n) instead of O(n*period).

    The naive sliding-window version costs 490M operations for a 2880-bar
    channel over 170k bars, which makes a 12-instrument sweep unusable. This
    keeps indices of candidates that could still become the extreme, dropping
    any that the newest value dominates.
    """
    n = values.size
    idx = np.empty(n, dtype=np.int64)
    head = 0
    tail = 0
    for i in range(n):
        v = values[i]
        while tail > head:
            last = values[idx[tail - 1]]
            if (v >= last) if want_max else (v <= last):
                tail -= 1
            else:
                break
        idx[tail] = i
        tail += 1
        if idx[head] <= i - period:
            head += 1
        if i >= period - 1:
            out[i] = values[idx[head]]


def donchian(high, low, period):
    """Rolling Donchian channel over the `period` bars ending at each index."""
    n = high.size
    hi = np.full(n, np.nan)
    lo = np.full(n, np.nan)
    if n <= period:
        return hi, lo
    _rolling_extreme(np.ascontiguousarray(high), period, hi, True)
    _rolling_extreme(np.ascontiguousarray(low), period, lo, False)
    return hi, lo


@njit(cache=True)
def _wilder_smooth(tr, period, out):
    out[period - 1] = tr[:period].mean()
    for i in range(period, tr.size):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period


def wilder_atr(high, low, close, period):
    """Wilder-smoothed ATR. Slower to react than MT4's SMA-of-TR, which is the
    behaviour a trailing stop actually wants."""
    n = high.size
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    prev = close[:-1]
    tr[1:] = np.maximum(high[1:], prev) - np.minimum(low[1:], prev)
    out = np.full(n, np.nan)
    if n <= period:
        return out
    _wilder_smooth(tr, period, out)
    return out
