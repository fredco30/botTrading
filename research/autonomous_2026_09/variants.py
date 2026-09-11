#!/usr/bin/env python3
"""Autonomous mission — Phase 2B exploratory signal variants.

EXPLORATORY: these ablations/variants are screened on contaminated history
only.  Nothing here is a validation.  A handful of families, each causally
defined, few parameters, quick kill.

  EmaBaseVariant      — the frozen EMA core with individual gates toggled
                        off (ablations).  Same incremental causal state and
                        features as the frozen signal; only the gate LIST
                        changes.  require_trend=False derives direction
                        from the pullback+rejection polarity itself.
  RsiMeanReversion    — EXPLORATORY_NEW_HYPOTHESIS: M15 RSI(14) mean
                        reversion (LONG < 30, SHORT > 70), nothing else.
  DonchianBreakoutH1  — EXPLORATORY_NEW_HYPOTHESIS: 24h channel breakout
                        measured on CLOSED H1 buckets only.
"""
from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from ema_base_signal import (  # noqa: E402
    EmaBaseCoreV1,
    SignalDiagnostic,
    SignalType,
)
from research_engine import CausalContext  # noqa: E402


def _mk_diag(ctx, signal, blocked, rsi_v=None, body_ratio=None,
             trend_long=None, trend_short=None, pullback_long=None,
             pullback_short=None, rejection_long=None, rejection_short=None,
             body_cmp=None):
    return SignalDiagnostic(
        decision_ts=ctx.decision_ts,
        final_signal=signal,
        warmup_m15_ema20_ready=True,
        warmup_m15_rsi_ready=True,
        warmup_h1_ema50_ready=True,
        warmup_h1_slope_ready=True,
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


class EmaBaseVariant(EmaBaseCoreV1):
    """Ablation variant of the frozen signal — EXPLORATORY ONLY."""

    def __init__(self, params=None, require_trend=True, use_pullback=True,
                 use_rejection=True, use_body_ratio=True, use_body_compare=True,
                 use_rsi=True):
        super().__init__(params)
        self.require_trend = require_trend
        self.use_pullback = use_pullback
        self.use_rejection = use_rejection
        self.use_body_ratio = use_body_ratio
        self.use_body_compare = use_body_compare
        self.use_rsi = use_rsi

    def evaluate(self, ctx: CausalContext) -> SignalDiagnostic:
        self._sync(ctx)
        p = self.p
        blocked = []
        ema_ready = len(self._ema20_last) == 2
        rsi_ready = self._rsi is not None
        h1_ready = (self._ema50 is not None
                    and len(self._ema50_hist) == p.h1_trend_bars + 1)
        if not ema_ready:
            blocked.append("M15_EMA20_NOT_WARM")
        if self.use_rsi and not rsi_ready:
            blocked.append("M15_RSI_NOT_WARM")
        if self.require_trend and not h1_ready:
            blocked.append("H1_NOT_WARM")
        if blocked:
            return _mk_diag(ctx, SignalType.NONE, tuple(blocked))

        n = len(ctx.m15)
        b1, b2 = n - 1, n - 2
        c1, o1 = ctx.m15.close(b1), ctx.m15.open(b1)
        hi1, lo1 = ctx.m15.high(b1), ctx.m15.low(b1)
        c2, o2 = ctx.m15.close(b2), ctx.m15.open(b2)
        lo2, hi2 = ctx.m15.low(b2), ctx.m15.high(b2)
        e1, e2 = self._ema20_last[-1], self._ema20_last[0]
        rsi_v = self._rsi

        # trend features only when required (avoid reading unwarm H1 state)
        if self.require_trend:
            last_h1_close = ctx.h1.close(len(ctx.h1) - 1)
            ema50_now = self._ema50_hist[-1]
            ema50_prev = self._ema50_hist[0]
            trend_long = last_h1_close > ema50_now and ema50_now > ema50_prev
            trend_short = last_h1_close < ema50_now and ema50_now < ema50_prev
        else:
            trend_long = trend_short = None

        pullback_long = lo2 <= e2
        pullback_short = hi2 >= e2
        rejection_long = c1 > e1 and c1 > o1
        rejection_short = c1 < e1 and c1 < o1
        body1, body2 = abs(c1 - o1), abs(c2 - o2)
        range1 = hi1 - lo1
        body_ratio = (body1 / range1) if range1 > 0 else None

        if self.require_trend:
            if trend_long:
                direction = 1
            elif trend_short:
                direction = -1
            else:
                return _mk_diag(ctx, SignalType.NONE, ("TREND_ABSENT",), rsi_v,
                                body_ratio, trend_long, trend_short,
                                pullback_long, pullback_short, rejection_long,
                                rejection_short)
        else:
            long_ok = pullback_long and rejection_long
            short_ok = pullback_short and rejection_short
            if long_ok and not short_ok:
                direction = 1
            elif short_ok and not long_ok:
                direction = -1
            else:
                return _mk_diag(ctx, SignalType.NONE, ("DIRECTION_ABSENT",),
                                rsi_v, body_ratio, trend_long, trend_short,
                                pullback_long, pullback_short, rejection_long,
                                rejection_short)

        suffix = "LONG" if direction == 1 else "SHORT"
        if self.use_pullback:
            ok = pullback_long if direction == 1 else pullback_short
            if not ok:
                return _mk_diag(ctx, SignalType.NONE, (f"PULLBACK_{suffix}",),
                                rsi_v, body_ratio, trend_long, trend_short,
                                pullback_long, pullback_short, rejection_long,
                                rejection_short)
        if self.use_rejection:
            ok = rejection_long if direction == 1 else rejection_short
            if not ok:
                return _mk_diag(ctx, SignalType.NONE, (f"REJECTION_{suffix}",),
                                rsi_v, body_ratio, trend_long, trend_short,
                                pullback_long, pullback_short, rejection_long,
                                rejection_short)
        if self.use_body_ratio:
            if body_ratio is None or body_ratio < p.rejection_body_min:
                return _mk_diag(ctx, SignalType.NONE, (f"BODY_RATIO_{suffix}",),
                                rsi_v, body_ratio, trend_long, trend_short,
                                pullback_long, pullback_short, rejection_long,
                                rejection_short)
        body_cmp = body1 > body2
        if self.use_body_compare and not body_cmp:
            return _mk_diag(ctx, SignalType.NONE,
                            (f"BODY_COMPARISON_{suffix}",), rsi_v, body_ratio,
                            trend_long, trend_short, pullback_long,
                            pullback_short, rejection_long, rejection_short,
                            body_cmp)
        if self.use_rsi:
            if direction == 1 and rsi_v > p.rsi_long_max:
                return _mk_diag(ctx, SignalType.NONE, ("RSI_LONG_OVER_MAX",),
                                rsi_v, body_ratio, trend_long, trend_short,
                                pullback_long, pullback_short, rejection_long,
                                rejection_short, body_cmp)
            if direction == -1 and rsi_v < p.rsi_short_min:
                return _mk_diag(ctx, SignalType.NONE, ("RSI_SHORT_UNDER_MIN",),
                                rsi_v, body_ratio, trend_long, trend_short,
                                pullback_long, pullback_short, rejection_long,
                                rejection_short, body_cmp)

        sig = SignalType.LONG if direction == 1 else SignalType.SHORT
        return _mk_diag(ctx, sig, (), rsi_v, body_ratio, trend_long,
                        trend_short, pullback_long, pullback_short,
                        rejection_long, rejection_short, body_cmp)


class RsiMeanReversion(EmaBaseCoreV1):
    """EXPLORATORY_NEW_HYPOTHESIS: pure M15 RSI(14) mean reversion.
    LONG when RSI(i-1) < 30, SHORT when RSI(i-1) > 70. No other condition."""

    def evaluate(self, ctx: CausalContext) -> SignalDiagnostic:
        self._sync(ctx)
        if self._rsi is None:
            return _mk_diag(ctx, SignalType.NONE, ("M15_RSI_NOT_WARM",))
        if self._rsi < self.p.rsi_short_min:
            sig, blocked = SignalType.LONG, ()
        elif self._rsi > self.p.rsi_long_max:
            sig, blocked = SignalType.SHORT, ()
        else:
            sig, blocked = SignalType.NONE, ("RSI_NEUTRAL",)
        return _mk_diag(ctx, sig, blocked, rsi_v=self._rsi)


class DonchianBreakoutH1(EmaBaseCoreV1):
    """EXPLORATORY_NEW_HYPOTHESIS: 24h-channel breakout on CLOSED H1 only.
    LONG when last closed H1 close > max(high of previous 24 closed buckets);
    SHORT mirrored.  Event = M15 decisions observing the breakout state."""

    CHANNEL = 24

    def evaluate(self, ctx: CausalContext) -> SignalDiagnostic:
        self._sync(ctx)   # keep parity with other variants; indicators unused
        h1 = ctx.h1
        n = len(h1)
        if n < self.CHANNEL + 1:
            return _mk_diag(ctx, SignalType.NONE, ("H1_NOT_WARM",))
        close = h1.close(n - 1)
        prev_hi = max(h1.high(n - 1 - k) for k in range(1, self.CHANNEL + 1))
        prev_lo = min(h1.low(n - 1 - k) for k in range(1, self.CHANNEL + 1))
        if close > prev_hi:
            sig, blocked = SignalType.LONG, ()
        elif close < prev_lo:
            sig, blocked = SignalType.SHORT, ()
        else:
            sig, blocked = SignalType.NONE, ("INSIDE_CHANNEL",)
        return _mk_diag(ctx, sig, blocked)
