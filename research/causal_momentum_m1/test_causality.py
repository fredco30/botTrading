#!/usr/bin/env python3
"""CAUSAL_MOMENTUM_M1 — FEATURE CAUSALITY AUDIT (mission 4).

Three automated tests per feature, on random decision timestamps:
  T1 MAX_INPUT_TIMESTAMP : max tick timestamp consumed <= decision T
  T2 TRUNCATION          : drop all ticks > T, rebuild, signal at T identical
  T3 FUTURE_MUTATION     : absurdly mutate all prices after T, signal unchanged
Runs BEFORE any PnL computation. Any failure => LAB_FEATURE_CAUSALITY_FAIL.
"""
import numpy as np
import cm_lib as C

NS = C.NS
N_SAMPLES = 30


def build(ts, bid, ask):
    bars = C.m1_bars(ts, bid, ask)
    h4_end, h4_close, h4_idx = C.h4_closes(bars["close_time"], bars["close"])
    h4_ltts = bars["last_tick_ts"][h4_idx]
    return bars, (h4_end, h4_close, h4_ltts)


def feat(bars, h4, which, j):
    if which == "H1":
        r = C.mom4h_rolling(bars, j)
    else:
        r = C.mom16h_h4_completed(bars, j, *h4)
    if r is None:
        return None
    return (r[0], int(r[1]), int(r[2]))   # (mom, cur_ts, ref_ts)


def run():
    ts, bid, ask = C.load_year(2017)
    bars, h4 = build(ts, bid, ask)
    n = len(bars["close"])
    rng = np.random.default_rng(20260915)
    all_ok = True
    results = {}
    for which in ("H1", "H2"):
        picks = rng.choice(np.arange(200, n), size=N_SAMPLES, replace=False)
        t1 = t2 = t3 = True
        for j in picks:
            T = int(bars["close_time"][j])
            full = feat(bars, h4, which, j)
            if full is None:
                continue
            mom, cur_ts, ref_ts = full
            # T1: max input timestamp <= T
            if not (cur_ts <= T and ref_ts <= T):
                t1 = False
                print(f"  T1 FAIL {which} j={j}: cur={cur_ts} ref={ref_ts} T={T}")
            # T2: truncation — drop ticks > T, rebuild, recompute
            m = int(np.searchsorted(ts, T, side="right"))
            bars_t, h4_t = build(ts[:m], bid[:m], ask[:m])
            jt = int(np.searchsorted(bars_t["close_time"], T, side="left"))
            ok_j = jt < len(bars_t["close_time"]) and bars_t["close_time"][jt] == T
            trunc = feat(bars_t, h4_t, which, jt) if ok_j else None
            if trunc is None or not (trunc[0] == mom and trunc[1] == cur_ts
                                     and trunc[2] == ref_ts):
                t2 = False
                print(f"  T2 FAIL {which} j={j}: full={full} trunc={trunc}")
            # T3: future mutation — +50 pips on every tick after T
            bid3, ask3 = bid.copy(), ask.copy()
            mut = ts > T
            bid3[mut] += 50 * C.PIP
            ask3[mut] += 50 * C.PIP
            bars_m, h4_m = build(ts, bid3, ask3)
            mutr = feat(bars_m, h4_m, which, int(j))
            if mutr is None or not (mutr[0] == mom and mutr[1] == cur_ts
                                    and mutr[2] == ref_ts):
                t3 = False
                print(f"  T3 FAIL {which} j={j}: full={full} mut={mutr}")
        results[which] = {"T1_max_input_ts": t1, "T2_truncation": t2,
                          "T3_future_mutation": t3, "samples": N_SAMPLES}
        print(f"{which}: T1_max_input_ts={'PASS' if t1 else 'FAIL'} "
              f"T2_truncation={'PASS' if t2 else 'FAIL'} "
              f"T3_future_mutation={'PASS' if t3 else 'FAIL'} ({N_SAMPLES} samples)")
        all_ok &= (t1 and t2 and t3)
    print("FEATURE_CAUSALITY:", "PASS" if all_ok else "LAB_FEATURE_CAUSALITY_FAIL")
    return all_ok


if __name__ == "__main__":
    ok = run()
    raise SystemExit(0 if ok else 2)
