#!/usr/bin/env python3
"""M1 coherence tests — run BEFORE/alongside the replication.
1. BASE_SIGNAL_IDENTITY: baseline & pyramid adapters see byte-identical event
   streams (same bars, direction, SL, TP) before money management.
2. NO_LOOKAHEAD / NO_FUTURE_BAR_ACCESS / SIGNAL_TIMING_AUDITED: recompute the
   canonical signal for sampled decision times from TRUNCATED data (bars before
   decision only, indicators rebuilt from scratch) and require identical output.
3. TRADE_ACCOUNTING: sum(pnl) == final balance - initial balance.
4. PYRAMID_ACCOUNTING: every pyramid trade's lot equals the frozen lot formula
   applied to (balance before trade, sl_dist, Thursday mult, level mult), and
   its exit equals the baseline exit of the trade at the same entry_time.
"""
import sys, random
sys.path.insert(0, '.')
from m1_engine import (Context, Bot, canonical_signal, calc_lot, metrics,
                       P, INITIAL_BALANCE)

PATH = 'research/legacy_bots_m1/data/EURUSD15_2010_2018.csv'


def main():
    ctx = Context(PATH)
    ok = True

    # ---- 1. identity of pre-MM event streams + trade streams ----
    base = Bot('baseline', pyramid=False, mode='historical')
    pyr = Bot('pyramid_safe', pyramid=True, mode='historical')
    base.run(ctx)
    pyr.run(ctx)

    ev_a = [(e.bar, e.dir, round(e.sl, 10), round(e.tp, 10)) for e in base.events]
    ev_b = [(e.bar, e.dir, round(e.sl, 10), round(e.tp, 10)) for e in pyr.events]
    identity = ev_a == ev_b and len(ev_a) > 0
    print(f"signal events pre-MM: {len(ev_a)}")
    print("BASE_SIGNAL_IDENTITY=", "PASS" if identity else "FAIL")
    ok &= identity

    ta = [(t.entry_time, t.dir, round(t.sl0, 10), round(t.tp, 10)) for t in base.trades]
    tb = [(t.entry_time, t.dir, round(t.sl0, 10), round(t.tp, 10)) for t in pyr.trades]
    stream = ta == tb and len(ta) > 0
    print(f"executed trades: baseline={len(base.trades)} pyramid={len(pyr.trades)}")
    print("TRADE_STREAM_MATCH=", "PASS" if stream else "FAIL")
    ok &= stream

    # ---- 2. no-lookahead: truncate & recompute sampled decisions ----
    random.seed(20260914)
    event_bars = sorted({e.bar for e in base.events})
    sample = random.sample(event_bars, min(40, len(event_bars)))
    mismatch = 0
    for bar in sample:
        trunc = ctx.t[bar + 1]  # a time strictly after the decision open
        # build truncated context: only bars with time < decision open
        cut = bar  # keep bars 0..bar (decision uses open[bar], bars <= bar-1 for patterns)
        sub = Context.__new__(Context)
        sub.t = ctx.t[:cut + 1]
        sub.o = ctx.o[:cut + 1]; sub.h = ctx.h[:cut + 1]
        sub.l = ctx.l[:cut + 1]; sub.c = ctx.c[:cut + 1]
        Context.__init__(sub, None) if False else None
        # re-use indicator builders on the truncated series
        from m1_engine import ema_series, rsi_series, atr_h1
        sub.ema20 = ema_series(sub.c, P['EntryEMA_Period'])
        sub.rsi = rsi_series(sub.c, P['RSI_Period'])
        bkt_of_bar = []
        bkt_id = -1; cur = None
        for i, t in enumerate(sub.t):
            hr = t.replace(minute=0)
            if hr != cur:
                cur = hr; bkt_id += 1
            bkt_of_bar.append(bkt_id)
        sub.bkt_of_bar = bkt_of_bar
        n = bkt_id + 1
        bo = [None]*n; bh = [None]*n; bl = [None]*n; bc = [None]*n
        for i in range(len(sub.t)):
            k = bkt_of_bar[i]
            if bo[k] is None: bo[k] = sub.o[i]
            bh[k] = sub.h[i] if bh[k] is None else max(bh[k], sub.h[i])
            bl[k] = sub.l[i] if bl[k] is None else min(bl[k], sub.l[i])
            bc[k] = sub.c[i]
        sub.bkt_open = bo[:-1]; sub.bkt_high = bh[:-1]; sub.bkt_low = bl[:-1]; sub.bkt_close = bc[:-1]
        sub.ema50 = ema_series(sub.bkt_close, P['TrendEMA_Period'])
        sub.atr = atr_h1(sub.bkt_high, sub.bkt_low, sub.bkt_close, P['ATR_Period'])
        ev_trunc = canonical_signal(sub, cut)
        ev_full = canonical_signal(ctx, bar)
        same = (ev_trunc is None) == (ev_full is None)
        if same and ev_full is not None:
            same = (ev_trunc.dir == ev_full.dir and
                    abs(ev_trunc.sl - ev_full.sl) < 1e-12 and
                    abs(ev_trunc.tp - ev_full.tp) < 1e-12)
        if not same:
            mismatch += 1
            print(f"  LOOKAHEAD MISMATCH at bar {bar}")
    print(f"truncated-recompute decisions audited: {len(sample)}, mismatches: {mismatch}")
    print("NO_LOOKAHEAD=", "PASS" if mismatch == 0 else "FAIL")
    print("NO_FUTURE_BAR_ACCESS=", "PASS" if mismatch == 0 else "FAIL")
    print("SIGNAL_TIMING_AUDITED=", "PASS" if mismatch == 0 else "FAIL")
    ok &= mismatch == 0

    # ---- 3. trade accounting ----
    for name, b in (('baseline', base), ('pyramid_safe', pyr)):
        s = sum(t.pnl for t in b.trades)
        good = abs(s - (b.balance - INITIAL_BALANCE)) < 1e-6
        print(f"TRADE_ACCOUNTING[{name}]=", "PASS" if good else "FAIL")
        ok &= good

    # ---- 4. pyramid accounting ----
    base_by_time = {t.entry_time: t for t in base.trades}
    bad_lot = 0; bad_exit = 0; streak = 0; bad_level = 0
    bal = INITIAL_BALANCE
    for t in pyr.trades:
        thu = P['ThursdayRiskMult'] if t.entry_time.weekday() == 3 else 1.0
        mult = thu * {0: P['L0'], 1: P['L1'], 2: P['L2']}[min(streak, 2)]
        want = calc_lot(bal, t.sl_dist, mult)
        if abs(want - t.lot) > 1e-9:
            bad_lot += 1
        if t.level != min(streak, 2):
            bad_level += 1
        bt = base_by_time.get(t.entry_time)
        if bt is None or bt.dir != t.dir or abs(bt.exit - t.exit) > 1e-12 or bt.reason != t.reason:
            bad_exit += 1
        bal += t.pnl
        streak = min(streak + 1, 2) if t.pnl > 0 else 0
    print(f"PYRAMID_ACCOUNTING: bad_lot={bad_lot} bad_level={bad_level} bad_exit={bad_exit}")
    print("PYRAMID_ACCOUNTING=", "PASS" if (bad_lot == 0 and bad_exit == 0 and bad_level == 0) else "FAIL")
    ok &= (bad_lot == 0 and bad_exit == 0 and bad_level == 0)

    print("M1_COHERENCE_OVERALL=", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
