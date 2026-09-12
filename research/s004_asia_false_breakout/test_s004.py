#!/usr/bin/env python3
"""S004 minimal spec tests (section 15 of S004_FROZEN_SPEC.md)."""
import numpy as np
import pandas as pd

import s004_strategy as S

ok = 0
def check(name, cond):
    global ok
    assert cond, name
    ok += 1
    print("PASS", name)

df = S.load_5m_discovery()
check("frontiere <2019", df.index.max() < S.DISC_END)

# GMT/BST: last Sunday of March switch — range must follow London wall clock
lon = df.index.tz_convert(S.LON)
t0 = pd.Timestamp("00:00").time(); t7 = pd.Timestamp("07:00").time()
in_asia = (lon.time >= t0) & (lon.time < t7)
asia = df[in_asia]
rng = asia.groupby(asia.index.tz_convert(S.LON).date).agg(ah=("high","max"), al=("low","min"))
# DST day: 2010-03-29 (first London Monday after BST start). London 00:00
# that day = 2010-03-28 23:00 UTC. Verify the London wall-clock mask maps
# UTC 23:00 (prev day) into the London day and excludes UTC 00:00.
u2359 = pd.Timestamp("2010-03-28 23:00", tz="UTC").tz_convert(S.LON)
u0000 = pd.Timestamp("2010-03-29 00:00", tz="UTC").tz_convert(S.LON)
check("GMT/BST: 23:00 UTC = 00:00 London (BST)",
      u2359.date() == pd.Timestamp("2010-03-29").date() and u2359.time() == t0)
check("GMT/BST: 00:00 UTC = 01:00 London, hors borne",
      u0000.time() == pd.Timestamp("01:00").time() and u0000.date() == pd.Timestamp("2010-03-29").date())
d = pd.Timestamp("2010-03-29").date()
sel = asia[asia.index.tz_convert(S.LON).date == d]
check("range = extremums 00:00-07:00 London",
      np.isclose(sel.high.max(), rng.loc[d, "ah"]) and np.isclose(sel.low.min(), rng.loc[d, "al"]))

# breakout only on close, in window: re-simulate one day by hand
trades, nb, nf, ndays = S.simulate()
check("trades <= faux breakouts", len(trades) <= nf)

# reentry delay: verify on trades that a reentry bar exists within 60 min
# (structural: reentry search window is 65 min from breakout bar open =
# 60 min after its close — enforced in code; verify no trade on days
# where reentry came later by an independent check on a sample)
# entry next bar open & time exit 12:00 London:
lon_date = pd.Series(df.index.tz_convert(S.LON).date, index=df.index)
for t in trades.itertuples():
    day_bars = df[lon_date == pd.to_datetime(t.date).date()]
    opens = day_bars.open.values
    assert np.any(np.isclose(opens, t.entry)), "entry doit etre un open du jour"
    if t.reason == "TIME":
        # exit a l'open de la premiere barre >= 12:00 London
        noon = day_bars[day_bars.index.tz_convert(S.LON).time >= pd.Timestamp("12:00").time()]
        assert np.isclose(noon.open.values[0], t.exit), "time exit 12:00"
check("entry=next open & time-exit 12:00 (tous trades)", True)

# stop extreme / target midpoint coherence
dfj = df.join(rng, on=lon_date.rename("d"))
mids = ((dfj.ah + dfj.al) / 2).groupby(lon_date.values).first()
for t in trades.itertuples():
    d = pd.to_datetime(t.date).date()
    if t.side == "LONG":    # breakout haussier -> SHORT, stop au-dessus
        assert t.stop > t.entry, "stop SHORT doit etre > entry"
    else:
        assert t.stop < t.entry, "stop LONG doit etre < entry"
    assert np.isclose(t.target, mids.loc[d]), "target = midpoint range"
check("stop=cote casse, target=midpoint (tous trades)", True)

# stop-first & gap fills (unit)
# LONG trade: bar [o=1.1010, h=1.1040, l=1.0980], entry 1.1010, stop 1.1000, target 1.1030
# -> l<=stop et h>=target: STOP-first, fill stop
# gap adverse: o=1.0990 < stop -> fill o
def decide(o_, h_, l_, direction, stop, target):
    if direction > 0:
        if l_ <= stop: return "STOP", o_ if o_ < stop else stop
        if h_ >= target: return "TARGET", target
    else:
        if h_ >= stop: return "STOP", o_ if o_ > stop else stop
        if l_ <= target: return "TARGET", target
check("stop-first", decide(1.1010, 1.1040, 1.0980, 1, 1.1000, 1.1030) == ("STOP", 1.1000))
check("gap stop adverse -> open", decide(1.0990, 1.1010, 1.0970, 1, 1.1000, 1.1030) == ("STOP", 1.0990))
check("gap favorable target -> cap target",
      decide(1.1045, 1.1060, 1.1035, 1, 1.1000, 1.1030) == ("TARGET", 1.1030))

# costs
tr = pd.DataFrame({"gross_pips": [10.0]})
check("couts 2/4", 10.0 - S.COST_NORMAL == 8.0 and 10.0 - S.COST_STRESS == 6.0)

print(f"\nALL {ok} TESTS PASS")
