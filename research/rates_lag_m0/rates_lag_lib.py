"""RATES-LAG-M0 core library: causal rate signals + tick-accurate EURUSD execution.

Pure functions only — no network, no filesystem access. All timestamps are int64
nanoseconds UTC. Implements exactly the frozen spec (RATES_LAG_M0_FROZEN_SPEC.md).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np

PIP = 1e-4  # EURUSD pip

# Frozen decision horizons (seconds).
HORIZONS_S = (10, 30, 60)
# Execution delays (seconds): baseline 1.0, slow stress 5.0.
DELAY_BASELINE_S = 1.0
DELAY_SLOW_S = 5.0
# Fill bound: executable quote must exist within this many seconds after the
# decision+delay reference time, else NO_FILL.
FILL_BOUND_S = 10.0
# Frozen exit horizon after ACTUAL entry.
EXIT_S = 120.0
# Exit search extension (never expected to trigger intraday).
EXIT_BOUND_S = 60.0
# Diagnostic MTM marks after entry.
MARK_S = (30.0, 60.0, 300.0)

# Discovery window: 2010-06-07 inclusive -> 2019-01-01 exclusive. 2019+ FORBIDDEN.
DISCOVERY_START_NS = 1275868800_000000000  # 2010-06-07T00:00:00Z
DISCOVERY_END_NS = 1546300800_000000000    # 2019-01-01T00:00:00Z

# Cost stress (pips per side).
SLIP_050 = 0.5
SLIP_100 = 1.0

# Bootstrap.
BOOTSTRAP_N = 2000
BOOTSTRAP_SEED = 42

# Profit factor sentinel when there are no losing trades.
PF_CAP = 999.0


class OutOfWindowError(RuntimeError):
    """Raised when any requested data range escapes the Discovery window."""


def assert_discovery_range(start_ns: int, end_ns: int) -> None:
    """Hard guard: requested [start, end) must lie inside the Discovery window.

    Protected OOS and everything 2019+ is forbidden.
    """
    if start_ns < DISCOVERY_START_NS or end_ns > DISCOVERY_END_NS:
        raise OutOfWindowError(
            f"range [{start_ns}, {end_ns}) escapes Discovery "
            f"[{DISCOVERY_START_NS}, {DISCOVERY_END_NS})")


# ---------------------------------------------------------------------------
# Event universe (from the RATES-EVENT-HIRES-M1 manifest)
# ---------------------------------------------------------------------------

EXCLUDED_STATUSES = {"EXPECTED_MARKET_CLOSED", "CONFIRMED_DATA_GAP",
                     "ROLL_WINDOW_INVALID", "zero_records"}


@dataclass(frozen=True)
class LagEvent:
    event_id: str
    family: str
    t0_ns: int
    zf_raw: str
    zn_raw: str
    zf_parquet: str
    zn_parquet: str


def load_valid_events(manifest_path: str) -> list[LagEvent]:
    """Events whose ZF AND ZN entries are both 'ok', inside the Discovery window."""
    m = json.loads(open(manifest_path).read())
    by_event: dict[str, dict] = {}
    for e in m["entries"].values():
        if e["family"] not in ("NFP", "CPI"):
            continue
        rec = by_event.setdefault(e["event_id"], {})
        rec[e["symbol"]] = e
    events = []
    for event_id, rec in sorted(by_event.items()):
        if "ZF" not in rec or "ZN" not in rec:
            continue
        if any(rec[s]["status"] != "ok" for s in ("ZF", "ZN")):
            continue
        t0 = datetime.fromisoformat(rec["ZF"]["t0"].replace("Z", "+00:00"))
        t0_ns = int(t0.timestamp()) * 1_000_000_000
        if not (DISCOVERY_START_NS <= t0_ns < DISCOVERY_END_NS):
            continue
        events.append(LagEvent(
            event_id=event_id, family=rec["ZF"]["family"], t0_ns=t0_ns,
            zf_raw=rec["ZF"]["raw_symbol"], zn_raw=rec["ZN"]["raw_symbol"],
            zf_parquet=rec["ZF"].get("parquet") or "", zn_parquet=rec["ZN"].get("parquet") or ""))
    events.sort(key=lambda e: e.t0_ns)
    return events


def load_tick_sizes(path: str) -> dict[str, float]:
    """raw_symbol -> min_price_increment (from Databento definitions)."""
    ticks = json.loads(open(path).read())
    return {raw: float(v["min_price_increment"]) for raw, v in ticks.items()}


# ---------------------------------------------------------------------------
# Treasury book: causal mid selection on ts_recv
# ---------------------------------------------------------------------------

@dataclass
class RateBook:
    """Valid BBO mid series for one event/symbol, sorted by ts_recv.

    Contains only records with finite bid>0 and ask>0 (valid book).
    """

    ts: np.ndarray  # int64 ns
    mid: np.ndarray  # float64

    @classmethod
    def from_records(cls, ts_recv: np.ndarray, bid: np.ndarray, ask: np.ndarray,
                     window_start_ns: int) -> "RateBook":
        """Keep valid-book records at/after window_start (M1 boundary hygiene)."""
        ts_recv = np.asarray(ts_recv, dtype=np.int64)
        bid = np.asarray(bid, dtype=np.float64)
        ask = np.asarray(ask, dtype=np.float64)
        ok = np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > 0) \
            & (ts_recv >= window_start_ns)
        ts = ts_recv[ok]
        order = np.argsort(ts, kind="stable")
        return cls(ts=ts[order], mid=((bid[ok] + ask[ok]) / 2.0)[order])

    def pre_mid(self, t0_ns: int) -> float | None:
        """Last valid RATE_MID strictly BEFORE T0 (causal, ts < T0)."""
        i = np.searchsorted(self.ts, t0_ns, side="left")
        if i == 0:
            return None
        return float(self.mid[i - 1])

    def horizon_mid(self, t0_ns: int, horizon_s: float) -> float | None:
        """LAST valid RATE_MID with T0 <= ts_recv <= T0 + H; None if none exists.

        Causal per horizon: records beyond T0+H are never inspected.
        """
        hi = t0_ns + int(round(horizon_s * 1e9))
        lo = np.searchsorted(self.ts, t0_ns, side="left")
        hi_i = np.searchsorted(self.ts, hi, side="right")
        if lo >= hi_i:
            return None  # no observation in [T0, T0+H]
        return float(self.mid[hi_i - 1])


def rate_signal(zf_pre: float | None, zf_h: float | None,
                zn_pre: float | None, zn_h: float | None,
                zf_tick: float, zn_tick: float) -> int:
    """+1 (futures up -> EURUSD LONG), -1 (futures down -> SHORT), 0 = no signal.

    Requires same non-zero sign AND |move| >= 1 tick on BOTH contracts.
    """
    if zf_pre is None or zf_h is None or zn_pre is None or zn_h is None:
        return 0
    zf_move = zf_h - zf_pre
    zn_move = zn_h - zn_pre
    if zf_move == 0.0 or zn_move == 0.0:
        return 0
    if (zf_move > 0) != (zn_move > 0):
        return 0
    if abs(zf_move) < zf_tick or abs(zn_move) < zn_tick:
        return 0
    return 1 if zf_move > 0 else -1


def data_derived_tick(mids: np.ndarray) -> float:
    """Diagnostic: smallest positive absolute mid change in a series."""
    m = np.sort(np.asarray(mids, dtype=np.float64))
    d = np.diff(m)
    d = d[d > 0]
    return float(d.min()) if d.size else float("nan")


# ---------------------------------------------------------------------------
# EURUSD tick execution (side-accurate, real historical spread)
# ---------------------------------------------------------------------------

@dataclass
class FxBook:
    """Sorted EURUSD tick arrays for one event window."""

    ts: np.ndarray    # int64 ns ascending
    bid: np.ndarray   # float64
    ask: np.ndarray   # float64

    @classmethod
    def from_records(cls, ts, bid, ask) -> "FxBook":
        ts = np.asarray(ts, dtype=np.int64)
        bid = np.asarray(bid, dtype=np.float64)
        ask = np.asarray(ask, dtype=np.float64)
        order = np.argsort(ts, kind="stable")
        return cls(ts=ts[order], bid=bid[order], ask=ask[order])

    def _first_at(self, ref_ns: int) -> int:
        return int(np.searchsorted(self.ts, ref_ns, side="left"))

    def quote(self, ref_ns: int, side: str) -> tuple[int, float] | None:
        """First tick at/after ref_ns; returns (ts, price) on the executed side.

        side='ASK' -> ask price (LONG entry / SHORT exit),
        side='BID' -> bid price (SHORT entry / LONG exit).
        """
        if side not in ("BID", "ASK"):
            raise ValueError(side)
        i = self._first_at(ref_ns)
        if i >= len(self.ts):
            return None
        return int(self.ts[i]), float(self.ask[i] if side == "ASK" else self.bid[i])

    def entry(self, decision_ns: int, delay_s: float, direction: int,
              fill_bound_s: float = FILL_BOUND_S) -> tuple[int, float] | None:
        """First executable quote at/after decision+delay within the fill bound.

        direction +1 (LONG): first ASK; -1 (SHORT): first BID. None => NO_FILL.
        """
        ref = decision_ns + int(round(delay_s * 1e9))
        bound = ref + int(round(fill_bound_s * 1e9))
        side = "ASK" if direction > 0 else "BID"
        q = self.quote(ref, side)
        if q is None or q[0] > bound:
            return None
        return q

    def exit(self, entry_ns: int, direction: int,
             exit_s: float = EXIT_S, bound_s: float = EXIT_BOUND_S) -> tuple[int, float] | None:
        """First BID (LONG) / ASK (SHORT) at/after entry+exit_s, within bound."""
        ref = entry_ns + int(round(exit_s * 1e9))
        bound = ref + int(round(bound_s * 1e9))
        side = "BID" if direction > 0 else "ASK"
        q = self.quote(ref, side)
        if q is None or q[0] > bound:
            return None
        return q

    def mark(self, entry_ns: int, direction: int, mark_s: float) -> tuple[int, float] | None:
        """Diagnostic MTM: executable-side quote at/after entry+mark_s."""
        ref = entry_ns + int(round(mark_s * 1e9))
        side = "BID" if direction > 0 else "ASK"
        return self.quote(ref, side)


def net_pips(entry_px: float, exit_px: float, direction: int) -> float:
    """Net pips including the real historical spread (already in side prices)."""
    return (exit_px - entry_px) / PIP * direction


def stressed(net: float, slip_per_side: float) -> float:
    """Adverse slippage applied per side (entry + exit)."""
    return net - 2.0 * slip_per_side


# ---------------------------------------------------------------------------
# Metrics (frozen definitions)
# ---------------------------------------------------------------------------

def remove_best_1pct_mean(nets: np.ndarray) -> float:
    """Mean after removing k = max(1, ceil(0.01*N)) best trades."""
    nets = np.sort(np.asarray(nets, dtype=np.float64))
    n = len(nets)
    if n == 0:
        return float("nan")
    k = max(1, int(math.ceil(0.01 * n)))
    return float(nets[: n - k].mean())


def bootstrap_ci95_mean(nets: np.ndarray, n_resamples: int = BOOTSTRAP_N,
                        seed: int = BOOTSTRAP_SEED) -> tuple[float, float]:
    """Percentile bootstrap CI of the mean; frozen 2000 resamples, seed 42."""
    nets = np.asarray(nets, dtype=np.float64)
    n = len(nets)
    if n == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_resamples, n))
    means = nets[idx].mean(axis=1)
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def profit_factor(nets: np.ndarray) -> float:
    wins = nets[nets > 0].sum()
    losses = -nets[nets < 0].sum()
    if losses == 0:
        return PF_CAP
    return float(wins / losses)


def year_bucket_stats(entry_ts_ns: np.ndarray, nets: np.ndarray) -> tuple[int, int]:
    """(POSITIVE_YEARS, YEARS_ELIGIBLE) by UTC calendar year of entry."""
    yrs = (entry_ts_ns.astype("datetime64[ns]").astype("datetime64[Y]").astype(np.int64)
           + 1970)
    eligible = set(int(v) for v in np.unique(yrs))
    positive = set()
    for yr in eligible:
        m = yrs == yr
        if float(nets[m].sum()) > 0:
            positive.add(yr)
    return len(positive), len(eligible)


def metrics(trades: list[dict], family_counts: dict | None = None) -> dict:
    """Frozen section-12 metrics over trade dicts with keys:
    net_pips, latency5_net, stress050_net, stress100_net, realistic_net,
    entry_ts_ns, family, mtm30, mtm60, mtm300 (latter three diagnostic pips,
    NaN when unavailable).
    """
    out: dict = {}
    n = len(trades)
    out["N_TRADES"] = n
    if n == 0:
        empty = dict(N_TRADES=0, NET_MEAN_PIPS=float("nan"), MEDIAN_NET_PIPS=float("nan"),
                     TOTAL_NET_PIPS=0.0, WIN_RATE=float("nan"), AVG_WIN=float("nan"),
                     AVG_LOSS=float("nan"), PROFIT_FACTOR=0.0, POSITIVE_YEARS=0,
                     YEARS_ELIGIBLE=0, REMOVE_BEST_1_PERCENT_NET_MEAN=float("nan"),
                     LATENCY_5S_MEAN=float("nan"), LATENCY_5S_NFILLS=0,
                     SLIPPAGE_050_MEAN=float("nan"), SLIPPAGE_100_MEAN=float("nan"),
                     REALISTIC_STRESS_MEAN=float("nan"), REALISTIC_STRESS_NFILLS=0,
                     BOOT_LO=float("nan"), BOOT_HI=float("nan"),
                     MTM30_MEAN=float("nan"), MTM60_MEAN=float("nan"), MTM300_MEAN=float("nan"))
        empty.update(family_counts or {})
        return empty
    nets = np.array([t["net_pips"] for t in trades], dtype=np.float64)
    l5 = np.array([t["latency5_net"] for t in trades], dtype=np.float64)
    s05 = np.array([t["stress050_net"] for t in trades], dtype=np.float64)
    s10 = np.array([t["stress100_net"] for t in trades], dtype=np.float64)
    rs = np.array([t["realistic_net"] for t in trades], dtype=np.float64)
    ets = np.array([t["entry_ts_ns"] for t in trades], dtype=np.int64)
    wins = nets[nets > 0]
    losses = nets[nets < 0]
    pos_y, elig_y = year_bucket_stats(ets, nets)
    lo, hi = bootstrap_ci95_mean(nets)
    mtm30 = np.array([t["mtm30"] for t in trades], dtype=np.float64)
    mtm60 = np.array([t["mtm60"] for t in trades], dtype=np.float64)
    mtm300 = np.array([t["mtm300"] for t in trades], dtype=np.float64)

    def nanmean(a: np.ndarray) -> float:
        return float(np.nanmean(a)) if np.isfinite(a).any() else float("nan")

    out.update(
        NET_MEAN_PIPS=float(nets.mean()),
        MEDIAN_NET_PIPS=float(np.median(nets)),
        TOTAL_NET_PIPS=float(nets.sum()),
        WIN_RATE=float(len(wins) / n),
        AVG_WIN=float(wins.mean()) if len(wins) else 0.0,
        AVG_LOSS=float(losses.mean()) if len(losses) else 0.0,
        PROFIT_FACTOR=profit_factor(nets),
        POSITIVE_YEARS=pos_y,
        YEARS_ELIGIBLE=elig_y,
        REMOVE_BEST_1_PERCENT_NET_MEAN=remove_best_1pct_mean(nets),
        LATENCY_5S_MEAN=nanmean(l5),
        LATENCY_5S_NFILLS=int((~np.isfinite(l5)).sum()),
        SLIPPAGE_050_MEAN=float(s05.mean()),
        SLIPPAGE_100_MEAN=float(s10.mean()),
        REALISTIC_STRESS_MEAN=nanmean(rs),
        REALISTIC_STRESS_NFILLS=int((~np.isfinite(rs)).sum()),
        BOOT_LO=lo,
        BOOT_HI=hi,
        MTM30_MEAN=nanmean(mtm30),
        MTM60_MEAN=nanmean(mtm60),
        MTM300_MEAN=nanmean(mtm300),
    )

    def fam(f):
        sub = [t for t in trades if t["family"] == f]
        if not sub:
            return 0, 0.0, 0.0
        fn = np.array([t["net_pips"] for t in sub])
        return len(sub), float(fn.mean()), profit_factor(fn)

    nfp_n, nfp_mean, nfp_pf = fam("NFP")
    cpi_n, cpi_mean, cpi_pf = fam("CPI")
    out.update(NFP_N=nfp_n, NFP_MEAN=nfp_mean, NFP_PF=nfp_pf,
               CPI_N=cpi_n, CPI_MEAN=cpi_mean, CPI_PF=cpi_pf)
    return out


def gate(m: dict) -> bool:
    """Frozen section-14 economic gate. PROFIT_FACTOR sentinel counts as >= 1.20."""
    if m["N_TRADES"] < 50:
        return False
    checks = [
        m["NET_MEAN_PIPS"] >= 2.0,
        m["PROFIT_FACTOR"] >= 1.20,
        m["TOTAL_NET_PIPS"] > 0,
        m["YEARS_ELIGIBLE"] > 0 and (m["POSITIVE_YEARS"] / m["YEARS_ELIGIBLE"]) >= 0.67,
        m["REMOVE_BEST_1_PERCENT_NET_MEAN"] > 0,
        m["LATENCY_5S_MEAN"] > 0,
        m["REALISTIC_STRESS_MEAN"] > 0,
        m["NFP_MEAN"] > 0,
        m["CPI_MEAN"] > 0,
    ]
    return all(checks)


def stability_counts(signals: dict[str, dict[str, int]]) -> dict:
    """Diagnostic section-13 stats.

    signals: horizon -> event_id -> direction (+1/-1). Same-direction pct over
    events where BOTH horizons have a signal.
    """
    def pair(a: str, b: str) -> tuple[int, int, float]:
        common = sorted(set(signals[a]) & set(signals[b]))
        same = sum(1 for e in common if signals[a][e] == signals[b][e])
        pct = (100.0 * same / len(common)) if common else float("nan")
        return len(common), same, pct

    n1030, s1030, p1030 = pair("H10", "H30")
    n3060, s3060, p3060 = pair("H30", "H60")
    n1060, s1060, p1060 = pair("H10", "H60")
    return {
        "H10_SIGNAL_COUNT": len(signals["H10"]),
        "H30_SIGNAL_COUNT": len(signals["H30"]),
        "H60_SIGNAL_COUNT": len(signals["H60"]),
        "H10_TO_H30_N": n1030, "H10_TO_H30_SAME": s1030,
        "H10_TO_H30_SAME_DIRECTION_PCT": p1030,
        "H30_TO_H60_N": n3060, "H30_TO_H60_SAME": s3060,
        "H30_TO_H60_SAME_DIRECTION_PCT": p3060,
        "H10_TO_H60_N": n1060, "H10_TO_H60_SAME": s1060,
        "H10_TO_H60_SAME_DIRECTION_PCT": p1060,
    }
