#!/usr/bin/env python3
"""M1 engine — strict historical replication of EMA_Pullback_EA (baseline) and
EMA_Pullback_pyramid v1 SAFE on EURUSD M15 bid-only bars 2010-2018.

Port of the original MQL4 logic (see M1_PREREGISTRATION.md). One canonical
signal function shared by both strategy adapters. Historical quirks are
preserved on purpose in HISTORICAL mode (forming-H1 EMA50 trend, close[1] vs
forming EMA20, bid-only fills). Intra-bar OHLC ambiguity resolved pessimistically.
"""
from __future__ import annotations
import csv, math, sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    SERVER_TZ = ZoneInfo("Europe/Helsinki")  # documented assumption: IC Markets EET/EEST
except Exception:
    SERVER_TZ = timezone(timedelta(hours=2))

PIP = 0.0001
CONTRACT = 100000.0
TICK_SIZE = 0.00001
TICK_VALUE = 1.0
LOT_STEP = 0.01
MIN_LOT = 0.01
MAX_LOT = 100.0

# ---- frozen strategy parameters (M1_PREREGISTRATION.md section 5) ----
P = dict(
    RiskPercent=1.0, MaxSpreadPips=3.0, MinRR=2.5,
    MinSL_Pips=15.0, MaxSL_Pips=25.0,
    TrendEMA_Period=50, TrendBars=5, EntryEMA_Period=20, SL_SwingBars=3,
    RSI_Period=14, RSI_OB=70.0, RSI_OS=30.0,
    LondonStart=8, LondonEnd=12, NYStart=13, NYEnd=17,
    UseBreakeven=True, BE_Trigger_R=1.5, MaxTradesPerDay=2,
    UseATRFilter=True, ATR_Period=14, ATR_MinPips=9.0, ATR_MaxPips=19.0,
    UseEMA50DistFilter=True, MaxEMA50DistPips=30.0,
    BlockFriday=True, BlockHour13=True, BlockToxicCombos=True,
    ReduceThursdayRisk=True, ThursdayRiskMult=0.5,
    MaxStreakLevel=2, L0=1.0, L1=4.0, L2=2.5,  # SAFE (L-mults used by pyramid adapter only)
)
INITIAL_BALANCE = 10000.0
WARMUP_M15 = 21
WARMUP_H1 = 55

# realistic-mode costs (frozen in prereg section 13)
COMM_PER_LOT_RT = 7.0      # USD per lot round-turn
SLIP_PIPS = 0.2            # adverse pips per side (entry + stop exits)


# ---------------------------------------------------------------- data ----
def load_bars(path):
    times, o, h, l, c = [], [], [], [], []
    with open(path) as f:
        for line in f:
            d, t, oo, hh, ll, cc, _v = line.split(',')
            times.append(datetime.strptime(d + ' ' + t, '%Y.%m.%d %H:%M'))
            o.append(float(oo)); h.append(float(hh)); l.append(float(ll)); c.append(float(cc))
    return times, o, h, l, c


# ---------------------------------------------------------- indicators ----
def ema_series(vals, period):
    """MT4-style EMA over a closed-bar series; seeded with the first value."""
    a = 2.0 / (period + 1.0)
    out = [0.0] * len(vals)
    e = vals[0]
    out[0] = e
    for i in range(1, len(vals)):
        e = e + a * (vals[i] - e)
        out[i] = e
    return out


def rsi_series(closes, period):
    """MT4 iRSI (Wilder SMMA), seeded with SMA of first `period` moves."""
    n = len(closes)
    out = [None] * n
    if n <= period:
        return out
    g = 0.0; ls = 0.0
    for i in range(1, period + 1):
        ch = closes[i] - closes[i - 1]
        if ch > 0: g += ch
        else: ls -= ch
    ag = g / period; al = ls / period
    out[period] = 100.0 - 100.0 / (1.0 + (ag / al if al > 0 else float('inf')))
    for i in range(period + 1, n):
        ch = closes[i] - closes[i - 1]
        gain = ch if ch > 0 else 0.0
        loss = -ch if ch < 0 else 0.0
        ag = (ag * (period - 1) + gain) / period
        al = (al * (period - 1) + loss) / period
        out[i] = 100.0 - 100.0 / (1.0 + (ag / al if al > 0 else float('inf')))
    return out


def atr_h1(buckets_hi, buckets_lo, buckets_close, period):
    """Wilder ATR over closed H1 buckets (SMA seed), as MT4 iATR."""
    n = len(buckets_hi)
    out = [None] * n
    if n == 0:
        return out
    trs = [0.0] * n
    trs[0] = buckets_hi[0] - buckets_lo[0]
    for i in range(1, n):
        tr = max(buckets_hi[i], buckets_close[i - 1]) - min(buckets_lo[i], buckets_close[i - 1])
        trs[i] = tr
    if n < period:
        return out
    a = sum(trs[:period]) / period
    out[period - 1] = a
    for i in range(period, n):
        a = a + (trs[i] - a) / period
        out[i] = a
    return out


class Context:
    """Causal market context built once; every query is O(1) and uses only
    information available at decision time."""

    def __init__(self, path):
        self.t, self.o, self.h, self.l, self.c = load_bars(path)
        self.ema20 = ema_series(self.c, P['EntryEMA_Period'])
        self.rsi = rsi_series(self.c, P['RSI_Period'])
        # H1 buckets (closed)
        self.bkt_index = []      # for each M15 bar: index of its bucket
        bkt_of_bar = []
        bkt_id = -1
        cur_hour = None
        for i, t in enumerate(self.t):
            hr = t.replace(minute=0, second=0)
            if hr != cur_hour:
                cur_hour = hr
                bkt_id += 1
            bkt_of_bar.append(bkt_id)
        self.bkt_of_bar = bkt_of_bar
        n_bkt = bkt_id + 1
        bo = [None] * n_bkt; bh = [None] * n_bkt; bl = [None] * n_bkt; bc = [None] * n_bkt
        bt = [None] * n_bkt
        for i in range(len(self.t)):
            k = bkt_of_bar[i]
            if bo[k] is None:
                bo[k] = self.o[i]; bt[k] = self.t[i].replace(minute=0)
            bh[k] = self.h[i] if bh[k] is None else max(bh[k], self.h[i])
            bl[k] = self.l[i] if bl[k] is None else min(bl[k], self.l[i])
            bc[k] = self.c[i]
        # bucket k is CLOSED once a bar of bucket k+1 exists
        self.bkt_open = [bo[k] for k in range(n_bkt - 1)]
        self.bkt_high = [bh[k] for k in range(n_bkt - 1)]
        self.bkt_low = [bl[k] for k in range(n_bkt - 1)]
        self.bkt_close = [bc[k] for k in range(n_bkt - 1)]
        self.ema50 = ema_series(self.bkt_close, P['TrendEMA_Period'])
        self.atr = atr_h1(self.bkt_high, self.bkt_low, self.bkt_close, P['ATR_Period'])

    def forming_h1(self, i, price):
        """(ema_now_forming, ema_prev_shift5, atr_forming) using only closed
        buckets + the forming price — faithful to MT4 shift-0 semantics."""
        k = self.bkt_of_bar[i] - 1          # last CLOSED bucket
        a50 = 2.0 / (P['TrendEMA_Period'] + 1.0)
        ema_last = self.ema50[k]
        ema_now = ema_last + a50 * (price - ema_last)
        ema_prev = self.ema50[k - (P['TrendBars'] - 1)] if k - (P['TrendBars'] - 1) >= 0 else None
        # shift 5 counts the forming bar itself: forming=0, closed 1..5 -> index k-4
        ema_prev = self.ema50[k - 4] if k - 4 >= 0 else None
        a14 = 1.0 / P['ATR_Period']
        tr0 = abs(price - self.bkt_close[k])
        atr_last = self.atr[k]
        atr0 = atr_last + a14 * (tr0 - atr_last) if atr_last is not None else None
        return ema_now, ema_prev, atr0


# ----------------------------------------------------------- signal ----
@dataclass
class Event:
    bar: int
    time: datetime
    dir: int          # +1 buy, -1 sell
    entry_ref: float  # bid (hist) at decision; sl/tp derived per-mode
    sl: float
    tp: float
    sl_dist: float


def canonical_signal(ctx: Context, i: int, spread: float = 0.0):
    """Single canonical signal, port of GetTrendDirection()+CheckEntry().
    Returns Event or None. `spread` = ask-bid at decision (0 in historical mode).
    Bid-only filters evaluated on bid; buy sl/tp computed from ask (port exact)."""
    if i < WARMUP_M15 or ctx.bkt_of_bar[i] - 1 < WARMUP_H1:
        return None
    t = ctx.t[i]
    p = ctx.o[i]                       # decision price (bid at bar open)
    ask = p + spread
    hour, dow = t.hour, t.weekday()    # python Mon=0 .. Fri=4 (MT4 Fri=5)

    # --- OnTick pre-checks (order preserved) ---
    in_session = (P['LondonStart'] <= hour < P['LondonEnd']) or (P['NYStart'] <= hour < P['NYEnd'])
    if not in_session:
        return None
    if spread > P['MaxSpreadPips']:    # hist: spread=0 -> always pass
        return None
    if P['BlockFriday'] and dow == 4:
        return None
    if P['BlockHour13'] and hour == 13:
        return None
    if P['BlockToxicCombos']:
        if (hour, dow) in ((14, 1), (11, 0), (14, 3), (16, 0)):
            return None
    if P['UseATRFilter']:
        ema_any, _, atr0 = ctx.forming_h1(i, p)
        if atr0 is None:
            return None
        atr_pips = atr0 / PIP
        if atr_pips < P['ATR_MinPips'] or atr_pips > P['ATR_MaxPips']:
            return None
    if P['UseEMA50DistFilter']:
        ema_now, _, _ = ctx.forming_h1(i, p)
        if abs(p - ema_now) / PIP > P['MaxEMA50DistPips']:
            return None

    # --- GetTrendDirection (forming H1, preserved) ---
    ema_now, ema_prev, _ = ctx.forming_h1(i, p)
    if ema_prev is None:
        return None
    if p > ema_now and ema_now > ema_prev:
        trend = 1
    elif p < ema_now and ema_now < ema_prev:
        trend = -1
    else:
        return None

    b1, b2 = i - 1, i - 2
    o1, c1, h1, l1 = ctx.o[b1], ctx.c[b1], ctx.h[b1], ctx.l[b1]
    o2, c2, h2, l2 = ctx.o[b2], ctx.c[b2], ctx.h[b2], ctx.l[b2]
    body1 = abs(c1 - o1); range1 = h1 - l1; body2 = abs(c2 - o2)
    rsi1 = ctx.rsi[b1]
    ema20_bar2 = ctx.ema20[b2]
    a20 = 2.0 / (P['EntryEMA_Period'] + 1.0)
    ema20_form = ctx.ema20[b1] + a20 * (p - ctx.ema20[b1])   # forming EMA20 (preserved quirk)

    if trend == 1:
        if rsi1 is None or rsi1 > P['RSI_OB']:
            return None
        if l2 > ema20_bar2:
            return None
        if c1 <= ema20_form:
            return None
        if c1 <= o1:
            return None
        if range1 > 0 and body1 / range1 < 0.6:
            return None
        if body1 <= body2:
            return None
        sl = l1
        for k in range(1, P['SL_SwingBars'] + 1):
            if ctx.l[i - k] < sl:
                sl = ctx.l[i - k]
        sl -= 2 * PIP
        sl_dist = (ask - sl)
        if sl_dist / PIP < P['MinSL_Pips'] or sl_dist / PIP > P['MaxSL_Pips']:
            return None
        tp = ask + sl_dist * P['MinRR']
        return Event(i, t, 1, p, sl, tp, sl_dist)

    else:
        if rsi1 is None or rsi1 < P['RSI_OS']:
            return None
        if h2 < ema20_bar2:
            return None
        if c1 >= ema20_form:
            return None
        if c1 >= o1:
            return None
        if range1 > 0 and body1 / range1 < 0.6:
            return None
        if body1 <= body2:
            return None
        sl = h1
        for k in range(1, P['SL_SwingBars'] + 1):
            if ctx.h[i - k] > sl:
                sl = ctx.h[i - k]
        sl += 2 * PIP
        sl_dist = (sl - p)          # sell: distance measured from BID (port exact)
        if sl_dist / PIP < P['MinSL_Pips'] or sl_dist / PIP > P['MaxSL_Pips']:
            return None
        tp = p - sl_dist * P['MinRR']
        return Event(i, t, -1, p, sl, tp, sl_dist)


# ------------------------------------------------------- trade walker ----
@dataclass
class Trade:
    entry_time: datetime; exit_time: datetime
    dir: int; level: int; lot: float
    entry: float; sl0: float; tp: float; sl_dist: float
    exit: float; reason: str; pnl: float; r_mult: float
    balance_after: float; be_moved: bool


def simulate_exit(ctx, ev, trade, spread_fn=None):
    """Walk M15 bars from entry bar open; pessimistic OHLC conventions.
    Buy: SL/TP/BE-trigger on BID. Sell: triggers on ASK (bid+spread; spread of
    the decision bar used for the whole trade — documented approximation).
    Returns (exit_price_exec, exit_time, reason, be_moved, exit_slip)."""
    i0 = ev.bar
    d = ev.dir
    entry_exec = trade.entry
    sl = ev.sl if d == 1 else ev.sl
    tp = ev.tp
    risk = ev.sl_dist
    be_trig = risk * P['BE_Trigger_R']
    be_moved = False
    spread0 = spread_fn(ctx.t[i0]) if spread_fn else 0.0

    for i in range(i0, len(ctx.t)):
        o, h, l = ctx.o[i], ctx.h[i], ctx.l[i]
        if d == 1:
            bh = h                     # triggers on bid
            bl = l
        else:
            sp = spread_fn(ctx.t[i]) if spread_fn else spread0
            bh = h + sp                # ask path for sells
            bl = l + sp
        # gap at open (trade already open before this bar)
        if i > i0:
            if d == 1:
                if o <= sl:
                    return o, ctx.t[i], 'sl', be_moved, 0.0
                if o >= tp:
                    return o, ctx.t[i], 'tp', be_moved, 0.0
            else:
                sp_o = spread_fn(ctx.t[i]) if spread_fn else spread0
                if o + sp_o >= sl:
                    return o + sp_o, ctx.t[i], 'sl', be_moved, 0.0
                if o + sp_o <= tp:
                    return o + sp_o, ctx.t[i], 'tp', be_moved, 0.0
        # BE trigger + SL + TP within the bar (pessimistic order)
        if d == 1:
            hit_tp = bh >= tp
            hit_sl = bl <= sl
            trig = (not be_moved) and P['UseBreakeven'] and (bh - entry_exec) >= be_trig and sl < entry_exec
            if hit_sl:
                return sl, ctx.t[i], 'sl', be_moved, 1.0
            if trig:
                sl = entry_exec + 1 * PIP
                be_moved = True
                if bl <= sl:                       # same-bar pullback (pessimistic)
                    return sl, ctx.t[i], 'sl', be_moved, 1.0
            if hit_tp:
                return tp, ctx.t[i], 'tp', be_moved, 0.0
        else:
            hit_tp = bl <= tp
            hit_sl = bh >= sl
            trig = (not be_moved) and P['UseBreakeven'] and (entry_exec - bh) >= be_trig and sl > entry_exec
            if hit_sl:
                return sl, ctx.t[i], 'sl', be_moved, 1.0
            if trig:
                sl = entry_exec - 1 * PIP
                be_moved = True
                if bh >= sl:                       # same-bar pullback (pessimistic)
                    return sl, ctx.t[i], 'sl', be_moved, 1.0
            if hit_tp:
                return tp, ctx.t[i], 'tp', be_moved, 0.0
    # data end with open trade -> close at last bar close (documented; window end)
    last = len(ctx.t) - 1
    px = ctx.c[last] if d == 1 else ctx.c[last] + (spread_fn(ctx.t[last]) if spread_fn else 0.0)
    return px, ctx.t[last], 'eod', be_moved, 1.0


def calc_lot(balance, sl_dist_price, mult):
    risk_money = balance * P['RiskPercent'] / 100.0 * mult
    sl_ticks = sl_dist_price / TICK_SIZE
    lot = risk_money / (sl_ticks * TICK_VALUE)
    lot = math.floor(lot / LOT_STEP) * LOT_STEP
    lot = max(MIN_LOT, min(MAX_LOT, lot))
    return round(lot, 2)


def trade_pnl(d, entry, exit_, lot, sl_dist, commission=0.0):
    move = (exit_ - entry) if d == 1 else (entry - exit_)
    return move * lot * CONTRACT - commission * lot


# ----------------------------------------------------------- adapters ----
class Bot:
    def __init__(self, name, pyramid=False, mode='historical', spread_fn=None):
        self.name = name
        self.pyramid = pyramid
        self.mode = mode
        self.spread_fn = spread_fn      # returns spread in PRICE units
        self.balance = INITIAL_BALANCE
        self.streak = 0
        self.daily = 0
        self.cur_day = None
        self.open_trade = None
        self.trades = []
        self.events = []                # pre-MM event stream (identity audit)

    def level_mult(self):
        if not self.pyramid:
            return 1.0
        return {0: P['L0'], 1: P['L1'], 2: P['L2']}[min(self.streak, P['MaxStreakLevel'])]

    def run(self, ctx: Context):
        for i in range(len(ctx.t)):
            t = ctx.t[i]
            day = t.date()
            if day != self.cur_day:
                self.cur_day = day
                self.daily = 0

            # --- exits of the open trade are simulated per-bar inside the
            #     walker; here we detect the pending entry decision only when
            #     no trade is open at bar-open time. ---
            entry_blocked_by_position = self.open_trade is not None
            ev = canonical_signal(ctx, i, spread=(self.spread_fn(t) if self.spread_fn else 0.0))
            if ev is not None:
                self.events.append(ev)

            if ev is not None and not entry_blocked_by_position and self.daily < P['MaxTradesPerDay']:
                d = ev.dir
                spread = self.spread_fn(t) if self.spread_fn else 0.0
                slip = SLIP_PIPS * PIP if self.mode == 'realistic' else 0.0
                # SL/TP stay as computed by the EA from the observed price
                # (buy: ask incl. spread; sell: bid); only the FILL slips.
                entry = ev.entry_ref + spread + slip if d == 1 else ev.entry_ref - slip
                sl_dist = ev.sl_dist
                thu = P['ThursdayRiskMult'] if (P['ReduceThursdayRisk'] and t.weekday() == 3) else 1.0
                mult = thu * self.level_mult()
                lot = calc_lot(self.balance, sl_dist, mult)
                trade = Trade(t, None, d, min(self.streak, 2) if self.pyramid else 0,
                              lot, entry, ev.sl, ev.tp, sl_dist, None, None, 0.0, 0.0, 0.0, False)
                self.open_trade = (ev, trade, d)
                self.daily += 1

            # --- simulate the (possibly just-opened) trade across this bar ---
            if self.open_trade is not None:
                ev0, tr, d = self.open_trade
                exit_px, exit_t, reason, be_moved, slip_side = simulate_exit(
                    ctx, ev0, tr, spread_fn=self.spread_fn)
                if self.mode == 'realistic' and reason in ('sl', 'eod'):
                    exit_px += (-SLIP_PIPS * PIP if d == 1 else SLIP_PIPS * PIP)
                comm = COMM_PER_LOT_RT if self.mode == 'realistic' else 0.0
                pnl = trade_pnl(d, tr.entry, exit_px, tr.lot, tr.sl_dist, comm)
                tr.exit = exit_px; tr.exit_time = exit_t; tr.reason = reason
                tr.pnl = pnl; tr.be_moved = be_moved
                tr.r_mult = pnl / (tr.sl_dist * tr.lot * CONTRACT)
                tr.balance_after = self.balance + pnl
                self.balance += pnl
                self.trades.append(tr)
                if pnl > 0:
                    self.streak = min(self.streak + 1, P['MaxStreakLevel'])
                else:
                    self.streak = 0
                self.open_trade = None


# ------------------------------------------------------------ metrics ----
def metrics(trades):
    n = len(trades)
    if n == 0:
        return dict(TRADES=0)
    wins = [t.pnl for t in trades if t.pnl > 0]
    losses = [t.pnl for t in trades if t.pnl <= 0]
    gross = sum(wins); lg = sum(losses)
    pf = gross / abs(lg) if lg != 0 else float('inf')
    peak = INITIAL_BALANCE; bal = INITIAL_BALANCE; maxdd = 0.0; maxdd_pct = 0.0
    for t in trades:
        bal = t.balance_after
        peak = max(peak, bal)
        dd = peak - bal
        if dd > maxdd:
            maxdd = dd
        if peak > 0 and (dd / peak) > maxdd_pct:
            maxdd_pct = dd / peak
    consec = 0; mx = 0
    for t in trades:
        if t.pnl <= 0:
            consec += 1; mx = max(mx, consec)
        else:
            consec = 0
    avg_w = gross / len(wins) if wins else 0.0
    avg_l = lg / len(losses) if losses else 0.0
    return dict(
        TRADES=n,
        WIN_RATE=round(100.0 * len(wins) / n, 2),
        NET_PROFIT=round(sum(t.pnl for t in trades), 2),
        PROFIT_FACTOR=round(pf, 4),
        MAX_DRAWDOWN_ABS=round(maxdd, 2),
        MAX_DRAWDOWN_PCT=round(100.0 * maxdd_pct, 2),
        EXPECTANCY_PER_TRADE=round(sum(t.pnl for t in trades) / n, 2),
        AVG_WIN=round(avg_w, 2),
        AVG_LOSS=round(avg_l, 2),
        PAYOFF_RATIO=round(avg_w / abs(avg_l), 4) if avg_l else float('inf'),
        MAX_CONSECUTIVE_LOSSES=mx,
        SUM_R=round(sum(t.r_mult for t in trades), 2),
        EXPECTANCY_R=round(sum(t.r_mult for t in trades) / n, 4),
    )


def yearly(trades):
    out = {}
    for t in trades:
        y = t.entry_time.year
        a = out.setdefault(y, dict(trades=0, net=0.0, wins=0.0, losses=0.0, peak=INITIAL_BALANCE,
                                   bal=INITIAL_BALANCE, maxdd=0.0, bal_start=None))
        a['trades'] += 1
        a['net'] += t.pnl
        if t.pnl > 0:
            a['wins'] += t.pnl
        else:
            a['losses'] += t.pnl
        a['bal'] = t.balance_after
        if a['bal_start'] is None:
            a['bal_start'] = t.balance_after - t.pnl
        a['peak'] = max(a['peak'], a['bal'])
        a['maxdd'] = max(a['maxdd'], a['peak'] - a['bal'])
    return out


# -------------------------------------------------------------- main ----
def run_all(data_path):
    ctx = Context(data_path)
    bots = {
        'baseline': Bot('baseline', pyramid=False, mode='historical'),
        'pyramid_safe': Bot('pyramid_safe', pyramid=True, mode='historical'),
    }
    for b in bots.values():
        b.run(ctx)
    return ctx, bots


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else 'research/legacy_bots_m1/data/EURUSD15_2010_2018.csv'
    ctx, bots = run_all(path)
    for name, b in bots.items():
        m = metrics(b.trades)
        print(f"== {name} ==")
        for k, v in m.items():
            print(f"  {k}={v}")
        # trade-stream identity check
    ev_a = bots['baseline'].events
    ev_b = bots['pyramid_safe'].events
    same = len(ev_a) == len(ev_b) and all(
        a.bar == b.bar and a.dir == b.dir and a.sl == b.sl and a.tp == b.tp
        for a, b in zip(ev_a, ev_b))
    print("BASE_SIGNAL_IDENTITY=", "PASS" if same else "FAIL")
    ta = abs(sum(t.pnl for t in bots['baseline'].trades) -
             (bots['baseline'].balance - INITIAL_BALANCE)) < 1e-6
    print("TRADE_ACCOUNTING=", "PASS" if ta else "FAIL")
    seq_match = ([(t.entry_time, t.dir) for t in bots['baseline'].trades] ==
                 [(t.entry_time, t.dir) for t in bots['pyramid_safe'].trades])
    print("TRADE_STREAM_MATCH=", "PASS" if seq_match else "FAIL")
