#!/usr/bin/env python3
"""MACRO-TICK-M1 library: tick-accurate event-driven EURUSD strategy
discovery around NFP/CPI releases, per `MACRO_TICK_M1_FROZEN_SPEC.md`
(commit b701d95, frozen BEFORE any outcome computation).

Exactly 3 frozen strategies:
  A  MACRO_A_30S_CONTINUATION
  B  MACRO_B_FAILED_SHOCK_REVERSAL
  C  MACRO_C_5M_DIGESTION_BREAKOUT

Reuses the validated TICK/MTF-M1 pipeline primitives (month-partition
TickStore with the 2010..2018 hard guard, frozen weekend/gap rule, tick
accurate BID/ASK trade resolution, bootstrap/remove-best metrics) by
importing `mtf_lib` directly. Units: int64 ns UTC timestamps, float64
prices, 1 pip = 1e-4.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_MTF_DIR = os.path.normpath(os.path.join(_HERE, "..", "mtf_m1_tick_execution"))
if _MTF_DIR not in sys.path:
    sys.path.insert(0, _MTF_DIR)
import mtf_lib as MTF  # noqa: E402  (validated pipeline primitives)

NS = MTF.NS
PIP = MTF.PIP
DISCOVERY_START_NS = MTF.DISCOVERY_START_NS
DISCOVERY_END_NS = MTF.DISCOVERY_END_NS          # 2019-01-01 hard cut
YEARS = MTF.YEARS                                 # 2010..2018
LATENCY_NS = MTF.LATENCY_NS                       # frozen 250 ms
NO_FILL_WINDOW_NS = MTF.NO_FILL_WINDOW_NS         # 1 h entry search bound

# ---- frozen event geometry (spec §2-§9) --------------------------------
BASELINE_PRE_NS = 60 * 60 * NS                    # T0 - 60 min
BASELINE_EXCLUDE_NS = 5 * 60 * NS                 # last 5 min excluded
BUCKET_NS = 30 * NS                               # 30 s baseline buckets
SHOCK_AT_NS = 30 * NS                             # P30 at T0 + 30 s
P30_SEARCH_NS = 90 * NS                           # P30 search bound
QUAL_SCORE = 2.0                                  # frozen shock-score gate
QUAL_PIPS = 1.0                                   # frozen minimum |shock|
SPREAD_MULT = 3.0                                 # frozen spread safety
MIN_RISK_PIPS = 1.0                               # frozen minimum risk

A_DECISION_NS = 30 * NS
A_R_MULT = 1.5
A_TIME_NS = 60 * 60 * NS

B_OBS_START_NS = 30 * NS
B_OBS_END_NS = 5 * 60 * NS
B_RETRACE = 0.50
B_TIME_NS = 30 * 60 * NS

C_RANGE_END_NS = 5 * 60 * NS
C_SEARCH_END_NS = 35 * 60 * NS
C_R_MULT = 1.5
C_TIME_NS = 120 * 60 * NS

# per-event tick slice (spec §22): covers baseline (60 m back), the C
# breakout search to T0+35 m and the longest time exit (120 m after an
# entry at T0+35 m) with margin.
EVENT_WIN_PRE_NS = 62 * 60 * NS
EVENT_WIN_POST_NS = 200 * 60 * NS

VALID_EXIT_REASONS = ("STOP", "TARGET", "TIME")
EXIT_COUNT_KEYS = ("STOP", "TARGET", "TIME", "DATA_GAP_INVALID",
                   "SPREAD_TOO_WIDE", "NO_FILL")

STRATEGY_IDS = {"A": "MACRO_A_30S_CONTINUATION",
                "B": "MACRO_B_FAILED_SHOCK_REVERSAL",
                "C": "MACRO_C_5M_DIGESTION_BREAKOUT"}


# ------------------------------------------------------------- events

def load_events(csv_path):
    """NFP/CPI events from the validated M0 database, Discovery window only.
    FOMC rows are dropped first (spec §0/§2). 2019+ rows are dropped by the
    frozen hard cut and never touched further."""
    df = pd.read_csv(csv_path)
    df = df[df["family"].isin(["NFP", "CPI"])]
    out = []
    for _, r in df.iterrows():
        t0 = int(pd.Timestamp(r["release_timestamp_utc"]).value)
        if not (DISCOVERY_START_NS <= t0 < DISCOVERY_END_NS):
            continue
        out.append({
            "event_id": r["event_id"],
            "family": r["family"],
            "t0_ns": t0,
            "alignment": r["tick_alignment_status"],
            "post_lag_ms": (float(r["post_tick_lag_ms"])
                            if pd.notna(r["post_tick_lag_ms"]) else np.inf),
        })
    out.sort(key=lambda e: e["t0_ns"])
    return out


# ------------------------------------------------------------- windows

def valid_mask(bid, ask):
    """Frozen valid-tick rule: finite, bid>0, ask>0, ask>=bid."""
    return (np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask > 0)
            & (ask >= bid))


def gaps_in_window(ts):
    """Frozen gap rule reused from the validated pipeline: inter-tick delta
    whose non-weekend portion exceeds 1 h. Returns [(g1, g2), ...]."""
    out = []
    if len(ts) < 2:
        return out
    d = np.diff(ts)
    for i in np.flatnonzero(d > MTF.GAP_NS):
        t1, t2 = int(ts[i]), int(ts[i + 1])
        if MTF.is_data_gap(t1, t2):
            out.append((t1, t2))
    return out


# ------------------------------------------------------------ baseline

def baseline_stats(ts, mid, spread_pips, t0):
    """Frozen baseline over [T0-60m, T0-5m): non-overlapping 30 s MID
    changes anchored at T0-60m (bucket skipped iff no tick inside), Q95 of
    |changes| in pips (np.percentile, linear), and median spread (np.median).
    Returns (q95_pips, median_spread_pips, n_buckets)."""
    lo = t0 - BASELINE_PRE_NS
    hi = t0 - BASELINE_EXCLUDE_NS
    anchors = lo + BUCKET_NS * np.arange(111, dtype=np.int64)
    i_lo = int(np.searchsorted(ts, lo, side="left"))
    i_hi = int(np.searchsorted(ts, hi, side="left"))
    if i_hi <= i_lo:
        return float("nan"), float("nan"), 0
    starts = np.searchsorted(ts, anchors[:-1], side="left")
    ends = np.searchsorted(ts, anchors[1:], side="left") - 1
    ok = ends >= starts
    changes = mid[ends[ok]] - mid[starts[ok]]
    n = int(ok.sum())
    if n == 0:
        return float("nan"), float("nan"), 0
    q95 = float(np.percentile(np.abs(changes) / PIP, 95))
    med_spread = float(np.median(spread_pips[i_lo:i_hi]))
    return q95, med_spread, n


def shock_stats(ts, mid, t0):
    """Frozen P0 (last valid tick strictly before T0) and P30 (first valid
    tick >= T0+30 s, searched to T0+90 s). Returns dict with p0/p30/shock."""
    i0 = int(np.searchsorted(ts, t0, side="left")) - 1
    if i0 < 0:
        return {"status": "PRE_TICK_MISSING"}
    p0 = float(mid[i0])
    i30 = int(np.searchsorted(ts, t0 + SHOCK_AT_NS, side="left"))
    if i30 >= len(ts) or ts[i30] > t0 + P30_SEARCH_NS:
        return {"status": "POST_TICK_MISSING_P30"}
    p30 = float(mid[i30])
    return {"status": "OK", "p0": p0, "p0_ts": int(ts[i0]),
            "p30": p30, "p30_ts": int(ts[i30]),
            "shock_pips": (p30 - p0) / PIP}


def qualifying(shock_pips, noise_scale):
    """Frozen: SHOCK_SCORE = |shock|/NOISE_SCALE >= 2.0 AND |shock| >= 1 pip."""
    if not np.isfinite(noise_scale) or noise_scale <= 0:
        return False, float("inf")
    score = abs(shock_pips) / noise_scale
    return (score >= QUAL_SCORE and abs(shock_pips) >= QUAL_PIPS), score


# ----------------------------------------------------------- execution

def _entry_gap_blocked(gap_starts, decision_ns, fill_ts):
    """A data gap starting strictly between decision and the fill tick means
    the quote stream was not continuously observable -> no fill."""
    gi = int(np.searchsorted(gap_starts, decision_ns, side="right"))
    return gi < len(gap_starts) and gap_starts[gi] < fill_ts


def find_entry(ts, bid, ask, decision_ns, side, gap_starts):
    """Frozen entry: first valid tick >= decision+250ms (bound 1 h), filled
    at ASK for LONG / BID for SHORT. Returns (status, idx, fill_ts, price).
    Spread safety (§5) is applied by the caller at the returned tick."""
    i0 = int(np.searchsorted(ts, decision_ns + LATENCY_NS, side="left"))
    if i0 >= len(ts) or ts[i0] > decision_ns + NO_FILL_WINDOW_NS:
        return "NO_FILL", None, None, None
    fill_ts = int(ts[i0])
    if fill_ts >= DISCOVERY_END_NS:
        return "SKIPPED_HARD_END", None, None, None
    if _entry_gap_blocked(gap_starts, decision_ns, fill_ts):
        return "NO_FILL_GAP", None, None, None
    price = float(ask[i0] if side == 1 else bid[i0])
    return "FILLED", i0, fill_ts, price


def spread_too_wide(bid, ask, idx, median_spread_pips):
    """Frozen §5: CURRENT_SPREAD > 3 x baseline MEDIAN_SPREAD -> skip."""
    cur = (ask[idx] - bid[idx]) / PIP
    return cur > SPREAD_MULT * median_spread_pips


def resolve_trade(ts, bid, ask, side, entry_idx, stop, target, time_exit_ns,
                  gap_starts):
    """Thin wrapper over the validated MTF-M1 trade resolution: ticks
    strictly after the entry tick, first event wins STOP > TARGET > TIME,
    stop filled at the actual executable tick (overshoot), target capped,
    data gap (onset strictly before the resolved exit) -> DATA_GAP_INVALID."""
    entry_ts = int(ts[entry_idx])
    last_tick = (int(ts[-1]), float(bid[-1]), float(ask[-1]))
    return MTF.resolve_trade(ts, bid, ask, side, entry_idx, entry_ts,
                             float(stop), float(target), int(time_exit_ns),
                             np.asarray(gap_starts, dtype=np.int64),
                             last_tick)


# ----------------------------------------------------------- strategies

def strategy_a(ev, ts, bid, ask, mid, p0, shock_pips, med_spread,
               gaps, gap_starts):
    """MACRO_A_30S_CONTINUATION (frozen §7)."""
    side = 1 if shock_pips > 0 else -1
    st = {"status": None}
    status, idx, fill_ts, entry = find_entry(ts, bid, ask,
                                             ev["t0_ns"] + A_DECISION_NS,
                                             side, gap_starts)
    if status != "FILLED":
        st["status"] = status
        return None, st
    if spread_too_wide(bid, ask, idx, med_spread):
        st["status"] = "SPREAD_TOO_WIDE"
        return None, st
    stop = p0
    risk = entry - stop if side == 1 else stop - entry
    if (side == 1 and stop >= entry) or (side == -1 and stop <= entry):
        st["status"] = "NO_TRADE_INVALID_STOP"
        return None, st
    if risk / PIP < MIN_RISK_PIPS:
        st["status"] = "NO_TRADE_RISK_TOO_SMALL"
        return None, st
    target = entry + side * A_R_MULT * risk
    res = resolve_trade(ts, bid, ask, side, idx, stop, target,
                        fill_ts + A_TIME_NS, gap_starts)
    trade = _trade_record("A", ev, side, ev["t0_ns"] + A_DECISION_NS,
                          fill_ts, entry, stop, target, risk, res, ts, bid,
                          ask, idx)
    st["status"] = "TRADED"
    return trade, st


def strategy_b(ev, ts, bid, ask, mid, p0, shock_pips, med_spread,
               gaps, gap_starts):
    """MACRO_B_FAILED_SHOCK_REVERSAL (frozen §8)."""
    d_pips = shock_pips  # D = P30 - P0, in pips here
    t0 = ev["t0_ns"]
    level = p0 + B_RETRACE * (d_pips * PIP)
    up = d_pips > 0
    side = -1 if up else 1
    st = {"status": None}
    i_lo = int(np.searchsorted(ts, t0 + B_OBS_START_NS, side="left"))
    i_hi = int(np.searchsorted(ts, t0 + B_OBS_END_NS, side="right"))
    if i_hi <= i_lo:
        st["status"] = "NO_TRIGGER"
        return None, st
    seg = mid[i_lo:i_hi]
    hit = np.flatnonzero(seg <= level) if up else np.flatnonzero(seg >= level)
    if len(hit) == 0:
        st["status"] = "NO_TRIGGER"
        return None, st
    trig_idx = i_lo + int(hit[0])
    trig_ts = int(ts[trig_idx])
    # observation continuity: a data gap starting after T0+30 s and at or
    # before the trigger makes the setup unobservable (no invented path)
    for g1, _g2 in gaps:
        if t0 + B_OBS_START_NS < g1 <= trig_ts:
            st["status"] = "GAP_SETUP_INVALID"
            st["gap_ts"] = int(g1)
            return None, st
    status, idx, fill_ts, entry = find_entry(ts, bid, ask, trig_ts, side,
                                             gap_starts)
    if status != "FILLED":
        st["status"] = status
        return None, st
    if spread_too_wide(bid, ask, idx, med_spread):
        st["status"] = "SPREAD_TOO_WIDE"
        return None, st
    # stop = most extreme MID in [T0, trigger] (both inclusive)
    t0_idx = int(np.searchsorted(ts, t0, side="left"))
    seg2 = mid[t0_idx:trig_idx + 1]
    stop = float(seg2.max()) if up else float(seg2.min())
    target = p0
    crossed = (ask[idx] <= target) if side == -1 else (bid[idx] >= target)
    if crossed:
        st["status"] = "NO_TRADE_TARGET_CROSSED"
        return None, st
    risk = (stop - entry) if side == -1 else (entry - stop)
    if (side == -1 and stop <= entry) or (side == 1 and stop >= entry):
        st["status"] = "NO_TRADE_INVALID_STOP"
        return None, st
    if risk / PIP < MIN_RISK_PIPS:
        st["status"] = "NO_TRADE_RISK_TOO_SMALL"
        return None, st
    res = resolve_trade(ts, bid, ask, side, idx, stop, target,
                        fill_ts + B_TIME_NS, gap_starts)
    trade = _trade_record("B", ev, side, trig_ts, fill_ts, entry, stop,
                          target, risk, res, ts, bid, ask, idx,
                          trigger_ts=trig_ts)
    st["status"] = "TRADED"
    return trade, st


def strategy_c(ev, ts, bid, ask, mid, med_spread, gaps, gap_starts,
               shock_pips=None):
    """MACRO_C_5M_DIGESTION_BREAKOUT (frozen §9)."""
    t0 = ev["t0_ns"]
    st = {"status": None}
    i_r0 = int(np.searchsorted(ts, t0, side="left"))
    i_r1 = int(np.searchsorted(ts, t0 + C_RANGE_END_NS, side="left"))
    if i_r1 <= i_r0:
        st["status"] = "NO_RANGE_TICKS"
        return None, st
    seg_r = mid[i_r0:i_r1]
    news_high = float(seg_r.max())
    news_low = float(seg_r.min())
    news_mid = 0.5 * (news_high + news_low)
    i_b0 = i_r1
    i_b1 = int(np.searchsorted(ts, t0 + C_SEARCH_END_NS, side="right"))
    if i_b1 <= i_b0:
        st["status"] = "NO_BREAKOUT"
        return None, st
    seg_b = mid[i_b0:i_b1]
    up_hit = np.flatnonzero(seg_b > news_high)
    dn_hit = np.flatnonzero(seg_b < news_low)
    i_up = int(up_hit[0]) if len(up_hit) else None
    i_dn = int(dn_hit[0]) if len(dn_hit) else None
    if i_up is None and i_dn is None:
        st["status"] = "NO_BREAKOUT"
        return None, st
    if i_up is not None and (i_dn is None or i_up <= i_dn):
        off, side = i_up, 1
    else:
        off, side = i_dn, -1
    trig_idx = i_b0 + off
    trig_ts = int(ts[trig_idx])
    for g1, _g2 in gaps:
        if t0 + C_RANGE_END_NS < g1 <= trig_ts:
            st["status"] = "GAP_SETUP_INVALID"
            st["gap_ts"] = int(g1)
            return None, st
    status, idx, fill_ts, entry = find_entry(ts, bid, ask, trig_ts, side,
                                             gap_starts)
    if status != "FILLED":
        st["status"] = status
        return None, st
    if spread_too_wide(bid, ask, idx, med_spread):
        st["status"] = "SPREAD_TOO_WIDE"
        return None, st
    stop = news_mid
    risk = entry - stop if side == 1 else stop - entry
    if (side == 1 and stop >= entry) or (side == -1 and stop <= entry):
        st["status"] = "NO_TRADE_INVALID_STOP"
        return None, st
    if risk / PIP < MIN_RISK_PIPS:
        st["status"] = "NO_TRADE_RISK_TOO_SMALL"
        return None, st
    target = entry + side * C_R_MULT * risk
    res = resolve_trade(ts, bid, ask, side, idx, stop, target,
                        fill_ts + C_TIME_NS, gap_starts)
    trade = _trade_record("C", ev, side, trig_ts, fill_ts, entry, stop,
                          target, risk, res, ts, bid, ask, idx,
                          trigger_ts=trig_ts, news_high=news_high,
                          news_low=news_low, news_mid=news_mid)
    st["status"] = "TRADED"
    return trade, st


def _trade_record(kind, ev, side, decision_ts, fill_ts, entry, stop, target,
                  risk, res, ts, bid, ask, entry_idx, trigger_ts=None,
                  **extra):
    rec = {
        "strategy": kind,
        "strategy_id": STRATEGY_IDS[kind],
        "event_id": ev["event_id"],
        "family": ev["family"],
        "side": int(side),
        "t0_ns": int(ev["t0_ns"]),
        "decision_ns": int(decision_ts),
        "trigger_ns": int(trigger_ts) if trigger_ts is not None else None,
        "entry_ts": int(fill_ts),
        "entry": float(entry),
        "stop": float(stop),
        "target": float(target),
        "risk_pips": float(risk / PIP),
        "exit_ts": int(res["exit_ts"]) if np.isfinite(res.get("exit_ts", np.inf)) else None,
        "exit_reason": res["status"],
        "exit_price": (float(res["exit_price"])
                       if res.get("exit_price") is not None else None),
        "entry_bid": float(bid[entry_idx]),
        "entry_ask": float(ask[entry_idx]),
    }
    if res["status"] == "DATA_GAP_INVALID":
        rec["exit_ts"] = int(res["gap_ts"])          # gap onset tick
        rec["net_pips"] = None
        rec["gross_mid_pips"] = None
        rec["exit_price"] = None
    else:
        exit_px = float(res["exit_price"])
        rec["net_pips"] = ((exit_px - entry) if side == 1
                           else (entry - exit_px)) / PIP
        k = res.get("exit_idx")
        exit_mid = (float((bid[k] + ask[k]) / 2.0)
                    if k is not None and k < len(ts) else exit_px)
        entry_mid = float((bid[entry_idx] + ask[entry_idx]) / 2.0)
        rec["gross_mid_pips"] = side * (exit_mid - entry_mid) / PIP
    rec.update(extra)
    return rec


# ------------------------------------------------------- event pipeline

def run_event_on_window(ev, ts, bid, ask):
    """Full frozen pipeline for one event over its tick window slice.
    Returns a dict: event metadata, eligibility, shock/baseline stats and
    per-strategy trades/setup statuses. Pure function of (ev, arrays)."""
    out = {"event_id": ev["event_id"], "family": ev["family"],
           "t0_ns": ev["t0_ns"], "exclusion": None, "trades": [],
           "setups": {}}
    if ev["alignment"] != "ALIGNED":
        out["exclusion"] = "NOT_ALIGNED"
        return out
    if ev["post_lag_ms"] > 5000.0:
        out["exclusion"] = "POST_TICK_GT_5S"
        return out
    m = valid_mask(bid, ask)
    if not m.all():
        ts, bid, ask = ts[m], bid[m], ask[m]
    if len(ts) == 0:
        out["exclusion"] = "NO_TICKS_IN_WINDOW"
        return out
    mid = (bid + ask) / 2.0
    spread_pips = (ask - bid) / PIP
    gaps = gaps_in_window(ts)
    # primary eligibility: no data gap intersecting [T0-60m, T0+30s]
    for g1, g2 in gaps:
        if g1 < ev["t0_ns"] + SHOCK_AT_NS and g2 > ev["t0_ns"] - BASELINE_PRE_NS:
            out["exclusion"] = "BASELINE_OR_SHOCK_GAP"
            out["gap_ts"] = int(g1)
            return out
    q95, med_spread, n_buckets = baseline_stats(ts, mid, spread_pips,
                                                ev["t0_ns"])
    out["baseline"] = {"q95_pips": q95, "median_spread_pips": med_spread,
                       "n_buckets": n_buckets}
    if n_buckets == 0 or not np.isfinite(q95):
        out["exclusion"] = "BASELINE_EMPTY"
        return out
    noise_scale = max(q95, med_spread)
    out["noise_scale_pips"] = float(noise_scale)
    sh = shock_stats(ts, mid, ev["t0_ns"])
    out["shock"] = sh
    if sh["status"] != "OK":
        out["exclusion"] = sh["status"]
        return out
    qual, score = qualifying(sh["shock_pips"], noise_scale)
    out["shock_score"] = float(score)
    out["qualifying"] = bool(qual)
    out["p0"] = sh["p0"]
    out["p30"] = sh["p30"]
    out["shock_pips"] = sh["shock_pips"]
    if not qual:
        for k in "ABC":
            out["setups"][k] = {"status": "SHOCK_NOT_QUALIFYING"}
        return out
    gap_starts = np.array([g[0] for g in gaps], dtype=np.int64) \
        if gaps else np.array([], dtype=np.int64)
    common = dict(ev=ev, ts=ts, bid=bid, ask=ask, mid=mid,
                  shock_pips=sh["shock_pips"], med_spread=med_spread,
                  gaps=gaps, gap_starts=gap_starts)
    tr, st_a = strategy_a(p0=sh["p0"], **common)
    out["setups"]["A"] = st_a
    if tr:
        out["trades"].append(tr)
    tr, st_b = strategy_b(p0=sh["p0"], **common)
    out["setups"]["B"] = st_b
    if tr:
        out["trades"].append(tr)
    tr, st_c = strategy_c(**common)
    out["setups"]["C"] = st_c
    if tr:
        out["trades"].append(tr)
    for t in out["trades"]:
        t["shock_pips"] = float(sh["shock_pips"])
        t["shock_score"] = float(score)
    return out


# ------------------------------------------------------------- metrics

def _pf(net):
    wins = net[net > 0]
    losses = net[net < 0]
    if len(losses) == 0:
        return float("inf") if len(wins) else float("nan")
    return float(wins.sum() / abs(losses.sum()))


def compute_metrics(kind, trades, setups, n_events_eligible,
                    n_qualifying):
    """Frozen §16 metric block for one strategy, then §17 gate + §18
    fail-fast verdict."""
    valid = [t for t in trades if t["exit_reason"] in VALID_EXIT_REASONS]
    gap_inv = [t for t in trades if t["exit_reason"] == "DATA_GAP_INVALID"]
    exit_counts = {k: 0 for k in EXIT_COUNT_KEYS}
    for t in trades:
        r = t["exit_reason"]
        if r in ("STOP", "TARGET", "TIME", "DATA_GAP_INVALID"):
            exit_counts[r] += 1
    for s in setups:
        if s in ("SPREAD_TOO_WIDE", "NO_FILL"):
            exit_counts[s] += 1
        elif s == "NO_FILL_GAP":
            exit_counts["NO_FILL"] += 1
    m = {"strategy": kind, "strategy_id": STRATEGY_IDS[kind],
         "events_eligible": n_events_eligible,
         "qualifying_shocks": n_qualifying,
         "n_trades": len(valid),
         "n_data_gap_invalid": len(gap_inv),
         "setup_status_counts": {},
         "exit_counts": exit_counts}
    sc = {}
    for s in setups:
        sc[s] = sc.get(s, 0) + 1
    m["setup_status_counts"] = dict(sorted(sc.items()))
    if not valid:
        m["verdict"] = "REJECT"
        m["verdict_reason"] = "NO_TRADES"
        return m
    net = np.array([t["net_pips"] for t in valid], dtype=np.float64)
    risk = np.array([t["risk_pips"] for t in valid], dtype=np.float64)
    fam = np.array([t["family"] for t in valid])
    years = np.array([int(pd.Timestamp(t["entry_ts"], tz="UTC").year)
                      for t in valid])
    mean_net = float(net.mean())
    m["trades_per_year"] = round(len(valid) / 9.0, 3)
    m["mean_shock_pips"] = round(float(np.mean([t["shock_pips"]
                                                for t in valid])), 4)
    m["median_shock_pips"] = round(float(np.median([t["shock_pips"]
                                                    for t in valid])), 4)
    m["mean_shock_score"] = round(float(np.mean([t["shock_score"]
                                                 for t in valid])), 4)
    m["net_mean_pips"] = round(mean_net, 4)
    m["net_median_pips"] = round(float(np.median(net)), 4)
    m["stress_025_mean"] = round(mean_net - 0.50, 4)
    m["stress_050_mean"] = round(mean_net - 1.00, 4)
    m["stress_100_mean"] = round(mean_net - 2.00, 4)
    wins = net[net > 0]
    losses = net[net < 0]
    m["win_rate"] = round(float((net > 0).mean()), 4)
    m["avg_win"] = round(float(wins.mean()), 4) if len(wins) else 0.0
    m["avg_loss"] = round(float(losses.mean()), 4) if len(losses) else 0.0
    pf = _pf(net)
    m["profit_factor"] = round(min(pf, 1e9), 4) if np.isfinite(pf) else 1e9
    m["expectancy_r"] = round(float(np.mean(net / risk)), 4)
    m["total_net_pips"] = round(float(net.sum()), 4)
    order = np.argsort([t["entry_ts"] for t in valid], kind="stable")
    net_chron = net[order]
    cum = np.cumsum(net_chron)
    peak = np.maximum.accumulate(cum)
    m["max_drawdown_pips"] = round(float((peak - cum).max()), 4)
    streak = best = 0
    for v in net_chron:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    m["max_consecutive_losses"] = int(best)
    pos_years = 0
    by_year = {}
    for y in YEARS:
        sel = years == y
        if not sel.any():
            by_year[str(y)] = None
            continue
        ynet = float(net[sel].sum())
        if ynet > 0:
            pos_years += 1
        ypf = _pf(net[sel])
        by_year[str(y)] = {
            "n": int(sel.sum()),
            "mean_net": round(float(net[sel].mean()), 4),
            "total_net": round(ynet, 4),
            "pf": round(min(ypf, 1e9), 4) if np.isfinite(ypf) else 1e9,
        }
    m["positive_years"] = pos_years
    m["by_year"] = by_year
    for fname in ("NFP", "CPI"):
        sel = fam == fname
        if sel.any():
            fnet = net[sel]
            fpos = sum(1 for y in YEARS
                       if (years == y)[sel].any()
                       and float(fnet[years[sel] == y].sum()) > 0)
            fpf = _pf(fnet)
            m[f"{fname.lower()}_mean_net"] = round(float(fnet.mean()), 4)
            m[f"{fname.lower()}_n"] = int(sel.sum())
            m[f"{fname.lower()}_pf"] = (round(min(fpf, 1e9), 4)
                                        if np.isfinite(fpf) else 1e9)
            m[f"{fname.lower()}_positive_years"] = int(fpos)
        else:
            m[f"{fname.lower()}_mean_net"] = None
            m[f"{fname.lower()}_n"] = 0
            m[f"{fname.lower()}_pf"] = None
            m[f"{fname.lower()}_positive_years"] = 0
    m["remove_best_1pct_mean"] = round(MTF.remove_best_1pct(net), 4)
    ci_lo, ci_hi = MTF.bootstrap_ci95(net, n_res=2000, seed=42)
    m["ci95_lo"] = round(ci_lo, 4)
    m["ci95_hi"] = round(ci_hi, 4)
    m["ci_positive"] = bool(ci_lo > 0)
    m.update(_verdict(m))
    return m


def _verdict(m):
    """Frozen §17 economic gate, then §18 fail-fast. Verdicts:
    MACRO_TICK_PROMISING / REJECT / FAIL_GATE."""
    if (m["n_trades"] >= 40
            and m["net_mean_pips"] >= 3.0
            and m["profit_factor"] >= 1.25
            and m["expectancy_r"] >= 0.10
            and m["positive_years"] >= 6
            and m["remove_best_1pct_mean"] > 0
            and m["stress_050_mean"] > 0
            and m["total_net_pips"] > 0
            and (m["nfp_mean_net"] or 0) > 0
            and (m["cpi_mean_net"] or 0) > 0):
        return {"verdict": "MACRO_TICK_PROMISING", "verdict_reason": "GATE_PASS"}
    if (m["net_mean_pips"] <= 0 or m["profit_factor"] <= 1.0
            or m["remove_best_1pct_mean"] <= 0):
        return {"verdict": "REJECT", "verdict_reason": "FAIL_FAST"}
    return {"verdict": "FAIL_GATE", "verdict_reason": "BELOW_GATE"}
