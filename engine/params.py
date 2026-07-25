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
    tick_value: float = 1.0         # $ per tick per standard lot (EURUSD 5-digit)
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
    pessimistic_intrabar: bool = True  # SL wins when SL and TP share a bar

    def with_mode(self, mode):
        """Return a copy using one of the named pyramid presets."""
        l0, l1, l2 = PYRAMID_MODES[mode]
        return replace(self, l0_mult=l0, l1_mult=l1, l2_mult=l2)

    @property
    def blocked_hours_array(self):
        return np.asarray(self.blocked_hours, dtype=np.int32)

    @property
    def toxic_combos_array(self):
        combos = self.toxic_combos if self.block_toxic_combos else ()
        if not combos:
            return np.zeros((0, 2), dtype=np.int32)
        return np.asarray(combos, dtype=np.int32)
