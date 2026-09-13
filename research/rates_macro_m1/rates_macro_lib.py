#!/usr/bin/env python3
"""RATES-MACRO-M1 library: cross-market event-driven EURUSD discovery.

Signal chain: NFP/CPI release -> ZF/ZN 1-minute Treasury repricing ->
delayed EURUSD adjustment. Every rule lives in
`RATES_MACRO_M1_FROZEN_SPEC.md` (commit ab05ff3, frozen BEFORE any outcome
computation). Exactly three frozen strategies:
  A  RATES_A_1M_REPRICING_CONTINUATION
  B  RATES_B_FX_LAG
  C  RATES_C_FX_DISAGREEMENT_REVERSION

Reuses the validated TICK/MTF-M1 pipeline primitives (month-partition
TickStore with the 2019 hard guard, frozen weekend/gap rule, tick-accurate
BID/ASK trade resolution, bootstrap/remove-best metrics) by importing
`mtf_lib`. Units: int64 ns UTC timestamps, float64 prices, 1 pip = 1e-4.
"""
import json
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
MIN_NS = 60 * NS
DISCOVERY_START_NS = int(pd.Timestamp("2010-06-07T00:00:00Z").value)  # inclusive
DISCOVERY_END_NS = MTF.DISCOVERY_END_NS          # 2019-01-01 hard cut, exclusive
YEARS = list(range(2010, 2019))                  # 2010 is a partial year

LATENCY_NS = MTF.LATENCY_NS                      # frozen 250 ms
NO_FILL_WINDOW_NS = 60 * NS                      # frozen: 60 s entry search bound

# ---- frozen rates geometry (spec §3-§7) --------------------------------
BASELINE_PRE_NS = 60 * MIN_NS                    # T0 - 60 min
BASELINE_EXCLUDE_NS = 5 * MIN_NS                 # last 5 min excluded
MIN_BASELINE_RETURNS = 30                        # frozen
SHOCK_SCORE = 2.0                                # frozen both instruments

# ---- frozen FX geometry (spec §10) -------------------------------------
MIN_FX_BASELINE_CHANGES = 30                     # frozen
FX_P1_BOUND_NS = 2 * MIN_NS                      # FX_P1 must exist by T0+2 min

# ---- frozen strategy constants (spec §12-§14) --------------------------
MIN_RISK_PIPS = 1.0                              # frozen minimum risk
AB_R_MULT = 2.0                                  # frozen target 2.0R
AB_TIME_NS = 60 * MIN_NS                         # frozen time exit
C_TIME_NS = 30 * MIN_NS                          # frozen time exit
C_DISAGREE_FRAC = 0.50                           # frozen |FX1M| >= 0.5*FX_Q95

STRATEGY_IDS = {"A": "RATES_A_1M_REPRICING_CONTINUATION",
                "B": "RATES_B_FX_LAG",
                "C": "RATES_C_FX_DISAGREEMENT_REVERSION"}

RATES_DIR = os.environ.get(
    "RATES_DATA_DIR", "E:/ResearchData/botTrading/rates/databento")
TICKS_DIR = os.environ.get(
    "TICKS_DATA_DIR", "E:/ResearchData/botTrading/ticks/parquet")
MACRO_CSV = os.path.join(
    _HERE, "data", "macro_events_2010_2018_aligned.csv")


# ------------------------------------------------------------- events

def load_events(csv_path=MACRO_CSV):
    """NFP/CPI events from the validated MACRO-TICK-M0 artifact, Discovery
    window only (spec §1/§2). FOMC dropped; 2019+ dropped by hard cut;
    events whose validated tick alignment is not ALIGNED are dropped
    ('valid EURUSD tick data' requirement)."""
    df = pd.read_csv(csv_path)
    df = df[df["family"].isin(["NFP", "CPI"])]
    out = []
    for _, r in df.iterrows():
        t0 = int(pd.Timestamp(r["release_timestamp_utc"]).value)
        if not (DISCOVERY_START_NS <= t0 < DISCOVERY_END_NS):
            continue
        if r["tick_alignment_status"] != "ALIGNED":
            continue
        if t0 % MIN_NS != 0:
            raise ValueError(f"event {r['event_id']} not minute-aligned")
        out.append({"event_id": r["event_id"], "family": r["family"],
                    "t0_ns": t0})
    out.sort(key=lambda e: e["t0_ns"])
    return out


# ------------------------------------------------------------- rates

class RateStore:
    """ZF/ZN/ZT continuous 1-minute bars (unadjusted) + validated roll
    transitions and unexpected-gap intervals. Whole-history load is fine
    (~6.65M rows total); per-event logic is pure array slicing.
    `rates_dir=None` builds an empty store (synthetic tests inject
    `bars` / `rolls` / `gaps` directly)."""

    def __init__(self, rates_dir=RATES_DIR):
        self.bars = {}       # sym -> {start, close}
        self.rolls = {}      # sym -> (old_last_ns[], new_first_ns[])
        self.gaps = {}       # sym -> (g1[], g2[]) UNEXPECTED_DATA_GAP only
        for sym in ("ZF", "ZN", "ZT"):
            self.rolls[sym] = (np.array([], np.int64),
                               np.array([], np.int64))
            self.gaps[sym] = (np.array([], np.int64),
                              np.array([], np.int64))
        if rates_dir is not None:
            self._load(rates_dir)

    def _load(self, rates_dir):
        for sym in ("ZF", "ZN", "ZT"):
            df = pd.read_parquet(os.path.join(rates_dir, "parquet",
                                              f"{sym}.parquet"),
                                 columns=["close"])
            starts = df.index.astype("int64").to_numpy()
            if not np.all(np.diff(starts) > 0):
                raise ValueError(f"{sym}: bars not strictly increasing")
            self.bars[sym] = {"start": starts,
                              "close": df["close"].to_numpy(np.float64)}
            audit = pd.read_csv(os.path.join(rates_dir, "metadata",
                                             "roll_audit.csv"))
            audit = audit[audit["symbol"] == sym]
            self.rolls[sym] = (
                pd.to_datetime(audit["old_last_ts"], utc=True
                               ).astype("int64").to_numpy(),
                pd.to_datetime(audit["new_first_ts"], utc=True
                               ).astype("int64").to_numpy())
            gj = json.load(open(os.path.join(
                rates_dir, "metadata", f"{sym.lower()}_gaps_full.json")))
            ung = [g for g in gj if g["kind"] == "UNEXPECTED_DATA_GAP"]
            self.gaps[sym] = (
                np.array([int(pd.Timestamp(g["start"]).value) for g in ung],
                         dtype=np.int64),
                np.array([int(pd.Timestamp(g["end"]).value) for g in ung],
                         dtype=np.int64))

    # -- primitive checks -----------------------------------------------

    def roll_invalid(self, sym, t0):
        """Frozen §4: transition overlapping [t0-60m, t0+1m] for `sym`."""
        olast, nfirst = self.rolls[sym]
        lo = t0 - BASELINE_PRE_NS
        hi = t0 + MIN_NS
        return bool(np.any((olast >= lo) & (nfirst <= hi)))

    def gap_crosses(self, sym, t1, t2):
        """True iff an UNEXPECTED_DATA_GAP [g1,g2) intersects (t1, t2]."""
        g1, g2 = self.gaps[sym]
        if len(g1) == 0:
            return False
        i = int(np.searchsorted(g2, t1 + 1, side="left"))  # g2 > t1
        return bool(i < len(g1) and g1[i] < t2)            # g1 < t2... (t2]

    def window(self, sym, t0):
        """Rate window for one event/instrument per frozen spec §3-§7.
        Returns dict with status OK / ROLL_WINDOW_INVALID /
        BASELINE_INVALID / RATE_WINDOW_INVALID / EVENT_BAR_MISSING."""
        b = self.bars[sym]
        starts, close = b["start"], b["close"]
        out = {"sym": sym}
        if self.roll_invalid(sym, t0):
            out["status"] = "ROLL_WINDOW_INVALID"
            return out
        # event bar [T0, T0+1m): must exist (trades printed that minute)
        i_ev = int(np.searchsorted(starts, t0, side="left"))
        if i_ev >= len(starts) or starts[i_ev] != t0:
            out["status"] = "EVENT_BAR_MISSING"
            return out
        # unexpected gap inside (PRE_CLOSE bar start, T0] must not sit
        # between the shock's two closes
        i_pre = i_ev - 1
        if i_pre < 0:
            out["status"] = "EVENT_BAR_MISSING"
            return out
        if self.gap_crosses(sym, starts[i_pre], t0):
            out["status"] = "RATE_WINDOW_INVALID"
            return out
        pre_close = float(close[i_pre])
        post1_close = float(close[i_ev])
        # baseline: bars with start in [T0-60m, T0-5m); consecutive-only
        # close-to-close changes (never across a missing bar, never across
        # an unexpected gap; rolls inside the window are excluded by §4)
        lo = t0 - BASELINE_PRE_NS
        hi = t0 - BASELINE_EXCLUDE_NS
        i0 = int(np.searchsorted(starts, lo, side="left"))
        i1 = int(np.searchsorted(starts, hi, side="left"))
        rets = []
        for k in range(i0 + 1, i1):
            if starts[k] - starts[k - 1] != MIN_NS:
                continue                       # missing bar between: skip
            if self.gap_crosses(sym, starts[k - 1], starts[k]):
                continue
            rets.append(float(close[k] - close[k - 1]))
        n_ret = len(rets)
        if n_ret < MIN_BASELINE_RETURNS:
            out["status"] = "BASELINE_INVALID"
            out["n_baseline_returns"] = n_ret
            return out
        q95 = float(np.percentile(np.abs(rets), 95, method="linear"))
        move = post1_close - pre_close
        out.update({
            "status": "OK",
            "pre_close": pre_close,
            "pre_bar_start": int(starts[i_pre]),
            "post1_close": post1_close,
            "rate_move": move,
            "rate_q95": q95,
            "n_baseline_returns": n_ret,
            "rate_score": (abs(move) / q95) if q95 > 0 else np.inf,
        })
        return out


def primary_rate_shock(zf, zn):
    """Frozen §7: same non-zero sign AND both scores >= 2.0."""
    if zf["status"] != "OK" or zn["status"] != "OK":
        return False
    if zf["rate_move"] == 0.0 or zn["rate_move"] == 0.0:
        return False
    if np.sign(zf["rate_move"]) != np.sign(zn["rate_move"]):
        return False
    return zf["rate_score"] >= SHOCK_SCORE and zn["rate_score"] >= SHOCK_SCORE


def rate_direction(zf):
    """Frozen §8 mapping (never reversed after seeing outcomes):
    futures UP -> EURUSD LONG (+1); futures DOWN -> EURUSD SHORT (-1)."""
    return int(np.sign(zf["rate_move"]))


# ---------------------------------------------------------------- FX refs

def fx_event_refs(ts, mid, t0):
    """Frozen §10 references from a tick slice that covers
    [T0-62m, T0+2m). Returns (refs, fx_baseline) with refs = None when
    FX_REF_INVALID."""
    lo = t0 - BASELINE_PRE_NS
    hi = t0 - BASELINE_EXCLUDE_NS
    # FX_P0: last tick strictly before T0; demand one within [T0-60m, T0)
    i_p0 = int(np.searchsorted(ts, t0, side="left")) - 1
    if i_p0 < 0 or ts[i_p0] < lo:
        return None, None
    fx_p0 = float(mid[i_p0])
    # FX_P1: first tick at/after T0+1m, must exist by T0+2m
    p1_t = t0 + MIN_NS
    i_p1 = int(np.searchsorted(ts, p1_t, side="left"))
    if i_p1 >= len(ts) or ts[i_p1] > t0 + FX_P1_BOUND_NS:
        return None, None
    fx_p1 = float(mid[i_p1])
    # first-minute mid extremes from ticks in [T0, T0+1m)
    i_fm0 = int(np.searchsorted(ts, t0, side="left"))
    if i_fm0 >= i_p1:                     # no tick inside the first minute
        fm_lo = fm_hi = None
    else:
        fm_lo = float(np.min(mid[i_fm0:i_p1]))
        fm_hi = float(np.max(mid[i_fm0:i_p1]))
    # baseline: bucket-close mids, non-overlapping 1-minute changes
    nb = int((hi - lo) // MIN_NS)          # 55 buckets
    closes = []
    idxs = []
    for k in range(nb):
        a = lo + k * MIN_NS
        b = a + MIN_NS
        j0 = int(np.searchsorted(ts, a, side="left"))
        j1 = int(np.searchsorted(ts, b, side="left"))
        if j1 > j0:
            closes.append(float(mid[j1 - 1]))
            idxs.append(k)
    changes = []
    for m in range(1, len(closes)):
        if idxs[m] - idxs[m - 1] == 1:     # consecutive buckets only
            changes.append(closes[m] - closes[m - 1])
    base = {"n_changes": len(changes), "fx_q95": None}
    if len(changes) >= MIN_FX_BASELINE_CHANGES:
        base["fx_q95"] = float(np.percentile(np.abs(changes), 95,
                                             method="linear"))
    refs = {"fx_p0": fx_p0, "fx_p1": fx_p1,
            "fx_move_1m_pips": (fx_p1 - fx_p0) / PIP,
            "fm_low": fm_lo, "fm_high": fm_hi,
            "n_first_minute_ticks": int(i_p1 - i_fm0)}
    return refs, base


# -------------------------------------------------------------- execution

def resolve_entry_60s(ts, bid, ask, decision_ns, side, gap_starts):
    """Frozen §11 entry: first ASK (LONG) / BID (SHORT) tick at/after
    decision+250ms; NO_FILL if none within 60 s; NO_FILL_GAP if a true data
    gap sits between decision and the fill tick."""
    t0 = decision_ns + LATENCY_NS
    i0 = int(np.searchsorted(ts, t0, side="left"))
    if i0 >= len(ts) or ts[i0] > decision_ns + NO_FILL_WINDOW_NS:
        return {"status": "NO_FILL"}
    fill_ts = int(ts[i0])
    gi = int(np.searchsorted(gap_starts, decision_ns, side="right"))
    if gi < len(gap_starts) and gap_starts[gi] < fill_ts:
        return {"status": "NO_FILL_GAP"}
    return {"status": "FILLED", "idx": i0, "fill_ts": fill_ts,
            "price": float(ask[i0] if side == 1 else bid[i0])}


# -------------------------------------------------------------- strategies

def structural_stop(side, refs, entry):
    """Frozen §12/§14 stop: adverse first-minute MID extreme; validity vs
    the executable entry and the 1.0 pip minimum risk."""
    stop = refs["fm_low"] if side == 1 else refs["fm_high"]
    if stop is None:
        return None, "NO_TRADE_FIRST_MINUTE_NO_TICKS"
    if (side == 1 and stop >= entry) or (side == -1 and stop <= entry):
        return None, "NO_TRADE_INVALID_STOP"
    risk = abs(entry - stop)
    if risk / PIP < MIN_RISK_PIPS:
        return None, "NO_TRADE_RISK_TOO_SMALL"
    return stop, None


def fx_eligibility(kind, direction, refs, base):
    """Frozen FX-based eligibility that is checkable before the entry:
    B's lag rule and C's disagreement rules. direction = rate-implied
    EURUSD direction (+1/-1) from §8. Returns a no-trade reason or None.
    (fx_move_1m_pips is in pips; fx_q95 in price units -> compare in pips.)"""
    q95_pips = base["fx_q95"] / PIP
    if kind == "B":
        if abs(refs["fx_move_1m_pips"]) > q95_pips:
            return "NOT_ELIGIBLE_FX_ALREADY_MOVED"
    elif kind == "C":
        fx = refs["fx_move_1m_pips"]
        if np.sign(fx) != -direction:
            return "NOT_ELIGIBLE_NO_DISAGREEMENT"
        if abs(fx) < C_DISAGREE_FRAC * q95_pips:
            return "NOT_ELIGIBLE_FX_MOVE_TOO_SMALL"
    return None


def run_event(ev, rate_win, refs, base, store, fx_gaps):
    """Evaluate one event for A/B/C. Returns (trades, notes) where trades
    are filled/resolved trades and notes the per-strategy no-trade reason.
    One trade maximum per event per strategy; events are >= days apart and
    trades last <= 60 min, so no occupancy logic is needed."""
    trades, notes = [], {}
    t0 = ev["t0_ns"]
    shock = primary_rate_shock(rate_win["ZF"], rate_win["ZN"])
    if not shock:
        return trades, {"_shock": False}
    direction = rate_direction(rate_win["ZF"])
    decision = t0 + MIN_NS                      # close known at T0+1min
    if base["fx_q95"] is None:
        return trades, {"_shock": True, "_fx_baseline": "FX_BASELINE_INVALID"}
    for kind in ("A", "B", "C"):
        err = fx_eligibility(kind, direction, refs, base)
        if err:
            notes[kind] = err
            continue
        side = direction
        ts, bid, ask = store.get_range(
            decision + LATENCY_NS, min(decision + LATENCY_NS
                                       + NO_FILL_WINDOW_NS + NS,
                                       DISCOVERY_END_NS))
        er = resolve_entry_60s(ts, bid, ask, decision, side, fx_gaps)
        if er["status"] != "FILLED":
            notes[kind] = er["status"]
            continue
        entry = er["price"]
        stop, err = structural_stop(side, refs, entry)
        if err:
            notes[kind] = err
            continue
        risk = abs(entry - stop)
        if kind == "C":
            target = refs["fx_p0"]
            if (side == 1 and entry <= target) or \
                    (side == -1 and entry >= target):
                notes[kind] = "NO_TRADE_TARGET_ALREADY_CROSSED"
                continue
            t_exit = C_TIME_NS
        else:
            target = entry + side * AB_R_MULT * risk
            t_exit = AB_TIME_NS
        entry_ts = er["fill_ts"]
        if entry_ts + t_exit >= DISCOVERY_END_NS:
            notes[kind] = "SKIPPED_HARD_END"
            continue
        # tick window MUST extend past the time-exit timestamp (weekend at
        # entry+T pushes the first tick beyond it); grow the pad until the
        # window reaches the discovery hard cut.
        pad = 4 * 86400 * NS
        while True:
            end_bound = min(entry_ts + t_exit + NS + pad, DISCOVERY_END_NS)
            ts, bid, ask = store.get_range(entry_ts, end_bound)
            k = int(np.searchsorted(ts, entry_ts, side="left"))
            j_time = int(np.searchsorted(ts, entry_ts + t_exit, side="left"))
            if j_time < len(ts) or end_bound >= DISCOVERY_END_NS:
                break
            pad *= 4
        if k >= len(ts) or ts[k] != entry_ts:
            notes[kind] = "UNRESOLVED"
            continue
        last_tick = (int(ts[-1]), float(bid[-1]), float(ask[-1]))
        res = MTF.resolve_trade(ts, bid, ask, side, k, entry_ts, stop,
                                target, entry_ts + t_exit, fx_gaps,
                                last_tick)
        if res["status"] == "UNRESOLVED":
            notes[kind] = "UNRESOLVED"
            continue
        row = {
            "kind": kind, "event_id": ev["event_id"],
            "family": ev["family"], "t0_ns": t0,
            "direction": int(side), "decision_ns": int(decision),
            "entry_ts": int(entry_ts), "entry": float(entry),
            "stop": float(stop), "target": float(target),
            "risk_pips": float(risk / PIP),
            "fx_p0": refs["fx_p0"], "fx_p1": refs["fx_p1"],
            "fx_move_1m_pips": float(refs["fx_move_1m_pips"]),
            "fx_q95_pips": float(base["fx_q95"] / PIP),
        }
        if res["status"] == "DATA_GAP_INVALID":
            row.update({"exit_ts": int(res["gap_ts"]),
                        "exit_reason": "DATA_GAP_INVALID",
                        "exit_price": float("nan"), "net_pips": float("nan"),
                        "year": int(pd.Timestamp(entry_ts, tz="UTC").year)})
            trades.append(row)
            continue
        net = ((res["exit_price"] - entry) if side == 1
               else (entry - res["exit_price"])) / PIP
        row.update({"exit_ts": int(res["exit_ts"]),
                    "exit_reason": res["status"],
                    "exit_price": float(res["exit_price"]),
                    "net_pips": float(net),
                    "year": int(pd.Timestamp(entry_ts, tz="UTC").year)})
        trades.append(row)
    return trades, notes


# ---------------------------------------------------------------- metrics

def _pf(net):
    wins = net[net > 0]
    losses = net[net < 0]
    if len(losses) and losses.sum() != 0:
        return float(wins.sum() / abs(losses.sum()))
    return float("inf")


def strategy_metrics(trades, zf_scores, zn_scores, zt_avail, zt_confirm):
    """Frozen §22 metric set + §23 gate + §24 fail-fast. DATA_GAP_INVALID
    trades are excluded from main metrics and only counted."""
    valid = [t for t in trades if t["exit_reason"] != "DATA_GAP_INVALID"]
    gap_invalid = [t for t in trades if t["exit_reason"] == "DATA_GAP_INVALID"]
    out = {"n_trades": len(valid), "n_gap_invalid": len(gap_invalid)}
    if not valid:
        out.update({"verdict": "REJECT",
                    "zf_score_mean": round(float(np.mean(zf_scores)), 4)
                    if zf_scores else None,
                    "zn_score_mean": round(float(np.mean(zn_scores)), 4)
                    if zn_scores else None})
        return out
    net = np.array([t["net_pips"] for t in valid])
    risk = np.array([t["risk_pips"] for t in valid])
    fam = np.array([t["family"] for t in valid])
    years = np.array([t["year"] for t in valid])
    order = np.argsort([t["entry_ts"] for t in valid], kind="stable")
    net_chron = net[order]
    cum = np.cumsum(net_chron)
    peak = np.maximum.accumulate(cum)
    streak = best = 0
    for v in net_chron:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    mean_net = float(net.mean())
    # §21: POSITIVE_YEARS denominator = years with >= 3 trades
    years_eligible, pos_years, by_year = 0, 0, {}
    for y in YEARS:
        m = years == y
        n = int(m.sum())
        if n == 0:
            by_year[str(y)] = {"n": 0}
            continue
        ynet = float(net[m].sum())
        by_year[str(y)] = {"n": n, "total_net": round(ynet, 4),
                           "mean_net": round(float(net[m].mean()), 4)}
        if n >= 3:
            years_eligible += 1
            if ynet > 0:
                pos_years += 1
    ci_lo, ci_hi = MTF.bootstrap_ci95(net)          # 2000 resamples, seed 42
    nfp = net[fam == "NFP"]
    cpi = net[fam == "CPI"]
    out.update({
        "net_mean_pips": round(mean_net, 4),
        "net_median_pips": round(float(np.median(net)), 4),
        "total_net_pips": round(float(net.sum()), 4),
        "win_rate": round(float((net > 0).mean()), 4),
        "avg_win": round(float(net[net > 0].mean()), 4)
        if (net > 0).any() else 0.0,
        "avg_loss": round(float(net[net < 0].mean()), 4)
        if (net < 0).any() else 0.0,
        "profit_factor": round(min(_pf(net), 1e9), 4),
        "expectancy_r": round(float(np.mean(net / risk)), 4),
        "max_drawdown_pips": round(float((peak - cum).max()), 4),
        "max_consecutive_losses": int(best),
        "positive_years": pos_years,
        "years_eligible": years_eligible,
        "by_year": by_year,
        "remove_best_1pct_mean": round(MTF.remove_best_1pct(net), 4),
        "stress_025_mean": round(mean_net - 0.50, 4),
        "stress_050_mean": round(mean_net - 1.00, 4),
        "stress_100_mean": round(mean_net - 2.00, 4),
        "nfp_n": int(len(nfp)), "cpi_n": int(len(cpi)),
        "nfp_mean": round(float(nfp.mean()), 4) if len(nfp) else None,
        "cpi_mean": round(float(cpi.mean()), 4) if len(cpi) else None,
        "nfp_pf": round(min(_pf(nfp), 1e9), 4) if len(nfp) else None,
        "cpi_pf": round(min(_pf(cpi), 1e9), 4) if len(cpi) else None,
        "ci95_lo": round(ci_lo, 4), "ci95_hi": round(ci_hi, 4),
        "exits": {r: int(sum(1 for t in valid if t["exit_reason"] == r))
                  for r in ("STOP", "TARGET", "TIME")},
        "zf_score_mean": round(float(np.mean(zf_scores)), 4)
        if zf_scores else None,
        "zn_score_mean": round(float(np.mean(zn_scores)), 4)
        if zn_scores else None,
        "zt_available_pct": round(float(zt_avail), 4),
        "zt_confirm_pct": round(float(zt_confirm), 4),
    })
    out["ci_positive"] = "YES" if ci_lo > 0 else "NO"
    out["verdict"] = gate_verdict(out)
    return out


def gate_verdict(m):
    """Frozen §23 economic pass gate, then frozen §24 fail-fast."""
    if m["n_trades"] == 0:
        return "REJECT"
    if (m["net_mean_pips"] <= 0 or m["profit_factor"] <= 1.0
            or m["remove_best_1pct_mean"] <= 0):
        return "REJECT"
    pooled_ok = (m["nfp_mean"] is not None and m["nfp_mean"] > 0
                 and m["cpi_mean"] is not None and m["cpi_mean"] > 0)
    ratio = (m["positive_years"] / m["years_eligible"]
             if m["years_eligible"] else 0.0)
    if (m["n_trades"] >= 40
            and m["net_mean_pips"] >= 3.0
            and m["profit_factor"] >= 1.25
            and m["expectancy_r"] >= 0.10
            and ratio >= 0.67
            and m["remove_best_1pct_mean"] > 0
            and m["stress_050_mean"] > 0
            and m["total_net_pips"] > 0
            and pooled_ok):
        return "PASS"
    return "FAIL_GATE"
