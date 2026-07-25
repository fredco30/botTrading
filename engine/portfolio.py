"""Portfolio simulation across instruments with one shared, compounding equity.

Why this can be built by replaying per-instrument trades rather than by running
one big simultaneous loop: in this system the entry level, the stop and the
exit are all price-derived. Position *size* depends on equity, but nothing
about *when* a trade opens or closes does. P&L is linear in size, so a trade
recorded at some reference risk can be rescaled exactly to whatever risk the
shared equity implies at its entry timestamp.

That gives a portfolio curve that is exact rather than approximate, at the cost
of ignoring lot-step rounding at the portfolio level - worth a fraction of a
percent, and it errs neither way systematically.

The correlation caveat is not solved by any of this: EURUSD and GBPUSD trend
together, so two simultaneous positions are closer to one double-sized bet than
to two independent ones. `max_concurrent` and `corr_groups` exist to bound that
rather than pretend it away.
"""

from dataclasses import dataclass

import numpy as np

from . import trend


@dataclass
class PortfolioResult:
    equity: np.ndarray        # equity after each closed trade
    times: np.ndarray         # exit timestamp of each closed trade
    symbols: list
    r_multiples: np.ndarray
    final: float
    initial: float
    max_dd_pct: float
    cagr: float
    trades: int
    skipped: int              # trades refused by the concurrency cap


def to_r_multiples(trades, ts, symbol):
    """Convert a raw trade matrix into (entry_ts, exit_ts, R-multiple) rows.

    R is P&L divided by the money that was actually at risk on that trade, so
    it is independent of account size and can be rescaled freely.
    """
    if len(trades) == 0:
        return []
    rows = []
    for t in trades:
        risk = t[trend.R_RISK]
        if risk <= 0:
            continue
        rows.append(
            (int(ts[int(t[trend.R_ENTRY_IDX])]),
             int(ts[int(t[trend.R_EXIT_IDX])]),
             t[trend.R_PNL] / risk,
             symbol)
        )
    return rows


def simulate(all_rows, risk_pct=1.0, initial=10000.0, max_concurrent=4,
             corr_groups=None, max_group_concurrent=99, ruin_floor=0.10):
    """Replay every instrument's trades on one compounding account.

    `corr_groups` maps a symbol to a group name; at most `max_group_concurrent`
    positions may be open inside a group at once. Used to stop EURUSD and
    GBPUSD from silently becoming a single double-sized position.
    """
    corr_groups = corr_groups or {}
    rows = sorted(all_rows, key=lambda r: (r[0], r[3]))

    equity = initial
    peak = initial
    max_dd = 0.0
    open_pos = []      # (exit_ts, symbol, risk_money)
    eq_curve = []
    eq_times = []
    syms = []
    rmults = []
    skipped = 0

    for entry_ts, exit_ts, r, sym in rows:
        # Close everything that finished before this entry, in time order.
        open_pos.sort()
        while open_pos and open_pos[0][0] <= entry_ts:
            _, s, risk_money, rr = open_pos.pop(0)
            equity += rr * risk_money
            peak = max(peak, equity)
            if peak > 0:
                max_dd = max(max_dd, (peak - equity) / peak)
            eq_curve.append(equity)
            eq_times.append(_)
            syms.append(s)
            rmults.append(rr)

        if equity <= initial * ruin_floor:
            break

        if len(open_pos) >= max_concurrent:
            skipped += 1
            continue
        grp = corr_groups.get(sym)
        if grp is not None:
            n_grp = sum(1 for p in open_pos if corr_groups.get(p[1]) == grp)
            if n_grp >= max_group_concurrent:
                skipped += 1
                continue

        risk_money = equity * risk_pct / 100.0
        open_pos.append((exit_ts, sym, risk_money, r))

    open_pos.sort()
    for _, s, risk_money, rr in open_pos:
        equity += rr * risk_money
        peak = max(peak, equity)
        if peak > 0:
            max_dd = max(max_dd, (peak - equity) / peak)
        eq_curve.append(equity)
        eq_times.append(_)
        syms.append(s)
        rmults.append(rr)

    eq = np.asarray(eq_curve)
    tt = np.asarray(eq_times, dtype=np.int64)
    years = (tt[-1] - tt[0]) / (365.25 * 86400) if tt.size > 1 else 0.0
    cagr = ((equity / initial) ** (1 / years) - 1) * 100 if years > 0 and equity > 0 else -100.0

    return PortfolioResult(
        equity=eq, times=tt, symbols=syms, r_multiples=np.asarray(rmults),
        final=equity, initial=initial, max_dd_pct=max_dd * 100.0,
        cagr=cagr, trades=eq.size, skipped=skipped,
    )


def rolling_windows(all_rows, years=5, step_months=6, **kw):
    """Every `years`-long window, stepped `step_months` at a time.

    A single 5-year backtest says what one draw of the dice did. The spread
    across all available windows says what the strategy is.
    """
    rows = sorted(all_rows, key=lambda r: r[0])
    if not rows:
        return []
    t0, t1 = rows[0][0], rows[-1][1]
    span = int(years * 365.25 * 86400)
    step = int(step_months * 30.44 * 86400)
    out = []
    start = t0
    while start + span <= t1:
        end = start + span
        sub = [r for r in rows if r[0] >= start and r[1] <= end]
        if len(sub) >= 20:
            res = simulate(sub, **kw)
            out.append((start, end, res))
        start += step
    return out
