#!/usr/bin/python3
"""LAB_AUDIT_M0 shared library.

Independent audit utilities. Imports production code ONLY for:
  - PO3.execute() (the execution function under test — used as "engine A"
    and as the normal pipeline for controls A-F),
  - PO3 metric functions (controls A-C, H),
  - LEGACY lib (controls G/I/J; engine A for legacy semantics).
Nothing here is used to modify any frozen research result.
All timestamps int64 ns UTC. 2019+ and protected OOS are FORBIDDEN and
blocked by guards below.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
for p in (_REPO / "research" / "po3_base_m0",
          _REPO / "research" / "legacy_reverse_m1",
          _REPO / "research" / "legacy_bots_m1"):
    sys.path.insert(0, str(p))

import po3_base_m0_lib as PO3            # noqa: E402  (engine under test)
import legacy_reverse_m1_lib as LEGACY   # noqa: E402  (engine under test)

UTC = timezone.utc
PIP = 1e-4
SEC = 1_000_000_000
STORE = Path(r"E:\ResearchData\botTrading\ticks\parquet\EURUSD")
MANIFEST_PATH = _REPO / "research" / "po3_base_m0" / "data_manifest.json"
UTC_START_NS = PO3.UTC_GUARD_START_NS   # 2010-01-01Z
UTC_END_NS = PO3.UTC_GUARD_END_NS       # 2019-01-01Z (exclusive bound)
LONDON = PO3.LONDON


class ForbiddenRangeError(RuntimeError):
    pass


def london_ns(d: date, hour: int, minute: int, second: int = 0) -> int:
    dt = datetime(d.year, d.month, d.day, hour, minute, second, tzinfo=LONDON)
    return int(dt.astimezone(UTC).timestamp()) * SEC


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text())


# ---------------------------------------------------------------------------
# Independent audit tick loader (pyarrow direct, 2010-2018 hard guard)
# ---------------------------------------------------------------------------
_PQ = None


def _pq_mod():
    global _PQ
    if _PQ is None:
        import pyarrow.parquet as _p
        _PQ = _p
    return _PQ


def partition_path(year: int, month: int) -> Path:
    if not (2010 <= year <= 2018):
        raise ForbiddenRangeError(f"forbidden partition year={year} (2019+ / OOS)")
    return STORE / f"year={year}" / f"month={month:02d}" / "ticks.parquet"


def load_partition_raw(year: int, month: int):
    """RAW columns, no cleaning/sorting (for integrity checks)."""
    import pyarrow.parquet as pq
    rel = str(partition_path(year, month))
    tbl = pq.read_table(rel, columns=["timestamp_utc", "bid", "ask", "mid",
                                      "spread_pips"])
    ts = tbl.column("timestamp_utc").to_numpy().astype("datetime64[ns]").astype("int64")
    return (ts,
            tbl.column("bid").to_numpy().astype(np.float64),
            tbl.column("ask").to_numpy().astype(np.float64),
            tbl.column("mid").to_numpy().astype(np.float64),
            tbl.column("spread_pips").to_numpy().astype(np.float64))


def load_range(start_ns: int, end_ns: int):
    """Production-equivalent slice: clean + stable sort, [start, end] inclusive.
    Mirrors TickStore.load_range conventions without importing it."""
    if start_ns < UTC_START_NS or end_ns > UTC_END_NS:
        raise ForbiddenRangeError(
            f"range [{start_ns}, {end_ns}] escapes the 2010-2018 UTC guard")
    pq = _pq_mod()
    d0 = np.datetime64(start_ns, "ns").astype("datetime64[M]")
    d1 = np.datetime64(end_ns, "ns").astype("datetime64[M]")
    tss, bids, asks = [], [], []
    for ym in np.arange(d0, d1 + np.timedelta64(1, "M"), dtype="datetime64[M]"):
        yy, mm = int(str(ym)[:4]), int(str(ym)[5:7])
        if yy < 2010 or yy > 2018:
            raise ForbiddenRangeError(f"forbidden partition year={yy}")
        rel = str(partition_path(yy, mm))
        tbl = pq.read_table(rel, columns=["timestamp_utc", "bid", "ask"])
        ts = tbl.column("timestamp_utc").to_numpy().astype("datetime64[ns]").astype("int64")
        bid = tbl.column("bid").to_numpy().astype(np.float64)
        ask = tbl.column("ask").to_numpy().astype(np.float64)
        bad = (~np.isfinite(bid)) | (~np.isfinite(ask)) | (bid <= 0) | (ask <= 0)
        if bad.any():
            keep = ~bad
            ts, bid, ask = ts[keep], bid[keep], ask[keep]
        order = np.argsort(ts, kind="stable")
        ts, bid, ask = ts[order], bid[order], ask[order]
        i0 = int(np.searchsorted(ts, start_ns, side="left"))
        i1 = int(np.searchsorted(ts, end_ns, side="right"))
        if i1 > i0:
            tss.append(ts[i0:i1]); bids.append(bid[i0:i1]); asks.append(ask[i0:i1])
    if not tss:
        e = np.empty(0, dtype=np.int64)
        return e, np.empty(0), np.empty(0)
    if len(tss) == 1:
        return tss[0], bids[0], asks[0]
    return (np.concatenate(tss), np.concatenate(bids), np.concatenate(asks))


# ---------------------------------------------------------------------------
# Fixed-horizon quote extraction for controls D/E/F
# ---------------------------------------------------------------------------
ENTRY_DELAY_NS = 5 * SEC
FILL_BOUND_NS = 30 * SEC
HOLD_NS = 3600 * SEC
EXIT_REF_NS = (5 + 3600) * SEC          # decision + 65 min
EXIT_BOUND_NS = 60 * SEC


def extract_day_quotes(ts, bid, ask, dec_ns):
    """Fixed-horizon fill at first tick >= dec+5s (<= +30s), exit at first
    tick >= dec+65min (within +60s). Returns dict or None if ineligible."""
    ref = dec_ns + ENTRY_DELAY_NS
    i_e = int(np.searchsorted(ts, ref, side="left"))
    if i_e >= len(ts) or ts[i_e] > ref + FILL_BOUND_NS:
        return None
    refx = dec_ns + EXIT_REF_NS
    i_x = int(np.searchsorted(ts, refx, side="left"))
    if i_x >= len(ts) or ts[i_x] >= refx + EXIT_BOUND_NS:
        return None
    return dict(entry_ts=int(ts[i_e]), ask_e=float(ask[i_e]), bid_e=float(bid[i_e]),
                exit_ts=int(ts[i_x]), ask_x=float(ask[i_x]), bid_x=float(bid[i_x]))


def day_eligibility_and_quotes(days, dec_hour=10, dec_minute=0):
    """Extract quotes for all days; one full-month load per month. Returns
    (eligible_days, quotes list). Drops are direction-independent."""
    out_days, out_q = [], []
    cur_month = None
    ts = bid = ask = None
    for d in days:
        key = (d.year, d.month)
        if key != cur_month:
            m0 = int(np.datetime64(f"{d.year:04d}-{d.month:02d}", "M")
                     .astype("datetime64[ns]").astype(np.int64))
            m1 = int((np.datetime64(f"{d.year:04d}-{d.month:02d}", "M")
                      + np.timedelta64(1, "M")).astype("datetime64[ns]").astype(np.int64)) - 1
            ts, bid, ask = load_range(m0, m1)
            cur_month = key
        dec = london_ns(d, dec_hour, dec_minute)
        q = extract_day_quotes(ts, bid, ask, dec)
        if q is not None:
            out_days.append(d)
            out_q.append(q)
    return out_days, out_q


# ---------------------------------------------------------------------------
# Synthetic stream builder (spec section 3) — deterministic seed 42
# ---------------------------------------------------------------------------
SYN_CADENCE_S = 5
SYN_HOLD_S = 3900                    # decision -> exit (65 min)
SYN_WINDOW_TICKS = SYN_HOLD_S // SYN_CADENCE_S + 1     # 781
SYN_SPREAD_PIPS = 0.5
SYN_SLIP_PIPS = 0.15                 # per side, deterministic
SYN_R_PIPS = 10.0
SYN_ENTRY_IDX = 1                    # tick at decision+5s
SYN_EXIT_IDX = SYN_WINDOW_TICKS - 1  # tick at decision+3900s


def build_synthetic_stream(n_trades: int, p_win: float, seed: int = 42):
    """Synthetic BID/ASK stream per frozen spec section 3. Mid constant at m0
    through the entry tick, then linear m0 -> m1 (anchored at the entry tick),
    zero at the exit tick; seeded iid wiggle (<= ~0.5 pip) with a triangular
    envelope that is 0 at entry and exit indices. Winners: mid moves +10 pips
    in the trade direction; losers: -10 pips. Returns (ts, bid, ask, meta)."""
    rng = np.random.default_rng(seed)
    n = SYN_WINDOW_TICKS
    ts_w = (np.arange(n, dtype=np.int64) * SYN_CADENCE_S * SEC)
    tss, bids, asks, meta = [], [], [], []
    mid0 = 1.10000
    for i in range(n_trades):
        direction = 1 if int(rng.integers(0, 2)) == 1 else -1
        winner = bool(rng.random() < p_win)
        disp = (SYN_R_PIPS if winner else -SYN_R_PIPS) * direction * PIP  # signed price delta
        wig_raw = rng.standard_normal(n)
        # triangular envelope: 0 at idx1 (entry) and at exit idx, peak 1 mid-window
        k = np.arange(n, dtype=np.float64)
        up = k / SYN_ENTRY_IDX                      # 0 at idx1
        down = (n - 1 - k) / (n - 1 - (n // 2))     # 0 at exit idx
        env = np.clip(np.minimum(up, down), 0.0, 1.0)
        wig = wig_raw * 0.2 * PIP * env
        k0 = i * SYN_HOLD_S * SEC
        base = np.empty(n, dtype=np.float64)
        base[:SYN_ENTRY_IDX + 1] = mid0
        frac = (k[SYN_ENTRY_IDX:] - SYN_ENTRY_IDX) / (SYN_EXIT_IDX - SYN_ENTRY_IDX)
        base[SYN_ENTRY_IDX:] = mid0 + disp * frac
        mid = base + wig
        mid[SYN_ENTRY_IDX] = mid0                   # exact entry mid
        mid[SYN_EXIT_IDX] = mid0 + disp             # exact exit mid
        half = SYN_SPREAD_PIPS * PIP / 2.0
        tss.append(ts_w + k0)
        bids.append(mid - half)
        asks.append(mid + half)
        meta.append(dict(trade=i, T=k0, direction=direction, winner=winner,
                         m0=mid0, m1=mid0 + disp))
        mid0 = float(mid[SYN_EXIT_IDX])
    return (np.concatenate(tss), np.concatenate(bids), np.concatenate(asks), meta)


def run_synthetic_trade(ts, bid, ask, meta_i, slip_pips=SYN_SLIP_PIPS):
    """One synthetic trade through the NORMAL pipeline: PO3.execute() on the
    trade's window slice (far stop -> forced TIME exit), then the frozen
    deterministic per-side slippage wrapper. Returns dict with effective
    prices, net pips, and R in the frozen unit (10 pips)."""
    T = meta_i["T"]
    i0 = meta_i["trade"] * SYN_WINDOW_TICKS
    i1 = i0 + SYN_WINDOW_TICKS
    d = meta_i["direction"]
    m0 = meta_i["m0"]
    stop = m0 - 200 * PIP if d > 0 else m0 + 200 * PIP   # untouchable by design
    ex = PO3.execute(ts[i0:i1], bid[i0:i1], ask[i0:i1], d, stop,
                     T, ENTRY_DELAY_NS, T + SYN_HOLD_S * SEC)
    if ex.status != "TRADE":
        return dict(status=ex.status)
    slip = slip_pips * PIP
    entry_eff = ex.entry_px + slip if d > 0 else ex.entry_px - slip
    exit_eff = ex.exit_px - slip if d > 0 else ex.exit_px + slip
    net_pips = (exit_eff - entry_eff) * d / PIP
    return dict(status="TRADE", entry_ts=ex.entry_ts, entry_px=entry_eff,
                exit_ts=ex.exit_ts, exit_px=exit_eff, net_pips=net_pips,
                r_mult=net_pips / SYN_R_PIPS, exit_type=ex.exit_type)


# ---------------------------------------------------------------------------
# Independent metric implementations (control H) — written from the frozen
# documented conventions, NOT by copying PO3 code paths.
# ---------------------------------------------------------------------------
def m_mean(v): return float(np.sum(v)) / len(v)


def m_median(v):
    s = sorted(float(x) for x in v)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def m_total(v): return float(np.sum(v))


def m_pf(v, cap=999.0):
    w = sum(x for x in v if x > 0)
    l = -sum(x for x in v if x < 0)
    if l == 0:
        return cap if w > 0 else 0.0
    return w / l


def m_win_rate(v): return sum(1 for x in v if x > 0) / len(v)


def m_max_dd(v):
    eq = 0.0
    peak = 0.0
    dd = 0.0
    for x in v:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return dd


def m_remove_best_1pct(v):
    s = sorted(float(x) for x in v)
    k = max(1, int(np.ceil(0.01 * len(s))))
    return float(np.sum(s[:len(s) - k]) / (len(s) - k))


def m_positive_years(entry_years, v):
    seen = {}
    for y, x in zip(entry_years, v):
        seen.setdefault(y, 0.0)
        seen[y] += x
    elig = sorted(seen)
    return sum(1 for y in elig if seen[y] > 0), len(elig)


def m_bootstrap_ci(v, n_resamples=2000, seed=42):
    v = np.asarray(v, dtype=np.float64)
    n = len(v)
    rng = np.random.default_rng(seed)
    means = np.empty(n_resamples)
    for b in range(n_resamples):           # deliberately plain-loop independent impl
        idx = rng.integers(0, n, size=n)
        means[b] = v[idx].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))
