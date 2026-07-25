"""MT4 report parsing, performance metrics and engine/MT4 comparison."""

from collections import OrderedDict

import numpy as np

from .core import (
    T_BALANCE, T_BE, T_DIR, T_ENTRY, T_ENTRY_IDX, T_EXIT, T_EXIT_IDX, T_LEVEL,
    T_CONFLICT, T_LOTS, T_PNL, T_SL, T_SL0, T_SWAP, T_TP,
)


# ---------------------------------------------------------------------------
# MT4 side
# ---------------------------------------------------------------------------

def parse_mt4_report(path, initial_balance=10000.0):
    """Parse a Strategy Tester trade list (the resultats_*.txt files).

    Columns are tab separated:
        #  time  type  order  lots  price  s/l  t/p  profit  balance

    Returns a list of dicts, one per closed trade, in close order.
    """
    open_orders = {}
    trades = []

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 10:
                continue
            _, tstamp, kind, order, lots, price, sl, tp, profit, balance = parts[:10]
            try:
                lots_f = float(lots)
                price_f = float(price)
            except ValueError:
                continue

            if kind in ("buy", "sell"):
                open_orders[order] = {
                    "order": order,
                    "dir": 1 if kind == "buy" else -1,
                    "entry_time": tstamp,
                    "lots": lots_f,
                    "entry": price_f,
                    "sl": float(sl),
                    "tp": float(tp),
                    "balance_before": float(balance),
                }
            elif kind in ("s/l", "t/p", "close", "close at stop"):
                rec = open_orders.pop(order, None)
                if rec is None:
                    continue
                rec.update(
                    exit_time=tstamp,
                    exit=price_f,
                    exit_sl=float(sl),
                    pnl=float(profit),
                    balance=float(balance),
                    how=kind,
                )
                trades.append(rec)

    trades.sort(key=lambda t: t["exit_time"])
    return trades


def infer_pyramid_multipliers(trades, risk_percent=1.0, thursday_mult=0.5,
                              max_streak_level=2):
    """Recover the L0/L1/L2 multipliers a report was generated with.

    Lot sizes are floored to the 0.01 step, so each trade only pins the
    multiplier down to an interval. Intersecting the intervals across all
    trades at a given streak level gives a tight bracket.
    """
    import datetime as _dt

    brackets = {0: [0.0, 1e9], 1: [0.0, 1e9], 2: [0.0, 1e9]}
    streak = 0
    for t in trades:
        dist = abs(t["entry"] - t["sl"])
        if dist <= 0:
            continue
        day = _dt.datetime.strptime(t["entry_time"][:10], "%Y.%m.%d")
        thursday = day.weekday() == 3
        base = t["balance_before"] * risk_percent / 100.0
        if thursday:
            base *= thursday_mult
        # lots = floor(base * mult / (dist * 1e5) / 0.01) * 0.01
        denom = base / (dist * 1e5)
        if denom > 0:
            lo = t["lots"] / denom
            hi = (t["lots"] + 0.01) / denom
            b = brackets[streak]
            b[0] = max(b[0], lo)
            b[1] = min(b[1], hi)
        streak = min(streak + 1, max_streak_level) if t["pnl"] > 0 else 0
    return brackets


# ---------------------------------------------------------------------------
# Engine side
# ---------------------------------------------------------------------------

def to_records(trades, md):
    """Turn the raw trade matrix into readable dicts with timestamps."""
    recs = []
    for row in trades:
        i = int(row[T_ENTRY_IDX])
        j = int(row[T_EXIT_IDX])
        recs.append(
            {
                "entry_time": _fmt(md.ts[i]),
                "exit_time": _fmt(md.ts[j]),
                "dir": int(row[T_DIR]),
                "level": int(row[T_LEVEL]),
                "lots": row[T_LOTS],
                "entry": row[T_ENTRY],
                "sl": row[T_SL0],       # SL as placed, comparable to MT4's open row
                "sl_final": row[T_SL],  # after any breakeven move
                "tp": row[T_TP],
                "exit": row[T_EXIT],
                "pnl": row[T_PNL],
                "balance": row[T_BALANCE],
                "be": int(row[T_BE]),
                "swap": row[T_SWAP],
                "conflict": int(row[T_CONFLICT]),
            }
        )
    return recs


def fmt_ts(ts):
    """Format an epoch-second timestamp the way MT4 reports do."""
    return str(np.datetime64(int(ts), "s")).replace("-", ".").replace("T", " ")[:16]


_fmt = fmt_ts  # backwards-compatible alias


def metrics(pnl, balances, initial_balance):
    """Net / PF / WR / max balance drawdown, matching how MT4 reports them."""
    pnl = np.asarray(pnl, dtype=np.float64)
    n = pnl.size
    if n == 0:
        return OrderedDict(trades=0, net=0.0, pf=0.0, wr=0.0, dd_pct=0.0,
                           dd_abs=0.0, final=initial_balance, ret_dd=0.0)

    gross_win = pnl[pnl > 0].sum()
    gross_loss = -pnl[pnl < 0].sum()
    equity = np.concatenate(([initial_balance], np.asarray(balances, dtype=np.float64)))
    peak = np.maximum.accumulate(equity)
    dd_abs = float((peak - equity).max())
    dd_pct = float(((peak - equity) / peak).max() * 100.0)
    net = float(equity[-1] - initial_balance)

    return OrderedDict(
        trades=int(n),
        net=net,
        pf=float(gross_win / gross_loss) if gross_loss > 0 else float("inf"),
        wr=float((pnl > 0).sum() / n * 100.0),
        dd_pct=dd_pct,
        dd_abs=dd_abs,
        final=float(equity[-1]),
        ret_dd=float(net / initial_balance * 100.0 / dd_pct) if dd_pct > 0 else 0.0,
    )


def level_breakdown(trades):
    """Per pyramid level stats - the table CLAUDE.md tracks for L0/L1/L2."""
    rows = []
    levels = np.asarray(trades[:, T_LEVEL], dtype=int)
    pnl = trades[:, T_PNL]
    for lv in sorted(set(levels.tolist())):
        sel = pnl[levels == lv]
        wins = sel[sel > 0].sum()
        losses = -sel[sel < 0].sum()
        rows.append(
            {
                "level": lv,
                "n": int(sel.size),
                "wr": float((sel > 0).sum() / sel.size * 100.0) if sel.size else 0.0,
                "net": float(sel.sum()),
                "pf": float(wins / losses) if losses > 0 else float("inf"),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def compare(engine_recs, mt4_trades, tolerance_pips=1.0, pip=0.0001):
    """Match engine trades to MT4 trades on entry timestamp.

    Returns (matched, engine_only, mt4_only, price_diffs). Matching on the bar
    timestamp is exact by construction: both sides enter at an M15 bar open.
    """
    by_time = {}
    for t in mt4_trades:
        by_time.setdefault(t["entry_time"][:16], []).append(t)

    matched, engine_only, diffs = [], [], []
    used = set()

    for r in engine_recs:
        key = r["entry_time"]
        cands = by_time.get(key)
        if not cands:
            engine_only.append(r)
            continue
        pick = None
        for idx, t in enumerate(cands):
            if (key, idx) in used:
                continue
            if t["dir"] == r["dir"]:
                pick = (idx, t)
                break
        if pick is None:
            engine_only.append(r)
            continue
        used.add((key, pick[0]))
        t = pick[1]
        matched.append((r, t))
        diffs.append(
            {
                "time": key,
                "entry_pips": (r["entry"] - t["entry"]) / pip,
                "sl_pips": (r["sl"] - t["sl"]) / pip,
                "tp_pips": (r["tp"] - t["tp"]) / pip,
                "lots": r["lots"] - t["lots"],
                "pnl": r["pnl"] - t["pnl"],
                "same_exit": abs(r["exit"] - t["exit"]) < tolerance_pips * pip,
            }
        )

    mt4_only = []
    for key, lst in by_time.items():
        for idx, t in enumerate(lst):
            if (key, idx) not in used:
                mt4_only.append(t)
    mt4_only.sort(key=lambda t: t["entry_time"])

    return matched, engine_only, mt4_only, diffs
