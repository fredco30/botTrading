#!/usr/bin/env python3
"""CANONICAL_RESEARCH_ENGINE — V1 (branch research/causal-engine-v1)

Causal, deterministic, cost-explicit research backtest engine.
Full contract: RESEARCH_ENGINE_SPEC.md.

Core guarantees
---------------
* Decision timeline: a decision taken at the open of bar i may only use
  fully closed bars [0 .. i-1] (M15) and closed H1 buckets whose close
  time <= open time of bar i.  LEGACY_MT4_USED_FORMING_H1=YES,
  RESEARCH_ENGINE_USES_CLOSED_H1=YES.  Any access to future data through
  the strategy view raises CausalityError.
* Entry executes at open[i] on the execution side (Ask for long, Bid for
  short) plus adverse slippage.  ENTRY USES NO FUTURE DATA.
* Input OHLC is treated explicitly as Bid.  Ask = Bid + spread (fixed,
  SYNTHETIC: no historical spread series exists in the repository).
* Parametric costs, fully decomposed:
      NET = GROSS - SPREAD_COST - SLIPPAGE_COST - COMMISSION_COST
* Gaps through stops fill at the first executable (worse) price.
* Intra-bar ambiguity (unknown OHLC path) resolves CONSERVATIVELY
  (worst outcome compatible with the bar) and is counted
  (AMBIGUOUS_BARS / AMBIGUOUS_TRADES).
* No pyramid / martingale / reverse.  Single position.  Fixed lot or
  fixed-risk-percent sizing.  100% deterministic.

This engine is intentionally NOT a replication of the legacy MT4 EAs
(which used forming H1 bars).  Legacy engines bt_engine.py / bt_fast.py
are preserved untouched for traceability.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

ENGINE_ID = "CANONICAL_RESEARCH_ENGINE_V1"
__version__ = "1.0.0"

INTRABAR_POLICY_CONSERVATIVE = "CONSERVATIVE"
SUPPORTED_INTRABAR_POLICIES = (INTRABAR_POLICY_CONSERVATIVE,)

AMBIGUOUS_SL_AND_TP = "SL_AND_TP_SAME_BAR"
AMBIGUOUS_BE_TRIGGER_AND_SL = "BE_TRIGGER_AND_SL_SAME_BAR"
AMBIGUOUS_BE_TRIGGER_AND_BE_STOP = "BE_TRIGGER_AND_BE_STOP_SAME_BAR"


class EngineError(Exception):
    """Invalid configuration or input data."""


class CausalityError(EngineError):
    """Attempt to read data that is not yet known at decision time."""


# ---------------------------------------------------------------------------
# Instrument specification (nothing pip/value-related is hard-coded elsewhere)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class InstrumentSpec:
    """Minimal instrument description.

    ASSUMPTION (V1): quote_currency == account_currency; no FX conversion is
    modeled.  tick_value is expressed in account currency.  Instruments with
    a different quote currency (USDJPY, XAUUSD...) require a conversion hook
    before being enabled — the fields exist so the architecture supports them.
    """

    symbol: str
    pip_size: float
    tick_size: float
    tick_value: float          # account currency per tick, per standard lot
    lot_size: int = 100_000
    min_lot: float = 0.01
    lot_step: float = 0.01
    max_lot: float = 100.0
    quote_currency: str = "USD"
    account_currency: str = "USD"

    def __post_init__(self) -> None:
        if self.pip_size <= 0 or self.tick_size <= 0 or self.tick_value <= 0:
            raise EngineError("instrument sizes/values must be > 0")
        if self.min_lot <= 0 or self.lot_step <= 0 or self.max_lot < self.min_lot:
            raise EngineError("invalid lot constraints")

    @property
    def pip_value_per_lot(self) -> float:
        """Account-currency value of one pip for one standard lot."""
        return (self.pip_size / self.tick_size) * self.tick_value


EURUSD_SPEC = InstrumentSpec(
    symbol="EURUSD", pip_size=0.0001, tick_size=0.00001, tick_value=1.0,
)

_INSTRUMENTS = {"EURUSD": EURUSD_SPEC}


def get_instrument(symbol: str) -> InstrumentSpec:
    try:
        return _INSTRUMENTS[symbol.upper()]
    except KeyError:
        raise EngineError(
            f"unknown instrument {symbol!r}; enabled: {sorted(_INSTRUMENTS)}"
        ) from None


# ---------------------------------------------------------------------------
# Cost model — parametric, deterministic
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CostModel:
    """Execution costs.  Nothing broker-specific is hard-coded.

    spread is SYNTHETIC in V1 (Bid-only OHLC inputs; no historical spread
    series available).  The engine never claims a fixed spread is realistic.
    """

    spread_mode: str = "fixed"                 # V1: "fixed" only
    spread_pips: float = 1.0                   # SYNTHETIC
    commission_per_lot_per_side: float = 0.0   # account currency, per fill
    adverse_slippage_pips: float = 0.0         # deterministic, always adverse

    def __post_init__(self) -> None:
        if self.spread_mode != "fixed":
            raise EngineError("V1 supports spread_mode='fixed' only")
        if (self.spread_pips < 0 or self.commission_per_lot_per_side < 0
                or self.adverse_slippage_pips < 0):
            raise EngineError("costs must be >= 0")


@dataclass(frozen=True)
class SizingConfig:
    mode: str = "fixed_lot"        # "fixed_lot" | "fixed_risk_percent"
    fixed_lot: float = 0.10
    risk_percent: float = 1.0      # % of current balance, compounded on close

    def __post_init__(self) -> None:
        if self.mode not in ("fixed_lot", "fixed_risk_percent"):
            raise EngineError("sizing mode must be fixed_lot|fixed_risk_percent")
        if self.fixed_lot <= 0 or self.risk_percent <= 0:
            raise EngineError("sizing parameters must be > 0")


@dataclass(frozen=True)
class BreakevenConfig:
    enabled: bool = False
    trigger_r: float = 1.5         # arm BE when favorable move >= trigger_r * risk
    offset_pips: float = 1.0       # new stop = entry_exec +/- offset

    def __post_init__(self) -> None:
        if self.enabled and (self.trigger_r <= 0 or self.offset_pips < 0):
            raise EngineError("invalid breakeven parameters")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Bar:
    dt: datetime    # OPEN time of the bar (server-time convention, tz unspecified)
    open: float     # Bid
    high: float     # Bid
    low: float      # Bid
    close: float    # Bid


@dataclass(frozen=True)
class ClosedH1Bar:
    close_dt: datetime  # END of the hour bucket = instant the bucket is fully known
    open: float
    high: float
    low: float
    close: float


def load_bars_csv(path: str, skip_malformed: bool = False) -> List[Bar]:
    """Load an MT4-style CSV (date,time,open,high,low,close[,volume]).

    Values are Bid OHLC.  Strictly validates chronology (monotonic, no
    duplicates) and OHLC sanity.  Pure stdlib: deterministic, read-only.
    """
    bars: List[Bar] = []
    prev_dt: Optional[datetime] = None
    with open(path, "r", newline="") as fh:
        for row in csv.reader(fh):
            if not row or all(not c.strip() for c in row):
                continue
            if len(row) < 6:
                if skip_malformed:
                    continue
                raise EngineError(f"malformed CSV row: {row!r}")
            try:
                dt = datetime.strptime(f"{row[0]} {row[1]}", "%Y.%m.%d %H:%M")
                o, h, lo, c = (float(x) for x in row[2:6])
            except ValueError as exc:
                if skip_malformed:
                    continue
                raise EngineError(f"malformed CSV row {row!r}: {exc}") from None
            if h < lo or h < max(o, c) - 1e-12 or lo > min(o, c) + 1e-12:
                if skip_malformed:
                    continue
                raise EngineError(f"OHLC inconsistency at {dt}: {row!r}")
            if prev_dt is not None and dt <= prev_dt:
                raise EngineError(f"non-monotonic timestamps at {dt}")
            prev_dt = dt
            bars.append(Bar(dt, o, h, lo, c))
    if not bars:
        raise EngineError("no valid bars loaded")
    return bars


def build_closed_h1(bars: List[Bar]) -> List[ClosedH1Bar]:
    """Aggregate M15 bars into CLOSED H1 buckets.

    A bucket covering [h, h+1) is published with close_dt = h+1:00 — the
    instant at which it is fully known.  Only bars with dt in the bucket
    contribute; no forming bucket is ever returned.
    """
    acc: Dict[datetime, List[float]] = {}
    for b in bars:
        key = b.dt.replace(minute=0, second=0, microsecond=0)
        cur = acc.get(key)
        if cur is None:
            acc[key] = [b.open, b.high, b.low, b.close]
        else:
            cur[1] = max(cur[1], b.high)
            cur[2] = min(cur[2], b.low)
            cur[3] = b.close  # last close of the bucket
    return [
        ClosedH1Bar(k + timedelta(hours=1), *acc[k]) for k in sorted(acc)
    ]


# ---------------------------------------------------------------------------
# Causal indicators (use values[0..t] only; NaN until warm-up complete)
# ---------------------------------------------------------------------------
def ema(values: List[float], period: int) -> List[float]:
    """EMA seeded with the SMA of the first `period` values (causal)."""
    n = len(values)
    out = [float("nan")] * n
    if n < period or period <= 0:
        return out
    alpha = 2.0 / (period + 1.0)
    out[period - 1] = sum(values[:period]) / period
    for t in range(period, n):
        out[t] = alpha * values[t] + (1.0 - alpha) * out[t - 1]
    return out


def rsi_wilder(values: List[float], period: int = 14) -> List[float]:
    """Wilder RSI (causal)."""
    n = len(values)
    out = [float("nan")] * n
    if n < period + 1:
        return out
    gains = losses = 0.0
    for t in range(1, period + 1):
        d = values[t] - values[t - 1]
        gains += max(d, 0.0)
        losses += max(-d, 0.0)
    ag, al = gains / period, losses / period
    out[period] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    for t in range(period + 1, n):
        d = values[t] - values[t - 1]
        ag = (ag * (period - 1) + max(d, 0.0)) / period
        al = (al * (period - 1) + max(-d, 0.0)) / period
        out[t] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def atr_wilder(highs: List[float], lows: List[float], closes: List[float],
               period: int = 14) -> List[float]:
    """Wilder ATR (causal)."""
    n = len(closes)
    out = [float("nan")] * n
    if n < period + 1:
        return out
    trs = [highs[0] - lows[0]]
    for t in range(1, n):
        trs.append(max(highs[t] - lows[t],
                       abs(highs[t] - closes[t - 1]),
                       abs(lows[t] - closes[t - 1])))
    val = sum(trs[1:period + 1]) / period
    out[period] = val
    for t in range(period + 1, n):
        val = (val * (period - 1) + trs[t]) / period
        out[t] = val
    return out


# ---------------------------------------------------------------------------
# Causally bounded views (any future access raises CausalityError)
# ---------------------------------------------------------------------------
class _BoundedSeries:
    __slots__ = ("_opens", "_highs", "_lows", "_closes", "_dts", "_n")

    def __init__(self, opens, highs, lows, closes, dts, n: int) -> None:
        self._opens, self._highs = opens, highs
        self._lows, self._closes, self._dts = lows, closes, dts
        self._n = n

    def __len__(self) -> int:
        return self._n

    def _chk(self, t: int) -> None:
        if not 0 <= t < self._n:
            raise CausalityError(
                f"access at index {t} beyond the {self._n} closed bars "
                f"known at decision time"
            )

    def open(self, t: int) -> float:
        self._chk(t); return self._opens[t]

    def high(self, t: int) -> float:
        self._chk(t); return self._highs[t]

    def low(self, t: int) -> float:
        self._chk(t); return self._lows[t]

    def close(self, t: int) -> float:
        self._chk(t); return self._closes[t]

    def dt(self, t: int) -> datetime:
        self._chk(t); return self._dts[t]


class ClosedH1Series(_BoundedSeries):
    __slots__ = ()

    def close_dt(self, t: int) -> datetime:
        self._chk(t)
        return self._dts[t]  # dts are close times for H1 buckets


@dataclass(frozen=True)
class CausalContext:
    """Everything a strategy may know at the open of bar i — and nothing more."""
    i: int
    decision_ts: datetime
    open_bid: float          # execution reference price of bar i (Bid side)
    m15: _BoundedSeries      # fully closed bars [0 .. i-1]
    h1: ClosedH1Series       # closed H1 buckets with close_dt <= decision_ts
    instrument: InstrumentSpec
    costs: CostModel


# ---------------------------------------------------------------------------
# Strategy interface
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Order:
    direction: int           # +1 long, -1 short
    sl_price: float          # exit-side price: Bid level for long, Ask for short
    tp_price: Optional[float] = None
    comment: str = ""


class Strategy:
    def on_bar(self, ctx: CausalContext) -> Optional[Order]:
        raise NotImplementedError


class NullStrategy(Strategy):
    """Reference no-op strategy (used by the technical smoke test)."""

    def on_bar(self, ctx: CausalContext) -> Optional[Order]:
        return None


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------
@dataclass
class TradeRecord:
    direction: int
    decision_ts: datetime
    entry_ts: datetime
    entry_ref: float          # mid reference at entry
    entry_exec: float         # actual executed price (side + slippage)
    initial_sl: float
    tp: Optional[float]
    lots: float
    exit_ts: datetime
    exit_ref: float
    exit_exec: float
    exit_reason: str          # SL | TP | BE | END_OF_DATA
    gap_exit: bool
    gross_pnl: float
    spread_cost: float
    slippage_cost: float
    commission_cost: float
    net_pnl: float
    ambiguous_events: int
    balance_after: float


@dataclass
class RunResult:
    engine_id: str
    symbol: str
    intrabar_policy: str
    n_bars_processed: int
    trades: List[TradeRecord]
    ambiguous_bars: int
    ambiguous_trades: int
    ambiguity_event_counts: Dict[str, int]
    forced_closes: int
    orders_ignored: int
    initial_balance: float
    final_balance: float
    total_gross_pnl: float
    total_spread_cost: float
    total_slippage_cost: float
    total_commission_cost: float
    total_net_pnl: float
    costs: CostModel
    sizing: SizingConfig
    breakeven: BreakevenConfig

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    @property
    def wins(self) -> int:
        return sum(1 for t in self.trades if t.net_pnl > 0)

    @property
    def losses(self) -> int:
        return sum(1 for t in self.trades if t.net_pnl <= 0)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
class _Position:
    __slots__ = ("direction", "decision_ts", "entry_ts", "entry_ref",
                 "entry_exec", "initial_sl", "sl", "tp", "lots", "risk_dist",
                 "be_done", "slip_in", "amb_start")

    def __init__(self, direction, decision_ts, entry_ts, entry_ref,
                 entry_exec, sl, tp, lots, risk_dist, slip_in, amb_start) -> None:
        self.direction = direction
        self.decision_ts = decision_ts
        self.entry_ts = entry_ts
        self.entry_ref = entry_ref
        self.entry_exec = entry_exec
        self.initial_sl = sl
        self.sl = sl
        self.tp = tp
        self.lots = lots
        self.risk_dist = risk_dist
        self.be_done = False
        self.slip_in = slip_in
        self.amb_start = amb_start  # ambiguity events before this position


class ResearchEngine:
    """Deterministic causal backtest engine (single position, V1 policy set)."""

    def __init__(self,
                 instrument: InstrumentSpec,
                 costs: CostModel,
                 sizing: SizingConfig,
                 breakeven: BreakevenConfig = BreakevenConfig(),
                 intrabar_policy: str = INTRABAR_POLICY_CONSERVATIVE,
                 initial_balance: float = 10_000.0) -> None:
        if intrabar_policy not in SUPPORTED_INTRABAR_POLICIES:
            raise EngineError(
                f"intrabar policy {intrabar_policy!r} not supported in V1; "
                f"supported: {SUPPORTED_INTRABAR_POLICIES}"
            )
        self.instrument = instrument
        self.costs = costs
        self.sizing = sizing
        self.breakeven = breakeven
        self.intrabar_policy = intrabar_policy
        self.initial_balance = float(initial_balance)

        self._pip = instrument.pip_size
        self._pip_value = instrument.pip_value_per_lot
        self._conv = self._pip_value / self._pip          # money per 1.0 price per lot
        self._spread_price = costs.spread_pips * self._pip
        self._half_spread = self._spread_price / 2.0
        self._slip_price = costs.adverse_slippage_pips * self._pip
        self._commission = costs.commission_per_lot_per_side

        # reset per run
        self._balance = self.initial_balance
        self._trades: List[TradeRecord] = []
        self._amb_events: List[str] = []
        self._forced_closes = 0
        self._orders_ignored = 0

    # -- public ------------------------------------------------------------
    def run(self, bars: List[Bar], strategy: Strategy,
            start_dt: Optional[datetime] = None,
            end_dt: Optional[datetime] = None) -> RunResult:
        if not bars:
            raise EngineError("empty bar list")
        for a, b in zip(bars, bars[1:]):
            if b.dt <= a.dt:
                raise EngineError("bars must be strictly chronologically sorted")

        self._balance = self.initial_balance
        self._trades = []
        self._amb_events = []
        self._forced_closes = 0
        self._orders_ignored = 0

        lo = 0 if start_dt is None else max(
            0, next((k for k, b in enumerate(bars) if b.dt >= start_dt), len(bars)))
        hi = len(bars) if end_dt is None else next(
            (k for k, b in enumerate(bars) if b.dt >= end_dt), len(bars))
        window = bars[lo:hi]
        n = len(window)
        if n == 0:
            raise EngineError("empty run window")

        opens = [b.open for b in window]
        highs = [b.high for b in window]
        lows = [b.low for b in window]
        closes = [b.close for b in window]
        dts = [b.dt for b in window]
        h1 = build_closed_h1(window)
        h1_opens = [h.open for h in h1]
        h1_highs = [h.high for h in h1]
        h1_lows = [h.low for h in h1]
        h1_closes = [h.close for h in h1]
        h1_close_dts = [h.close_dt for h in h1]

        pos: Optional[_Position] = None
        h1_ptr = 0  # number of closed H1 buckets known so far

        for i in range(n):
            t = dts[i]
            while h1_ptr < len(h1) and h1_close_dts[h1_ptr] <= t:
                h1_ptr += 1
            ctx = CausalContext(
                i=i, decision_ts=t, open_bid=opens[i],
                m15=_BoundedSeries(opens, highs, lows, closes, dts, i),
                h1=ClosedH1Series(h1_opens, h1_highs, h1_lows, h1_closes,
                                  h1_close_dts, h1_ptr),
                instrument=self.instrument, costs=self.costs,
            )

            order = strategy.on_bar(ctx)
            if order is not None:
                if pos is not None:
                    self._orders_ignored += 1
                else:
                    pos = self._open_position(order, opens[i], t)

            if pos is not None:
                pos = self._manage_bar(pos, i, opens, highs, lows, closes, dts)

        if pos is not None:
            self._force_close(pos, n - 1, closes, dts)

        gross = 0.0
        spr = 0.0
        slp = 0.0
        com = 0.0
        for tr in self._trades:
            gross += tr.gross_pnl
            spr += tr.spread_cost
            slp += tr.slippage_cost
            com += tr.commission_cost
        amb_counts: Dict[str, int] = {}
        for ev in self._amb_events:
            amb_counts[ev] = amb_counts.get(ev, 0) + 1

        return RunResult(
            engine_id=ENGINE_ID,
            symbol=self.instrument.symbol,
            intrabar_policy=self.intrabar_policy,
            n_bars_processed=n,
            trades=self._trades,
            ambiguous_bars=len(self._amb_events),
            ambiguous_trades=sum(1 for tr in self._trades if tr.ambiguous_events > 0),
            ambiguity_event_counts=dict(sorted(amb_counts.items())),
            forced_closes=self._forced_closes,
            orders_ignored=self._orders_ignored,
            initial_balance=self.initial_balance,
            final_balance=self._balance,
            total_gross_pnl=gross,
            total_spread_cost=spr,
            total_slippage_cost=slp,
            total_commission_cost=com,
            total_net_pnl=gross - spr - slp - com,
            costs=self.costs,
            sizing=self.sizing,
            breakeven=self.breakeven,
        )

    # -- internals -----------------------------------------------------------
    def _lots_for(self, entry_exec: float, sl_price: float, direction: int) -> float:
        inst = self.instrument
        risk_dist = abs(entry_exec - sl_price)
        if self.sizing.mode == "fixed_lot":
            lots = self.sizing.fixed_lot
        else:
            risk_money = self._balance * self.sizing.risk_percent / 100.0
            raw = risk_money / (risk_dist * self._conv) if risk_dist > 0 else 0.0
            lots = math.floor(raw / inst.lot_step) * inst.lot_step
            if lots < inst.min_lot:
                lots = inst.min_lot  # ASSUMPTION: clamp, do not reject (legacy-like)
        lots = math.floor(lots / inst.lot_step) * inst.lot_step
        return min(inst.max_lot, max(inst.min_lot, lots))

    def _open_position(self, order: Order, open_bid: float, ts: datetime) -> _Position:
        if order.direction not in (1, -1):
            raise EngineError("order.direction must be +1 or -1")
        s, sp = self._spread_price, self._slip_price
        if order.direction == 1:
            entry_exec = open_bid + s + sp          # Ask + adverse slippage
            entry_ref = open_bid + self._half_spread  # mid
            if not order.sl_price < entry_exec:
                raise EngineError("long SL must be below entry")
            if order.tp_price is not None and not order.tp_price > entry_exec:
                raise EngineError("long TP must be above entry")
        else:
            entry_exec = open_bid - sp              # Bid - adverse slippage
            entry_ref = open_bid + self._half_spread  # mid
            if not order.sl_price > entry_exec:
                raise EngineError("short SL must be above entry")
            if order.tp_price is not None and not order.tp_price < entry_exec:
                raise EngineError("short TP must be below entry")
        risk_dist = abs(entry_exec - order.sl_price)
        lots = self._lots_for(entry_exec, order.sl_price, order.direction)
        return _Position(order.direction, ts, ts, entry_ref, entry_exec,
                         order.sl_price, order.tp_price, lots, risk_dist, sp,
                         len(self._amb_events))

    def _amb(self, kind: str) -> None:
        self._amb_events.append(kind)

    def _manage_bar(self, pos: _Position, j: int, opens, highs, lows, closes,
                    dts) -> Optional[_Position]:
        """Conservative intra-bar management of one bar (post-entry fill included)."""
        s, sp, hs = self._spread_price, self._slip_price, self._half_spread
        be = self.breakeven

        if pos.direction == 1:
            sl_hit = lows[j] <= pos.sl
            tp_hit = pos.tp is not None and highs[j] >= pos.tp
            be_trigger = (pos.entry_exec + be.trigger_r * pos.risk_dist) if (
                be.enabled and not pos.be_done) else None
            arm = be_trigger is not None and highs[j] >= be_trigger
            if sl_hit:
                if tp_hit:
                    self._amb(AMBIGUOUS_SL_AND_TP)
                if arm:
                    self._amb(AMBIGUOUS_BE_TRIGGER_AND_SL)
                gap = opens[j] < pos.sl
                fill = opens[j] if gap else pos.sl   # gap: first available (worse)
                self._close(pos, j, dts, exit_ref=fill + hs,
                            exit_exec=fill - sp, reason="BE" if pos.be_done else "SL",
                            gap=gap, slip_out=sp)
                return None
            if tp_hit:
                fill = max(pos.tp, opens[j])         # limit semantics: better on gap
                self._close(pos, j, dts, exit_ref=fill + hs, exit_exec=fill,
                            reason="TP", gap=fill > pos.tp, slip_out=0.0)
                return None
            if arm:
                be_stop = pos.entry_exec + be.offset_pips * self._pip
                if lows[j] <= be_stop:
                    # arming bar: never exit at the new BE stop in the same bar
                    self._amb(AMBIGUOUS_BE_TRIGGER_AND_BE_STOP)
                pos.be_done = True
                pos.sl = be_stop                      # effective from NEXT bar
            return pos

        # short
        ask_open = opens[j] + s
        sl_hit = (highs[j] + s) >= pos.sl
        tp_hit = pos.tp is not None and (lows[j] + s) <= pos.tp
        be_trigger = (pos.entry_exec - be.trigger_r * pos.risk_dist) if (
            be.enabled and not pos.be_done) else None
        arm = be_trigger is not None and (lows[j] + s) <= be_trigger
        if sl_hit:
            if tp_hit:
                self._amb(AMBIGUOUS_SL_AND_TP)
            if arm:
                self._amb(AMBIGUOUS_BE_TRIGGER_AND_SL)
            gap = ask_open > pos.sl
            fill = ask_open if gap else pos.sl
            self._close(pos, j, dts, exit_ref=fill - hs,
                        exit_exec=fill + sp, reason="BE" if pos.be_done else "SL",
                        gap=gap, slip_out=sp)
            return None
        if tp_hit:
            fill = min(pos.tp, ask_open)
            self._close(pos, j, dts, exit_ref=fill - hs, exit_exec=fill,
                        reason="TP", gap=fill < pos.tp, slip_out=0.0)
            return None
        if arm:
            be_stop = pos.entry_exec - be.offset_pips * self._pip
            if (highs[j] + s) >= be_stop:
                self._amb(AMBIGUOUS_BE_TRIGGER_AND_BE_STOP)
            pos.be_done = True
            pos.sl = be_stop                          # effective from NEXT bar
        return pos

    def _force_close(self, pos: _Position, j: int, closes, dts) -> None:
        s, sp, hs = self._spread_price, self._slip_price, self._half_spread
        if pos.direction == 1:
            self._close(pos, j, dts, exit_ref=closes[j] + hs,
                        exit_exec=closes[j] - sp, reason="END_OF_DATA",
                        gap=False, slip_out=sp)
        else:
            self._close(pos, j, dts, exit_ref=closes[j] + hs,
                        exit_exec=closes[j] + s + sp, reason="END_OF_DATA",
                        gap=False, slip_out=sp)
        self._forced_closes += 1

    def _close(self, pos: _Position, j: int, dts, exit_ref: float,
               exit_exec: float, reason: str, gap: bool, slip_out: float) -> None:
        d = pos.direction
        gross = d * (exit_ref - pos.entry_ref) * self._conv * pos.lots
        spread_cost = self._spread_price * self._conv * pos.lots
        slippage_cost = (pos.slip_in + slip_out) * self._conv * pos.lots
        commission_cost = 2.0 * self._commission * pos.lots
        net = gross - spread_cost - slippage_cost - commission_cost
        self._balance += net
        self._trades.append(TradeRecord(
            direction=d, decision_ts=pos.decision_ts, entry_ts=pos.entry_ts,
            entry_ref=pos.entry_ref, entry_exec=pos.entry_exec,
            initial_sl=pos.initial_sl, tp=pos.tp, lots=pos.lots,
            exit_ts=dts[j], exit_ref=exit_ref, exit_exec=exit_exec,
            exit_reason=reason, gap_exit=gap, gross_pnl=gross,
            spread_cost=spread_cost, slippage_cost=slippage_cost,
            commission_cost=commission_cost, net_pnl=net,
            ambiguous_events=len(self._amb_events) - pos.amb_start,
            balance_after=self._balance,
        ))
