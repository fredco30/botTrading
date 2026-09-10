#!/usr/bin/env python3
"""EMA_BASE_CORE_V1 — pre-registered pure signal component (Mission 2).

Answers only LONG / SHORT / NONE at the open of M15 bar i.

This component is a SIGNAL ONLY:
  * it opens no trade, sizes no lot, knows no capital;
  * it contains no pyramid, no reverse, no breakeven, no TP, no SL,
    no sessions, no hour/day filters, no ATR band, no EMA50-distance,
    no MaxTradesPerDay, no cooldown, no news filter, no optimization.

It depends only on the causal CausalContext provided by
research_engine.py.  Data accessible at decision time:
  * M15: fully closed bars up to i-1 inclusive (bounded view);
  * H1: only buckets fully closed at decision_ts (close_dt <= decision_ts).

Canonical definition (pre-registered BEFORE any performance observation,
reconstructed from EMA_Pullback_EA.mq4 / EMA_Pullback_pyramid*.mq4 /
bt_engine.py — see RESEARCH report Mission 0 and this file's gates):

  A. H1 TREND (closed H1 only; NO forming H1)
     last closed H1 close > EMA50(last closed bucket) AND
     EMA50(last) > EMA50(last - TrendBars)              -> LONG trend
     mirrored for SHORT trend.
  B. M15 PULLBACK on bar i-2
     LONG:  low[i-2]  <= EMA20[i-2]
     SHORT: high[i-2] >= EMA20[i-2]
  C. M15 REJECTION on bar i-1
     LONG:  close[i-1] > EMA20[i-1] AND close[i-1] > open[i-1]
     SHORT: close[i-1] < EMA20[i-1] AND close[i-1] < open[i-1]
     body ratio: (close-open)/(high-low) >= 0.60 (when range > 0)
     body(i-1) > body(i-2)
  D. RSI (Wilder 14) on bar i-1
     LONG allowed iff RSI <= 70 ; SHORT allowed iff RSI >= 30

Historical divergences reported (canonical choices are the CAUSAL ones,
consistent with bt_engine.py, NOT the MT4 forming-bar artifacts):
  * MT4 used FORMING H1 (shift 0) for EMA50/close/slope  -> closed H1 here;
  * MT4 compared close[i-1] to EMA20 at shift 0 (forming) -> EMA20[i-1] here;
  * zero-range i-1 bars: legacy skips the ratio check; such bars have
    open==close and are already rejected by the color condition, so the
    canonical gate order never reaches an undefined ratio.

Gate order below is for DIAGNOSTICS ONLY (which condition blocked the
signal); the final signal is unaffected by the order because ALL gates
must pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from research_engine import CausalContext

ENGINE_DEPENDENCY = "research_engine.CausalContext"
SIGNAL_ID = "EMA_BASE_CORE_V1"

# Pre-registration markers (Mission 2 contract)
PARAMETERS_FROZEN_BEFORE_RESULTS = True
LEGACY_DERIVED_PARAMETERS = True
HISTORICALLY_CONTAMINATED_PARAMETERS = True

# Post-hoc filters deliberately EXCLUDED from the signal core (they were
# selected after repeated observation of historical results and may only be
# studied later IF the raw signal survives its event study).
EXCLUDED_POSTHOC_FILTERS = [
    "ATR min/max band (H1)",
    "EMA50 distance max",
    "Friday block",
    "blocked hour 13",
    "toxic hour/day combinations",
    "Thursday risk reduction / multiplier",
    "MinSL / MaxSL bounds",
    "strategic spread filter",
    "MaxTradesPerDay",
    "London / NY session windows",
    "cooldown after consecutive losses",
    "news filter",
    "pullback size filter",
    "structure filter",
    "swing SL + pip buffer",
    "MinRR / take-profit",
    "breakeven",
    "pyramid L0/L1/L2",
    "reverse trades",
    "rolling WR cold-signal logic",
]


class SignalType(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"


@dataclass(frozen=True)
class EmaBaseCoreV1Params:
    """Frozen historical parameters, exposed for auditability ONLY.

    They derive from the legacy project (contaminated by historical
    observation).  They are NOT optimized in Mission 2 and will be frozen
    in the future event-study experiment.
    """

    h1_trend_ema_period: int = 50
    h1_trend_bars: int = 5
    m15_entry_ema_period: int = 20
    rsi_period: int = 14
    rsi_long_max: float = 70.0
    rsi_short_min: float = 30.0
    rejection_body_min: float = 0.60


@dataclass(frozen=True)
class SignalDiagnostic:
    """Deterministic, human-auditable explanation of one decision.

    For verification/audit ONLY — never for tuning.
    """
    decision_ts: object
    final_signal: SignalType
    warmup_m15_ema20_ready: bool
    warmup_m15_rsi_ready: bool
    warmup_h1_ema50_ready: bool
    warmup_h1_slope_ready: bool
    trend_long: Optional[bool]
    trend_short: Optional[bool]
    pullback_long: Optional[bool]
    pullback_short: Optional[bool]
    rejection_long: Optional[bool]
    rejection_short: Optional[bool]
    rsi_value: Optional[float]
    body_ratio: Optional[float]
    body_comparison: Optional[bool]      # body(i-1) > body(i-2)
    blocked_by: Tuple[str, ...] = field(default_factory=tuple)


def _alpha(period: int) -> float:
    return 2.0 / (period + 1.0)


class EmaBaseCoreV1:
    """Stateful, deterministic, causal signal evaluator.

    Feed it exactly once per M15 decision bar, in chronological order
    (research_engine guarantees this ordering).  Internal indicator state
    is updated incrementally from the bounded views; calling evaluate()
    twice with the same context is idempotent (no double consumption).
    """

    def __init__(self, params: Optional[EmaBaseCoreV1Params] = None) -> None:
        self.p = params or EmaBaseCoreV1Params()
        self.signal_id = SIGNAL_ID

        # M15 state: incremental EMA20 (last two closed-bar values) + Wilder RSI
        self._m15_n = 0
        self._m15_ema_seed: List[float] = []
        self._ema20_last: List[float] = []       # last two EMA values (b2, b1)
        self._rsi_n = 0
        self._rsi_seed_gains: List[float] = []
        self._rsi_seed_losses: List[float] = []
        self._prev_close: Optional[float] = None
        self._avg_gain: Optional[float] = None
        self._avg_loss: Optional[float] = None
        self._rsi: Optional[float] = None

        # H1 state: incremental EMA50 + history for slope
        self._h1_n = 0
        self._h1_ema_seed: List[float] = []
        self._ema50: Optional[float] = None
        self._ema50_hist: List[float] = []       # per closed bucket after seeding

    # -- incremental indicator state ---------------------------------------
    def _sync(self, ctx: CausalContext) -> None:
        m15, h1 = ctx.m15, ctx.h1
        p = self.p

        while self._m15_n < len(m15):
            c = m15.close(self._m15_n)
            # EMA20 (seed = SMA of first `period` closes, as in bt_engine)
            if len(self._m15_ema_seed) < p.m15_entry_ema_period:
                self._m15_ema_seed.append(c)
                if len(self._m15_ema_seed) == p.m15_entry_ema_period:
                    v = sum(self._m15_ema_seed) / p.m15_entry_ema_period
                    self._ema20_last = [v]
            else:
                a = _alpha(p.m15_entry_ema_period)
                v = a * c + (1.0 - a) * self._ema20_last[-1]
                self._ema20_last.append(v)
                if len(self._ema20_last) > 2:
                    self._ema20_last.pop(0)
            # Wilder RSI (seed = mean of first `period` deltas)
            self._update_rsi(c)
            self._m15_n += 1

        while self._h1_n < len(h1):
            c = h1.close(self._h1_n)
            if len(self._h1_ema_seed) < p.h1_trend_ema_period:
                self._h1_ema_seed.append(c)
                if len(self._h1_ema_seed) == p.h1_trend_ema_period:
                    self._ema50 = sum(self._h1_ema_seed) / p.h1_trend_ema_period
                    self._ema50_hist = [self._ema50]
            else:
                a = _alpha(p.h1_trend_ema_period)
                self._ema50 = a * c + (1.0 - a) * self._ema50
                self._ema50_hist.append(self._ema50)
                if len(self._ema50_hist) > p.h1_trend_bars + 1:
                    self._ema50_hist.pop(0)
            self._h1_n += 1

    def _update_rsi(self, c: float) -> None:
        p = self.p
        if self._prev_close is None:
            self._prev_close = c
            return
        delta = c - self._prev_close
        self._prev_close = c
        if self._avg_gain is None:
            if delta > 0:
                self._rsi_seed_gains.append(delta)
            else:
                self._rsi_seed_losses.append(-delta)
            self._rsi_n += 1
            if self._rsi_n == p.rsi_period:
                self._avg_gain = sum(self._rsi_seed_gains) / p.rsi_period
                self._avg_loss = sum(self._rsi_seed_losses) / p.rsi_period
                self._rsi = self._rsi_from(self._avg_gain, self._avg_loss)
            return
        self._avg_gain = (self._avg_gain * (p.rsi_period - 1) + max(delta, 0.0)) / p.rsi_period
        self._avg_loss = (self._avg_loss * (p.rsi_period - 1) + max(-delta, 0.0)) / p.rsi_period
        self._rsi = self._rsi_from(self._avg_gain, self._avg_loss)

    @staticmethod
    def _rsi_from(avg_gain: float, avg_loss: float) -> float:
        if avg_loss == 0:
            return 100.0  # legacy convention: rs = inf -> RSI 100
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    # -- public --------------------------------------------------------------
    def warmup_requirements(self) -> dict:
        """Minimum data before ANY signal is admissible (NONE otherwise)."""
        p = self.p
        return {
            "m15_ema20_closed_bars": p.m15_entry_ema_period + 1,   # EMA at i-1 AND i-2
            "m15_rsi_closed_bars": p.rsi_period + 1,               # RSI at i-1
            "h1_ema50_closed_buckets": p.h1_trend_ema_period,
            "h1_slope_closed_buckets": p.h1_trend_ema_period + p.h1_trend_bars,
            "combined_m15_bars": p.m15_entry_ema_period + 1,
            "combined_h1_buckets": p.h1_trend_ema_period + p.h1_trend_bars,
            "note": "If any requirement is unmet the signal is NONE; "
                    "no artificial values are used.",
        }

    def on_bar(self, ctx: CausalContext) -> SignalType:
        return self.evaluate(ctx).final_signal

    def evaluate(self, ctx: CausalContext) -> SignalDiagnostic:
        self._sync(ctx)
        p = self.p
        blocked: List[str] = []

        # ---- warm-up gates -------------------------------------------------
        ema_ready = len(self._ema20_last) == 2
        rsi_ready = self._rsi is not None
        h1_ema_ready = self._ema50 is not None
        h1_slope_ready = len(self._ema50_hist) == p.h1_trend_bars + 1
        if not ema_ready:
            blocked.append("M15_EMA20_NOT_WARM")
        if not rsi_ready:
            blocked.append("M15_RSI_NOT_WARM")
        if not h1_ema_ready:
            blocked.append("H1_EMA50_NOT_WARM")
        if not h1_slope_ready:
            blocked.append("H1_SLOPE_NOT_WARM")
        if blocked:
            return self._diag(ctx, SignalType.NONE, blocked, ema_ready, rsi_ready,
                              h1_ema_ready, h1_slope_ready, None, None, None,
                              None, None, None)

        # ---- features on closed bars only ----------------------------------
        n = len(ctx.m15)
        b1, b2 = n - 1, n - 2                 # historical i-1 and i-2
        c1, o1 = ctx.m15.close(b1), ctx.m15.open(b1)
        hi1, lo1 = ctx.m15.high(b1), ctx.m15.low(b1)
        c2, o2 = ctx.m15.close(b2), ctx.m15.open(b2)
        lo2, hi2 = ctx.m15.low(b2), ctx.m15.high(b2)
        e1, e2 = self._ema20_last[-1], self._ema20_last[0]
        rsi_v = self._rsi

        last_h1_close = ctx.h1.close(len(ctx.h1) - 1)
        ema50_now = self._ema50_hist[-1]
        ema50_prev = self._ema50_hist[0]      # TrendBars H1 buckets back

        trend_long = last_h1_close > ema50_now and ema50_now > ema50_prev
        trend_short = last_h1_close < ema50_now and ema50_now < ema50_prev

        pullback_long = lo2 <= e2
        pullback_short = hi2 >= e2
        rejection_long = c1 > e1 and c1 > o1
        rejection_short = c1 < e1 and c1 < o1
        body1, body2 = abs(c1 - o1), abs(c2 - o2)
        range1 = hi1 - lo1
        body_ratio = (body1 / range1) if range1 > 0 else None  # legacy: skipped if 0

        if not trend_long and not trend_short:
            return self._diag(ctx, SignalType.NONE, ["TREND_ABSENT"], ema_ready,
                              rsi_ready, h1_ema_ready, h1_slope_ready,
                              trend_long, trend_short, pullback_long,
                              pullback_short, rejection_long, rejection_short,
                              rsi_v, body_ratio, None)

        direction = 1 if trend_long else -1

        # ---- direction gates (order = diagnostics only) ---------------------
        if direction == 1:
            if not pullback_long:
                return self._diag(ctx, SignalType.NONE, ["PULLBACK_LONG"], ema_ready,
                                  rsi_ready, h1_ema_ready, h1_slope_ready,
                                  trend_long, trend_short, pullback_long,
                                  pullback_short, rejection_long, rejection_short,
                                  rsi_v, body_ratio, None)
            if not rejection_long:
                return self._diag(ctx, SignalType.NONE, ["REJECTION_LONG"], ema_ready,
                                  rsi_ready, h1_ema_ready, h1_slope_ready,
                                  trend_long, trend_short, pullback_long,
                                  pullback_short, rejection_long, rejection_short,
                                  rsi_v, body_ratio, None)
            if body_ratio is None or body_ratio < p.rejection_body_min:
                return self._diag(ctx, SignalType.NONE, ["BODY_RATIO_LONG"], ema_ready,
                                  rsi_ready, h1_ema_ready, h1_slope_ready,
                                  trend_long, trend_short, pullback_long,
                                  pullback_short, rejection_long, rejection_short,
                                  rsi_v, body_ratio, None)
            body_cmp = body1 > body2
            if not body_cmp:
                return self._diag(ctx, SignalType.NONE, ["BODY_COMPARISON_LONG"],
                                  ema_ready, rsi_ready, h1_ema_ready, h1_slope_ready,
                                  trend_long, trend_short, pullback_long,
                                  pullback_short, rejection_long, rejection_short,
                                  rsi_v, body_ratio, body_cmp)
            if rsi_v > p.rsi_long_max:
                return self._diag(ctx, SignalType.NONE, ["RSI_LONG_OVER_MAX"],
                                  ema_ready, rsi_ready, h1_ema_ready, h1_slope_ready,
                                  trend_long, trend_short, pullback_long,
                                  pullback_short, rejection_long, rejection_short,
                                  rsi_v, body_ratio, body_cmp)
            return self._diag(ctx, SignalType.LONG, [], ema_ready, rsi_ready,
                              h1_ema_ready, h1_slope_ready,
                              trend_long, trend_short, pullback_long,
                              pullback_short, rejection_long, rejection_short,
                              rsi_v, body_ratio, body_cmp)

        # direction == -1
        if not pullback_short:
            return self._diag(ctx, SignalType.NONE, ["PULLBACK_SHORT"], ema_ready,
                              rsi_ready, h1_ema_ready, h1_slope_ready,
                              trend_long, trend_short, pullback_long,
                              pullback_short, rejection_long, rejection_short,
                              rsi_v, body_ratio, None)
        if not rejection_short:
            return self._diag(ctx, SignalType.NONE, ["REJECTION_SHORT"], ema_ready,
                              rsi_ready, h1_ema_ready, h1_slope_ready,
                              trend_long, trend_short, pullback_long,
                              pullback_short, rejection_long, rejection_short,
                              rsi_v, body_ratio, None)
        if body_ratio is None or body_ratio < p.rejection_body_min:
            return self._diag(ctx, SignalType.NONE, ["BODY_RATIO_SHORT"], ema_ready,
                              rsi_ready, h1_ema_ready, h1_slope_ready,
                              trend_long, trend_short, pullback_long,
                              pullback_short, rejection_long, rejection_short,
                              rsi_v, body_ratio, None)
        body_cmp = body1 > body2
        if not body_cmp:
            return self._diag(ctx, SignalType.NONE, ["BODY_COMPARISON_SHORT"],
                              ema_ready, rsi_ready, h1_ema_ready, h1_slope_ready,
                              trend_long, trend_short, pullback_long,
                              pullback_short, rejection_long, rejection_short,
                              rsi_v, body_ratio, body_cmp)
        if rsi_v < p.rsi_short_min:
            return self._diag(ctx, SignalType.NONE, ["RSI_SHORT_UNDER_MIN"],
                              ema_ready, rsi_ready, h1_ema_ready, h1_slope_ready,
                              trend_long, trend_short, pullback_long,
                              pullback_short, rejection_long, rejection_short,
                              rsi_v, body_ratio, body_cmp)
        return self._diag(ctx, SignalType.SHORT, [], ema_ready, rsi_ready,
                          h1_ema_ready, h1_slope_ready,
                          trend_long, trend_short, pullback_long,
                          pullback_short, rejection_long, rejection_short,
                          rsi_v, body_ratio, body_cmp)

    # -- diagnostic helper -----------------------------------------------------
    def _diag(self, ctx, signal, blocked, ema_ready, rsi_ready, h1_ema_ready,
              h1_slope_ready, trend_long, trend_short, pullback_long,
              pullback_short, rejection_long, rejection_short,
              rsi_v=None, body_ratio=None, body_cmp=None) -> SignalDiagnostic:
        return SignalDiagnostic(
            decision_ts=ctx.decision_ts,
            final_signal=signal,
            warmup_m15_ema20_ready=ema_ready,
            warmup_m15_rsi_ready=rsi_ready,
            warmup_h1_ema50_ready=h1_ema_ready,
            warmup_h1_slope_ready=h1_slope_ready,
            trend_long=trend_long,
            trend_short=trend_short,
            pullback_long=pullback_long,
            pullback_short=pullback_short,
            rejection_long=rejection_long,
            rejection_short=rejection_short,
            rsi_value=rsi_v,
            body_ratio=body_ratio,
            body_comparison=body_cmp,
            blocked_by=tuple(blocked),
        )
