"""Bar-by-bar simulation core for EMA_Pullback_pyramid.

This is the piece the Python analyses in this repo were missing. Every previous
script replayed a *fixed* list of MT4 trades and re-applied lot multipliers on
top, which silently assumes the trade sequence is invariant. It is not: change
any filter and the win/loss ordering changes, which changes every streak, which
changes every lot size downstream. See CLAUDE.md, "Les simulations Python sur
trades existants sont UNRELIABLE pour le pyramid".

Here the signal is re-derived from raw bars and the pyramid streak is a state
variable inside the loop, so a filter change propagates correctly.

Execution model, recovered from resultats_martingale_EMAPullback3ans.txt:
  * entry price = the M15 bar open (bid); buys pay the spread on top
  * SL/TP trigger on bid for buys, on ask for sells (MT4 semantics)
  * P&L = (exit - entry) * direction * lots * tick_value / tick_size
  * no commission (85 intraday trades reconcile to $0.0000 residual)
  * overnight swap per lot per 00:00 rollover, tripled on Thursday - this is
    what the pure-price formula was missing, and it is not small: it costs the
    3-year run about $110 and flips one trade from a breakeven win into a loss,
    which then resets the pyramid streak and rescales everything after it
"""

import numpy as np
from numba import njit

# Trade record columns, exposed as constants so callers do not index by magic
# numbers. Kept as a flat float64 matrix because numba cannot return a
# structured array from nopython mode.
T_ENTRY_IDX = 0
T_EXIT_IDX = 1
T_DIR = 2       # +1 buy, -1 sell
T_LEVEL = 3     # pyramid streak level at entry (0/1/2)
T_LOTS = 4
T_ENTRY = 5
T_SL = 6
T_TP = 7
T_EXIT = 8
T_PNL = 9
T_BALANCE = 10  # balance after the trade closed
T_BE = 11       # 1 if breakeven was armed before the exit
T_RISK = 12     # initial risk distance in price units
T_SL0 = 13      # SL as placed at entry, before any breakeven move
T_SWAP = 14     # overnight swap charged on this trade, in account currency
T_CONFLICT = 15 # 1 if the exit bar touched BOTH the SL and the TP, so the
                # outcome rests on the intrabar model rather than on data
T_COLS = 16

# Intrabar resolution when one bar touches both SL and TP.
INTRABAR_MODES = {"pessimistic": 0, "nearest": 1, "optimistic": 2}


@njit(cache=True, inline="always")
def _tp_first(direction, mode, bar_o, bar_h, bar_l):
    """Which of SL / TP was reached first, when one bar touches both.

    We only have the bar's OHLC, never the tick order, so this is a modelling
    choice - and it is not cosmetic. On USDJPY exactly two such bars out of 89
    trades swing the 3-year net by 38%.

      0 PESSIMISTIC - always the stop. Safe, but it understates any strategy
                      whose target sits inside normal bar range.
      1 NEAREST     - the extreme closer to the bar open is reached first.
                      Assumes one clean out-and-back swing within the bar.
      2 OPTIMISTIC  - always the target. Useful only as an upper bound.
    """
    if mode == 0:
        return False
    if mode == 2:
        return True
    high_first = (bar_h - bar_o) <= (bar_o - bar_l)
    # Long: target above, stop below, so hitting the high first means the
    # target went first. Short is the mirror image.
    return high_first if direction == 1 else not high_first


@njit(cache=True)
def _run(
    ts, o, h, l, c, hour, dow, day_id,
    ema_entry_closed, rsi_closed,
    h1_valid, h1_ema_now, h1_ema_prev, h1_close_now, h1_atr_now,
    roll_cum, day0,
    # account / instrument
    initial_balance, spread, pip, tick_size, tick_value,
    contract_size, inverse_quote, min_lot, max_lot, lot_step,
    # risk
    risk_percent, max_spread_pips, min_rr, min_sl_pips, max_sl_pips,
    # pyramid
    use_pyramid, l0_mult, l1_mult, l2_mult, max_streak_level,
    # signal
    entry_ema_k, sl_swing_bars, rsi_ob, rsi_os, body_ratio_min,
    # sessions
    use_london, london_start, london_end, ny_start, ny_end,
    # management
    use_breakeven, be_trigger_r, be_offset, max_trades_per_day,
    # context filters
    use_atr_filter, atr_min_pips, atr_max_pips,
    use_ema50_dist_filter, max_ema50_dist_pips,
    # calendar filters
    block_friday, block_monday, blocked_hours, toxic_combos,
    reduce_thursday_risk, thursday_risk_mult,
    # overnight swap
    use_swap, swap_long_per_lot, swap_short_per_lot,
    # realism
    exit_on_entry_bar, intrabar_mode,
    out,
):
    n = ts.size
    n_trades = 0

    balance = initial_balance
    streak = 0
    daily_trades = 0
    current_day = day_id[0] if n > 0 else 0

    in_pos = False
    p_dir = 0
    p_level = 0
    p_lots = 0.0
    p_entry = 0.0
    p_sl = 0.0
    p_tp = 0.0
    p_risk = 0.0
    p_sl0 = 0.0
    p_entry_idx = 0
    p_day_entry = 0
    p_be = 0
    p_conflict = 0

    spread_pips = spread / pip
    start_bar = max(sl_swing_bars + 2, 3)

    for i in range(start_bar, n):
        # --- daily counter reset (EA: TimeCurrent() day rollover) ---
        if day_id[i] != current_day:
            current_day = day_id[i]
            daily_trades = 0

        bar_o = o[i]
        bar_h = h[i]
        bar_l = l[i]

        # ------------------------------------------------------------------
        # Position management. A bar that carries an open position can never
        # also open one: the EA's CountOpenTrades() check runs at the bar open,
        # while the position is still alive.
        # ------------------------------------------------------------------
        if in_pos:
            exit_price = np.nan

            if p_dir == 1:
                hit_sl = bar_l <= p_sl
                hit_tp = bar_h >= p_tp
                if hit_sl and hit_tp:
                    p_conflict = 1
                    exit_price = p_tp if _tp_first(1, intrabar_mode, bar_o,
                                                   bar_h, bar_l) else p_sl
                elif hit_sl:
                    exit_price = p_sl
                elif hit_tp:
                    exit_price = p_tp
                elif use_breakeven and p_be == 0:
                    if bar_h - p_entry >= p_risk * be_trigger_r:
                        p_sl = p_entry + be_offset
                        p_be = 1
            else:
                ask_h = bar_h + spread
                ask_l = bar_l + spread
                hit_sl = ask_h >= p_sl
                hit_tp = ask_l <= p_tp
                if hit_sl and hit_tp:
                    p_conflict = 1
                    exit_price = p_tp if _tp_first(-1, intrabar_mode, bar_o,
                                                    bar_h, bar_l) else p_sl
                elif hit_sl:
                    exit_price = p_sl
                elif hit_tp:
                    exit_price = p_tp
                elif use_breakeven and p_be == 0:
                    if p_entry - ask_l >= p_risk * be_trigger_r:
                        p_sl = p_entry - be_offset
                        p_be = 1

            if not np.isnan(exit_price):
                pnl = (exit_price - p_entry) * p_dir * p_lots * contract_size
                if inverse_quote:
                    # Account currency is the base (USDJPY): profit accrues in
                    # the quote currency and MT4 converts it at the exit price.
                    pnl /= exit_price
                swap = 0.0
                if use_swap:
                    n_roll = (roll_cum[day_id[i] - day0]
                              - roll_cum[p_day_entry - day0])
                    if n_roll > 0.0:
                        rate = swap_long_per_lot if p_dir == 1 else swap_short_per_lot
                        swap = n_roll * p_lots * rate
                        pnl += swap
                balance += pnl

                out[n_trades, T_ENTRY_IDX] = p_entry_idx
                out[n_trades, T_EXIT_IDX] = i
                out[n_trades, T_DIR] = p_dir
                out[n_trades, T_LEVEL] = p_level
                out[n_trades, T_LOTS] = p_lots
                out[n_trades, T_ENTRY] = p_entry
                out[n_trades, T_SL] = p_sl
                out[n_trades, T_TP] = p_tp
                out[n_trades, T_EXIT] = exit_price
                out[n_trades, T_PNL] = pnl
                out[n_trades, T_BALANCE] = balance
                out[n_trades, T_BE] = p_be
                out[n_trades, T_RISK] = p_risk
                out[n_trades, T_SL0] = p_sl0
                out[n_trades, T_SWAP] = swap
                out[n_trades, T_CONFLICT] = p_conflict
                n_trades += 1
                if n_trades >= out.shape[0]:
                    return n_trades

                # Pyramid streak update, EA CheckPyramidClose(): any positive
                # P&L is a win, including a +1 pip breakeven exit.
                if pnl > 0.0:
                    streak += 1
                    if streak > max_streak_level:
                        streak = max_streak_level
                else:
                    streak = 0

                in_pos = False
            continue

        # ------------------------------------------------------------------
        # Pre-checks, in the EA's own order.
        # ------------------------------------------------------------------
        hr = hour[i]
        dw = dow[i]

        in_session = False
        if use_london and hr >= london_start and hr < london_end:
            in_session = True
        if hr >= ny_start and hr < ny_end:
            in_session = True
        if not in_session:
            continue

        if spread_pips > max_spread_pips:
            continue

        if block_friday and dw == 5:
            continue
        if block_monday and dw == 1:
            continue

        blocked = False
        for b in range(blocked_hours.size):
            if hr == blocked_hours[b]:
                blocked = True
                break
        if blocked:
            continue
        for b in range(toxic_combos.shape[0]):
            if hr == toxic_combos[b, 0] and dw == toxic_combos[b, 1]:
                blocked = True
                break
        if blocked:
            continue

        if not h1_valid[i]:
            continue

        if use_atr_filter:
            atr_pips = h1_atr_now[i] / pip
            if atr_pips < atr_min_pips:
                continue
            if atr_max_pips > 0.0 and atr_pips > atr_max_pips:
                continue

        mid = bar_o + spread * 0.5
        if use_ema50_dist_filter:
            if abs(mid - h1_ema_now[i]) / pip > max_ema50_dist_pips:
                continue

        if daily_trades >= max_trades_per_day:
            continue

        # ------------------------------------------------------------------
        # Signal. H1 trend from the forming bar, M15 pullback from bars 1-2.
        # ------------------------------------------------------------------
        ema_now = h1_ema_now[i]
        ema_prev = h1_ema_prev[i]
        close_h1 = h1_close_now[i]

        trend = 0
        if close_h1 > ema_now and ema_now > ema_prev:
            trend = 1
        elif close_h1 < ema_now and ema_now < ema_prev:
            trend = -1
        if trend == 0:
            continue

        # iMA(M15, period, 0) includes the forming bar, whose close is the
        # current price (== this bar's open).
        ema20_now = ema_entry_closed[i - 1] + entry_ema_k * (bar_o - ema_entry_closed[i - 1])
        ema20_bar2 = ema_entry_closed[i - 2]

        open1 = o[i - 1]
        close1 = c[i - 1]
        high1 = h[i - 1]
        low1 = l[i - 1]

        open2 = o[i - 2]
        close2 = c[i - 2]
        high2 = h[i - 2]
        low2 = l[i - 2]

        body1 = abs(close1 - open1)
        range1 = high1 - low1
        body2 = abs(close2 - open2)

        rsi_v = rsi_closed[i - 1]
        if np.isnan(rsi_v):
            continue

        ask = bar_o + spread
        bid = bar_o

        sl = 0.0
        tp = 0.0
        entry = 0.0

        if trend == 1:
            if rsi_v > rsi_ob:
                continue
            if low2 > ema20_bar2:
                continue
            if close1 <= ema20_now:
                continue
            if close1 <= open1:
                continue
            if range1 > 0.0 and body1 / range1 < body_ratio_min:
                continue
            if body1 <= body2:
                continue

            sl = low1
            for s in range(1, sl_swing_bars + 1):
                if l[i - s] < sl:
                    sl = l[i - s]
            sl -= 2.0 * pip

            sl_dist = (ask - sl) / pip
            if sl_dist < min_sl_pips or sl_dist > max_sl_pips:
                continue

            entry = ask
            tp = ask + (ask - sl) * min_rr
        else:
            if rsi_v < rsi_os:
                continue
            if high2 < ema20_bar2:
                continue
            if close1 >= ema20_now:
                continue
            if close1 >= open1:
                continue
            if range1 > 0.0 and body1 / range1 < body_ratio_min:
                continue
            if body1 <= body2:
                continue

            sl = high1
            for s in range(1, sl_swing_bars + 1):
                if h[i - s] > sl:
                    sl = h[i - s]
            sl += 2.0 * pip

            sl_dist = (sl - bid) / pip
            if sl_dist < min_sl_pips or sl_dist > max_sl_pips:
                continue

            entry = bid
            tp = bid - (sl - bid) * min_rr

        # ------------------------------------------------------------------
        # Sizing: risk % of the *closed* balance, scaled by pyramid and by the
        # Thursday reduction, then floored to the lot step.
        # ------------------------------------------------------------------
        risk_dist = abs(entry - sl)
        risk_mult = 1.0
        if reduce_thursday_risk and dw == 4:
            risk_mult = thursday_risk_mult

        level = 0
        if use_pyramid:
            level = streak
            if level == 0:
                risk_mult *= l0_mult
            elif level == 1:
                risk_mult *= l1_mult
            else:
                risk_mult *= l2_mult

        risk_money = balance * risk_percent / 100.0 * risk_mult
        sl_ticks = risk_dist / tick_size
        lots = risk_money / (sl_ticks * tick_value)
        lots = np.floor(lots / lot_step) * lot_step
        if lots < min_lot:
            lots = min_lot
        if lots > max_lot:
            lots = max_lot
        lots = round(lots * 100.0) / 100.0
        if lots <= 0.0:
            continue

        in_pos = True
        p_dir = trend
        p_level = level
        p_lots = lots
        p_entry = entry
        p_sl = sl
        p_tp = tp
        p_risk = risk_dist
        p_sl0 = sl
        p_entry_idx = i
        p_day_entry = day_id[i]
        p_conflict = 0
        p_be = 0
        daily_trades += 1

        # The EA is live from the entry tick onward, so the entry bar can stop
        # the trade out. We only know the bar's extremes, not their order.
        if exit_on_entry_bar:
            exit_price = np.nan
            if p_dir == 1:
                hit_sl = bar_l <= p_sl
                hit_tp = bar_h >= p_tp
                if hit_sl and hit_tp:
                    p_conflict = 1
                    exit_price = p_tp if _tp_first(1, intrabar_mode, bar_o,
                                                   bar_h, bar_l) else p_sl
                elif hit_sl:
                    exit_price = p_sl
                elif hit_tp:
                    exit_price = p_tp
                elif use_breakeven and bar_h - p_entry >= p_risk * be_trigger_r:
                    p_sl = p_entry + be_offset
                    p_be = 1
            else:
                ask_h = bar_h + spread
                ask_l = bar_l + spread
                hit_sl = ask_h >= p_sl
                hit_tp = ask_l <= p_tp
                if hit_sl and hit_tp:
                    p_conflict = 1
                    exit_price = p_tp if _tp_first(-1, intrabar_mode, bar_o,
                                                    bar_h, bar_l) else p_sl
                elif hit_sl:
                    exit_price = p_sl
                elif hit_tp:
                    exit_price = p_tp
                elif use_breakeven and p_entry - ask_l >= p_risk * be_trigger_r:
                    p_sl = p_entry - be_offset
                    p_be = 1

            if not np.isnan(exit_price):
                pnl = (exit_price - p_entry) * p_dir * p_lots * contract_size
                if inverse_quote:
                    # Account currency is the base (USDJPY): profit accrues in
                    # the quote currency and MT4 converts it at the exit price.
                    pnl /= exit_price
                swap = 0.0
                if use_swap:
                    n_roll = (roll_cum[day_id[i] - day0]
                              - roll_cum[p_day_entry - day0])
                    if n_roll > 0.0:
                        rate = swap_long_per_lot if p_dir == 1 else swap_short_per_lot
                        swap = n_roll * p_lots * rate
                        pnl += swap
                balance += pnl
                out[n_trades, T_ENTRY_IDX] = p_entry_idx
                out[n_trades, T_EXIT_IDX] = i
                out[n_trades, T_DIR] = p_dir
                out[n_trades, T_LEVEL] = p_level
                out[n_trades, T_LOTS] = p_lots
                out[n_trades, T_ENTRY] = p_entry
                out[n_trades, T_SL] = p_sl
                out[n_trades, T_TP] = p_tp
                out[n_trades, T_EXIT] = exit_price
                out[n_trades, T_PNL] = pnl
                out[n_trades, T_BALANCE] = balance
                out[n_trades, T_BE] = p_be
                out[n_trades, T_RISK] = p_risk
                out[n_trades, T_SL0] = p_sl0
                out[n_trades, T_SWAP] = swap
                out[n_trades, T_CONFLICT] = p_conflict
                n_trades += 1
                if n_trades >= out.shape[0]:
                    return n_trades
                if pnl > 0.0:
                    streak += 1
                    if streak > max_streak_level:
                        streak = max_streak_level
                else:
                    streak = 0
                in_pos = False

    return n_trades


def run(md, params, max_trades=20000):
    """Run the simulation over a MarketData slice. Returns a trade matrix.

    The returned array has one row per closed trade and `T_COLS` columns; use
    the `T_*` constants to index it, or `engine.report.to_records()` for a
    dict view.
    """
    out = np.zeros((max_trades, T_COLS), dtype=np.float64)
    spread = float(params.spread_points) * float(params.point)
    entry_ema_k = 2.0 / (float(params.entry_ema_period) + 1.0)

    # Every numeric argument is coerced explicitly. Passing an int where numba
    # already specialised on a float forces a fresh compilation of the whole
    # kernel, which turns a 0.7 ms backtest into a 140 ms one during a sweep.
    f = float
    b = bool

    n = _run(
        md.ts, md.open, md.high, md.low, md.close, md.hour, md.dow, md.day_id,
        md.ema_entry_closed, md.rsi_closed,
        md.h1_valid, md.h1_ema_now, md.h1_ema_prev, md.h1_close_now, md.h1_atr_now,
        md.roll_cum, md.day0,
        f(params.initial_balance), spread, f(params.pip), f(params.tick_size),
        f(params.tick_value),
        f(params.contract_size), b(params.inverse_quote),
        f(params.min_lot), f(params.max_lot), f(params.lot_step),
        f(params.risk_percent), f(params.max_spread_pips), f(params.min_rr),
        f(params.min_sl_pips), f(params.max_sl_pips),
        b(params.use_pyramid), f(params.l0_mult), f(params.l1_mult), f(params.l2_mult),
        int(params.max_streak_level),
        entry_ema_k, int(params.sl_swing_bars), f(params.rsi_ob), f(params.rsi_os),
        f(params.body_ratio_min),
        b(params.use_london), int(params.london_start), int(params.london_end),
        int(params.ny_start), int(params.ny_end),
        b(params.use_breakeven), f(params.be_trigger_r),
        f(params.be_offset_pips) * f(params.pip), int(params.max_trades_per_day),
        b(params.use_atr_filter), f(params.atr_min_pips), f(params.atr_max_pips),
        b(params.use_ema50_dist_filter), f(params.max_ema50_dist_pips),
        b(params.block_friday), b(params.block_monday),
        params.blocked_hours_array, params.toxic_combos_array,
        b(params.reduce_thursday_risk), f(params.thursday_risk_mult),
        b(params.use_swap), f(params.swap_long_per_lot), f(params.swap_short_per_lot),
        b(params.exit_on_entry_bar),
        int(INTRABAR_MODES[params.intrabar_model]),
        out,
    )
    return out[:n]
