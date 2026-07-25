"""Explain, filter by filter, why the engine did or did not enter on a bar.

Used to chase down disagreements with an MT4 report: given a timestamp where
MT4 opened a trade and the engine did not, this reproduces the EA's checks in
order and reports the first one that rejected the bar.
"""

import numpy as np

from .indicators import ema_step


def explain(md, params, timestamp):
    """Return an ordered list of (check_name, passed, detail) for one bar."""
    ts = np.datetime64(timestamp.replace(".", "-").replace(" ", "T"), "s").astype("int64")
    idx = int(np.searchsorted(md.ts, ts))
    if idx >= md.ts.size or md.ts[idx] != ts:
        return [("bar_exists", False, f"no M15 bar at {timestamp}")]

    i = idx
    p = params
    out = [("bar_exists", True, f"index {i}")]

    hr, dw = int(md.hour[i]), int(md.dow[i])
    in_session = ((p.use_london and p.london_start <= hr < p.london_end)
                  or (p.ny_start <= hr < p.ny_end))
    out.append(("session", in_session, f"hour={hr} dow={dw}"))

    out.append(("day_filter",
                not ((p.block_friday and dw == 5) or (p.block_monday and dw == 1)),
                f"dow={dw}"))
    out.append(("hour_filter", hr not in p.blocked_hours, f"blocked={p.blocked_hours}"))
    if p.block_toxic_combos:
        out.append(("toxic_combo", (hr, dw) not in p.toxic_combos, f"({hr},{dw})"))

    out.append(("h1_warm", bool(md.h1_valid[i]), ""))
    if not md.h1_valid[i]:
        return out

    atr_pips = md.h1_atr_now[i] / p.pip
    if p.use_atr_filter:
        ok = atr_pips >= p.atr_min_pips and (p.atr_max_pips <= 0 or atr_pips <= p.atr_max_pips)
        out.append(("atr", ok,
                    f"{atr_pips:.1f} pips, need {p.atr_min_pips}-{p.atr_max_pips}"))

    spread = p.spread_points * p.point
    mid = md.open[i] + spread * 0.5
    dist = abs(mid - md.h1_ema_now[i]) / p.pip
    if p.use_ema50_dist_filter:
        out.append(("ema50_dist", dist <= p.max_ema50_dist_pips,
                    f"{dist:.1f} pips, max {p.max_ema50_dist_pips}"))

    ema_now, ema_prev = md.h1_ema_now[i], md.h1_ema_prev[i]
    close_h1 = md.h1_close_now[i]
    trend = 1 if (close_h1 > ema_now and ema_now > ema_prev) else (
        -1 if (close_h1 < ema_now and ema_now < ema_prev) else 0)
    out.append(("h1_trend", trend != 0,
                f"trend={trend} close={close_h1:.5f} ema={ema_now:.5f} "
                f"ema[-{p.trend_bars}]={ema_prev:.5f}"))
    if trend == 0:
        return out

    ema20_now = ema_step(md.ema_entry_closed[i - 1], md.open[i], p.entry_ema_period)
    ema20_b2 = md.ema_entry_closed[i - 2]
    o1, c1, h1_, l1_ = md.open[i - 1], md.close[i - 1], md.high[i - 1], md.low[i - 1]
    o2, c2, h2, l2 = md.open[i - 2], md.close[i - 2], md.high[i - 2], md.low[i - 2]
    body1, range1, body2 = abs(c1 - o1), h1_ - l1_, abs(c2 - o2)
    rsi_v = md.rsi_closed[i - 1]

    if trend == 1:
        out.append(("rsi", rsi_v <= p.rsi_ob, f"{rsi_v:.1f} <= {p.rsi_ob}"))
        out.append(("pullback_touch", l2 <= ema20_b2,
                    f"low2={l2:.5f} ema20[2]={ema20_b2:.5f}"))
        out.append(("close_above_ema", c1 > ema20_now,
                    f"close1={c1:.5f} ema20={ema20_now:.5f}"))
        out.append(("bar1_bullish", c1 > o1, ""))
    else:
        out.append(("rsi", rsi_v >= p.rsi_os, f"{rsi_v:.1f} >= {p.rsi_os}"))
        out.append(("pullback_touch", h2 >= ema20_b2,
                    f"high2={h2:.5f} ema20[2]={ema20_b2:.5f}"))
        out.append(("close_below_ema", c1 < ema20_now,
                    f"close1={c1:.5f} ema20={ema20_now:.5f}"))
        out.append(("bar1_bearish", c1 < o1, ""))

    out.append(("body_ratio", not (range1 > 0 and body1 / range1 < p.body_ratio_min),
                f"{body1 / range1:.2f}" if range1 > 0 else "range=0"))
    out.append(("body1_gt_body2", body1 > body2,
                f"{body1 / p.pip:.1f} vs {body2 / p.pip:.1f} pips"))

    if trend == 1:
        sl = min([l1_] + [md.low[i - s] for s in range(1, p.sl_swing_bars + 1)]) - 2 * p.pip
        sl_dist = (md.open[i] + spread - sl) / p.pip
    else:
        sl = max([h1_] + [md.high[i - s] for s in range(1, p.sl_swing_bars + 1)]) + 2 * p.pip
        sl_dist = (sl - md.open[i]) / p.pip
    out.append(("sl_range", p.min_sl_pips <= sl_dist <= p.max_sl_pips,
                f"{sl_dist:.1f} pips, need {p.min_sl_pips}-{p.max_sl_pips}"))
    return out


def first_failure(md, params, timestamp):
    """Name of the first check that rejected the bar, or None if all passed."""
    for name, ok, detail in explain(md, params, timestamp):
        if not ok:
            return name, detail
    return None
