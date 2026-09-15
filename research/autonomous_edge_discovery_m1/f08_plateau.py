#!/usr/bin/env python3
"""F08 absorption plateau: structural neighborhood (lookback, fade bars,
mid-fade strictness) — coarse, no fine grids. Tick-exact replay each."""
import numpy as np
import pandas as pd
import m1lib as M
import infra_lib as I
import ledger as L

PIP = I.PIP
ts, bid, ask = I.load_year(2017)
bars = M.add_n_ticks(ts, I.m1_bars(ts, bid, ask))
months = pd.to_datetime(bars["close_time"], utc=True).month.to_numpy()


def make_feat(lookback, fade_n):
    def feat(bars, ex, j):
        if j < lookback + fade_n:
            return None
        import families as F
        hi = ex[f"hh{lookback}"][j] if f"hh{lookback}" in ex else None
        lo = ex[f"ll{lookback}"][j] if f"ll{lookback}" in ex else None
        if hi is None:
            return None
        closes = bars["close"][j - fade_n + 1:j + 1]
        mids = (bars["high"][j - fade_n + 1:j + 1]
                + bars["low"][j - fade_n + 1:j + 1]) / 2
        # up: current bar makes fresh extreme; all `fade_n` closes fade below mids
        if bars["high"][j] > hi and np.all(closes < mids):
            ok_fade = np.all(np.diff(closes) < 0)
            return {"value": float((closes[-1] - max(bars["high"][j - fade_n + 1:j + 1])) / PIP),
                    "input_ts": [bars["last_tick_ts"][j]], "aux": 1, "fade": ok_fade}
        if bars["low"][j] < lo and np.all(closes > mids):
            ok_fade = np.all(np.diff(closes) > 0)
            return {"value": float((closes[-1] - min(bars["low"][j - fade_n + 1:j + 1])) / PIP),
                    "input_ts": [bars["last_tick_ts"][j]], "aux": -1, "fade": ok_fade}
        return None
    return feat


def build_ex(lookback):
    def bex(ts, bid, ask, bars):
        import families as F
        ex = F.extras_common(ts, bid, ask, bars)
        import pandas as pd
        s = pd.Series
        ex[f"hh{lookback}"] = s(bars["high"]).shift(1).rolling(lookback).max().to_numpy()
        ex[f"ll{lookback}"] = s(bars["low"]).shift(1).rolling(lookback).min().to_numpy()
        return ex
    return bex


def sign_both(f):
    if not f.get("fade"):
        return 0
    if f["aux"] == 1 and f["value"] < 0:
        return -1
    if f["aux"] == -1 and f["value"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    for lookback in (90, 120, 180):
        for fade_n in (2, 3):
            feat = make_feat(lookback, fade_n)
            bex = build_ex(lookback)
            ex = bex(ts, bid, ask, bars)
            ok, ntest = M.causality_gate(f"F08p_lb{lookback}f{fade_n}", feat, bex,
                                         bars, ex, 24)
            if not ok:
                L.log("F08", "absorption plateau", "FAIL", f"lb={lookback} fade={fade_n}",
                      status="CAUSALITY_FAIL", reason="")
                continue
            sig = M.signal_vector(feat, sign_both, ts, bid, ask, bars, ex)
            base, _ = I.replay(ts, bid, ask, bars, sig, latency_ns=I.LATENCY_NS, slip_pips=0.0)
            stress, _ = I.replay(ts, bid, ask, bars, sig, latency_ns=30 * I.NS, slip_pips=0.50)
            bc, sc = I.common_sample(base, stress)
            mb = I.metrics(base, months, "p")
            mbc = I.metrics(bc, months, "p")
            msc = I.metrics(sc, months, "p")
            L.log("F08", "absorption plateau", "PASS",
                  f"lb={lookback} fade={fade_n} SL15 TP15 T120", mb.get("N", 0),
                  mb.get("mean_pips"), mb.get("PF"), mb.get("expectancy_r"),
                  stress_pips=msc.get("mean_pips"), remove_best_pips=mb.get("remove_best"),
                  status="REPLAY",
                  reason=f"L={mb.get('long_r')} S={mb.get('short_r')} "
                         f"posmon={mb.get('pos_months')} COMMON bPF={mbc.get('PF')} "
                         f"sPF={msc.get('PF')} sEV={msc.get('mean_pips')}")
            print(f"lb={lookback} fade={fade_n}: N={mb.get('N')} mean={mb.get('mean_pips')} "
                  f"PF={mb.get('PF')} expR={mb.get('expectancy_r')} L={mb.get('long_r')} "
                  f"S={mb.get('short_r')} posmon={mb.get('pos_months')} "
                  f"sCOMMON_EV={msc.get('mean_pips')} sCOMMON_PF={msc.get('PF')}")
    print("EXPERIMENTS_USED:", L.experiments_used())
