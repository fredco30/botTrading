"""RATES-LAG-M0 discovery runner: three frozen causal horizons on NFP/CPI events.

Reads only E: data (TBBO parquet + EURUSD ticks) — nothing bulk enters git.
Writes results JSON + trades JSON + report MD into this mission directory.

Usage: python run_discovery.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
import rates_lag_lib as L  # noqa: E402

MISSION_DIR = Path(__file__).resolve().parent
MANIFEST = Path(r"E:\ResearchData\botTrading\rates\databento_event_tbbo\manifests\manifest.json")
TICK_SIZES = MISSION_DIR / "instrument_tick_sizes.json"
FX_ROOT = Path(r"E:\ResearchData\botTrading\ticks\parquet\EURUSD")
WINDOW_BEFORE_NS = 5 * 60 * 1_000_000_000  # M1 window start = T0 - 5 min

# FX context per event: [T0 - 1s, T0 + 420s] covers decision(<=60s) + delay(<=5s)
# + fill bound(10s) + exit(120s) + exit bound(60s) + mark 300s, with margin.
FX_PRE_NS = 1_000_000_000
FX_POST_NS = 420_000_000_000


class FxMonthCache:
    """Month-partition EURUSD parquet loader with an LRU of 2 months."""

    def __init__(self, root: Path):
        self.root = root
        self._cache: dict[tuple[int, int], L.FxBook] = {}
        self._order: list[tuple[int, int]] = []

    def book(self, year: int, month: int) -> L.FxBook:
        key = (year, month)
        if key in self._cache:
            return self._cache[key]
        p = self.root / f"year={year}" / f"month={month:02d}" / "ticks.parquet"
        if not p.exists():
            raise FileNotFoundError(f"EURUSD month parquet missing: {p}")
        t = pq.read_table(p, columns=["timestamp_utc", "bid", "ask"])
        d = t.to_pandas()
        ts = d["timestamp_utc"].to_numpy().astype("datetime64[ns]").astype(np.int64)
        book = L.FxBook.from_records(ts, d["bid"].to_numpy(), d["ask"].to_numpy())
        self._cache[key] = book
        self._order.append(key)
        if len(self._order) > 2:
            old = self._order.pop(0)
            self._cache.pop(old, None)
        return book


def fx_window_book(cache: FxMonthCache, t0_ns: int) -> L.FxBook:
    """EURUSD book restricted to [T0-1s, T0+420s] (Discovery-safe slice)."""
    start = t0_ns - FX_PRE_NS
    end = t0_ns + FX_POST_NS
    L.assert_discovery_range(start, end)
    import datetime as _dt
    day = _dt.datetime.fromtimestamp(t0_ns / 1e9, _dt.timezone.utc)
    book = cache.book(day.year, day.month)
    i0 = int(np.searchsorted(book.ts, start, side="left"))
    i1 = int(np.searchsorted(book.ts, end, side="right"))
    return L.FxBook(ts=book.ts[i0:i1], bid=book.bid[i0:i1], ask=book.ask[i0:i1])


def rate_book_for_event(parquet_path: str, t0_ns: int) -> L.RateBook:
    L.assert_discovery_range(t0_ns - WINDOW_BEFORE_NS, t0_ns + FX_POST_NS)
    t = pq.read_table(parquet_path, columns=["ts_recv", "bid_px_00", "ask_px_00"])
    d = t.to_pandas()
    ts = d["ts_recv"].to_numpy().astype("datetime64[ns]").astype(np.int64)
    return L.RateBook.from_records(ts, d["bid_px_00"].to_numpy(),
                                   d["ask_px_00"].to_numpy(),
                                   window_start_ns=t0_ns - WINDOW_BEFORE_NS)


def make_trade(ev: L.LagEvent, direction: int, horizon_s: float,
               fx: L.FxBook) -> dict:
    """One trade record: baseline (1s) path + slow (5s) + stress + MTM marks."""
    dec_ns = ev.t0_ns + int(round(horizon_s * 1e9))
    entry = fx.entry(dec_ns, L.DELAY_BASELINE_S, direction)
    out = {
        "event_id": ev.event_id, "family": ev.family, "horizon_s": horizon_s,
        "direction": direction, "decision_ts_ns": dec_ns,
        "status": "NO_FILL", "net_pips": float("nan"),
    }
    if entry is None:
        return out
    e_ts, e_px = entry
    x = fx.exit(e_ts, direction)
    if x is None:
        out["status"] = "EXIT_UNAVAILABLE"
        return out
    x_ts, x_px = x
    base_net = L.net_pips(e_px, x_px, direction)
    l5 = fx.entry(dec_ns, L.DELAY_SLOW_S, direction)
    if l5 is None:
        out.update(status="ok", entry_ts_ns=e_ts, entry_px=e_px, exit_ts_ns=x_ts,
                   exit_px=x_px, net_pips=base_net,
                   latency5_net=float("nan"), stress050_net=L.stressed(base_net, L.SLIP_050),
                   stress100_net=L.stressed(base_net, L.SLIP_100),
                   realistic_net=float("nan"))
    else:
        l5_ts, l5_px = l5
        l5_exit = fx.exit(l5_ts, direction)
        l5_net = L.net_pips(l5_px, l5_exit[1], direction) if l5_exit else float("nan")
        out.update(status="ok", entry_ts_ns=e_ts, entry_px=e_px, exit_ts_ns=x_ts,
                   exit_px=x_px, net_pips=base_net, latency5_net=l5_net,
                   stress050_net=L.stressed(base_net, L.SLIP_050),
                   stress100_net=L.stressed(base_net, L.SLIP_100),
                   realistic_net=(l5_net - 2 * L.SLIP_050)
                   if l5_exit else float("nan"))
    for tag, secs in (("mtm30", 30.0), ("mtm60", 60.0), ("mtm300", 300.0)):
        m = fx.mark(e_ts, direction, secs)
        out[tag] = (L.net_pips(e_px, m[1], direction) if m else float("nan"))
    return out


def run() -> dict:
    events = L.load_valid_events(str(MANIFEST))
    ticks = L.load_tick_sizes(str(TICK_SIZES))
    print(f"EVENTS_AVAILABLE={len(events)}")
    fx_cache = FxMonthCache(FX_ROOT)

    trades_by_h: dict[float, list[dict]] = {h: [] for h in L.HORIZONS_S}
    no_fill_by_h: dict[float, int] = {h: 0 for h in L.HORIZONS_S}
    exit_unavail_by_h: dict[float, int] = {h: 0 for h in L.HORIZONS_S}
    signals: dict[str, dict[str, int]] = {f"H{h}": {} for h in L.HORIZONS_S}
    all_trades: list[dict] = []
    tick_crosscheck = {"ZF": [], "ZN": []}

    for k, ev in enumerate(events, 1):
        zf = rate_book_for_event(ev.zf_parquet, ev.t0_ns)
        zn = rate_book_for_event(ev.zn_parquet, ev.t0_ns)
        zf_tick, zn_tick = ticks[ev.zf_raw], ticks[ev.zn_raw]
        # diagnostic: data-derived min increment vs definition
        for name, book in (("ZF", zf), ("ZN", zn)):
            if len(book.mid) > 1:
                tick_crosscheck[name].append(L.data_derived_tick(book.mid))
        fx = None
        zf_pre = zf.pre_mid(ev.t0_ns)
        zn_pre = zn.pre_mid(ev.t0_ns)
        for h in L.HORIZONS_S:
            zf_h = zf.horizon_mid(ev.t0_ns, h)
            zn_h = zn.horizon_mid(ev.t0_ns, h)
            sig = L.rate_signal(zf_pre, zf_h, zn_pre, zn_h, zf_tick, zn_tick)
            if sig == 0:
                continue
            signals[f"H{h}"][ev.event_id] = sig
            if fx is None:  # lazy: only load FX when a signal exists
                try:
                    fx = fx_window_book(fx_cache, ev.t0_ns)
                except (FileNotFoundError, L.OutOfWindowError) as exc:
                    print(f"  {ev.event_id}: FX unavailable ({exc})")
                    continue
            tr = make_trade(ev, sig, float(h), fx)
            if tr["status"] == "NO_FILL":
                no_fill_by_h[h] += 1
            elif tr["status"] == "EXIT_UNAVAILABLE":
                exit_unavail_by_h[h] += 1
            else:
                trades_by_h[h].append(tr)
                all_trades.append(tr)
        if k % 25 == 0:
            print(f"  {k}/{len(events)} events processed")

    results: dict = {
        "mission": "RATES-LAG-M0",
        "spec": "RATES_LAG_M0_FROZEN_SPEC.md",
        "events_available": len(events),
        "nfp_n_events": sum(1 for e in events if e.family == "NFP"),
        "cpi_n_events": sum(1 for e in events if e.family == "CPI"),
        "horizons": {},
    }
    for h in L.HORIZONS_S:
        trs = trades_by_h[h]
        m = L.metrics(trs)
        m["RATE_SIGNALS"] = len(signals[f"H{h}"])
        m["NO_FILL"] = no_fill_by_h[h]
        m["EXIT_UNAVAILABLE"] = exit_unavail_by_h[h]
        m["ECONOMIC_CANDIDATE"] = L.gate(m)
        m["POSITIVE_YEAR_RATIO"] = (m["POSITIVE_YEARS"] / m["YEARS_ELIGIBLE"]
                                    if m["YEARS_ELIGIBLE"] else float("nan"))
        results["horizons"][f"H{h}"] = m
    results["stability"] = L.stability_counts(signals)
    results["tick_crosscheck"] = {
        k: {"definition": (0.0078125 if k == "ZF" else 0.015625),
            "data_derived_min_median": float(np.nanmedian(v)) if v else float("nan")}
        for k, v in tick_crosscheck.items()}

    (MISSION_DIR / "rates_lag_m0_results.json").write_text(json.dumps(results, indent=1))
    (MISSION_DIR / "rates_lag_m0_trades.json").write_text(json.dumps(all_trades, indent=1))

    for h in L.HORIZONS_S:
        m = results["horizons"][f"H{h}"]
        print(f"\nH{h}: SIGNALS={m['RATE_SIGNALS']} N={m['N_TRADES']} "
              f"MEAN={m['NET_MEAN_PIPS']:.3f} PF={m['PROFIT_FACTOR']:.3f} "
              f"L5={m['LATENCY_5S_MEAN']:.3f} STRESS={m['REALISTIC_STRESS_MEAN']:.3f} "
              f"NFP={m['NFP_MEAN']:.3f} CPI={m['CPI_MEAN']:.3f} "
              f"CANDIDATE={m['ECONOMIC_CANDIDATE']}")
    st = results["stability"]
    print(f"\nStability: H10->H30 {st['H10_TO_H30_SAME_DIRECTION_PCT']:.1f}% | "
          f"H30->H60 {st['H30_TO_H60_SAME_DIRECTION_PCT']:.1f}% | "
          f"H10->H60 {st['H10_TO_H60_SAME_DIRECTION_PCT']:.1f}%")
    return results


if __name__ == "__main__":
    run()
