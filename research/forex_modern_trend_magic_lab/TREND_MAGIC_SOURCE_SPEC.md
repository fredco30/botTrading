# TREND_MAGIC_SOURCE_SPEC — Trend Magic Enhanced [AlgoAlpha]

## Provenance

```
SOURCE_URL           = https://www.tradingview.com/script/64xgEdlW-Trend-Magic-Enhanced-AlgoAlpha/
SOURCE_AUTHOR        = AlgoAlpha
PINE_VERSION         = 5
SOURCE_RETRIEVED     = 2026-09-19 (UTC), via TradingView pine-facade API,
                       scriptAccess = open_no_auth, lastVersionMaj = 1.0
SOURCE_SHA256        = 82de45d028e0c8793115ef07f4c7d6f3de7d4f844ea96bb58a10b4f4bc1c2e21
LICENSE              = Mozilla Public License 2.0 (stated in source header)
LOCAL_COPY           = TREND_MAGIC_PINE_ORIGINAL.pine (verbatim, license header intact)
```

Retrieval method: the script page loads the source through the internal
pine-facade endpoint; script id part `PUB;bae1c3b130d247db98c7fe9648598e08`,
version 1, resolved from the page's embedded study metadata. The retrieved
file is stored verbatim including its MPL-2.0 header. Input defaults below
were additionally cross-checked against the input-definition block embedded
in the official page HTML (ids in_0..in_6).

## Verified input defaults

| id    | name                          | default | type/options                                   |
|-------|-------------------------------|---------|------------------------------------------------|
| in_0  | CCI Period                    | 20      | integer                                        |
| in_1  | ATR Multiplier                | 2.0     | float                                          |
| in_2  | ATR Period                    | 5       | integer                                        |
| in_3  | Trend Magic Smoothing Length  | 14      | integer                                        |
| in_4  | MA Smoothing Type             | SMA     | SMA / EMA / SMMA (RMA) / WMA / VWMA            |
| in_5  | Source                        | close   | open/high/low/close/hl2/hlc3/hlcc4/ohlc4       |
| in_6  | Smooth Trend Magic            | false   | bool                                           |

All values match the prompt's expected defaults (section 5). THE SOURCE CODE WINS —
and the source agrees with the assumptions on every default.

## Mathematical specification (translated, source-faithful)

Let `h,l,c` be the current completed bar's high/low/close, `c[-1]` the previous
bar's close (`nz` = replace-na-with-0, Pine semantics; previous close na only on
the very first bar).

1. **True range** (`ta.tr(true)`):
   `TR_t = max(h_t - l_t, |h_t - c_{t-1}|, |l_t - c_{t-1}|)`; on the first bar
   (no previous close) `TR_1 = h_1 - l_1`.

2. **Volatility = SMA of true range — NOT Wilder/RMA ATR**:
   `VOL_t = SMA(TR, 5)` — a simple rolling mean over 5 bars.
   This confirms section 6 of the protocol: the script uses
   `ta.sma(ta.tr(true), atrPeriod)`, *not* `ta.atr()`.

3. **CCI** on the chosen source (default close), period 20, Pine's
   `ta.cci` = `(src - SMA(src,N)) / (0.015 * MAD(src,N))` where `MAD` is the
   rolling mean absolute deviation `mean(|src_i - SMA(src,N)_i|)` over the same
   window (Pine `ta.dev`, population form — divided by N, not N-1).

4. **Trend Magic line** (ratchet recurrence; `MT_prev = nz(MT_{t-1})`, i.e. 0.0
   on the first bar):
   - candidate up:   `UP_t = l_t - VOL_t * 2.0`
   - candidate down: `DN_t = h_t + VOL_t * 2.0`
   - if `CCI_t >= 0`:   `MT_t = max(UP_t, MT_prev)`   (line may only rise/hold)
   - if `CCI_t < 0`  :  `MT_t = min(DN_t, MT_prev)`   (line may only fall/hold)
   - NOTE: when `CCI_t` is na (warm-up bars), Pine's `if cciValue >= 0` is false,
     so the *else* (bearish) branch executes: `MT_t = min(DN_t, MT_prev)`.
     With `MT_prev = 0` on the first bars and positive FX prices this leaves
     `MT_t = 0` for every warm-up bar until the first bar with a defined CCI.

5. **Optional smoothing** (default OFF): if enabled, `MT` is replaced by the
   chosen MA (default SMA-14) of the ratcheted series. A trailing MA is causal;
   it uses bars <= t only. Default research configuration keeps smoothing OFF.

6. **Trend direction state** — driven by price crossing the line with
   **Low/High** (NOT by CCI sign; confirms section 8):
   - bull crossover: `l_{t-1} <= MT_{t-1} AND l_t > MT_t`  -> `DIR_t = +1`
   - bear crossunder: `h_{t-1} >= MT_{t-1} AND h_t < MT_t` -> `DIR_t = -1`
   - otherwise `DIR_t = nz(DIR_{t-1})` (initial state 0, neither bull nor bear).
   Pine crossover semantics: `a crosses over b` iff `a[1] <= b[1]` and `a > b`
   (na -> false).

7. **Events** (script alerts): bullish-trend event = `DIR` becomes +1 from
   non-+1; bearish-trend event = `DIR` becomes -1 from non--1; trend-shift
   event = any `DIR` change. The very first transition out of state 0 (0 -> ±1)
   is a valid event under the script's alert definitions; event studies report
   both all-events and events-excluding-the-first-0-transition per series.

## Implementation-freeze statement

- The Python implementation (`tmlab.py`) translates the recurrence above
  bar-by-bar in a single causal pass (numpy loops only over bars, no future
  access).
- Per protocol sections 4/7/10: no strategy PnL was inspected before this spec
  and the implementation were frozen. The event study (Experiment A) is the
  first PnL-adjacent output.
- Pine quirks reproduced deliberately:
  - `nz(MT[1]) = 0.0` initialization (line sits at 0 during CCI warm-up);
  - bear-branch execution on na CCI during warm-up;
  - crossover requires the strict inequality pattern above.
  These only affect the first ~20 bars of a series (state 0, no events) but are
  replicated exactly so that PYTHON == ORIGINAL by construction.
