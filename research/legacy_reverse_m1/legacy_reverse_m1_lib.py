#!/usr/bin/python3
"""LEGACY_REVERSE_M1 core library.

Implements exactly LEGACY_REVERSE_M1_FROZEN_SPEC.md:
  H1  REVERSE_AFTER_STOP_RAW  — Test01 mechanics (reverse after L0 stop, no filters)
  H2  DIRECT_SIGNAL_INVERSION — mirrored-risk direct inversion of the canonical signal
  T4  TEST04_LEGACY           — historical benchmark (reconstructed config, no gates)

Reuses, unmodified:
  - research/legacy_bots_m1/m1_engine.py      (canonical EMA signal + frozen streams)
  - research/po3_base_m0/po3_base_m0_lib.py   (guards + generic metrics)
All market timestamps are int64 nanoseconds UTC. Server time = Europe/Helsinki.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

pq = None  # lazy: imported on first partition load (CI has no pyarrow)

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent / "legacy_bots_m1"))
sys.path.insert(0, str(_HERE.parent / "po3_base_m0"))

import m1_engine as M1            # noqa: E402  (canonical EMA engine, frozen)
import po3_base_m0_lib as PO3     # noqa: E402  (guards + metrics, frozen)

HEL = ZoneInfo("Europe/Helsinki")
UTC = timezone.utc

PIP = 1e-4
SEC = 1_000_000_000

# Frozen execution constants (spec §4-§6)
DELAY_BASE_NS = 5 * SEC
DELAY_LATENCY_NS = 30 * SEC
FILL_BOUND_NS = 30 * SEC
SLIP_STRESS_PIPS = 0.50
MIN_RR = 2.5                      # EA MinRR (frozen)
SWING_BARS = 3                    # EA SL_SwingBars
SWING_BUF_PIPS = 2.0              # EA swing buffer
BE_TRIGGER_R = 1.5                # EA BE_Trigger_R (live for reverse trades)
BE_LOCK_PIPS = 1.0                # EA: SL moved to open +/- 1 pip
MAX_TRADES_PER_DAY = 2            # EA MaxTradesPerDay (counts reverses)
WINDOW_END_NS = 1546300799_999999999   # last ns of 2018-12-31 UTC (guard end - 1)

STORE = Path(r"E:\ResearchData\botTrading\ticks\parquet\EURUSD")
MANIFEST = _HERE / "data_manifest.json"
M15_PATH = _HERE.parent / "legacy_bots_m1" / "data" / "EURUSD15_2010_2018.csv"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def server_to_ns(dt_naive: datetime) -> int:
    """Canonical stream naive server datetime -> UTC ns (IANA tz, DST-real)."""
    return int(dt_naive.replace(tzinfo=HEL).astimezone(UTC).timestamp()) * SEC


def ns_to_server(ns: int) -> datetime:
    return datetime.fromtimestamp(ns / SEC, tz=UTC).astimezone(HEL).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Tick store (SHA-verified month partitions, same design as po3 MonthStore)
# ---------------------------------------------------------------------------
class TickStore:
    def __init__(self, manifest_path: Path = MANIFEST, verify_hash: bool = True):
        self.entries = json.loads(manifest_path.read_text())["entries"]
        self.verify_hash = verify_hash
        self.verified: set[str] = set()
        self.cache: dict[tuple[int, int], tuple[np.ndarray, ...]] = {}

    def load(self, year: int, month: int):
        key = (year, month)
        if key in self.cache:
            return self.cache[key]
        if not (2010 <= year <= 2018):
            raise PO3.OutOfWindowError(f"forbidden partition year={year}")
        rel = f"{STORE}\\year={year}\\month={month:02d}\\ticks.parquet"
        entry = self.entries[f"{year}-{month:02d}"]
        if entry["path"] != rel:
            raise RuntimeError(f"manifest path mismatch: {entry['path']} vs {rel}")
        if self.verify_hash and rel not in self.verified:
            got = sha256_file(Path(rel))
            if got != entry["sha256"]:
                raise RuntimeError(f"SHA256 mismatch for {rel}")
            self.verified.add(rel)
        global pq
        if pq is None:
            import pyarrow.parquet as _pq
            pq = _pq
        tbl = pq.read_table(rel, columns=["timestamp_utc", "bid", "ask"])
        ts = tbl.column("timestamp_utc").to_numpy().astype("datetime64[ns]").astype("int64")
        bid = tbl.column("bid").to_numpy().astype(np.float64)
        ask = tbl.column("ask").to_numpy().astype(np.float64)
        bad = (~np.isfinite(bid)) | (~np.isfinite(ask)) | (bid <= 0) | (ask <= 0)
        if bad.any():
            keep = ~bad
            ts, bid, ask = ts[keep], bid[keep], ask[keep]
        order = np.argsort(ts, kind="stable")
        out = (ts[order], bid[order], ask[order])
        if len(self.cache) >= 4:
            self.cache.pop(next(iter(self.cache)))
        self.cache[key] = out
        return out

    def load_range(self, start_ns: int, end_ns: int):
        """Concatenated sorted [start_ns, end_ns] tick slice (inclusive)."""
        if start_ns < PO3.UTC_GUARD_START_NS or end_ns > PO3.UTC_GUARD_END_NS:
            raise PO3.OutOfWindowError(
                f"range [{start_ns}, {end_ns}] escapes the 2010-2018 UTC guard")
        end_ns = min(end_ns, WINDOW_END_NS)
        if end_ns < start_ns:
            e = np.empty(0, dtype=np.int64)
            return e, np.empty(0), np.empty(0)
        d0 = np.datetime64(start_ns, "ns").astype("datetime64[M]")
        d1 = np.datetime64(end_ns, "ns").astype("datetime64[M]")
        parts = []
        for ym in np.arange(d0, d1 + np.timedelta64(1, "M"), dtype="datetime64[M]"):
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

    def next_month_boundary(self, ns: int) -> int:
        d = np.datetime64(ns, "ns").astype("datetime64[M]")
        nxt = (d + np.timedelta64(1, "M")).astype("datetime64[ns]").astype(np.int64)
        return int(min(nxt, PO3.UTC_GUARD_END_NS))


# ---------------------------------------------------------------------------
# Canonical streams (regenerated + identity-checked against frozen CSVs)
# ---------------------------------------------------------------------------
_CTX_TS_CACHE: dict[int, np.ndarray] = {}


def build_canonical_streams():
    """Regenerate the frozen baseline + pyramid streams and verify identity
    against the frozen prior CSVs (mission §2). Returns (ctx, base, pyr)."""
    ctx = M1.Context(M15_PATH)
    base = M1.Bot("baseline", pyramid=False, mode="historical")
    pyr = M1.Bot("pyramid_safe", pyramid=True, mode="historical")
    base.run(ctx)
    pyr.run(ctx)
    return ctx, base, pyr


def verify_against_frozen_csv(base, pyr) -> dict:
    import csv
    frozen_b = [r for r in csv.DictReader(
        open(_HERE.parent / "legacy_bots_m1" / "results_baseline.csv"))
        if r["mode"] == "historical"]
    frozen_p = [r for r in csv.DictReader(
        open(_HERE.parent / "legacy_bots_m1" / "results_pyramid_safe.csv"))
        if r["mode"] == "historical"]

    def rows_match(frozen, trades):
        if len(frozen) != len(trades):
            return False
        for r, t in zip(frozen, trades):
            if (r["entry_time"] != t.entry_time.strftime("%Y-%m-%d %H:%M:%S")
                    or int(r["dir"]) != t.dir or r["reason"] != t.reason
                    or abs(float(r["pnl"]) - t.pnl) > 1e-6
                    or abs(float(r["entry"]) - t.entry) > 1e-9
                    or int(r["level"]) != t.level):
                return False
        return True

    return {
        "baseline_identity": rows_match(frozen_b, base.trades),
        "pyramid_identity": rows_match(frozen_p, pyr.trades),
        "n_baseline": len(base.trades),
        "n_pyramid": len(pyr.trades),
    }


def m15_bar_index_at(ctx, server_dt: datetime) -> int:
    """Index of the M15 bar containing server_dt (last bar with open <= t)."""
    key = id(ctx)
    if key not in _CTX_TS_CACHE:
        _CTX_TS_CACHE[key] = np.array([t.timestamp() for t in ctx.t])
    arr = _CTX_TS_CACHE[key]
    return int(np.searchsorted(arr, server_dt.timestamp(), side="right")) - 1


# ---------------------------------------------------------------------------
# Trade simulation: fill -> levels -> tick exit scan (with optional BE)
# ---------------------------------------------------------------------------
class SimResult:
    __slots__ = ("status", "entry_ts", "entry_px", "entry_px_eff", "sl", "tp",
                 "risk_dist", "exit_type", "exit_ts", "exit_px", "net_pips", "r",
                 "be_moved")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def _fill(store, direction, ref_ns, slip_pips):
    """First tick >= ref_ns within FILL_BOUND. Returns (ts, ref_px, eff_px) or
    None. ref_px = unslipped executable price; eff_px = fill incl. slippage."""
    ts, bid, ask = store.load_range(ref_ns, min(ref_ns + FILL_BOUND_NS, WINDOW_END_NS))
    if len(ts) == 0:
        return None
    ref_px = float(ask[0] if direction > 0 else bid[0])
    slip = slip_pips * PIP
    eff = ref_px + slip if direction > 0 else ref_px - slip
    return int(ts[0]), ref_px, eff


def _exit_scan(store, direction, entry_ts, ref_px, sl0, tp, risk_dist,
               be_enabled, slip_pips):
    """Tick-chronological exit scan, month-blocked. STOP fills at the exit-side
    tick price (+adverse slip), TARGET fills exactly at tp, optional EA
    breakeven (1.5R -> entry +/- 1 pip lock). Window end closes at the last
    tick (EOD_WINDOW)."""
    slip = slip_pips * PIP
    be_trig = BE_TRIGGER_R * risk_dist
    be_level = (ref_px + BE_LOCK_PIPS * PIP) if direction > 0 else (ref_px - BE_LOCK_PIPS * PIP)
    sl = sl0
    moved = False
    cursor = entry_ts
    last_ts = entry_ts
    last_px = None
    while True:
        seg_end = min(store.next_month_boundary(cursor), WINDOW_END_NS)
        seg_ts, bid, ask = store.load_range(cursor + 1, seg_end)
        if len(seg_ts) == 0:
            if seg_end >= WINDOW_END_NS:
                # end of data reached: close at the last tick seen
                if last_px is None:
                    return SimResult(status="NO_EXIT_DATA")
                px = last_px - slip if direction > 0 else last_px + slip
                return SimResult(status="TRADE", exit_type="EOD_WINDOW",
                                 exit_ts=int(last_ts), exit_px=px, be_moved=moved)
            cursor = seg_end        # data hole (weekend/holiday): skip forward
            continue
        side = bid if direction > 0 else ask
        last_ts = int(seg_ts[-1])
        last_px = float(side[-1])
        if direction > 0:
            stop_hits = np.nonzero(side <= sl)[0]
            tgt_hits = np.nonzero(side >= tp)[0]
            be_hits = (np.nonzero(side >= ref_px + be_trig)[0]
                       if be_enabled and not moved else None)
        else:
            stop_hits = np.nonzero(side >= sl)[0]
            tgt_hits = np.nonzero(side <= tp)[0]
            be_hits = (np.nonzero(side <= ref_px - be_trig)[0]
                       if be_enabled and not moved else None)
        cands = []
        if len(stop_hits):
            cands.append((int(stop_hits[0]), 0))
        if len(tgt_hits):
            cands.append((int(tgt_hits[0]), 1))
        if be_hits is not None and len(be_hits):
            cands.append((int(be_hits[0]), 2))
        if not cands:
            cursor = int(seg_ts[-1])
            continue
        cands.sort()
        i, kind = cands[0]
        if kind == 0:
            px = float(side[i]) - slip if direction > 0 else float(side[i]) + slip
            return SimResult(status="TRADE", exit_type="STOP",
                             exit_ts=int(seg_ts[i]), exit_px=px, be_moved=moved)
        if kind == 1:
            return SimResult(status="TRADE", exit_type="TARGET",
                             exit_ts=int(seg_ts[i]), exit_px=float(tp), be_moved=moved)
        moved = True          # BE trigger fired first
        sl = be_level
        cursor = int(seg_ts[i])


def simulate(store, direction, decision_ns, delay_ns, slip_pips, level_builder,
             be_enabled):
    """Generic causal trade: fill at decision+delay, build levels from the
    UNSLIPPED fill price, tick exit. level_builder(ref_px) -> (sl, tp) or None."""
    ref_ns = decision_ns + delay_ns
    if ref_ns >= PO3.UTC_GUARD_END_NS:
        return SimResult(status="NO_FILL")
    fill = _fill(store, direction, ref_ns, slip_pips)
    if fill is None:
        return SimResult(status="NO_FILL")
    entry_ts, ref_px, eff_px = fill
    built = level_builder(ref_px)
    if built is None:
        return SimResult(status="INVALID_LEVELS", entry_ts=entry_ts,
                         entry_px=ref_px, entry_px_eff=eff_px)
    sl, tp = built
    risk = abs(ref_px - sl)
    if risk <= 0:
        return SimResult(status="INVALID_LEVELS", entry_ts=entry_ts,
                         entry_px=ref_px, entry_px_eff=eff_px)
    ex = _exit_scan(store, direction, entry_ts, ref_px, sl, tp, risk,
                    be_enabled, slip_pips)
    if ex.status != "TRADE":
        return ex
    move = (ex.exit_px - eff_px) if direction > 0 else (eff_px - ex.exit_px)
    ex.entry_ts = entry_ts
    ex.entry_px = ref_px
    ex.entry_px_eff = eff_px
    ex.sl = sl
    ex.tp = tp
    ex.risk_dist = risk
    ex.net_pips = move / PIP
    ex.r = move / risk
    return ex


# ---------------------------------------------------------------------------
# Trigger extraction
# ---------------------------------------------------------------------------
def _trades_of(base):
    return base.trades if hasattr(base, "trades") else base


def h1_triggers(base):
    """Baseline L0 stop-loss triggers (EA loss rule pnl<=0, stop exits only)."""
    out = []
    for t in _trades_of(base):
        if t.reason != "sl" or t.pnl > 0:
            continue
        sl_at_exit = t.sl0
        if t.be_moved:
            sl_at_exit = t.entry + BE_LOCK_PIPS * PIP if t.dir > 0 \
                else t.entry - BE_LOCK_PIPS * PIP
        out.append({
            "trade": t, "dir": t.dir, "sl_at_exit": sl_at_exit,
            "exit_bar_open_ns": server_to_ns(t.exit_time),
            "entry_day": t.entry_time.date(),
        })
    return out


def h2_triggers(base):
    out = []
    for t in _trades_of(base):
        out.append({
            "trade": t, "dir": -t.dir,                   # flipped
            "decision_ns": server_to_ns(t.entry_time),
            "r0": t.sl_dist,                             # ORIGINAL causal risk distance
        })
    return out


def t4_triggers(pyr):
    """Test04: L0 stops gated by consecLosses>=3 + unconditional L2 stops."""
    consec = 0
    out = []
    for t in _trades_of(pyr):
        if t.pnl <= 0:
            consec += 1
        else:
            consec = 0
        if t.reason != "sl" or t.pnl > 0 or t.level not in (0, 2):
            continue
        if t.level == 0 and consec < 3:
            continue
        sl_at_exit = t.sl0
        if t.be_moved:
            sl_at_exit = t.entry + BE_LOCK_PIPS * PIP if t.dir > 0 \
                else t.entry - BE_LOCK_PIPS * PIP
        out.append({
            "trade": t, "dir": t.dir, "level": t.level, "consec": consec,
            "sl_at_exit": sl_at_exit,
            "exit_bar_open_ns": server_to_ns(t.exit_time),
            "entry_day": t.entry_time.date(),
        })
    return out


# ---------------------------------------------------------------------------
# Scenario runners (multi-variant: scenarios share hot partitions)
# ---------------------------------------------------------------------------
def run_h1(store, ctx, triggers, base_trades, variants, rev_max_sl_pips=0.0,
           consec_gate=0):
    """H1 (Test01 defaults) / T4 (Test04 overrides). variants = list of
    (name, delay_ns, slip_pips). Chronological overlay, EA-faithful daily
    counter + overlap guard per variant; baseline stream NOT displaced
    (frozen idealization). Returns {variant_name: [records]}."""
    daily_rev = {v[0]: {} for v in variants}
    last_exit_ns = {v[0]: -1 for v in variants}
    records = {v[0]: [] for v in variants}
    for tr in triggers:
        if consec_gate and tr.get("level", 0) == 0 and tr.get("consec", 0) < consec_gate:
            for name, _d, _s in variants:
                records[name].append({"status": "SKIP_CONSEC", "trigger": tr})
            continue
        t_stop_ns, confirmed = find_stop_tick(store, tr["dir"], tr["sl_at_exit"],
                                              tr["exit_bar_open_ns"],
                                              tr["exit_bar_open_ns"] + 15 * 60 * SEC)
        if t_stop_ns is None:
            for name, _d, _s in variants:
                records[name].append({"status": "SKIP_NO_TICK", "trigger": tr})
            continue
        day = ns_to_server(t_stop_ns).date()
        # EA daily counter: baseline trades OPENED on the stop day at/before
        # the reverse moment + reverses already taken today (per variant below)
        n_today = sum(1 for t in base_trades
                      if t.entry_time.date() == day
                      and server_to_ns(t.entry_time) <= t_stop_ns)
        for name, delay_ns, slip_pips in variants:
            recs = records[name]
            if t_stop_ns <= last_exit_ns[name]:
                recs.append({"status": "SKIP_OVERLAP", "trigger": tr})
                continue
            if n_today + daily_rev[name].get(day, 0) >= MAX_TRADES_PER_DAY:
                recs.append({"status": "SKIP_DAILY", "trigger": tr, "t_stop_ns": t_stop_ns})
                continue
            direction = -tr["dir"]
            builder = h1_level_builder(ctx, t_stop_ns, direction)
            res = simulate(store, direction, t_stop_ns, delay_ns, slip_pips, builder,
                           be_enabled=True)
            if res.status == "NO_FILL":
                recs.append({"status": "NO_FILL", "trigger": tr, "t_stop_ns": t_stop_ns,
                             "confirmed": confirmed})
                continue
            if res.status != "TRADE":
                recs.append({"status": res.status, "trigger": tr, "t_stop_ns": t_stop_ns,
                             "confirmed": confirmed})
                continue
            if rev_max_sl_pips > 0 and res.risk_dist / PIP > rev_max_sl_pips:
                recs.append({"status": "SKIP_REVMAXSL", "trigger": tr,
                             "t_stop_ns": t_stop_ns, "confirmed": confirmed,
                             "risk_pips": res.risk_dist / PIP})
                continue
            daily_rev[name][day] = daily_rev[name].get(day, 0) + 1
            last_exit_ns[name] = res.exit_ts
            recs.append({"status": "TRADE", "trigger": tr, "t_stop_ns": t_stop_ns,
                         "confirmed": confirmed, "res": res, "dir": direction,
                         "level": tr.get("level", 0)})
    return records


def h2_level_builder(r0: float, direction: int):
    def build(ref_px):
        if direction > 0:   # inverted LONG: stop below, target above
            return ref_px - r0, ref_px + MIN_RR * r0
        return ref_px + r0, ref_px - MIN_RR * r0
    return build


def run_h2(store, triggers, variants):
    """variants = list of (name, delay_ns, slip_pips). Returns
    {variant_name: [records]}."""
    records = {v[0]: [] for v in variants}
    for tr in triggers:
        for name, delay_ns, slip_pips in variants:
            res = simulate(store, tr["dir"], tr["decision_ns"], delay_ns, slip_pips,
                           h2_level_builder(tr["r0"], tr["dir"]), be_enabled=False)
            records[name].append({"status": res.status, "trigger": tr, "res": res,
                                  "dir": tr["dir"]})
    return records


def find_stop_tick(store, direction, sl_at_exit, bar_open_ns, bar_end_ns):
    """Causal stop-execution tick (spec §6 clarification). Returns
    (ts, confirmed) or (None, False)."""
    ts, bid, ask = store.load_range(bar_open_ns, bar_end_ns)
    side = bid if direction > 0 else ask
    hit = np.nonzero(side <= sl_at_exit)[0] if direction > 0 \
        else np.nonzero(side >= sl_at_exit)[0]
    if len(hit):
        return int(ts[hit[0]]), True
    ts2, _b, _a = store.load_range(bar_end_ns, bar_end_ns + 1800 * SEC)
    if len(ts2):
        return int(ts2[0]), False
    return None, False


def h1_level_builder(ctx, t_stop_ns: int, direction: int):
    """EA swing construction at the reverse moment (frozen §4)."""
    bars = m15_bar_index_at(ctx, ns_to_server(t_stop_ns))
    if bars < SWING_BARS:
        return lambda ref_px: None
    if direction < 0:  # reverse SELL: SL = max high of bars 1..3 + buffer
        sl = max(ctx.h[bars - k] for k in range(1, SWING_BARS + 1)) + SWING_BUF_PIPS * PIP
    else:              # reverse BUY: SL = min low of bars 1..3 - buffer
        sl = min(ctx.l[bars - k] for k in range(1, SWING_BARS + 1)) - SWING_BUF_PIPS * PIP

    def build(ref_px):
        if direction < 0:
            if sl - ref_px <= 0:
                return None
            return sl, ref_px - MIN_RR * (sl - ref_px)
        if ref_px - sl <= 0:
            return None
        return sl, ref_px + MIN_RR * (ref_px - sl)
    return build
