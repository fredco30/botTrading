#!/usr/bin/env python3
"""O01 PROSPECTIVE EOD PAPER PILOT — daily runner (MODE 2).

Rules: post-ACTIVATION data only; cost ceiling USD 0.50 hard; no synthetic
fills; DATA_GAP separate from strategy outcomes; 30 sessions max.
Run after the RTH close (e.g. 23:30 local / 21:30 UTC) each weekday.
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import databento

HERE = Path(__file__).parent
PROS = HERE / "prospective"
RAW = Path(r"E:\ResearchData\botTrading\nq\databento\highres\bbo_1s_o01_prospective")
STATE_F = PROS / "PILOT_STATE.json"
CEILING = 0.50
MAX_SESSIONS = 30
DATASET = "GLBX.MDP3"


def load_key():
    cfg = Path.home() / ".databento" / "config"
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            if line.strip().startswith("key"):
                return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("DATABENTO_API_KEY")


def main() -> int:
    state = json.loads(STATE_F.read_text())
    act = pd.Timestamp(state["ACTIVATION_TIMESTAMP"])
    cum = float(state["CUMULATIVE_COST_USD"])
    done = set(state["SESSIONS_DONE"])
    now = pd.Timestamp(datetime.now(timezone.utc))

    # ---- target session: latest weekday with RTH closed, post-activation,
    # not yet processed ----
    target = None
    for back in range(0, 6):
        d = (now - pd.Timedelta(days=back)).tz_convert("America/New_York")
        if d.dayofweek >= 5:
            continue
        close_ts = d.normalize() + pd.Timedelta(hours=16)
        day_str = str(d.date())
        if now.tz_convert("UTC") < close_ts + pd.Timedelta(hours=1):
            continue                      # session not closed + settled
        if d.normalize().tz_convert("UTC") <= act:
            continue                      # session started at/before activation
        if day_str in done:
            continue
        target = day_str
        break
    if target is None:
        print("NO_SESSION_DUE")
        return 0
    if len(done) >= MAX_SESSIONS:
        print("PILOT_COMPLETE (30 sessions)")
        return 0

    key = load_key()
    client = databento.Historical(key=key)
    day_open_utc = (pd.Timestamp(target, tz="America/New_York") -
                    pd.Timedelta(days=1) + pd.Timedelta(hours=9, minutes=30)
                    ).tz_convert("UTC")           # D-1 09:30 ET (context origin)
    day_end_utc = pd.Timestamp(f"{target} 16:00", tz="America/New_York").tz_convert("UTC")
    bbo_open_utc = pd.Timestamp(f"{target} 09:30", tz="America/New_York").tz_convert("UTC")

    # ---- contract for the day (free symbology) ----
    res = client.symbology.resolve(
        dataset=DATASET, symbols=["NQ.v.0"], stype_in="continuous",
        stype_out="raw_symbol", start_date=target, end_date=target)
    contract = res["result"]["NQ.v.0"][0]["s"]

    # ---- COST GUARD: estimate before pulling ----
    est_1m = float(client.metadata.get_cost(
        dataset=DATASET, symbols=["NQ.v.0"], schema="ohlcv-1m",
        start=day_open_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        end=day_end_utc.strftime("%Y-%m-%dT%H:%M:%S"), stype_in="continuous"))
    est_bbo = float(client.metadata.get_cost(
        dataset=DATASET, symbols=[contract], schema="bbo-1s",
        start=bbo_open_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        end=(day_end_utc + pd.Timedelta(5, "min")).strftime("%Y-%m-%dT%H:%M:%S"),
        stype_in="raw_symbol"))
    est = est_1m + est_bbo
    if cum + est > CEILING:
        print(f"CEILING_STOP cumulative={cum:.4f} + est={est:.4f} > {CEILING}")
        state["STOP_REASON"] = "CEILING"
        STATE_F.write_text(json.dumps(state, indent=1))
        return 3

    # ---- pull 1m (context/decisions) ----
    from databento import DBNStore
    day_1m = RAW / f"{target}_1m.dbn.zst"
    RAW.mkdir(parents=True, exist_ok=True)
    s1 = client.timeseries.get_range(
        dataset=DATASET, symbols=["NQ.v.0"], schema="ohlcv-1m",
        start=day_open_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        end=day_end_utc.strftime("%Y-%m-%dT%H:%M:%S"), stype_in="continuous")  # context window D-1 09:30 -> D 16:00
    s1.to_file(str(day_1m))
    df1 = s1.to_df().reset_index()

    # ---- pull BBO-1s (execution) on the actual contract ----
    day_bbo = RAW / f"{target}_bbo.dbn.zst"
    s2 = client.timeseries.get_range(
        dataset=DATASET, symbols=[contract], schema="bbo-1s",
        start=bbo_open_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        end=(day_end_utc + pd.Timedelta(5, "min")).strftime("%Y-%m-%dT%H:%M:%S"),
        stype_in="raw_symbol")
    s2.to_file(str(day_bbo))

    # ---- build 5m bars + per-bar quotes, feed engine MODE 2 ----
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(HERE.parents[1] / "nq_opr_modern_m1"))
    from o01_engine.engine import PaperEngine
    df1["ts"] = pd.to_datetime(df1["ts_event"] if "ts_event" in df1 else df1.index, utc=True)
    df1 = df1.set_index("ts")
    b5 = df1.resample("5min").agg(open=("open", "first"), high=("high", "max"),
                                  low=("low", "min"), close=("close", "last"),
                                  volume=("volume", "sum")).dropna()
    on_a = day_open_utc + pd.Timedelta(hours=8, minutes=30)   # D-1 18:00 ET
    on_mask = (df1.index >= on_a) & (df1.index < day_open_utc)
    on_hi = float(df1["high"][on_mask].max()) if on_mask.any() else None
    on_lo = float(df1["low"][on_mask].min()) if on_mask.any() else None
    qb = DBNStore.from_file(str(day_bbo)).to_df()
    qts = qb.index.asi8
    qbid = qb["bid_px_00"].to_numpy(float)
    qask = qb["ask_px_00"].to_numpy(float)
    lo_ns = int(day_open_utc.value)

    eng = PaperEngine(HERE / "prospective" / "engine_state",
                      contract_lookup=lambda d: contract, persist_every=0,
                      mode="PROSPECTIVE_PAPER",
                      activation_ts=json.loads(STATE_F.read_text())["ACTIVATION_TIMESTAMP"])
    for bts, row in b5.iterrows():
        a = np.searchsorted(qts, int(bts.value), side="left")
        b = np.searchsorted(qts, int(bts.value) + 5 * 60 * NS, side="left")
        bar_q = [(pd.Timestamp(qts[k], tz="UTC"), float(qbid[k]), float(qask[k]))
                 for k in range(a, b)]
        ev = {"type": "BAR", "ts": bts, "o": float(row["open"]),
              "h": float(row["high"]), "l": float(row["low"]),
              "c": float(row["close"]), "v": float(row["volume"]),
              "on_high": on_hi, "on_low": on_lo,
              "quotes_at_activation": bar_q, "bar_quotes": bar_q,
              "quotes_at_exit": []}
        # first quote after bar end as quotes_at_exit for the 15:55 bar
        if b < len(qts):
            ev["quotes_at_exit"] = [(pd.Timestamp(qts[b], tz="UTC"),
                                     float(qbid[b]), float(qask[b]))]
        eng.on_event(ev)
    day_close = float(b5["close"].iloc[-1])

    # ---- costs (actual = same-window get_cost identity) ----
    actual = est_1m + est_bbo
    cum += actual
    state["CUMULATIVE_COST_USD"] = round(cum, 4)
    state["SESSIONS_DONE"].append(target)
    trades_today = [t for t in eng.trades if str(pd.Timestamp(t["ENTRY_TS"]).date()) == target]
    tdict = trades_today[-1] if trades_today else None
    daily = {
        "DATE": target, "DATA_ACQUIRED": True, "DATA_COST_USD": round(actual, 4),
        "CUMULATIVE_COST_USD": round(cum, 4),
        "CONTRACT": contract,
        "O01_SIGNAL": "YES" if tdict else "NO",
        "SIDE": tdict["SIDE"] if tdict else None,
        "ENTRY": tdict["ENTRY"]["BASE"] if tdict else None,
        "STOP": tdict["STOP"] if tdict else None,
        "EXIT": tdict["EXIT"]["BASE"] if tdict and "EXIT" in tdict else None,
        "EXIT_REASON": tdict.get("EXIT_REASON") if tdict else None,
        "BASE_PNL": tdict.get("PNL_BASE_PTS") if tdict else None,
        "CONSERVATIVE_PNL": tdict.get("PNL_CONSERVATIVE_PTS") if tdict else None,
        "STRESS_PNL": tdict.get("PNL_STRESS_PTS") if tdict else None,
        "DATA_GAP": False, "ENGINE_ERROR": None,
        "PAPER_DAYS": len(state["SESSIONS_DONE"]),
        "PAPER_SIGNALS": int(len(eng.trades)),
        "PAPER_TRADES": int(len([t for t in eng.trades if "EXIT" in t])),
    }
    state.setdefault("DAILY", []).append(daily)
    STATE_F.write_text(json.dumps(state, indent=1, default=str))
    (PROS / f"DAILY_{target}.json").write_text(json.dumps(daily, indent=1, default=str))
    eng._persist()
    print(json.dumps(daily, indent=1, default=str))
    print(f"SESSION {target} PROCESSED cumulative=${cum:.4f}")
    if len(state["SESSIONS_DONE"]) >= MAX_SESSIONS:
        print("PILOT_COMPLETE (30 sessions)")
    return 0


NS = 10 ** 9

if __name__ == "__main__":
    sys.exit(main())
