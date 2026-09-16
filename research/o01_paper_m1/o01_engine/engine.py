#!/usr/bin/env python3
"""O01_ON_TRANSFER paper trading engine — provider-agnostic, PAPER_ONLY.

Event stream (strictly ts-ordered):
  BAR(ts,o,h,l,c,v,on_high,on_low,on_bars,
      quotes_at_activation, bar_quotes, quotes_at_exit)
      5m bar, bucket START; the quote attachments are execution mechanics
      supplied by the adapter:
        quotes_at_activation: quotes in [ts, ts+5min)   (entry bar only)
        bar_quotes          : quotes in [ts, ts+5min)   (any bar)
        quotes_at_exit      : first quote at/after ts+5min
  QUOTE(ts,bid,ask)  — live-mode samples (replay uses bar attachments).

Frozen lifecycle (O01_PAPER_FROZEN_SPEC.md):
  09:35 close -> decision; entry MARKET at next bar open (first quote >=
  activation); stop touch checked on the completed bar with quote proof
  (first executable opposite-side quote at/after the fill); chandelier
  1.0*ATR14 close-cross and EOD exit at first quote >= bar end.
  Three shadow ledgers BASE/CONSERVATIVE/STRESS; slippage 0/1/2 adverse
  ticks per marketable leg; fixed fees 1.0 pt RT per round trip.

PAPER_ONLY: no order routing exists in this package.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

PAPER_ONLY = True
MODE_REFERENCE = "REFERENCE_REGRESSION"
MODE_PROSPECTIVE = "PROSPECTIVE_PAPER"
MAX_TS_2026 = pd.Timestamp("2026-01-01", tz="UTC")   # historical research seal
TICK = 0.25
POINT_USD = 20.0
FIXED_FEES_RT = 1.0
SLIP_TICKS = {"BASE": 0, "CONSERVATIVE": 1, "STRESS": 2}
LEDGERS = ("BASE", "CONSERVATIVE", "STRESS")
ATR_MULT = 1.0
Z_THRESHOLD = 1.0
PM_ON_RATIO = 0.5
NO_TRADE_Z = "O01 no trade — overnight z-score insufficient."
NO_TRADE_PM = "O01 no trade — overnight move qualified but premarket range too wide."
NO_TRADE_CTX = "O01 no trade — context not ready (history still accumulating)."


class EventJournal:
    """Append-only JSONL + restart snapshot; idempotent by event_id."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.journal = self.root / "paper_journal.jsonl"
        self.snapshot = self.root / "engine_state.json"

    def append(self, rec: dict):
        with open(self.journal, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=str) + "\n")

    def seen(self, event_id) -> bool:
        if not self.journal.exists():
            return False
        with open(self.journal, encoding="utf-8") as f:
            for line in f:
                try:
                    if json.loads(line).get("event_id") == event_id:
                        return True
                except Exception:  # noqa: BLE001
                    continue
        return False

    def save_state(self, st: dict):
        self.snapshot.write_text(json.dumps(st, indent=1, default=str))

    def load_state(self):
        if self.snapshot.exists():
            return json.loads(self.snapshot.read_text())
        return None


@dataclass
class PositionState:
    side: int = 0
    entry: float = 0.0
    entry_shadows: dict = field(default_factory=dict)
    stop: float = 0.0
    trail: float = np.nan
    run_ext: float = np.nan
    entry_ts: object = None
    entry_i: int = -1              # index into the entry bar's quote list
    atr0: float = np.nan


@dataclass
class SignalEngine:
    """Causal context + frozen 09:35 decision (lab conventions)."""

    day_close: dict = field(default_factory=dict)
    day_tr: list = field(default_factory=list)
    on_ret_hist: list = field(default_factory=list)
    cur: dict = None

    def atr_next(self) -> float:
        if len(self.day_tr) < 14:
            return np.nan
        return float(np.mean(self.day_tr[-14:]))

    def process_bar(self, ev: dict) -> dict:
        ts = pd.Timestamp(ev["ts"])
        loc = ts.tz_convert("America/New_York")
        day, hm = loc.date(), loc.hour * 100 + loc.minute
        st = self.cur
        if st is None or st["day"] != day:
            self._finalize_prev()
            st = self.cur = {"day": day, "bars": [], "op": None, "close": None}
        st["bars"].append(ev)
        if ev.get("on_high") is not None:
            st["on_high"], st["on_low"] = ev["on_high"], ev["on_low"]
        if hm == 930:
            st["op"] = ev["o"]
        if 930 <= hm < 1600:
            st["close"] = ev["c"]
        if hm == 935:
            return self._decide(st)
        return {}

    def _finalize_prev(self):
        st = self.cur
        if st is None or st.get("close") is None:
            return
        rth = [b for b in st["bars"] if 930 <= _hm(b) < 1600]
        if not rth:
            return
        hi = max(b["h"] for b in rth)
        lo = min(b["l"] for b in rth)
        prev_close = list(self.day_close.values())[-1] if self.day_close else None
        tr = hi - lo
        if prev_close:
            tr = max(tr, abs(hi - prev_close), abs(lo - prev_close))
        self.day_tr.append(tr)
        self.day_close[st["day"]] = st["close"]
        if prev_close and st.get("op") is not None:
            self.on_ret_hist.append(st["op"] / prev_close - 1.0)

    def _decide(self, st) -> dict:
        atr = self.atr_next()
        prev_close = list(self.day_close.values())[-1] if self.day_close else None
        if (len(self.on_ret_hist) < 20 or atr != atr or
                st.get("op") is None or not prev_close):
            st["state"] = "NO_SETUP"
            return {"decision": "NO_TRADE", "reason": NO_TRADE_CTX,
                    "state": "NO_SETUP"}
        rets = np.array(self.on_ret_hist[-20:], float)
        mu, sd = rets.mean(), rets.std(ddof=1)
        on_ret = st["op"] / prev_close - 1.0
        z = (on_ret - mu) / sd if sd > 0 else np.nan
        on_hi, on_lo = st.get("on_high"), st.get("on_low")
        on_range = (on_hi - on_lo) if on_hi is not None else np.nan
        pm = [b for b in st["bars"] if 400 <= _hm(b) < 930]
        pm_range = (max(b["h"] for b in pm) - min(b["l"] for b in pm)) \
            if pm else np.nan
        gate = (pm_range == pm_range and on_range == on_range and
                pm_range <= PM_ON_RATIO * on_range)
        st["ctx"] = {"on_ret": on_ret, "z": z, "on_range": on_range,
                     "pm_range": pm_range, "gate": gate, "atr": atr}
        if z != z or abs(z) < Z_THRESHOLD:
            st["state"] = "NO_SETUP"
            return {"decision": "NO_TRADE", "reason": NO_TRADE_Z, "z": z,
                    "state": "NO_SETUP"}
        if not gate:
            st["state"] = "NO_SETUP"
            return {"decision": "NO_TRADE", "reason": NO_TRADE_PM, "z": z,
                    "pm_range": pm_range, "on_range": on_range,
                    "state": "NO_SETUP"}
        side = 1 if z > 0 else -1
        sw = [b for b in st["bars"] if 930 <= _hm(b) <= 935]
        stop = (min(b["l"] for b in sw) if side == 1
                else max(b["h"] for b in sw))
        st["state"] = "SIGNAL_VALID"
        return {"decision": "TRADE", "side": side, "stop": float(stop),
                "atr": atr, "z": z, "on_ret": on_ret,
                "activation_ts": pd.Timestamp(st["bars"][-1]["ts"]) +
                pd.Timedelta(5, "min"),
                "explain": (f"O01 {'LONG' if side == 1 else 'SHORT'}: overnight "
                            f"return z={z:.2f}, premarket-width condition passed."),
                "state": "ORDER_PENDING"}


def _hm(bar) -> int:
    loc = pd.Timestamp(bar["ts"]).tz_convert("America/New_York")
    return loc.hour * 100 + loc.minute


class PaperEngine:
    def __init__(self, journal_root, contract_lookup=None, persist_every=1,
                 mode=MODE_REFERENCE, activation_ts=None):
        """mode=REFERENCE_REGRESSION: hard 2026 research seal (ts>=2026-01-01Z
        refused). mode=PROSPECTIVE_PAPER: ts < activation_ts refused, ts >=
        activation allowed (prospective observations)."""
        assert PAPER_ONLY
        assert mode in (MODE_REFERENCE, MODE_PROSPECTIVE)
        self.mode = mode
        self.activation_ts = pd.Timestamp(activation_ts) if activation_ts else None
        if mode == MODE_PROSPECTIVE and self.activation_ts is None:
            raise ValueError("PROSPECTIVE_PAPER requires activation_ts")
        self.j = EventJournal(journal_root)
        self.sig = SignalEngine()
        self.pos = PositionState()
        self.state = "WAITING_SESSION"
        self.day = None
        self.contract = None
        self.contract_lookup = contract_lookup or (lambda day: None)
        self.pending_entry = None
        self.trades = []
        self.seq = 0
        self.persist_every = persist_every
        snap = self.j.load_state()
        if snap:
            for k, v in snap.items():
                if k == "sig":
                    self.sig.day_close = {pd.Timestamp(kk).date(): vv
                                          for kk, vv in v.get("day_close", [])}
                    self.sig.day_tr = v.get("day_tr", [])
                    self.sig.on_ret_hist = v.get("on_ret_hist", [])
                elif k == "pos_data":
                    self.pos = PositionState(**v)
                else:
                    setattr(self, k, v)
            if self.day is not None:
                self.day = pd.Timestamp(self.day).date()

    def _persist(self):
        self.j.save_state({
            "state": self.state, "day": str(self.day) if self.day else None,
            "contract": self.contract, "pending_entry": self.pending_entry,
            "pos_data": vars(self.pos), "trades": self.trades, "seq": self.seq,
            "sig": {"day_close": [[str(k), v] for k, v in self.sig.day_close.items()],
                    "day_tr": self.sig.day_tr,
                    "on_ret_hist": self.sig.on_ret_hist},
        })

    def on_event(self, ev: dict):
        eid = ev.get("event_id")
        if eid is not None and self.j.seen(eid):
            return
        ts = pd.Timestamp(ev["ts"])
        if self.mode == MODE_REFERENCE and ts >= MAX_TS_2026:
            raise ValueError("REFERENCE mode: 2026 research seal (ts >= 2026-01-01Z)")
        if self.mode == MODE_PROSPECTIVE and ts < self.activation_ts:
            raise ValueError("PROSPECTIVE mode: pre-activation timestamp refused")
        self.seq += 1
        ev["event_id"] = ev.get("event_id") or f"E{self.seq}"
        if ev["type"] == "QUOTE":
            self._quote(ev)
        else:
            self._bar(ev)
        if self.persist_every and (self.seq % self.persist_every == 0):
            self._persist()

    def _quote(self, ev: dict):
        """Live-granularity handling: fill working entry, touch-stop."""
        ts = pd.Timestamp(ev["ts"])
        if ts >= MAX_TS_2026:
            raise ValueError("2026 quote refused (seal)")
        if self.pending_entry is not None and                 ts >= pd.Timestamp(self.pending_entry["activation_ts"]):
            pe = self.pending_entry
            side = pe["side"]
            base = ev["ask"] if side == 1 else ev["bid"]
            fills = {k: base + SLIP_TICKS[k] * TICK * side for k in LEDGERS}
            self.pos = PositionState(
                side=side, entry=fills["BASE"], entry_shadows=fills,
                stop=pe["stop"], run_ext=base, entry_ts=ts,
                entry_i=-1, atr0=pe["atr"])
            self.trades.append({
                "DATE": str(ts.tz_convert("America/New_York").date()),
                "CONTRACT": self.contract, "SIDE": "LONG" if side == 1 else "SHORT",
                "ENTRY_TS": str(ts), "ENTRY_BID": ev["bid"], "ENTRY_ASK": ev["ask"],
                "ENTRY_SPREAD": round(ev["ask"] - ev["bid"], 4),
                "ENTRY": fills, "STOP": pe["stop"], "ATR": pe["atr"],
                "Z": pe["z"], "EXPLAIN": pe["explain"]})
            self.pending_entry = None
            self._log(ts, "PAPER_FILL", new_state="PAPER_POSITION_OPEN",
                      fills=fills, side=side,
                      reason="market entry on executable quote")
            return
        if self.pos.side != 0:
            p = self.pos
            if (p.side == 1 and ev["bid"] <= p.stop) or                (p.side == -1 and ev["ask"] >= p.stop):
                self._exit((ts, ev["bid"], ev["ask"]), "STOP", {})

    # ---------------- bar processing ----------------
    def _bar(self, ev: dict):
        ts = pd.Timestamp(ev["ts"])
        loc = ts.tz_convert("America/New_York")
        day, hm = loc.date(), loc.hour * 100 + loc.minute
        if self.day != day:
            self._log(ts, "DAY_START", new_state="WAITING_SESSION",
                      contract=self.contract_lookup(str(day)),
                      reason="new ET trading day")
            self.day = day
            self.contract = self.contract_lookup(str(day))
            self.pos = PositionState()
            self.pending_entry = None
        qa = ev.get("quotes_at_activation") or []
        bq = ev.get("bar_quotes") or []
        qe = ev.get("quotes_at_exit") or []

        # 1) pending entry fills at this bar's open (first quote >= activation)
        if self.pending_entry is not None and \
                str(self.pending_entry["activation_ts"]) == str(ts):
            side = self.pending_entry["side"]
            if qa:
                fill_q = qa[0]
                base = fill_q[2] if side == 1 else fill_q[1]
                fills = {k: base + SLIP_TICKS[k] * TICK * side for k in LEDGERS}
                self.pos = PositionState(
                    side=side, entry=fills["BASE"], entry_shadows=fills,
                    stop=self.pending_entry["stop"],
                    run_ext=ev["o"], entry_ts=fill_q[0],
                    entry_i=0, atr0=self.pending_entry["atr"])
                self.trades.append({
                    "DATE": str(day), "CONTRACT": self.contract,
                    "SIDE": "LONG" if side == 1 else "SHORT",
                    "SIGNAL_TS": str(ts - pd.Timedelta(5, "min")),
                    "ACTIVATION_TS": str(ts),
                    "ENTRY_TS": str(fill_q[0]),
                    "ENTRY_BID": fill_q[1], "ENTRY_ASK": fill_q[2],
                    "ENTRY_SPREAD": round(fill_q[2] - fill_q[1], 4),
                    "ENTRY": fills, "STOP": self.pending_entry["stop"],
                    "ATR": self.pending_entry["atr"],
                    "Z": self.pending_entry["z"],
                    "EXPLAIN": self.pending_entry["explain"]})
                self.pending_entry = None
                self._log(fill_q[0], "PAPER_FILL", new_state="PAPER_POSITION_OPEN",
                          fills=fills, side=side,
                          reason="market entry at bar open (BBO executable)")
            else:
                self._log(ts, "ENTRY_NO_QUOTE", new_state="ORDER_PENDING",
                          reason="no executable quote; order stays working")
                return
        # 2) manage an open position on this completed bar
        if self.pos.side != 0:
            self._manage_bar(ev, bq, qe, hm)
        # 3) signal decision at the 09:35 close (only when flat)
        if self.pos.side == 0:
            dec = self.sig.process_bar(ev)
            if dec:
                self._on_decision(ts, dec)

    def _manage_bar(self, ev, bq, qe, hm):
        p = self.pos
        entry_bar = str(p.entry_ts)[:16] == str(ev["ts"])[:16]
        start_i = (p.entry_i + 1) if entry_bar else 0
        # 1) initial stop: touch on the completed bar, quote-proven first
        touched = (p.side == 1 and ev["l"] <= p.stop) or \
                  (p.side == -1 and ev["h"] >= p.stop)
        if touched:
            k = self._first_touch_quote(bq, start_i, p.side, p.stop)
            if k is not None:
                self._exit(bq[k], "STOP", {"STOP_TS": str(bq[k][0])})
                return
            if self.mode == MODE_PROSPECTIVE:
                self._log(ev["ts"] + pd.Timedelta(5, "min"), "DATA_GAP",
                          new_state="PAPER_POSITION_OPEN",
                          reason="STOP touched by bar but no executable quote proof")
                return
            px = (min(ev["o"], p.stop) if p.side == 1 else max(ev["o"], p.stop))
            synth = (ev["ts"] + pd.Timedelta(5, "min"), px, px)
            self._exit(synth, "STOP", {"STOP_TS": str(synth[0]),
                                       "STOP_UNPROVEN": True})
            return
        # 2) chandelier: update running extreme, evaluate completed close
        p.run_ext = max(p.run_ext, ev["h"]) if p.side == 1 else \
            min(p.run_ext, ev["l"])
        p.trail = (p.run_ext - ATR_MULT * p.atr0) if p.side == 1 else \
                  (p.run_ext + ATR_MULT * p.atr0)
        crossed = (p.side == 1 and ev["c"] < p.trail) or \
                  (p.side == -1 and ev["c"] > p.trail)
        last_bar = hm >= 1555
        if crossed or last_bar:
            reason = "TRAIL" if crossed else "EOD"
            if qe:
                q = qe[0]
                px = q[2] if p.side == 1 else q[1]
                self._exit((q[0], px, px), reason, {"EXIT_TS": str(q[0])})
            else:
                synth_ts = pd.Timestamp(ev["ts"]) + pd.Timedelta(5, "min")
                self._exit((synth_ts, ev["c"], ev["c"]), reason,
                           {"EXIT_TS": str(synth_ts), "EXIT_UNPROVEN": True})
            return
        self.state = "PAPER_POSITION_OPEN"

    def _first_touch_quote(self, bq, start_i, side, stop):
        for k in range(max(start_i, 0), len(bq)):
            q = bq[k]
            if (side == 1 and q[1] <= stop) or (side == -1 and q[2] >= stop):
                return k
        return None

    def _exit(self, quote, reason, extra):
        p = self.pos
        qts, bid, ask = quote
        fills = {k: (bid if p.side == 1 else ask) -
                 SLIP_TICKS[k] * TICK * p.side for k in LEDGERS}
        trade = self.trades[-1]
        trade["EXIT_TS"] = str(qts)
        trade["EXIT_BID"] = bid
        trade["EXIT_ASK"] = ask
        trade["EXIT_SPREAD"] = round(ask - bid, 4)
        trade["EXIT_REASON"] = reason
        trade["EXIT"] = fills
        for k in LEDGERS:
            trade[f"PNL_{k}_PTS"] = round(
                p.side * (fills[k] - p.entry_shadows[k]) - FIXED_FEES_RT, 4)
        trail_txt = f"{p.trail:.2f}" if p.trail == p.trail else "n/a"
        trade["EXPLAIN"] = (
            f"O01 {'LONG' if p.side == 1 else 'SHORT'} entry {p.entry:.2f}, "
            f"stop {p.stop:.2f}, chandelier {trail_txt}, exit "
            f"{fills['BASE']:.2f} ({reason}); paper PnL BASE "
            f"{trade['PNL_BASE_PTS']:+.2f} pts")
        self._log(qts, "PAPER_EXIT", new_state="PAPER_EXITED", reason=reason,
                  fills=fills, pnl={k: trade[f"PNL_{k}_PTS"] for k in LEDGERS},
                  **extra)
        self.pos = PositionState()

    def _on_decision(self, ts, dec):
        if dec["decision"] == "TRADE":
            self.pending_entry = {"side": dec["side"], "stop": dec["stop"],
                                  "atr": dec["atr"],
                                  "activation_ts": str(dec["activation_ts"]),
                                  "z": dec["z"], "explain": dec["explain"]}
            self._log(ts, "SIGNAL", new_state="ORDER_PENDING",
                      side=dec["side"], stop=dec["stop"], z=dec["z"],
                      reason=dec["explain"])
        else:
            self._log(ts, "NO_TRADE", new_state="NO_SETUP",
                      reason=dec["reason"])

    def _log(self, ts, etype, **rec):
        rec.update({"event_type": etype, "ts": str(ts),
                    "previous_state": self.state})
        self.j.append(rec)
        self.state = rec.get("new_state", self.state)

    def status(self) -> dict:
        p = self.pos
        return {"O01_STATUS": {
            "CURRENT_CONTRACT": self.contract, "ENGINE_STATE": self.state,
            "POSITION": "FLAT" if p.side == 0 else
            ("LONG" if p.side == 1 else "SHORT"),
            "SIDE": p.side, "ENTRY": p.entry, "STOP": p.stop,
            "CHANDELIER": p.trail if p.trail == p.trail else None,
            "LAST_EVENT": self.seq, "PAPER_ONLY": PAPER_ONLY}}
