"""MACRO_TICK_M0 synthetic tests (mission §12).

Pure-synthetic: no network, no external tick files. Covers:
  * America/New_York DST conversion (EST date / EDT date / DST transitions)
  * duplicate event detection
  * event ordering
  * release timestamp UTC conversion
  * no 2019+ event (discovery-range guard)
  * value availability cannot predate release (causality)
  * tick alignment before/after event
  * missing tick handling
  * scheduled vs unscheduled FOMC distinction

Runs under both pytest and `python -m unittest discover` (repo CI).
"""
from __future__ import annotations

import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "build_scripts"))
import macro_lib as M  # noqa: E402

UTC = ZoneInfo("UTC")


# ---------------------------------------------------------------- DST / TZ
class TimezoneTests(unittest.TestCase):
    def test_et_winter_is_utc_minus_5(self):
        ts = M.et_to_utc(date(2016, 1, 8), "08:30")  # NFP, EST
        self.assertEqual(ts, datetime(2016, 1, 8, 13, 30, tzinfo=UTC))

    def test_et_summer_is_utc_minus_4(self):
        ts = M.et_to_utc(date(2016, 6, 3), "08:30")  # NFP, EDT
        self.assertEqual(ts, datetime(2016, 6, 3, 12, 30, tzinfo=UTC))

    def test_same_wall_clock_maps_differently_across_dst(self):
        winter = M.et_to_utc(date(2018, 1, 5), "08:30")
        summer = M.et_to_utc(date(2018, 7, 6), "08:30")
        self.assertEqual(winter.hour, 13)
        self.assertEqual(summer.hour, 12)

    def test_dst_spring_transition_week(self):
        # DST starts 2018-03-11: Mar 9 is EST, Mar 12 is EDT
        self.assertEqual(M.et_to_utc(date(2018, 3, 9), "08:30").hour, 13)
        self.assertEqual(M.et_to_utc(date(2018, 3, 12), "08:30").hour, 12)

    def test_dst_fall_transition_week(self):
        # DST ends 2018-11-04: Nov 2 is EDT, Nov 5 is EST
        self.assertEqual(M.et_to_utc(date(2018, 11, 2), "14:00").hour, 18)
        self.assertEqual(M.et_to_utc(date(2018, 11, 5), "14:00").hour, 19)

    def test_tz_label_matches_zoneinfo(self):
        self.assertTrue(M.tz_label_matches_date("EST", date(2016, 1, 27)))
        self.assertTrue(M.tz_label_matches_date("EDT", date(2016, 6, 15)))
        self.assertFalse(M.tz_label_matches_date("EDT", date(2016, 1, 27)))
        self.assertFalse(M.tz_label_matches_date("EST", date(2016, 6, 15)))

    def test_parse_schedule_time_ampm(self):
        self.assertEqual(M.parse_schedule_time("08:30 AM"), "08:30")
        self.assertEqual(M.parse_schedule_time("02:00 PM"), "14:00")
        self.assertEqual(M.parse_schedule_time("12:00 PM"), "12:00")
        self.assertEqual(M.parse_schedule_time("12:00 AM"), "00:00")
        with self.assertRaises(ValueError):
            M.parse_schedule_time("8:30")

    def test_parse_fomc_release_line(self):
        hhmm, tz = M.parse_fomc_release_line("For release at 2:00 p.m. EST")
        self.assertEqual((hhmm, tz), ("14:00", "EST"))
        hhmm, tz = M.parse_fomc_release_line("For release at 12:30 p.m. EDT")
        self.assertEqual((hhmm, tz), ("12:30", "EDT"))
        self.assertIsNone(M.parse_fomc_release_line(None))
        self.assertIsNone(
            M.parse_fomc_release_line("Release Date: January 26, 2011"))


# ------------------------------------------------------- reference periods
class ReferencePeriodTests(unittest.TestCase):
    def test_reference_period_parsing_both_label_styles(self):
        self.assertEqual(M.reference_period_from_label(
            "Employment Situation for December 2015"), "2015-12")
        self.assertEqual(M.reference_period_from_label(
            "December 2015 Employment Situation"), "2015-12")
        self.assertIsNone(M.reference_period_from_label("Some odd label"))

    def test_prev_and_shift_month(self):
        self.assertEqual(M.prev_month("2010-01"), "2009-12")
        self.assertEqual(M.prev_month("2013-04"), "2013-03")
        self.assertEqual(M.shift_month("2018-11", 1), "2018-12")
        self.assertEqual(M.shift_month("2018-12", 1), "2019-01")


# ------------------------------------------------------ event list guards
def _ev(eid, ts, vat=None):
    return {"event_id": eid, "release_timestamp_utc": ts,
            "value_available_time_utc": vat or ts}


class EventListGuardTests(unittest.TestCase):
    def test_duplicate_event_detection(self):
        evs = [_ev("A", "2015-01-01T13:30:00Z"),
               _ev("A", "2015-02-01T13:30:00Z")]
        with self.assertRaisesRegex(ValueError, "duplicate"):
            M.dedupe_and_sort(evs)

    def test_event_ordering(self):
        evs = [_ev("B", "2015-02-01T13:30:00Z"),
               _ev("A", "2015-01-01T13:30:00Z")]
        out = M.dedupe_and_sort(evs)
        self.assertEqual([e["event_id"] for e in out], ["A", "B"])

    def test_no_2019_plus_guard(self):
        evs = [_ev("OK", "2018-12-19T19:00:00Z"),
               _ev("BAD", "2019-01-01T13:30:00Z")]
        with self.assertRaisesRegex(ValueError, "outside discovery range"):
            M.assert_no_2019_plus(evs)
        M.assert_no_2019_plus([_ev("OK", "2018-12-19T19:00:00Z")])  # no raise

    def test_value_causality_guard(self):
        # value availability BEFORE the release must be rejected
        bad = _ev("X", "2015-01-08T13:30:00Z", vat="2015-01-08T13:00:00Z")
        with self.assertRaisesRegex(ValueError, "before release"):
            M.assert_value_causality(bad)
        good = _ev("X", "2015-01-08T13:30:00Z", vat="2015-01-08T13:30:00Z")
        M.assert_value_causality(good)  # equal is fine (release moment)


# ------------------------------------------------------------ tick align
def _ticks(base: datetime, offsets_ms):
    ts = [base + timedelta(milliseconds=o) for o in offsets_ms]
    return pd.DatetimeIndex(ts)  # already tz-aware UTC


class TickAlignmentTests(unittest.TestCase):
    def test_tick_alignment_neighbors_and_lags(self):
        base = datetime(2016, 1, 8, 13, 29, 50, tzinfo=UTC)
        ticks = _ticks(base, [0, 5000, 9500, 10000, 12000])
        ev = datetime(2016, 1, 8, 13, 30, 0, tzinfo=UTC)
        r = M.find_tick_neighbors(ticks, ev)
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["pre_tick_lag_ms"], 500)   # 13:29:59.500
        self.assertEqual(r["post_tick_lag_ms"], 0)    # tick exactly at 13:30

    def test_tick_alignment_first_executable_within_5s(self):
        base = datetime(2016, 3, 4, 13, 29, 50, tzinfo=UTC)
        # ticks at 13:29:50.0, 13:29:59.8 and 13:30:04.8
        ticks = _ticks(base, [0, 9800, 14800])
        ev = datetime(2016, 3, 4, 13, 30, 0, tzinfo=UTC)
        r = M.find_tick_neighbors(ticks, ev)
        self.assertEqual(r["status"], "OK")
        self.assertEqual(r["pre_tick_lag_ms"], 200)
        self.assertEqual(r["post_tick_lag_ms"], 4800)
        ticks2 = _ticks(base, [0, 9800, 17000])  # first executable +7s -> fail
        r2 = M.find_tick_neighbors(ticks2, ev)
        self.assertEqual(r2["status"], "NO_TICK_WITHIN_5S")
        self.assertEqual(r2["post_tick_lag_ms"], 7000)

    def test_tick_alignment_missing_ticks_and_empty(self):
        ev = datetime(2016, 6, 3, 12, 30, 0, tzinfo=UTC)
        r = M.find_tick_neighbors(pd.DatetimeIndex([]), ev)
        self.assertEqual(r["status"], "NO_TICKS_IN_WINDOW")
        far_ticks = _ticks(datetime(2016, 6, 3, 12, 0, 0, tzinfo=UTC), [0])
        r2 = M.find_tick_neighbors(far_ticks, ev)
        self.assertEqual(r2["status"], "NO_TICKS_IN_WINDOW")

    def test_tick_alignment_strictly_before_semantics(self):
        # the pre-event tick must be strictly before the release timestamp
        base = datetime(2016, 6, 3, 12, 29, 59, tzinfo=UTC)
        ticks = _ticks(base, [0, 1000])
        ev = datetime(2016, 6, 3, 12, 30, 0, tzinfo=UTC)
        r = M.find_tick_neighbors(ticks, ev)
        self.assertEqual(r["pre_tick_ts"],
                         datetime(2016, 6, 3, 12, 29, 59, tzinfo=UTC))
        self.assertEqual(r["post_tick_ts"],
                         datetime(2016, 6, 3, 12, 30, 0, tzinfo=UTC))

    def test_weekend_closure_and_weekday_gap_distinction(self):
        sat = datetime(2016, 6, 4, 12, 30, 0, tzinfo=UTC)
        wed = datetime(2016, 6, 8, 12, 30, 0, tzinfo=UTC)
        self.assertTrue(M.is_probable_market_closure(sat))
        self.assertFalse(M.is_probable_market_closure(wed))


# ------------------------------------------------------------------ FOMC
class FomcTests(unittest.TestCase):
    def test_scheduled_vs_unscheduled_classification(self):
        scheduled = {"date": "2018-12-19", "kind": "scheduled",
                     "release_line_raw": "For release at 2:00 p.m. EST",
                     "target_ranges_in_text": [{"low": 2.25, "high": 2.5}],
                     "conventional_time_hhmm_non_official": None,
                     "release_time_source": "statement_page",
                     "statement_url": "u"}
        unscheduled = {"date": "2010-05-09", "kind": "unscheduled_intermeeting",
                       "release_line_raw": "For release at 9:15 p.m. EDT",
                       "target_ranges_in_text": [],
                       "conventional_time_hhmm_non_official": None,
                       "release_time_source": "statement_page",
                       "statement_url": "u2"}

        def ev(r):
            ti = M.parse_fomc_release_line(r["release_line_raw"])
            return {"kind": r["kind"], "date": r["date"], "_time": ti,
                    "ranges": r["target_ranges_in_text"]}

        e1, e2 = ev(scheduled), ev(unscheduled)
        self.assertEqual(e1["kind"], "scheduled")
        self.assertNotEqual(e2["kind"], "scheduled")
        # unscheduled events must never silently merge into the scheduled chain
        self.assertEqual(e2["_time"][0], "21:15")

    def test_fomc_rate_chain_only_moves_when_range_extracted(self):
        evs = [
            {"date": "2012-01-25", "_extracted_range": (0.0, 0.25)},
            {"date": "2012-03-13", "_extracted_range": None},
            {"date": "2012-04-25", "_extracted_range": (0.0, 0.25)},
            {"date": "2012-06-20", "_extracted_range": (0.0, 0.25)},
            {"date": "2012-09-13", "_extracted_range": (0.0, 0.25)},
            {"date": "2012-12-12", "_extracted_range": (0.0, 0.25)},
            {"date": "2015-12-16", "_extracted_range": (0.25, 0.5)},
        ]
        out = M.fomc_rate_chain(evs)
        self.assertIsNone(out[0]["rate_change_bp"])      # no predecessor known
        self.assertIsNone(out[0]["target_before"])
        self.assertIsNone(out[1].get("rate_change_bp"))  # missing -> unavailable
        self.assertIsNone(out[1]["target_after"])        # never guessed
        self.assertEqual(out[2]["target_before"], (0.0, 0.25))
        self.assertEqual(out[6]["rate_change_bp"], 25)   # liftoff
        self.assertEqual(out[6]["target_after"], (0.25, 0.5))

    def test_num_normalisation_fractions(self):
        self.assertEqual(M.norm_num("0"), 0.0)
        self.assertEqual(M.norm_num("1/4"), 0.25)
        self.assertEqual(M.norm_num("1-1/2"), 1.5)
        self.assertEqual(M.norm_num("2\u20111/4"), 2.25)  # Fed NB-hyphen


if __name__ == "__main__":
    unittest.main()
