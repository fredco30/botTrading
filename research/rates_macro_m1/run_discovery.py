#!/usr/bin/env python3
"""RATES-MACRO-M1 discovery runner.

Full Discovery window 2010-06-07 -> 2019-01-01 (2019+ never touched).
Event-window tick access only; the 208M-tick store is never loaded whole
(spec §27). Produces small JSON artifacts only (spec §28: no bulk data).
"""
import json
import os

import numpy as np
import pandas as pd

import rates_macro_lib as R

HERE = os.path.dirname(os.path.abspath(__file__))
GAP_CACHE = os.path.join(HERE, "data", "eurusd_gaps_2010_2018.json")


def build_fx_gaps():
    """Validated EURUSD gap list (non-weekend > 1 h) over the tick store;
    cached to a small JSON next to the macro artifact."""
    if os.path.exists(GAP_CACHE):
        return [(int(a), int(b)) for a, b in
                (g for g in json.load(open(GAP_CACHE)))]
    gaps = MTF_detect_gaps()
    json.dump([[int(a), int(b)] for a, b in gaps], open(GAP_CACHE, "w"))
    return gaps


def MTF_detect_gaps():
    import mtf_lib as MTF
    return MTF.detect_gaps(MTF.iter_month_tick_ts(R.TICKS_DIR, "EURUSD"))


def main():
    import mtf_lib as MTF
    events = R.load_events()
    print(f"events: {len(events)} "
          f"({sum(1 for e in events if e['family'] == 'NFP')} NFP / "
          f"{sum(1 for e in events if e['family'] == 'CPI')} CPI)")
    store = MTF.TickStore(R.TICKS_DIR, "EURUSD", max_months=4)
    fx_gaps = build_fx_gaps()
    fx_gap_starts = MTF.gap_starts_array(fx_gaps)
    print(f"fx data gaps: {len(fx_gaps)}")
    rates = R.RateStore()

    trades = []
    rows = []
    n_avail = 0
    n_shock = 0
    zf_scores, zn_scores = [], []
    zt_avail_n = zt_confirm_n = 0
    for i, ev in enumerate(events):
        t0 = ev["t0_ns"]
        zw = {"ZF": rates.window("ZF", t0), "ZN": rates.window("ZN", t0)}
        zt = rates.window("ZT", t0)
        ts, bid, ask = store.get_range(t0 - 62 * R.MIN_NS,
                                       t0 + 2 * R.MIN_NS + R.NS)
        mid = (bid + ask) / 2.0
        refs, base = R.fx_event_refs(ts, mid, t0)
        valid = (zw["ZF"]["status"] == "OK" and zw["ZN"]["status"] == "OK"
                 and refs is not None and base["fx_q95"] is not None)
        row = {"event_id": ev["event_id"], "family": ev["family"],
               "t0": pd.Timestamp(t0, tz="UTC").isoformat(),
               "zf_status": zw["ZF"]["status"],
               "zn_status": zw["ZN"]["status"],
               "zt_status": zt["status"],
               "event_valid": bool(valid)}
        if zw["ZF"]["status"] == "OK":
            row["zf_move"] = zw["ZF"]["rate_move"]
            row["zf_score"] = zw["ZF"]["rate_score"]
        if zw["ZN"]["status"] == "OK":
            row["zn_move"] = zw["ZN"]["rate_move"]
            row["zn_score"] = zw["ZN"]["rate_score"]
        if zt["status"] == "OK":
            row["zt_move"] = zt["rate_move"]
            row["zt_score"] = zt["rate_score"]
        if refs is not None:
            row["fx_p0"] = refs["fx_p0"]
            row["fx_p1"] = refs["fx_p1"]
            row["fx_move_1m_pips"] = refs["fx_move_1m_pips"]
            row["fx_q95_pips"] = (base["fx_q95"] / R.PIP
                                  if base["fx_q95"] is not None else None)
        shock = R.primary_rate_shock(zw["ZF"], zw["ZN"])
        row["primary_rate_shock"] = bool(shock)
        if valid:
            n_avail += 1
        if not shock:
            rows.append(row)
            continue
        n_shock += 1
        zf_scores.append(zw["ZF"]["rate_score"])
        zn_scores.append(zw["ZN"]["rate_score"])
        direction = R.rate_direction(zw["ZF"])
        # ZT diagnostic (spec §9): never gates eligibility or direction
        zt_ok = zt["status"] == "OK"
        if zt_ok:
            zt_avail_n += 1
            if int(np.sign(zt["rate_move"])) == direction:
                zt_confirm_n += 1
        row["zt_confirms"] = bool(
            zt_ok and int(np.sign(zt["rate_move"])) == direction)
        ev_trades, notes = R.run_event(ev, zw, refs, base, store,
                                       fx_gap_starts)
        row["notes"] = {k: v for k, v in notes.items()}
        for t in ev_trades:
            row[f"trade_{t['kind']}"] = {
                "side": t["direction"], "entry_ts": pd.Timestamp(
                    t["entry_ts"], tz="UTC").isoformat(),
                "entry": t["entry"], "stop": t["stop"],
                "target": t["target"], "exit_ts": pd.Timestamp(
                    t["exit_ts"], tz="UTC").isoformat(),
                "exit_reason": t["exit_reason"],
                "exit_price": t["exit_price"], "net_pips": t["net_pips"]}
        trades.extend(ev_trades)
        rows.append(row)
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(events)} events, {len(trades)} trades")

    results = {"spec": "RATES_MACRO_M1_FROZEN_SPEC",
               "base_head": "7c63937670e30a5cfb41362455700b233917d43b",
               "macro_source_sha":
               "f89623096e36a12a98f3aaa23f1217dc245bfa9745cc46d4a6c1b6b4e3a"
               "2e418",
               "discovery": {"start": "2010-06-07", "end_exclusive":
                             "2019-01-01"},
               "events_nfp": sum(1 for e in events
                                 if e["family"] == "NFP"),
               "events_cpi": sum(1 for e in events
                                 if e["family"] == "CPI"),
               "events_total": len(events),
               "events_rate_valid": n_avail,
               "qualifying_rate_shocks": n_shock,
               "zt_available_pct": round(zt_avail_n / n_shock, 4)
               if n_shock else None,
               "zt_confirm_pct": round(zt_confirm_n / n_shock, 4)
               if n_shock else None,
               "strategies": {}}
    for kind in ("A", "B", "C"):
        kt = [t for t in trades if t["kind"] == kind]
        m = R.strategy_metrics(kt, zf_scores, zn_scores,
                               results["zt_available_pct"],
                               results["zt_confirm_pct"])
        m["strategy_id"] = R.STRATEGY_IDS[kind]
        results["strategies"][kind] = m

    with open(os.path.join(HERE, "rates_macro_m1_results.json"), "w") as f:
        json.dump(results, f, indent=1)
    with open(os.path.join(HERE, "rates_macro_m1_trades.json"), "w") as f:
        json.dump(trades, f, indent=1)
    with open(os.path.join(HERE, "rates_macro_m1_events.json"), "w") as f:
        json.dump(rows, f, indent=1)

    print(f"\nevents={len(events)} rate_valid={n_avail} "
          f"shocks={n_shock} zt_avail={results['zt_available_pct']} "
          f"zt_confirm={results['zt_confirm_pct']}")
    for kind in ("A", "B", "C"):
        m = results["strategies"][kind]
        print(f"{kind}: N={m['n_trades']} net_mean={m.get('net_mean_pips')} "
              f"PF={m.get('profit_factor')} expR={m.get('expectancy_r')} "
              f"posY={m.get('positive_years')}/{m.get('years_eligible')} "
              f"remove_best={m.get('remove_best_1pct_mean')} "
              f"stress050={m.get('stress_050_mean')} "
              f"NFP={m.get('nfp_mean')} CPI={m.get('cpi_mean')} "
              f"CI=[{m.get('ci95_lo')},{m.get('ci95_hi')}] "
              f"=> {m['verdict']}")


if __name__ == "__main__":
    main()
