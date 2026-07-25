"""Strategy parameters, mirroring the inputs of EMA_Pullback_pyramid.mq4."""

from dataclasses import dataclass, field, replace

import numpy as np

# Pyramid presets. SAFE / AGGRESSIVE come from the EA's ApplyPyramidMode().
# GEOMETRIC15 is what resultats_martingale_EMAPullback3ans.txt was actually
# generated with (recovered from the lot sizes in the report, see
# calibrate_pullback_pyramid.py --infer-mults).
PYRAMID_MODES = {
    "SAFE": (1.0, 4.0, 2.5),
    "AGGRESSIVE": (2.0, 7.0, 4.0),
    "GEOMETRIC15": (1.0, 1.5, 2.25),
    "FLAT": (1.0, 1.0, 1.0),
}

# EURUSD toxic hour x day combos hard-coded in IsHourBlocked().
EURUSD_TOXIC_COMBOS = ((14, 2), (11, 1), (14, 4), (16, 1))


@dataclass
class Params:
    # --- account / instrument ---
    initial_balance: float = 10000.0
    spread_points: float = 2.0      # MT4 tester spread, in points (5-digit)
    point: float = 0.00001
    pip: float = 0.0001
    tick_size: float = 0.00001
    # $ per tick per standard lot, as MarketInfo(MODE_TICKVALUE) reports it.
    # On USDJPY the MT4 tester returns a *constant* value taken from the live
    # symbol at the time the test was run, not the historical bar price - so
    # sizing uses a constant while P&L still converts at the exit price.
    tick_value: float = 1.0
    contract_size: float = 100000.0
    # True when the account currency is the BASE of the pair (USDJPY), so
    # profit is earned in the quote currency and converted at the exit price.
    inverse_quote: bool = False
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01

    # --- risk ---
    risk_percent: float = 1.0
    max_spread_pips: float = 3.0
    min_rr: float = 2.5
    min_sl_pips: float = 15.0
    max_sl_pips: float = 25.0

    # --- pyramid ---
    use_pyramid: bool = True
    l0_mult: float = 1.0
    l1_mult: float = 1.5
    l2_mult: float = 2.25
    max_streak_level: int = 2

    # --- signal ---
    trend_ema_period: int = 50
    trend_bars: int = 5
    entry_ema_period: int = 20
    sl_swing_bars: int = 3
    rsi_period: int = 14
    rsi_ob: float = 70.0
    rsi_os: float = 30.0
    body_ratio_min: float = 0.6

    # --- sessions ---
    use_london: bool = True
    london_start: int = 8
    london_end: int = 12
    ny_start: int = 13
    ny_end: int = 17

    # --- management ---
    use_breakeven: bool = True
    be_trigger_r: float = 1.5
    be_offset_pips: float = 1.0
    max_trades_per_day: int = 2

    # --- context filters ---
    use_atr_filter: bool = True
    atr_period: int = 14
    atr_min_pips: float = 9.0
    atr_max_pips: float = 19.0
    use_ema50_dist_filter: bool = True
    max_ema50_dist_pips: float = 30.0

    # --- calendar filters ---
    block_friday: bool = True
    block_monday: bool = False
    blocked_hours: tuple = (13,)
    block_toxic_combos: bool = True
    toxic_combos: tuple = EURUSD_TOXIC_COMBOS
    reduce_thursday_risk: bool = True
    thursday_risk_mult: float = 0.5

    # --- overnight swap ---
    # MT4 charges a fixed swap per lot at every 00:00 server rollover, tripled
    # on the Thursday rollover (Wed -> Thu) to cover the weekend. The tester
    # uses one constant for the whole run, so these are constants here too.
    # Values below were fitted to resultats_martingale_EMAPullback3ans.txt and
    # reproduce every overnight trade in it to within $0.05.
    use_swap: bool = True
    swap_long_per_lot: float = -8.3433    # $ per lot per rollover, EURUSD long
    swap_short_per_lot: float = 2.5357    # $ per lot per rollover, EURUSD short

    # --- simulation realism ---
    exit_on_entry_bar: bool = True   # allow SL/TP on the bar the trade opened
    # How to resolve a bar that touches both SL and TP: "pessimistic" (the stop
    # wins), "nearest" (the extreme closer to the bar open is reached first) or
    # "optimistic" (the target wins). See _tp_first() in core.py - on USDJPY
    # this single choice moves the 3-year net by 38%.
    intrabar_model: str = "nearest"

    def with_mode(self, mode):
        """Return a copy using one of the named pyramid presets."""
        l0, l1, l2 = PYRAMID_MODES[mode]
        return replace(self, l0_mult=l0, l1_mult=l1, l2_mult=l2)

    @classmethod
    def for_pair(cls, pair, **overrides):
        """Build params from a pair preset, mirroring the EA's ApplyPreset()."""
        try:
            preset = PAIR_PRESETS[pair]
        except KeyError:
            raise KeyError(f"unknown pair '{pair}', have {sorted(PAIR_PRESETS)}")
        return cls(**{**preset, **overrides})

    @property
    def is_jpy(self):
        return self.inverse_quote

    @property
    def blocked_hours_array(self):
        return np.asarray(self.blocked_hours, dtype=np.int32)

    @property
    def toxic_combos_array(self):
        combos = self.toxic_combos if self.block_toxic_combos else ()
        if not combos:
            return np.zeros((0, 2), dtype=np.int32)
        return np.asarray(combos, dtype=np.int32)


# ---------------------------------------------------------------------------
# Per-pair presets, mirroring ApplyPreset() in EMA_Pullback_EA.mq4.
#
# The market-microstructure numbers (spread, tick value, swap) are not guesses:
# they were recovered from the MT4 tester runs stored in this repo by
# reconciling every trade's lot size and P&L. See engine/README.md.
# ---------------------------------------------------------------------------
PAIR_PRESETS = {
    "EURUSD": dict(
        spread_points=2.0, point=0.00001, pip=0.0001, tick_size=0.00001,
        tick_value=1.0, inverse_quote=False,
        swap_long_per_lot=-8.3433, swap_short_per_lot=2.5357,
        max_spread_pips=3.0, min_sl_pips=15.0, max_sl_pips=25.0,
        use_atr_filter=True, atr_min_pips=9.0, atr_max_pips=19.0,
        use_ema50_dist_filter=True, max_ema50_dist_pips=30.0,
        london_start=8, london_end=12, ny_start=13, ny_end=17,
        block_friday=True, block_monday=False, blocked_hours=(13,),
        block_toxic_combos=True, toxic_combos=EURUSD_TOXIC_COMBOS,
        reduce_thursday_risk=True, thursday_risk_mult=0.5,
    ),
    # GBPUSD: spread 10 points and swaps fitted on historique trade gbpusd 3ansV4.
    # Both swap sides are negative here, so holding overnight costs either way.
    "GBPUSD": dict(
        spread_points=10.0, point=0.00001, pip=0.0001, tick_size=0.00001,
        tick_value=1.0, inverse_quote=False,
        swap_long_per_lot=-3.5088, swap_short_per_lot=-3.8000,
        max_spread_pips=4.0, min_sl_pips=20.0, max_sl_pips=25.0,
        use_atr_filter=True, atr_min_pips=9.0, atr_max_pips=25.0,
        use_ema50_dist_filter=True, max_ema50_dist_pips=50.0,
        london_start=9, london_end=12, ny_start=14, ny_end=17,
        block_friday=True, block_monday=True, blocked_hours=(10, 13, 15),
        block_toxic_combos=False, toxic_combos=(),
        reduce_thursday_risk=False, thursday_risk_mult=1.0,
    ),
    # USDJPY: 3-digit quotes, so pip = 0.01 and tick = 0.001. Long pays a
    # positive swap (USD rate above JPY), which makes overnight longs cheap and
    # overnight shorts expensive - the opposite of EURUSD.
    "USDJPY": dict(
        spread_points=9.0, point=0.001, pip=0.01, tick_size=0.001,
        tick_value=0.63046, inverse_quote=True,
        swap_long_per_lot=7.7671, swap_short_per_lot=-12.4791,
        max_spread_pips=3.0, min_sl_pips=17.0, max_sl_pips=25.0,
        use_atr_filter=False, atr_min_pips=0.0, atr_max_pips=0.0,
        use_ema50_dist_filter=True, max_ema50_dist_pips=75.0,
        london_start=8, london_end=12, ny_start=14, ny_end=17,
        block_friday=True, block_monday=True, blocked_hours=(9, 11, 13, 16),
        block_toxic_combos=False, toxic_combos=(),
        reduce_thursday_risk=False, thursday_risk_mult=1.0,
    ),
}

# EURUSD now points at the full export (M15 back to 1999) rather than the
# 65k-row _cut file. The _cut files stay usable via --m15 / --h1.
PAIR_DATA = {
    "EURUSD": ("EURUSD15.csv", "EURUSD60.csv"),
    "GBPUSD": ("GBPUSD15_cut.csv", "GBPUSD60_cut.csv"),
    "USDJPY": ("USDJPY15_cut.csv", "USDJPY60_cut.csv"),
}


# ---------------------------------------------------------------------------
# Tuned overrides on top of PAIR_PRESETS, found with optimize_pullback_pyramid
# and validated with validate_pair.py (walk-forward halves + year by year).
#
# EURUSD keeps its published SAFE settings - it was already the champion and
# nothing here improved it out of sample.
# ---------------------------------------------------------------------------
CHAMPION_OVERRIDES = {
    "EURUSD": dict(l0_mult=1.0, l1_mult=4.0, l2_mult=2.5),
    # GBPUSD: the two levers that mattered were a much tighter EMA50 distance
    # (30 instead of 50) and a later breakeven (2.0R instead of 1.5R). A wider
    # SL swing lookback (5 bars) placed better stops. Baseline PF 1.21 -> 1.92.
    "GBPUSD": dict(
        max_ema50_dist_pips=30.0, be_trigger_r=2.0, sl_swing_bars=5,
        min_sl_pips=20.0,
        l0_mult=1.5, l1_mult=2.0, l2_mult=2.0,
    ),
    # USDJPY: a higher reward target (RR 3.5), a stricter oversold gate on
    # sells (RSI 40), wider stops (20-30) and an early breakeven (1.0R).
    # Baseline PF 1.48 -> 2.00.
    "USDJPY": dict(
        min_rr=3.5, rsi_os=40.0, sl_swing_bars=5,
        min_sl_pips=20.0, max_sl_pips=30.0, be_trigger_r=1.0,
        # L2=4.0 scored better (net 24.5k, R/DD 20) but put 80% of the profit
        # in the deepest level. 3.0 keeps most of the gain, respects the
        # "L2 <= 3.0" rule in CLAUDE.md, and spreads the profit wider.
        l0_mult=1.0, l1_mult=2.0, l2_mult=3.0,
    ),
}
