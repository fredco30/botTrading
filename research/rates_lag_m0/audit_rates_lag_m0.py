"""RATES-LAG-M0 independent audit (frozen spec section 19).

Independently re-derives >= 30 H30 trades from the raw E: sources using a
deliberately different implementation path:
  - no rates_lag_lib, no numpy: pure python, pyarrow .to_pylist() columns
  - linear scans instead of searchsorted
  - independent timestamp parsing (arrow -> int ns, no pandas/datetime64)
Re-derives per trade: rate direction, Treasury PRE/H timestamps, EURUSD entry
side/time/price, exit side/time/price, net pips — then compares exactly.

Usage: python audit_rates_lag_m0.py [n_audits=40]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pyarrow.parquet as pq

MISSION = Path(__file__).resolve().parent
MANIFEST = Path(r"E:\ResearchData\botTrading\rates\databento_event_tbbo\manifests\manifest.json")
FX_ROOT = Path(r"E:\ResearchData\botTrading\ticks\parquet\EURUSD")
PIP = 1e-4
AUDIT_HORIZON_S = 30.0
DELAY_S = 1.0
FILL_BOUND_S = 10.0
EXIT_S = 120.0
EXIT_BOUND_S = 60.0


def iso_to_ns(s: str) -> int:
    # independent parse: 'YYYY-MM-DDTHH:MM:SS[+00:00]' whole seconds only
    d, t = s.split("T")
    y, mo, da = (int(x) for x in d.split("-"))
    hh, mi, ss = (int(x) for x in t[:8].split(":"))
    days = _days_from_civil(y, mo, da)
    return ((days * 86400) + hh * 3600 + mi * 60 + ss) * 1_000_000_000


def _days_from_civil(y: int, m: int, d: int) -> int:
    # Howard Hinnant's civil_from_days inverse
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def valid_events() -> dict[str, dict]:
    m = json.loads(MANIFEST.read_text())
    out: dict[str, dict] = {}
    for e in m["entries"].values():
        if e["family"] not in ("NFP", "CPI") or e["status"] != "ok":
            continue
        rec = out.setdefault(e["event_id"], {})
        rec[e["symbol"]] = e
    return {k: v for k, v in out.items() if len(v) == 2}


def rate_mid_series(path: str, t0_ns: int):
    """(ts_list, mid_list) of valid-book records with window_start <= ts, pure python."""
    t = pq.read_table(path, columns=["ts_recv", "bid_px_00", "ask_px_00"])
    ts_col = t.column("ts_recv").cast("int64").to_pylist()
    bid = t.column("bid_px_00").to_pylist()
    ask = t.column("ask_px_00").to_pylist()
    wstart = t0_ns - 300 * 1_000_000_000
    ts_out, mid_out = [], []
    for i in range(len(ts_col)):
        b, a = bid[i], ask[i]
        if b is None or a is None or not (b > 0) or not (a > 0):
            continue
        ts = ts_col[i]
        if ts < wstart:
            continue
        ts_out.append(ts)
        mid_out.append((b + a) / 2.0)
    order = sorted(range(len(ts_out)), key=lambda i: ts_out[i])
    return [ts_out[i] for i in order], [mid_out[i] for i in order]


def pick_pre(ts, mid, t0_ns):
    best = None
    for i in range(len(ts)):
        if ts[i] < t0_ns:
            best = mid[i]
        else:
            break
    return best


def pick_horizon(ts, mid, t0_ns, h_ns):
    best = None
    for i in range(len(ts)):
        if t0_ns <= ts[i] <= t0_ns + h_ns:
            best = mid[i]
    return best


def fx_ticks(t0_ns):
    """EURUSD (ts, bid, ask) lists for [T0-1s, T0+420s], independent read."""
    y = _days_from_civil_year(t0_ns)
    mo = _month(t0_ns)
    p = FX_ROOT / f"year={y}" / f"month={mo:02d}" / "ticks.parquet"
    t = pq.read_table(p, columns=["timestamp_utc", "bid", "ask"])
    ts = t.column("timestamp_utc").cast("int64").to_pylist()
    bid = t.column("bid").to_pylist()
    ask = t.column("ask").to_pylist()
    lo, hi = t0_ns - 1_000_000_000, t0_ns + 420_000_000_000
    return ([ts[i] for i in range(len(ts)) if lo <= ts[i] <= hi],
            [bid[i] for i in range(len(ts)) if lo <= ts[i] <= hi],
            [ask[i] for i in range(len(ts)) if lo <= ts[i] <= hi])


def _days_from_civil_year(ns_val):
    days = ns_val // 1_000_000_000 // 86400
    z = days + 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    m = mp + (3 if mp < 10 else -9)
    return y + (1 if m <= 2 else 0)


def _month(ns_val):
    days = ns_val // 1_000_000_000 // 86400
    z = days + 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    m = mp + (3 if mp < 10 else -9)
    return m


def first_at(ts, px, ref_ns):
    for i in range(len(ts)):
        if ts[i] >= ref_ns:
            return ts[i], px[i]
    return None


def main() -> int:
    n_audits = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    trades = json.loads((MISSION / "rates_lag_m0_trades.json").read_text())
    h30 = [t for t in trades if abs(t["horizon_s"] - AUDIT_HORIZON_S) < 1e-9
           and t["status"] == "ok"]
    h30.sort(key=lambda t: t["entry_ts_ns"])
    # spread across the sample: take evenly spaced audit targets
    step = max(1, len(h30) // n_audits)
    targets = h30[::step][:n_audits]
    if len(targets) < 30:
        print(f"ABORT: only {len(targets)} auditable trades (need >= 30)")
        return 2

    ticks = json.loads((MISSION / "instrument_tick_sizes.json").read_text())
    events = valid_events()
    ok = 0
    mismatches = []
    for t in targets:
        ev = events[t["event_id"]]
        zf, zn = ev["ZF"], ev["ZN"]
        t0 = iso_to_ns(zf["t0"])
        assert iso_to_ns(zn["t0"]) == t0
        zf_ts, zf_mid = rate_mid_series(zf["parquet"], t0)
        zn_ts, zn_mid = rate_mid_series(zn["parquet"], t0)
        zf_pre, zf_h = pick_pre(zf_ts, zf_mid, t0), pick_horizon(zf_ts, zf_mid, t0, 30 * 10**9)
        zn_pre, zn_h = pick_pre(zn_ts, zn_mid, t0), pick_horizon(zn_ts, zn_mid, t0, 30 * 10**9)
        zft = ticks[zf["raw_symbol"]]["min_price_increment"]
        znt = ticks[zn["raw_symbol"]]["min_price_increment"]
        zm, nm = zf_h - zf_pre, zn_h - zn_pre
        if zm == 0 or nm == 0 or (zm > 0) != (nm > 0) \
                or abs(zm) < zft or abs(nm) < znt:
            direction = 0
        else:
            direction = 1 if zm > 0 else -1
        fx_ts, fx_bid, fx_ask = fx_ticks(t0)
        dec = t0 + int(round(30.0 * 1e9))
        ref = dec + int(round(DELAY_S * 1e9))
        if direction > 0:
            e = first_at(fx_ts, fx_ask, ref)
        else:
            e = first_at(fx_ts, fx_bid, ref)
        e_ts, e_px = e
        if e_ts > ref + int(round(FILL_BOUND_S * 1e9)):
            e = None
        xref = e_ts + int(round(EXIT_S * 1e9))
        if direction > 0:
            x = first_at(fx_ts, fx_bid, xref)
        else:
            x = first_at(fx_ts, fx_ask, xref)
        x_ts, x_px = x
        if x_ts > xref + int(round(EXIT_BOUND_S * 1e9)):
            x = None
        net = (x_px - e_px) / PIP * direction

        checks = {
            "direction": (direction, t["direction"]),
            "entry_ts_ns": (e_ts, t["entry_ts_ns"]),
            "entry_px": (e_px, t["entry_px"]),
            "exit_ts_ns": (x_ts, t["exit_ts_ns"]),
            "exit_px": (x_px, t["exit_px"]),
            "net_pips": (net, t["net_pips"]),
        }
        bad = {}
        for k, (mine, theirs) in checks.items():
            same = (abs(mine - theirs) < 1e-9) if isinstance(mine, float) \
                else mine == theirs
            if not same:
                bad[k] = {"audit": mine, "pipeline": theirs}
        if not bad:
            ok += 1
        else:
            mismatches.append({"event_id": t["event_id"], "diffs": bad})

    verdict = "PASS" if not mismatches else "FAIL"
    result = {
        "audit": "RATES-LAG-M0 independent audit (H30)",
        "n_audited": len(targets),
        "n_exact": ok,
        "mismatches": mismatches,
        "verdict": verdict,
    }
    (MISSION / "rates_lag_m0_audit.json").write_text(json.dumps(result, indent=1))
    print(f"AUDIT H30: {ok}/{len(targets)} exact -> {verdict}")
    for m in mismatches[:10]:
        print(" ", m)
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
