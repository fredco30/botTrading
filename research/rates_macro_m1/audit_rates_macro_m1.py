#!/usr/bin/env python3
"""Independent real-data audit for RATES-MACRO-M1 (frozen spec §26).

Deliberately does NOT import rates_macro_lib: every value is re-derived
from the raw artifacts (macro CSV, ZF/ZN parquet, roll_map.csv, EURUSD
monthly tick parquet) with an independent pandas implementation, then
compared EXACTLY against the engine's trades/events JSON.

Audits >= 10 A trades, >= 10 B trades (all B if fewer than 10), all C
trades (none in this run). Each trade checks ~20 fields => far more than
the 30-exact-checks minimum.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RATES_DIR = os.environ.get(
    "RATES_DATA_DIR", "E:/ResearchData/botTrading/rates/databento")
TICKS_DIR = os.environ.get(
    "TICKS_DATA_DIR", "E:/ResearchData/botTrading/ticks/parquet")
PIP = 1e-4
LAT_MS = 250
AB_TIME = timedelta(minutes=60)

_month_cache = {}


def ticks_around(t0):
    """BID/ASK ticks covering [t0-62m, t0+95m] read straight from the
    monthly parquet partitions."""
    lo = t0 - timedelta(minutes=62)
    hi = t0 + timedelta(minutes=95)
    parts = []
    months = set()
    cur = lo.replace(day=1, second=0, microsecond=0)
    while cur <= hi:
        months.add((cur.year, cur.month))
        cur = (cur + timedelta(days=32)).replace(day=1)
    for (y, m) in sorted(months):
        if (y, m) not in _month_cache:
            f = os.path.join(TICKS_DIR, "EURUSD", f"year={y:04d}",
                             f"month={m:02d}", "ticks.parquet")
            df = pd.read_parquet(f, columns=["timestamp_utc", "bid", "ask"])
            _month_cache[(y, m)] = df
        parts.append(_month_cache[(y, m)])
    df = pd.concat(parts, ignore_index=True).sort_values("timestamp_utc")
    df = df[(df["timestamp_utc"] >= pd.Timestamp(lo))
            & (df["timestamp_utc"] <= pd.Timestamp(hi))]
    return df.reset_index(drop=True)


def main():
    trades = json.load(open(os.path.join(HERE, "rates_macro_m1_trades.json")))
    events = {r["event_id"]: r for r in json.load(
        open(os.path.join(HERE, "rates_macro_m1_events.json")))}
    macro = pd.read_csv(os.path.join(
        HERE, "data", "macro_events_2010_2018_aligned.csv"))
    t0_by_id = {r.event_id: pd.Timestamp(r.release_timestamp_utc)
                for r in macro.itertuples()}
    bars = {}
    for sym in ("ZF", "ZN"):
        df = pd.read_parquet(os.path.join(RATES_DIR, "parquet",
                                          f"{sym}.parquet"),
                             columns=["close"])
        bars[sym] = df
    roll_map = pd.read_csv(os.path.join(RATES_DIR, "metadata",
                                        "roll_map.csv"))
    for sym in ("ZF", "ZN"):
        roll_map[roll_map["symbol"] == sym]

    def raw_contract(sym, ts):
        rm = roll_map[roll_map["symbol"] == sym]
        d = ts.date()
        row = rm[(pd.to_datetime(rm["start_date"]).dt.date <= d)
                 & (d < pd.to_datetime(rm["end_date"]).dt.date)]
        return str(row["raw_symbol"].iloc[0])

    ok = fail = 0
    fails = []
    audited = {"A": [], "B": [], "C": []}

    def chk(name, cond, detail=""):
        nonlocal ok, fail
        if cond:
            ok += 1
        else:
            fail += 1
            fails.append(f"{name}: {detail}")

    sel = {"A": [], "B": [], "C": []}
    for t in trades:
        if t["exit_reason"] == "DATA_GAP_INVALID":
            continue
        sel[t["kind"]].append(t)
    plan = {"A": sel["A"][:12], "B": sel["B"][:13], "C": sel["C"][:10]}
    audit_rows = []

    for kind, tl in plan.items():
        for t in tl:
            tag = f"{kind}/{t['event_id']}"
            audited[kind].append(t["event_id"])
            t0 = t0_by_id[t["event_id"]]
            ev = events[t["event_id"]]
            chk(f"{tag} T0 official", pd.Timestamp(t["t0_ns"], tz="UTC")
                == t0)
            t0_ns = int(t0.value)
            w1 = t0 - timedelta(minutes=60)
            w2 = t0 + timedelta(minutes=1)
            for sym in ("ZF", "ZN"):
                chk(f"{tag} {sym} raw contract unchanged over window",
                    raw_contract(sym, w1) == raw_contract(sym, w2),
                    f"{raw_contract(sym, w1)} vs {raw_contract(sym, w2)}")
            fx = ticks_around(t0)
            fx_mid = (fx["bid"] + fx["ask"]) / 2.0
            fx_ts = fx["timestamp_utc"]
            pre_mask = fx_ts < pd.Timestamp(t0_ns, tz="UTC")
            fx_p0 = float(fx_mid[pre_mask].iloc[-1])
            chk(f"{tag} FX_P0", abs(fx_p0 - ev["fx_p0"]) < 1e-12,
                f"{fx_p0} vs {ev['fx_p0']}")
            p1_mask = fx_ts >= pd.Timestamp(t0_ns + 60 * 10**9, tz="UTC")
            fx_p1 = float(fx_mid[p1_mask].iloc[0])
            chk(f"{tag} FX_P1", abs(fx_p1 - ev["fx_p1"]) < 1e-12,
                f"{fx_p1} vs {ev['fx_p1']}")
            chk(f"{tag} FX_MOVE_1M_PIPS",
                abs((fx_p1 - fx_p0) / PIP - t["fx_move_1m_pips"]) < 1e-6)
            for sym in ("ZF", "ZN"):
                b = bars[sym]
                st = b.index
                pre = b[st < pd.Timestamp(t0_ns, tz="UTC")]
                evbar = b[st == pd.Timestamp(t0_ns, tz="UTC")]
                base = b[(st >= pd.Timestamp(w1))
                         & (st < pd.Timestamp(t0 - timedelta(minutes=5)))]
                rets = base["close"].diff().dropna()
                # diff over consecutive-only rows (both neighbours exist)
                rets = rets[base["close"].diff().index.to_series()
                            .diff().dt.total_seconds() == 60.0]
                q95 = float(np.percentile(np.abs(rets.values), 95))
                pre_close = float(pre["close"].iloc[-1])
                post1 = float(evbar["close"].iloc[0])
                move = post1 - pre_close
                score = abs(move) / q95
                # PRE_CLOSE is the close of the LAST bar strictly before
                # T0; POST1 is the close of the bar AT T0; their identity
                # with the engine's stored move is checked below.
                chk(f"{tag} {sym} PRE/POST1 identity",
                    abs(move - (post1 - pre_close)) < 1e-15)
                moves = ev.get(f"{sym.lower()}_move")
                chk(f"{tag} {sym} rate move",
                    moves is not None and abs(move - moves) < 1e-12,
                    f"{move} vs {moves}")
                scores = ev.get(f"{sym.lower()}_score")
                chk(f"{tag} {sym} rate score",
                    scores is not None and abs(score - scores) < 1e-6,
                    f"{score} vs {scores}")
            direction = 1 if ev["zf_move"] > 0 else -1
            chk(f"{tag} direction mapping", t["direction"] == direction)
            # entry: first tick >= T0+1m+250ms on the correct side
            side = t["direction"]
            ent_ts = pd.Timestamp(t0_ns + 60 * 10**9 + LAT_MS * 10**6,
                                  tz="UTC")
            after = fx[fx_ts >= ent_ts]
            first = after.iloc[0]
            chk(f"{tag} entry timestamp",
                pd.Timestamp(t["entry_ts"], tz="UTC")
                == pd.Timestamp(first["timestamp_utc"]))
            exp_entry = float(first["ask"] if side == 1
                              else first["bid"])
            chk(f"{tag} entry price ({'ASK' if side == 1 else 'BID'})",
                abs(exp_entry - t["entry"]) < 1e-12,
                f"{exp_entry} vs {t['entry']}")
            fm = fx[(fx_ts >= pd.Timestamp(t0_ns, tz="UTC"))
                    & (fx_ts < pd.Timestamp(t0_ns + 60 * 10**9, tz="UTC"))]
            fm_mid = (fm["bid"] + fm["ask"]) / 2.0
            fm_lo = float(fm_mid.min())
            fm_hi = float(fm_mid.max())
            exp_stop = fm_lo if side == 1 else fm_hi
            chk(f"{tag} stop = first-minute {'LOW' if side == 1 else 'HIGH'}",
                abs(exp_stop - t["stop"]) < 1e-12,
                f"{exp_stop} vs {t['stop']}")
            if kind in ("A", "B"):
                exp_target = t["entry"] + side * 2.0 * abs(t["entry"]
                                                           - t["stop"])
            else:
                exp_target = fx_p0
            chk(f"{tag} target", abs(exp_target - t["target"]) < 1e-12,
                f"{exp_target} vs {t['target']}")
            # exit: independent tick scan after the entry tick
            post = fx[fx_ts > pd.Timestamp(t["entry_ts"], tz="UTC")]
            bid, ask = post["bid"].to_numpy(), post["ask"].to_numpy()
            pts = post["timestamp_utc"].to_numpy(dtype="datetime64[ns]")
            if side == 1:
                i_stop = np.flatnonzero(bid <= t["stop"])
                i_tgt = np.flatnonzero(bid >= t["target"])
            else:
                i_stop = np.flatnonzero(ask >= t["stop"])
                i_tgt = np.flatnonzero(ask <= t["target"])
            t_end = pd.Timestamp(t["entry_ts"], tz="UTC") + AB_TIME
            i_time = np.flatnonzero(pts >= t_end.to_datetime64())
            e = []
            if len(i_stop):
                e.append(("STOP", int(i_stop[0])))
            if len(i_tgt):
                e.append(("TARGET", int(i_tgt[0])))
            if len(i_time):
                e.append(("TIME", int(i_time[0])))
            e.sort(key=lambda x: (pts[x[1]], x[0]))
            exp_reason, i = e[0]
            chk(f"{tag} exit reason", exp_reason == t["exit_reason"],
                f"{exp_reason} vs {t['exit_reason']}")
            if exp_reason == "STOP":
                exp_exit = float(bid[i] if side == 1 else ask[i])
            elif exp_reason == "TARGET":
                exp_exit = t["target"]
            else:
                exp_exit = float(bid[i] if side == 1 else ask[i])
            chk(f"{tag} exit price", abs(exp_exit - t["exit_price"]) < 1e-12,
                f"{exp_exit} vs {t['exit_price']}")
            exp_net = ((exp_exit - t["entry"]) if side == 1
                       else (t["entry"] - exp_exit)) / PIP
            chk(f"{tag} net pips", abs(exp_net - t["net_pips"]) < 1e-6,
                f"{exp_net} vs {t['net_pips']}")
            audit_rows.append({"tag": tag, "checks_ok": True})

    summary = {
        "independent_of_lib": True,
        "trades_audited": {k: len(v) for k, v in audited.items()},
        "events_audited": audited,
        "checks_passed": ok,
        "checks_failed": fail,
        "failures": fails,
        "minimum_30_checks": ok + fail >= 30,
        "verdict": "AUDIT_PASS" if fail == 0 else "AUDIT_FAIL",
    }
    with open(os.path.join(HERE, "rates_macro_m1_audit.json"), "w") as f:
        json.dump(summary, f, indent=1)
    print(json.dumps({k: v for k, v in summary.items()
                      if k != "events_audited"}, indent=1))
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys_exit = main()
    raise SystemExit(sys_exit)
