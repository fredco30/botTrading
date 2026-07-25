"""Instrument specifications and H1 series loading.

Spread / swap figures for the three FX pairs were recovered from the MT4 tester
runs in this repo by reconciling lot sizes and P&L trade by trade, so they are
measurements rather than estimates. Gold has no MT4 report here, so its numbers
are estimates and are flagged as such.
"""

from dataclasses import dataclass

import numpy as np

from . import data as _data
from . import trend as _trend


@dataclass
class Instrument:
    symbol: str
    m15_csv: str
    point: float
    pip: float
    tick_size: float
    tick_value: float
    contract_size: float
    inverse_quote: bool
    spread: float          # price units, round turn cost paid by the buyer
    slippage: float        # price units, extra cost assumed on a breakout fill
    swap_long: float       # account currency per unit per rollover
    swap_short: float
    calibrated: bool       # False = spread/swap are estimates, not measured
    min_lot: float = 0.01
    max_lot: float = 200.0
    lot_step: float = 0.01


INSTRUMENTS = {
    "EURUSD": Instrument(
        "EURUSD", "EURUSD15.csv", 0.00001, 0.0001, 0.00001, 1.0, 100000.0, False,
        spread=0.00002, slippage=0.00002,
        swap_long=-8.3433, swap_short=2.5357, calibrated=True),
    "GBPUSD": Instrument(
        "GBPUSD", "GBPUSD15.csv", 0.00001, 0.0001, 0.00001, 1.0, 100000.0, False,
        spread=0.00010, slippage=0.00002,
        swap_long=-3.5088, swap_short=-3.8000, calibrated=True),
    "USDJPY": Instrument(
        "USDJPY", "USDJPY15.csv", 0.001, 0.01, 0.001, 0.63046, 100000.0, True,
        spread=0.009, slippage=0.002,
        swap_long=7.7671, swap_short=-12.4791, calibrated=True),
    # Gold: 100 oz contract, 2-digit quotes. Spread and swap are estimates -
    # no MT4 gold run exists in this repo to reconcile against.
    "XAUUSD": Instrument(
        "XAUUSD", "XAUUSD15.csv", 0.01, 0.01, 0.01, 1.0, 100.0, False,
        spread=0.20, slippage=0.10,
        swap_long=-15.0, swap_short=5.0, calibrated=False),
}


_H1_CACHE = {}


def _h1_ohlc(symbol):
    """M15 CSV -> H1 OHLC, cached.

    Parsing a 680k-line CSV takes seconds, and a parameter sweep asks for the
    same symbol dozens of times. Only the indicators depend on the parameters,
    so the bars themselves are built once and reused.
    """
    if symbol not in _H1_CACHE:
        inst = INSTRUMENTS[symbol]
        m15_dt, m_o, m_h, m_l, m_c = _data.load_mt4_csv(inst.m15_csv)
        _H1_CACHE[symbol] = _data.derive_h1(m15_dt, m_o, m_h, m_l, m_c)
    return _H1_CACHE[symbol]


def load_h1(symbol, atr_period=14, entry_period=55, exit_period=20):
    """Build the H1 series and every indicator the breakout core needs."""
    inst = INSTRUMENTS[symbol]
    h_dt, h_o, h_h, h_l, h_c = _h1_ohlc(symbol)

    ts = h_dt.astype("int64")
    atr = _trend.wilder_atr(h_h, h_l, h_c, atr_period)
    don_hi, don_lo = _trend.donchian(h_h, h_l, entry_period)
    ex_hi, ex_lo = _trend.donchian(h_h, h_l, exit_period)

    # Rollover weight per bar: swap is charged at 00:00, tripled on Thursday.
    hour = (ts % 86400) // 3600
    dow = ((ts // 86400) + 4) % 7
    roll_w = np.zeros(ts.size)
    at_midnight = hour == 0
    roll_w[at_midnight] = 1.0
    roll_w[at_midnight & (dow == 4)] = 3.0
    roll_w[at_midnight & ((dow == 0) | (dow == 6))] = 0.0

    return dict(ts=ts, o=h_o, h=h_h, l=h_l, c=h_c, atr=atr,
                don_hi=don_hi, don_lo=don_lo, exit_hi=ex_hi, exit_lo=ex_lo,
                roll_w=roll_w, inst=inst)


def run(series, risk_pct=1.0, atr_stop_mult=3.0, atr_trail_mult=4.0,
        use_trailing=True, allow_long=True, allow_short=True,
        initial_equity=10000.0, use_swap=True, max_trades=200000,
        max_risk_units=1.5, max_units=1, add_step_atr=1.0):
    """Run the breakout core over one instrument."""
    inst = series["inst"]
    out = np.zeros((max_trades, _trend.R_COLS))
    n = _trend._run_trend(
        series["ts"], series["o"], series["h"], series["l"], series["c"],
        series["atr"], series["don_hi"], series["don_lo"],
        series["exit_hi"], series["exit_lo"], series["roll_w"],
        float(initial_equity), float(inst.spread), float(inst.slippage),
        float(inst.contract_size), bool(inst.inverse_quote),
        float(inst.min_lot), float(inst.max_lot), float(inst.lot_step),
        float(inst.tick_size), float(inst.tick_value),
        float(inst.swap_long), float(inst.swap_short), bool(use_swap),
        float(risk_pct), float(atr_stop_mult), float(atr_trail_mult),
        bool(use_trailing), bool(allow_long), bool(allow_short),
        float(max_risk_units),
        int(max_units), float(add_step_atr),
        out,
    )
    return out[:n]
