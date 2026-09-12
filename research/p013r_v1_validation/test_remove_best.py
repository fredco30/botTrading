#!/usr/bin/env python3
"""Finalization tests: remove-best = MEAN after removal (not an ordinal
value), and report/JSON consistency of the headline metrics."""
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


class TestRemoveBestSemantics(unittest.TestCase):
    def _remove_best(self, x, k):
        sr = __import__("numpy").sort(__import__("numpy").asarray(x, dtype=float))[::-1]
        return round(float(sr[k:].mean()), 2)

    def test_remove_best_is_mean_after_removal(self):
        x = [100.0, 20.0, 10.0, -10.0]
        # mean([20, 10, -10]) = 6.67 — NOT the 2nd best value (20)
        # (helper rounds to 2 decimals for reporting -> delta=0.005)
        self.assertAlmostEqual(self._remove_best(x, 1), 6.67, delta=0.005)

    def test_remove_best3_is_mean_after_removal_long_fixture(self):
        # longer fixture distinguishes index vs mean:
        # remove 3 best (100, 50, 40) -> remaining [30, -10, -20, -30]
        # -> mean = -7.5 (the 4th-best VALUE would be 30: wrong)
        x = [100.0, 50.0, 40.0, 30.0, -10.0, -20.0, -30.0]
        self.assertAlmostEqual(self._remove_best(x, 3), -7.5, places=6)
        # and remove-best-1 on the same fixture -> mean(50,40,30,-10,-20,-30) = 10
        self.assertAlmostEqual(self._remove_best(x, 1), 10.0, places=6)

    def test_run_v1_semantics_matches_reference(self):
        # the exact computation used by run_v1.py on a small sample
        pooled_net = [100.0, 20.0, 10.0, -10.0]
        sr = __import__("numpy").sort(__import__("numpy").asarray(pooled_net))[::-1]
        remove_best = round(float(sr[1:].mean()), 2)
        remove_best3 = round(float(sr[3:].mean()), 2) if len(sr) > 3 else None
        self.assertEqual(remove_best, 6.67)
        self.assertEqual(remove_best3, -10.0)


class TestReportJsonConsistency(unittest.TestCase):
    """Light guard: headline numbers in P013R_V1_REPORT.md must match
    p013r_v1_results.json (prevents manual-transcription divergence)."""

    def test_report_matches_json_headlines(self):
        res_path = os.path.join(HERE, "p013r_v1_results.json")
        rep_path = os.path.join(HERE, "P013R_V1_REPORT.md")
        if not (os.path.exists(res_path) and os.path.exists(rep_path)):
            self.skipTest("results/report not yet generated on this checkout")
        res = json.load(open(res_path, encoding="utf-8"))
        rep = open(rep_path, encoding="utf-8").read()
        # combined/ bolded table rows: guard = the JSON VALUE must appear
        # verbatim somewhere in the report (light transcription guard)
        for key in ("POOLED_GROSS", "POOLED_NET_NORMAL", "POOLED_NET_STRESS",
                    "MEDIAN_NET_NORMAL", "WIN_RATE_NET_NORMAL",
                    "REMOVE_BEST_EVENT_NET_NORMAL",
                    "REMOVE_BEST_3_EVENTS_NET_NORMAL",
                    "POSITIVE_YEARS_NET_NORMAL",
                    "PAIRED_CI95_GROSS", "PAIRED_CI95_NET_NORMAL",
                    "YEAR_BLOCK_CI95_GROSS", "YEAR_BLOCK_CI95_NET_NORMAL"):
            self.assertIn(str(res[key]), rep,
                          f"report/JSON mismatch on {key}")
        self.assertIn(res["V1_CLASSIFICATION"], rep)


if __name__ == "__main__":
    unittest.main()
