# ENTRY_IDENTITY — HISTORICAL_SIGNAL_EXIT_AUDIT_M1

Frozen historical entry event sets, reconstructed from the
source commits and verified against historical artifacts.
ENTRY LOGIC IS FROZEN: no threshold/lookback/session/TF/pair/
direction/trigger change. Any mismatch => STOP that signal.

## SIGNAL_A: A — MTF F08 Asia->London continuation (|move|>=10p)

SOURCE_COMMIT=29dfb7b1710c58bb939e39a869d3aff26be01af9
SOURCE_CODE_PATH=research/mtf_discovery_m1/families_m3.py::f08_asia_transfer
SOURCE_PARAMETERS=mode="continuation", min_move=10.0, signal_tf=M15, EURUSD
EVENT_COUNT=1257 (raw fires, event-level set)
EVENTS_PER_WEEK=3.017
PAIR_COUNTS=EURUSD only
LONG_COUNT=673  SHORT_COUNT=584
FIRST_EVENT=2010-01-04 07:00
LAST_EVENT=2017-12-29 07:00
EVENT_HASH=87d603bb8089b19ba2fb777dcbe892b1eafba8c7221b4e28ebbf70ac4ca85782

HIST_SCREEN N/mean = 1257 / 3.9016 | replicated = 1257 / 3.9016

HISTORICAL_REF=M3_E015 SCREEN_PASS h=64 gross +3.90 posYR 7/8 (REJECT was side-concentration sanity: S +8.0 / L +0.3, RESULT.md §12)

IDENTITY_CHECK=PASS

---

## SIGNAL_B: B — SWING G10 D1-trend x H4-Donchian20 state machine

SOURCE_COMMIT=7e3bd46baea6dcd6ec4e5bf763e8d3c6eda1233b
SOURCE_CODE_PATH=research/fx_multipair_swing_m1/families_sw.py::g10_state_machine
SOURCE_PARAMETERS={'fast': 20, 'slow': 50, 'break_n': 20} signal_tf=H4, pairs EURUSD+GBPUSD
EVENT_COUNT=3038 (raw fires, event-level set)
EVENTS_PER_WEEK=7.3
PAIR_COUNTS={'EURUSD': {'events': 1536, 'scan_N': 540, 'scan_mean': 1.473}, 'GBPUSD': {'events': 1502, 'scan_N': 517, 'scan_mean': 2.1153}}
LONG_COUNT=1506  SHORT_COUNT=1532
FIRST_EVENT=2010-01-07 12:00
LAST_EVENT=2017-12-29 16:00
EVENT_HASH=f1b6385668e8a86c1b3c7273ee931fc67d67f568e612f3f4eaaf49710a7db2c7

HIST_SCAN N/mean/PF = 1057 / 1.7871 / 1.0644 | replicated = 1057 / 1.7871 / 1.0644
per-pair events+scan: {'EURUSD': {'events': 1536, 'scan_N': 540, 'scan_mean': 1.473}, 'GBPUSD': {'events': 1502, 'scan_N': 517, 'scan_mean': 2.1153}}

HISTORICAL_REF=SW_E029 SCAN h=6 (best of grid, never deepened): N=1057 mean +1.7871 PF 1.0644

IDENTITY_CHECK=PASS

---

## SIGNAL_C: C — MTF F04b previous-day H/L fade (M15 07-17h)

SOURCE_COMMIT=29dfb7b1710c58bb939e39a869d3aff26be01af9
SOURCE_CODE_PATH=research/mtf_discovery_m1/families_m3.py::f04_prev_day
SOURCE_PARAMETERS=mode="fade", M15 trigger 07:00-17:00 UTC, EURUSD; hist exit SL20/TP30/T240
EVENT_COUNT=1232 (raw fires, event-level set)
EVENTS_PER_WEEK=2.961
PAIR_COUNTS=EURUSD only
LONG_COUNT=588  SHORT_COUNT=644
FIRST_EVENT=2010-01-05 07:45
LAST_EVENT=2017-12-27 07:30
EVENT_HASH=c19c33252846a8a0460a74505c5576006041958e222e5821981ed0f01cae0140

MIDPOINT_FROZEN_FINITE=1232/1232
HIST_CACHED_TRADES=1183 SUBSET_MATCH=1183

HISTORICAL_REF=M3_E023 DEEPEN tick replay SL20/TP30/T240: N=1183 mean +0.388 PF 1.04

IDENTITY_CHECK=PASS

---
