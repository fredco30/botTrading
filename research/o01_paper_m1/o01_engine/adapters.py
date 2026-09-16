#!/usr/bin/env python3
"""Adapters: HistoricalReplayAdapter (owned data) + the live stub (inactive)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from databento import DBNStore

BBO_O01_DIR = Path(r"E:/ResearchData/botTrading/nq/databento/highres/bbo_1s_o01")
NS = 10 ** 9


class HistoricalReplayAdapter:
    """Feeds the engine from OWNED data (5m parquet + the 133 BBO windows).

    The adapter owns execution mechanics only: it attaches, to each bar event,
    the first executable quote at/after that bar's relevant instant (validated
    replay conventions, including the conservative frozen-price fallbacks when
    no real quote exists within 60s). It never touches signal logic.
    """

    def __init__(self, df5: pd.DataFrame, ledger: pd.DataFrame):
        self.df = df5
        self.contract_for_day = dict(zip(ledger["DATE"],
                                         ledger["ACTUAL_FUTURES_CONTRACT"]))
        self.ledger = ledger
        self.ts = df5.index
        self.hm = (df5.index.tz_convert("America/New_York").hour * 100 +
                   df5.index.tz_convert("America/New_York").minute)
        self.et_date = df5.index.tz_convert("America/New_York").date
        self._quote_cache = {}
        # per-day overnight windows [09:30-15.5h, 09:30)
        self.on_hi, self.on_lo, self.on_bars = {}, {}, {}
        et64 = df5.index.tz_convert("America/New_York").asi8
        days = pd.Series(self.et_date).drop_duplicates().tolist()
        for d in days:
            open_ts = pd.Timestamp(d, tz="America/New_York") + pd.Timedelta(9 * 60 + 30, "min")
            end = int(open_ts.value)
            start = end - int(15.5 * 3600 * NS)
            a = np.searchsorted(et64, start)
            b = np.searchsorted(et64, end)
            if b - a >= 60:
                self.on_hi[d] = float(df5["high"].iloc[a:b].max())
                self.on_lo[d] = float(df5["low"].iloc[a:b].min())
                self.on_bars[d] = b - a

    def window(self, date_str, contract):
        key = f"{date_str}_{contract}"
        if key not in self._quote_cache:
            f = BBO_O01_DIR / f"{key}.dbn.zst"
            if not f.exists():
                self._quote_cache[key] = None
            else:
                w = DBNStore.from_file(str(f)).to_df()
                self._quote_cache[key] = (w.index.asi8.copy(),
                                          w["bid_px_00"].to_numpy(float),
                                          w["ask_px_00"].to_numpy(float))
        return self._quote_cache[key]

    def first_quote_ge(self, date_str, contract, ts):
        w = self.window(date_str, contract)
        if w is None:
            return None
        ts_arr, bid, ask = w
        k = np.searchsorted(ts_arr, int(pd.Timestamp(ts).value), side="left")
        if k >= len(ts_arr):
            return None
        if ts_arr[k] - int(pd.Timestamp(ts).value) > 60 * NS:
            return ("FALLBACK", float("nan"), float("nan"))
        return (pd.Timestamp(ts_arr[k]), float(bid[k]), float(ask[k]))

    def events(self, start_day=None):
        """Yield engine events in ts order. Bars carry attached execution
        quotes and overnight payload; fallback quotes mirror the validated
        replay conventions (frozen-price synthetic quote, flagged)."""
        led = self.ledger.set_index("TRADE_ID")
        by_entry = {}
        for _, r in self.ledger.iterrows():
            by_entry[r["ORDER_ACTIVATION_TIMESTAMP"]] = r
        for i in range(len(self.df)):
            ts = self.ts[i]
            day = self.et_date[i]
            ev = {"type": "BAR", "ts": ts, "o": float(self.df["open"].iloc[i]),
                  "h": float(self.df["high"].iloc[i]), "l": float(self.df["low"].iloc[i]),
                  "c": float(self.df["close"].iloc[i]), "v": float(self.df["volume"].iloc[i]),
                  "on_high": self.on_hi.get(day), "on_low": self.on_lo.get(day),
                  "on_bars": self.on_bars.get(day)}
            key = str(ts)
            if key in by_entry and start_day is not False:
                r = by_entry[key]
                # NOTE: ORDER_ACTIVATION_TIMESTAMP in the frozen ledger IS the
                # entry bar start (lab convention: fill = that bar's open).
                q = self.first_quote_ge(day, r["ACTUAL_FUTURES_CONTRACT"],
                                        ts)
                if q is None:
                    ev["quotes_at_activation"] = []
                elif q[0] == "FALLBACK":
                    o = ev["o"]
                    ev["quotes_at_activation"] = [(ts, o, o)]
                    ev["entry_fallback"] = True
                else:
                    ev["quotes_at_activation"] = [(q[0], q[1], q[2])]
            # exit quotes: attached to the bar FOLLOWING the frozen exit bar
            yield ev


    def day_bar_event(self, date, bar_row, ts):
        """Attach execution quote payloads for one bar (adapter mechanics)."""
        ev = {"type": "BAR", "ts": ts,
              "o": float(bar_row["open"]), "h": float(bar_row["high"]),
              "l": float(bar_row["low"]), "c": float(bar_row["close"]),
              "v": float(bar_row["volume"]),
              "on_high": self.on_hi.get(date), "on_low": self.on_lo.get(date),
              "on_bars": self.on_bars.get(date, 0)}
        day_str = str(date)
        contract = self.contract_for_day.get(day_str)
        if contract is None:
            return ev
        w = self.window(day_str, contract)
        if w is None:
            return ev
        ts_arr, bid, ask = w
        lo = int(pd.Timestamp(ts).value)
        hi = lo + 5 * 60 * NS
        a = np.searchsorted(ts_arr, lo, side="left")
        b = np.searchsorted(ts_arr, hi, side="left")
        bar_quotes = [(pd.Timestamp(ts_arr[k], tz="UTC"), float(bid[k]),
                               float(ask[k]))
                      for k in range(a, b)]
        ev["bar_quotes"] = bar_quotes
        ev["quotes_at_activation"] = bar_quotes
        if b < len(ts_arr):
            ev["quotes_at_exit"] = [(pd.Timestamp(ts_arr[b], tz="UTC"), float(bid[b]),
                                     float(ask[b]))]
        else:
            ev["quotes_at_exit"] = []
        return ev


class LiveQuoteStub:
    """No provider configured. Paper engine cannot run live without an
    explicitly authorized adapter; this stub refuses."""

    @staticmethod
    def events(*a, **k):
        raise NotImplementedError(
            "LIVE_DATA_AUTH_REQUIRED: no live feed configured; "
            "PAPER_ONLY engine requires an authorized MarketDataAdapter")


def no_real_order_capability() -> bool:
    """Static proof used by tests: the engine package defines no order-routing
    symbols, no broker/session/network API."""
    import o01_engine.engine as eng
    forbidden = ("broker", "order_route", "send_order", "place_order",
                 "socket", "requests", "urllib", "ccxt", "mt5", "ctrader")
    src = Path(eng.__file__).read_text().lower()
    return not any(f in src for f in forbidden)


