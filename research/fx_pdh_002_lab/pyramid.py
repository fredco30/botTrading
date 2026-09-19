#!/usr/bin/env python3
"""FX_PDH_002B — anti-martingale pyramiding engine (per RESEARCH_PROTOCOL 4B).

BASE layer = the exact STRICT V1 trade (entry/stop/trail/48h untouched);
ADD layers are independent STRICT positions (own 1-ATR initial stop from
their own fill, own 3-ATR trail from their own extreme, own 48h hold).

Sequencing: base entries follow 001 one-position sequencing exactly (the
next signal strictly after the previous BASE exits, never the same bar), so
the base trade set is identical to FX_PDH_001 (unit-tested). Adds fire only
while the BASE layer of the current group is still open, max ONE add per
bar, max two adds per group, fills at next H1 open. Stops are never widened.

Risk caps (pre-registered): total worst-case open risk <= policy % of
current equity (500 + realized + marked unrealized). Layer worst-case risk
= max(0, entry_fill - effective_stop_now) * pip_EUR * lots. Sizing: target
0.5% of FIXED EUR 500, floor-rounded to 0.01 lots, min 0.01; an add is
truncated to the remaining capacity and SKIPPED if that leaves < 0.01 lots.

Pre-registered architectures:
  B1 R-MOMENTUM   add1 at first H1 close with base PnL >= +1R; add2 >= +2R
  B2 H1-CONTINU.  add1 at first post-entry new H1 high with base >= +0.5R;
                  add2 at the next new high above the extreme since the ADD1
                  trigger bar, base still >= +0.5R
  B3 PULLBACK     once base has reached +0.5R: reclaim bars (low <= PDH-in-
                  force < close); add1 = first, add2 = second
  B4 DAY-PERSIST  add1 at first H1 close on a later UTC day with base
                  >= +0.5R; add2 on a third UTC day, base >= +0.5R
"""
import numpy as np
import pandas as pd

import engine as E
import tmlab as T

PIP = E.PIP
SPREAD = E.SPREAD


class Layer:
    __slots__ = ("kind", "group", "k", "fill", "stop", "ext", "sig",
                 "pip_eur", "lot", "done", "exit_i", "exit_px", "reason",
                 "net_pips", "n_adds", "add1_i", "half_r")

    def __init__(self, kind, group, k, fill, stop, sig, pip_eur, lot):
        self.kind = kind            # BASE / ADD1 / ADD2
        self.group = group
        self.k = k
        self.fill = fill
        self.stop = stop
        self.ext = None             # extreme since own entry (high for long)
        self.sig = sig
        self.pip_eur = pip_eur
        self.lot = lot
        self.done = False
        self.exit_i = None
        self.exit_px = None
        self.reason = None
        self.net_pips = None
        self.n_adds = 0
        self.add1_i = None
        self.half_r = False

    @property
    def stop_pips(self):
        return abs(self.fill - self.stop) / PIP


def run_pyramid(D, arch, cap_pct, slip=0.0, risk=E.RISK):
    """One pyramid cell -> (layers DataFrame, info dict)."""
    o, h, l, c = D["o"], D["h"], D["l"], D["c"]
    atr, pdh, n = D["atr"], D["pdh"], D["n_bars"]
    idx, day_pos = D["idx"], D["day_pos"]
    spread_abs, slip_abs = SPREAD * PIP, slip * PIP
    eur5 = T.load_5m("EURUSD", E.START, E.END)
    euri, eurc = eur5.index, eur5["close"].to_numpy()
    sig = E.signals(D, "long_touch")
    target_eur = risk * E.CAPITAL               # fixed-capital sizing

    def pip_eur_at(k2):
        i = np.searchsorted(euri, idx[k2], side="right") - 1
        return 1000.0 * PIP / D["c"][k2] * eurc[i]

    def open_layer(l_kind, group, k2, trigsig):
        fill = o[k2] + spread_abs + slip_abs
        stop = fill - 1.0 * atr[trigsig]
        pe = pip_eur_at(k2)
        lot = max(0.01, np.floor(
            (target_eur / (abs(fill - stop) / PIP * pe * 100.0)) / 0.01) * 0.01)
        return Layer(l_kind, group, k2, fill, stop, trigsig, pe, float(lot))

    layers, open_layers = [], []
    realized = 0.0
    group_id = -1
    base = None
    max_open_risk = 0.0
    peak_notional = 0.0
    add_log = []                                # (bar, risk_before, risk_after)

    def close_layer(L, i, px, reason):
        nonlocal realized
        L.done, L.exit_i, L.exit_px, L.reason = True, i, px, reason
        L.net_pips = (px - L.fill) / PIP
        realized += L.net_pips * L.pip_eur * (L.lot / 0.01)

    for i in range(n):
        # ---- 1) manage open layers (strict per-layer exits) ----
        still = []
        for L in open_layers:
            if i == L.k:                        # entry bar: initial stop only
                if l[i] <= L.stop:
                    close_layer(L, i, min(o[i], L.stop) - slip_abs, "stop")
                else:
                    L.ext = h[i]
                    still.append(L)
                continue
            a = atr[i - 1]
            eff_stop = L.stop
            if np.isfinite(a):
                eff_stop = max(L.stop, L.ext - 3.0 * a)
            if l[i] <= eff_stop:
                close_layer(L, i, min(o[i], eff_stop) - slip_abs, "stop")
                continue
            if (i - L.k) >= E.MAX_HOLD:
                close_layer(L, i, c[i] - slip_abs, "time")
                continue
            L.ext = max(L.ext, h[i])
            still.append(L)
        open_layers = still
        base_open = base is not None and not base.done

        # ---- 2) mark equity / open risk / notional at close i ----
        unreal = risk_open = notional = 0.0
        a_now = atr[i] if np.isfinite(atr[i]) else atr[i - 1]
        for L in open_layers:
            unreal += (c[i] - L.fill) / PIP * L.pip_eur * (L.lot / 0.01)
            eff = L.stop if i < L.k else max(L.stop, L.ext - 3.0 * a_now)
            risk_open += max(0.0, L.fill - eff) / PIP * L.pip_eur * (L.lot / 0.01)
            notional += L.lot * 100000.0
        equity_mark = E.CAPITAL + realized + unreal
        max_open_risk = max(max_open_risk, risk_open)
        peak_notional = max(peak_notional, notional)
        cap_room = cap_pct * equity_mark - risk_open

        # ---- 3) add triggers at close i (base layer must be open) ----
        if base_open and np.isfinite(atr[base.sig]) and i + 1 < n \
                and base.n_adds < 2:
            base_r = (c[i] - base.fill) / PIP / (atr[base.sig] / PIP)
            fired = None
            if arch == "B1":
                if base.n_adds < 1 and base_r >= 1.0:
                    fired = "ADD1"
                elif base.n_adds == 1 and base_r >= 2.0:
                    fired = "ADD2"
            elif arch == "B2":
                new_hi = i > base.k and h[i] > h[base.k:i].max()
                if base.n_adds < 1 and base_r >= 0.5 and new_hi:
                    fired = "ADD1"
                elif base.n_adds == 1 and base_r >= 0.5 \
                        and base.add1_i is not None and i > base.add1_i:
                    ext2 = h[base.add1_i:i - 1].max() if i - 1 > base.add1_i \
                        else h[base.add1_i]
                    if h[i] > ext2:
                        fired = "ADD2"
            elif arch == "B3":
                if not base.half_r and base_r >= 0.5:
                    base.half_r = True
                if base.half_r and l[i] <= pdh[i] and c[i] > pdh[i]:
                    fired = "ADD1" if base.n_adds < 1 else "ADD2"
            elif arch == "B4":
                if base.n_adds < 1 and base_r >= 0.5 \
                        and day_pos[i] > day_pos[base.k]:
                    fired = "ADD1"
                elif base.n_adds == 1 and base_r >= 0.5 \
                        and day_pos[i] > day_pos[base.k] + 1:
                    fired = "ADD2"
            else:
                raise ValueError(arch)
            if fired is not None:
                risk_before = risk_open
                L = open_layer(fired, group_id, i + 1, i)
                lot_cap = np.floor(
                    (max(cap_room, 0.0) /
                     (L.stop_pips * L.pip_eur * 100.0)) / 0.01) * 0.01
                L.lot = float(min(L.lot, max(lot_cap, 0.0)))
                if L.lot >= 0.01:
                    layers.append(L)
                    open_layers.append(L)
                    base.n_adds += 1
                    if fired == "ADD1":
                        base.add1_i = i
                    risk_after = risk_before + L.stop_pips * L.pip_eur * \
                        (L.lot / 0.01)
                    max_open_risk = max(max_open_risk, risk_after)
                    add_log.append((int(i), fired, float(risk_before),
                                    float(risk_after), L.lot))

        # ---- 4) base entries follow 001 sequencing exactly ----
        if base is None or base.done:
            j = np.searchsorted(sig, i, side="right") - 1
            if j >= 0 and sig[j] == i and i + 1 < n and np.isfinite(atr[i]):
                prev_exit = -1
                if group_id >= 0:
                    prev_exit = next(L.exit_i for L in layers
                                     if L.group == group_id
                                     and L.kind == "BASE")
                if i > prev_exit:
                    group_id += 1
                    b = open_layer("BASE", group_id, i + 1, i)
                    layers.append(b)
                    open_layers.append(b)
                    base = b

        # release the base reference once its whole group is flat
        if base is not None and base.done and \
                not any(not L.done and L.group == base.group
                        for L in open_layers):
            base = None

    # Groups whose BASE never exits inside the sealed window are DROPPED
    # entirely (frozen 001 counts closed trades only; group metrics need the
    # base). This affects at most the final group at the data edge.
    done_groups = {L.group for L in layers if L.kind == "BASE" and L.done}
    dropped = sum(1 for L in layers if L.group not in done_groups)

    ldf = pd.DataFrame([{
        "group": L.group, "kind": L.kind, "sig_i": L.sig, "entry_i": L.k,
        "exit_i": L.exit_i, "reason": L.reason, "entry_fill": round(L.fill, 6),
        "exit_px": round(L.exit_px, 6), "net_pips": L.net_pips,
        "stop_pips": L.stop_pips,
        "r_mult": L.net_pips / L.stop_pips, "lot": L.lot,
        "pnl_eur": L.net_pips * L.pip_eur * (L.lot / 0.01),
    } for L in layers if L.group in done_groups and L.done])
    info = {"arch": arch, "cap_pct": cap_pct, "slip": slip,
            "n_layers": int(len(ldf)),
            "n_add1": int((ldf["kind"] == "ADD1").sum()) if len(ldf) else 0,
            "n_add2": int((ldf["kind"] == "ADD2").sum()) if len(ldf) else 0,
            "n_dropped_open_layers": dropped,
            "max_open_risk_eur": float(max_open_risk),
            "peak_notional_eur": float(peak_notional),
            "add_log": add_log}
    return ldf, info


def group_stats(D, ldf):
    """Group-level (per base entry) metrics + EUR path on layer exit times."""
    if len(ldf) == 0:
        return {}, pd.DataFrame()
    g = ldf.groupby("group")
    grp = g.agg(entry_i=("entry_i", "min"), exit_i=("exit_i", "max"),
                net_pips=("net_pips", "sum"), pnl_eur=("pnl_eur", "sum"),
                n_layers=("kind", "size")).reset_index()
    grp["year"] = [D["idx"][i].year for i in grp["entry_i"]]
    base_r = ldf[ldf["kind"] == "BASE"].set_index("group")["r_mult"]
    grp["base_r"] = grp["group"].map(base_r)
    path = ldf.sort_values(["exit_i", "entry_i"]).copy()
    eq = E.CAPITAL + np.cumsum(path["pnl_eur"].to_numpy())
    peak = np.maximum.accumulate(eq)
    times = D["idx"][path["exit_i"].to_numpy().astype(int)]
    dd = peak - eq
    day_key = np.array([t.date() for t in times])
    worst_day = float(pd.Series(path["pnl_eur"].to_numpy(), day_key)
                      .groupby(level=0).sum().min())
    out = {
        "n_groups": int(len(grp)),
        "n_layers": int(len(ldf)),
        "net_pips": float(grp["net_pips"].sum()),
        "net_pips_per_group": float(grp["net_pips"].mean()),
        "pnl_eur_total": float(grp["pnl_eur"].sum()),
        "pf_group": float(
            grp.loc[grp["net_pips"] > 0, "net_pips"].sum()
            / -grp.loc[grp["net_pips"] <= 0, "net_pips"].sum()),
        "win_rate_group": float((grp["net_pips"] > 0).mean()),
        "by_year_group_pips": {int(y): float(v) for y, v in
                               grp.groupby("year")["net_pips"].sum().items()},
        "ending_equity": float(eq[-1]),
        "max_dd_eur": float(dd.max()),
        "max_dd_percent": float(100 * dd.max() / peak.max()),
        "worst_group_eur": float(grp["pnl_eur"].min()),
        "worst_day_eur": worst_day,
    }
    r = grp["net_pips"].to_numpy()
    k = max(1, int(round(0.01 * len(r))))
    out["remove_best_1pct_pips"] = float(np.mean(np.sort(r)[:-k]))
    return out, grp


def layer_contribution(ldf):
    if len(ldf) == 0:
        return {}
    return {k2: {"n": int(len(v)), "net_pips": float(v["net_pips"].sum()),
                 "net_r": float(v["r_mult"].sum()),
                 "pnl_eur": float(v["pnl_eur"].sum())}
            for k2, v in ldf.groupby("kind")}
