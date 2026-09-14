"""PO3-BASE-M0 discovery runner: 2010-01-04 .. 2018-12-31 (Europe/London dates).

Loads the frozen EURUSD tick store partition-by-partition (SHA256-verified against
data_manifest.json), processes each London trading day through the frozen engine,
and writes results + trades + report. 2019+ and protected OOS are hard-guarded.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

import po3_base_m0_lib as L

HERE = Path(__file__).parent
STORE = Path(r"E:\ResearchData\botTrading\ticks\parquet\EURUSD")
MANIFEST = HERE / "data_manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class MonthStore:
    """LRU cache of verified month partitions -> (ts, bid, ask)."""

    def __init__(self, manifest: dict, verify_hash: bool = True):
        self.entries = manifest["entries"]
        self.verify_hash = verify_hash
        self.verified: set[str] = set()
        self.cache: dict[tuple[int, int], tuple[np.ndarray, ...]] = {}
        self.mid_checked = False

    def load(self, year: int, month: int) -> tuple[np.ndarray, ...]:
        key = (year, month)
        if key in self.cache:
            return self.cache[key]
        rel = f"{STORE}\\year={year}\\month={month:02d}\\ticks.parquet"
        L.guard_partition_path(rel)
        entry = self.entries[f"{year}-{month:02d}"]
        if entry["path"] != rel:
            raise RuntimeError(f"manifest path mismatch: {entry['path']} vs {rel}")
        if self.verify_hash and rel not in self.verified:
            got = sha256_file(Path(rel))
            if got != entry["sha256"]:
                raise RuntimeError(f"SHA256 mismatch for {rel}: store changed "
                                   f"since the frozen manifest")
            self.verified.add(rel)
        tbl = pq.read_table(rel, columns=["timestamp_utc", "bid", "ask"]
                            + ([] if self.mid_checked else ["mid"]))
        ts = tbl.column("timestamp_utc").to_numpy().astype("datetime64[ns]").astype("int64")
        bid = tbl.column("bid").to_numpy().astype(np.float64)
        ask = tbl.column("ask").to_numpy().astype(np.float64)
        bad = (~np.isfinite(bid)) | (~np.isfinite(ask)) | (bid <= 0) | (ask <= 0)
        if bad.any():
            keep = ~bad
            ts, bid, ask = ts[keep], bid[keep], ask[keep]
        if not self.mid_checked:
            stored_mid = tbl.column("mid").to_numpy().astype(np.float64)
            stored_mid = stored_mid[~bad]
            if not np.allclose(stored_mid, (bid + ask) / 2, rtol=0, atol=1e-12):
                raise RuntimeError("stored mid != (bid+ask)/2 on first partition")
            self.mid_checked = True
        order = np.argsort(ts, kind="stable")
        out = (ts[order], bid[order], ask[order])
        if len(self.cache) >= 3:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = out
        return out

    def slice_day(self, start_ns: int, end_ns: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        d_start = np.datetime64(start_ns, "ns").astype("datetime64[M]")
        d_end = np.datetime64(end_ns, "ns").astype("datetime64[M]")
        parts = []
        for ym in np.arange(d_start, d_end + np.timedelta64(1, "M"), dtype="datetime64[M]"):
            yy, mm = int(str(ym)[:4]), int(str(ym)[5:7])
            ts, bid, ask = self.load(yy, mm)
            i0 = int(np.searchsorted(ts, start_ns, side="left"))
            i1 = int(np.searchsorted(ts, end_ns, side="right"))
            if i1 > i0:
                parts.append((ts[i0:i1], bid[i0:i1], ask[i0:i1]))
        if not parts:
            e = np.empty(0, dtype=np.int64)
            return e, np.empty(0), np.empty(0)
        if len(parts) == 1:
            return parts[0]
        return (np.concatenate([p[0] for p in parts]),
                np.concatenate([p[1] for p in parts]),
                np.concatenate([p[2] for p in parts]))


def classify_day(store: MonthStore, d) -> dict:
    b = L.day_bounds(d)
    L.assert_utc_range(b.asia_start, b.slice_end + 1)
    ts, bid, ask = store.slice_day(b.asia_start, b.slice_end + 1)
    mid = (bid + ask) / 2
    rng = L.asian_range(ts, mid, b)
    rec: dict = {"date": d.isoformat(), "eligible": rng.eligible,
                 "asian_high": rng.high, "asian_low": rng.low,
                 "asian_range_pips": rng.range_ / L.PIP if rng.eligible else float("nan")}
    if not rng.eligible:
        rec["status"] = "NOT_ELIGIBLE"
        return rec
    setup = L.detect_setup(ts, mid, b, rng)
    rec["status"] = setup.status
    rec["sweep_side"] = setup.side
    rec["sweep_ts"] = setup.sweep_ts
    rec["sweep_extreme"] = setup.sweep_extreme
    rec["decision_ts"] = setup.decision_ts
    rec["sweep_latency_min"] = setup.sweep_latency_min
    if setup.status != L.TRADE:
        return rec
    ex = L.execute(ts, bid, ask, -setup.side, setup.sweep_extreme,
                   setup.decision_ts, L.ENTRY_DELAY_BASE_NS, b.time_exit)
    rec["status"] = ex.status
    if ex.status != L.TRADE:
        return rec

    # LATENCY_30S scenario: same signal/stop, re-executed later (spec 12).
    ex30 = L.execute(ts, bid, ask, -setup.side, setup.sweep_extreme,
                     setup.decision_ts, L.ENTRY_DELAY_STRESS_NS, b.time_exit)

    direction = -setup.side
    trade = {
        "date": d.isoformat(),
        "direction": "LONG" if direction > 0 else "SHORT",
        "sweep": "UPPER" if setup.side > 0 else "LOWER",
        "asian_high": rng.high, "asian_low": rng.low,
        "asian_range_pips": rng.range_ / L.PIP,
        "sweep_ts": setup.sweep_ts,
        "sweep_extreme": setup.sweep_extreme,
        "decision_ts": setup.decision_ts,
        "sweep_latency_min": setup.sweep_latency_min,
        "sweep_ext_over_range": (abs(setup.sweep_extreme -
                                     (rng.high if setup.side > 0 else rng.low))
                                 / rng.range_),
        "entry_ts": ex.entry_ts, "entry_px": ex.entry_px,
        "stop": ex.stop, "r_pips": ex.r / L.PIP, "target": ex.target,
        "exit_type": ex.exit_type, "exit_ts": ex.exit_ts, "exit_px": ex.exit_px,
        "net_pips": ex.net_pips, "r_mult": ex.net_pips / (ex.r / L.PIP),
        "stop_gap_pips": ex.stop_gap_pips,
        "mfe30_r": L.mfe_r(ts, bid, ask, ex, direction, 30.0),
        "mfe60_r": L.mfe_r(ts, bid, ask, ex, direction, 60.0),
        "mfe120_r": L.mfe_r(ts, bid, ask, ex, direction, 120.0),
        "kr1": L.reaches_kr_before_stop(ts, bid, ask, ex, direction, 1.0),
        "kr15": L.reaches_kr_before_stop(ts, bid, ask, ex, direction, 1.5),
        "kr2": L.reaches_kr_before_stop(ts, bid, ask, ex, direction, 2.0),
        "lat_status": ex30.status,
    }
    if ex30.status == L.TRADE:
        trade.update(lat_entry_ts=ex30.entry_ts, lat_entry_px=ex30.entry_px,
                     lat_r_pips=ex30.r / L.PIP, lat_net_pips=ex30.net_pips,
                     lat_r_mult=ex30.net_pips / (ex30.r / L.PIP),
                     lat_exit_type=ex30.exit_type)
    rec["trade"] = trade
    return rec


def main() -> None:
    t_start = time.time()
    manifest = json.loads(MANIFEST.read_text())
    store = MonthStore(manifest)
    counters = dict(DAYS_TOTAL=0, NOT_ELIGIBLE=0, ELIGIBLE_DAYS=0, NO_SWEEP=0,
                    SWEEP_DAYS=0, UPPER_SWEEPS=0, LOWER_SWEEPS=0,
                    REINTEGRATED_SETUPS=0, DOUBLE_SWEEP_INVALID=0,
                    NO_REINTEGRATION=0, NO_FILL=0, INVALID_RISK=0,
                    NO_TIME_EXIT_DATA=0, N_TRADES=0,
                    LAT30_TRADES=0, LAT30_NO_FILL=0, LAT30_INVALID_RISK=0)
    trades: list[dict] = []
    sweep_lat, reint_lat, ext_ratios, range_pips = [], [], [], []
    dates = L.discovery_dates()
    for k, d in enumerate(dates):
        rec = classify_day(store, d)
        counters["DAYS_TOTAL"] += 1
        if not rec["eligible"]:
            counters["NOT_ELIGIBLE"] += 1
            continue
        counters["ELIGIBLE_DAYS"] += 1
        range_pips.append(rec["asian_range_pips"])
        if rec["status"] == L.NO_SWEEP:
            counters["NO_SWEEP"] += 1
            continue
        counters["SWEEP_DAYS"] += 1
        counters["UPPER_SWEEPS" if rec["sweep_side"] > 0 else "LOWER_SWEEPS"] += 1
        sweep_lat.append(rec["sweep_latency_min"])
        if rec["status"] == L.NO_REINTEGRATION:
            counters["NO_REINTEGRATION"] += 1
            continue
        if rec["status"] == L.DOUBLE_SWEEP_INVALID:
            counters["DOUBLE_SWEEP_INVALID"] += 1
            continue
        if rec["status"] in (L.NO_FILL, L.INVALID_RISK, L.NO_TIME_EXIT_DATA):
            counters[rec["status"]] += 1
            continue
        if rec["status"] != L.TRADE:
            raise RuntimeError(f"unexpected status {rec['status']} on {d}")
        counters["REINTEGRATED_SETUPS"] += 1
        tr = rec["trade"]
        trades.append(tr)
        counters["N_TRADES"] += 1
        reint_lat.append((tr["decision_ts"] - tr["sweep_ts"]) / 60e9)
        ext_ratios.append(tr["sweep_ext_over_range"])
        if tr["lat_status"] == L.TRADE:
            counters["LAT30_TRADES"] += 1
        elif tr["lat_status"] == L.NO_FILL:
            counters["LAT30_NO_FILL"] += 1
        elif tr["lat_status"] == L.INVALID_RISK:
            counters["LAT30_INVALID_RISK"] += 1
        if (k + 1) % 250 == 0:
            print(f"  {k + 1}/{len(dates)} days, {counters['N_TRADES']} trades, "
                  f"{time.time() - t_start:.0f}s", flush=True)

    # ---- frozen metrics (spec 13) ----
    nets = np.array([t["net_pips"] for t in trades], dtype=np.float64)
    rs = np.array([t["r_mult"] for t in trades], dtype=np.float64)
    entry_ts = np.array([t["entry_ts"] for t in trades], dtype=np.int64)
    lat_mask = np.array([t["lat_status"] == L.TRADE for t in trades], dtype=bool)
    lat_rs = np.array([t["lat_r_mult"] for t in trades if t["lat_status"] == L.TRADE],
                      dtype=np.float64)
    lat_r_pips = np.array([t["lat_r_pips"] for t in trades if t["lat_status"] == L.TRADE],
                          dtype=np.float64)
    base_r_pips = np.array([t["r_pips"] for t in trades], dtype=np.float64)
    slip_rs = (nets - 2 * L.SLIP_PER_SIDE_PIPS) / base_r_pips
    stress_rs = lat_rs - (2 * L.SLIP_PER_SIDE_PIPS) / lat_r_pips
    wins_r = rs[nets > 0]
    losses_r = rs[nets < 0]
    pos_y, elig_y = L.positive_years(entry_ts, nets)
    lo, hi = L.bootstrap_ci95_mean(rs)
    dirs = np.array([t["direction"] for t in trades])
    longs_r = rs[dirs == "LONG"]
    shorts_r = rs[dirs == "SHORT"]

    def _mean(a: np.ndarray) -> float:
        return float(a.mean()) if len(a) else float("nan")

    results = {
        "spec": "PO3_BASE_M0_FROZEN_SPEC.md",
        "data": {"store": str(STORE), "partitions": manifest["partition_count"],
                 "total_ticks": manifest["total_rows"],
                 "discovery_dates": f"{L.DISCOVERY_FIRST}..{L.DISCOVERY_LAST}"},
        **counters,
        "TRADES_PER_YEAR": counters["N_TRADES"] / 9.0,
        "TRADES_PER_MONTH": counters["N_TRADES"] / 108.0,
        "WIN_RATE": float((nets > 0).mean()) if len(nets) else float("nan"),
        "MEAN_NET_PIPS": _mean(nets),
        "MEDIAN_NET_PIPS": float(np.median(nets)) if len(nets) else float("nan"),
        "TOTAL_NET_PIPS": float(nets.sum()),
        "PROFIT_FACTOR": L.profit_factor(nets),
        "EXPECTANCY_R": _mean(rs),
        "AVG_WIN_R": _mean(wins_r),
        "AVG_LOSS_R": _mean(losses_r),
        "MAX_DRAWDOWN_R": L.max_drawdown_r(rs),
        "MAX_CONSECUTIVE_LOSSES": L.max_consecutive_losses(nets),
        "POSITIVE_YEARS": pos_y,
        "YEARS_ELIGIBLE": elig_y,
        "REMOVE_BEST_1_PERCENT_MEAN_R": L.remove_best_1pct_mean(rs),
        "LONG_N": int((dirs == "LONG").sum()),
        "SHORT_N": int((dirs == "SHORT").sum()),
        "LONG_EXPECTANCY_R": _mean(longs_r),
        "SHORT_EXPECTANCY_R": _mean(shorts_r),
        "LATENCY_30S_EXPECTANCY_R": _mean(lat_rs),
        "SLIPPAGE_050_EXPECTANCY_R": _mean(slip_rs),
        "REALISTIC_STRESS_EXPECTANCY_R": _mean(stress_rs),
        "BOOTSTRAP_CI95_EXPECTANCY_R": [lo, hi],
        "DIAGNOSTICS": {
            "ASIAN_RANGE_MEDIAN_PIPS": float(np.median(range_pips)) if range_pips else None,
            "SWEEP_STRENGTH_MEDIAN": float(np.median(ext_ratios)) if ext_ratios else None,
            "LONDON_TO_SWEEP_MEDIAN_MIN": float(np.median(sweep_lat)) if sweep_lat else None,
            "SWEEP_TO_REINTEGRATION_MEDIAN_MIN": (float(np.median(reint_lat))
                                                  if reint_lat else None),
            "MFE30_R_MEAN": _mean(np.array([t["mfe30_r"] for t in trades],
                                           dtype=np.float64)),
            "MFE60_R_MEAN": _mean(np.array([t["mfe60_r"] for t in trades],
                                           dtype=np.float64)),
            "MFE120_R_MEAN": _mean(np.array([t["mfe120_r"] for t in trades],
                                            dtype=np.float64)),
            "P_REACH_1R": _mean(np.array([t["kr1"] for t in trades], dtype=np.float64)),
            "P_REACH_1.5R": _mean(np.array([t["kr15"] for t in trades], dtype=np.float64)),
            "P_REACH_2R": _mean(np.array([t["kr2"] for t in trades], dtype=np.float64)),
        },
        "runtime_s": round(time.time() - t_start, 1),
    }
    # gate (spec 15)
    m = results
    gate = {
        "N_TRADES>=200": m["N_TRADES"] >= 200,
        "EXPECTANCY_R>=0.10": m["EXPECTANCY_R"] >= 0.10,
        "PF>=1.20": m["PROFIT_FACTOR"] >= 1.20,
        "TOTAL_NET_PIPS>0": m["TOTAL_NET_PIPS"] > 0,
        "POSITIVE_YEARS_RATIO>=0.67": (m["YEARS_ELIGIBLE"] > 0 and
                                       m["POSITIVE_YEARS"] / m["YEARS_ELIGIBLE"] >= 0.67),
        "REMOVE_BEST_1PCT>0": m["REMOVE_BEST_1_PERCENT_MEAN_R"] > 0,
        "LATENCY_30S>0": m["LATENCY_30S_EXPECTANCY_R"] > 0,
        "REALISTIC_STRESS>0": m["REALISTIC_STRESS_EXPECTANCY_R"] > 0,
        "LONG>0": m["LONG_EXPECTANCY_R"] > 0,
        "SHORT>0": m["SHORT_EXPECTANCY_R"] > 0,
    }
    results["GATE"] = gate
    results["GATE_PASS"] = all(gate.values())
    results["CLASSIFICATION"] = (
        "PO3_BASE_CANDIDATE" if results["GATE_PASS"]
        else ("PO3_BASE_NO_EDGE" if (m["EXPECTANCY_R"] <= 0 or m["PROFIT_FACTOR"] <= 1
                                     or m["REALISTIC_STRESS_EXPECTANCY_R"] <= 0)
              else "PO3_BASE_WEAK_PHENOMENON"))

    (HERE / "po3_base_m0_results.json").write_text(json.dumps(results, indent=1))
    (HERE / "po3_base_m0_trades.json").write_text(json.dumps(trades, indent=1))
    print(json.dumps({k: v for k, v in results.items() if k != "DIAGNOSTICS"},
                     indent=1, default=str))
    print(json.dumps(results["DIAGNOSTICS"], indent=1))


if __name__ == "__main__":
    sys.exit(main())
