#!/usr/bin/env python3
"""MACRO_TICK_M0: final quality report + metrics (mission §9, §13).

Reads data/macro_events_2010_2018_aligned.csv and
data/tick_store_month_coverage.csv, writes data/quality_report.json and
REPORT.md.
"""
from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(BASE, "data")

EXACT_GRADES = {"EXACT_STATEMENT_PAGE", "EXACT_SCHEDULE_PAGE"}
PACKAGE_GRADE = {"OFFICIAL_SAME_RELEASE_PACKAGE_PAGE"}


def rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def main():
    ev = rows(os.path.join(OUT, "macro_events_2010_2018_aligned.csv"))
    fam = {f: [e for e in ev if e["family"] == f] for f in ("NFP", "CPI", "FOMC")}

    def vint(f, field):
        return sum(1 for e in fam[f] if e[field] not in ("", "DATA_UNAVAILABLE", None))

    nfp = {
        "N_EXPECTED_EVENTS": 108,
        "N_EVENTS_FOUND": len(fam["NFP"]),
        "N_EXACT_TIMESTAMPS": sum(
            1 for e in fam["NFP"] if e["timestamp_grade"] in EXACT_GRADES),
        "N_VALUE_VINTAGES_FOUND": vint("NFP", "actual_initial_payems_thousands"),
        "N_EXACT_TIMESTAMP_PCT": pct(sum(1 for e in fam["NFP"]
                                         if e["timestamp_grade"] in EXACT_GRADES), len(fam["NFP"])),
        "N_INITIAL_VALUE_PCT": pct(vint("NFP", "actual_initial_payems_thousands"),
                                   len(fam["NFP"])),
    }
    cpi = {
        "N_EXPECTED_EVENTS": 108,
        "N_EVENTS_FOUND": len(fam["CPI"]),
        "N_EXACT_TIMESTAMPS": sum(1 for e in fam["CPI"]
                                  if e["timestamp_grade"] in EXACT_GRADES),
        "N_VALUE_VINTAGES_FOUND": vint("CPI", "actual_initial_cpiaucsl_index"),
        "N_CORE_VALUE_VINTAGES_FOUND": vint("CPI", "actual_initial_cpilfesl_index"),
        "N_EXACT_TIMESTAMP_PCT": pct(sum(1 for e in fam["CPI"]
                                         if e["timestamp_grade"] in EXACT_GRADES), len(fam["CPI"])),
        "N_INITIAL_VALUE_PCT": pct(vint("CPI", "actual_initial_cpiaucsl_index"),
                                   len(fam["CPI"])),
    }
    fomc_sched = [e for e in fam["FOMC"] if e["fomc_kind"] == "scheduled"]
    fomc_uns = [e for e in fam["FOMC"] if e["fomc_kind"] != "scheduled"]
    fomc = {
        "N_EXPECTED_EVENTS": 72,
        "N_EVENTS_FOUND": len(fam["FOMC"]),
        "N_SCHEDULED": len(fomc_sched),
        "N_UNSCHEDULED": len(fomc_uns),
        "N_UNSCHEDULED_DATES": [e["release_date"] for e in fomc_uns],
        "N_EXACT_TIMESTAMPS_STATEMENT_PAGE": sum(
            1 for e in fam["FOMC"] if e["timestamp_grade"] == "EXACT_STATEMENT_PAGE"),
        "N_SAME_RELEASE_PACKAGE_TIMESTAMPS": sum(
            1 for e in fam["FOMC"]
            if e["timestamp_grade"] in PACKAGE_GRADE),
        "N_DATE_ONLY_DOCUMENTED_BLOCKER": sum(
            1 for e in fam["FOMC"]
            if e["timestamp_grade"] == "DATE_ONLY_OFFICIAL_TIME_UNAVAILABLE"),
        "N_RATE_DECISIONS_RESOLVED": sum(
            1 for e in fomc_sched if e["rate_change_bp"] not in ("", None)),
        "N_EXACT_TIMESTAMP_PCT_SCHEDULED": pct(
            sum(1 for e in fomc_sched if e["timestamp_grade"] in
                (EXACT_GRADES | PACKAGE_GRADE)), len(fomc_sched)),
        "N_RATE_DECISION_VALUE_PCT": pct(
            sum(1 for e in fomc_sched if e["rate_change_bp"] not in ("", None)),
            len(fomc_sched)),
    }

    aligned = [e for e in ev if e["tick_alignment_status"] == "ALIGNED"]
    no5s = [e for e in ev if e["tick_alignment_status"] == "NO_TICK_WITHIN_5S"]
    gaps = [e for e in ev if e["tick_alignment_status"] == "TICK_FILE_MISSING"
            or e["tick_alignment_status"] == "NO_TICKS_IN_WINDOW"]
    lags = sorted(int(e["post_tick_lag_ms"]) for e in aligned
                  if e["post_tick_lag_ms"] != "")
    max_lag = max(lags) if lags else None
    median_lag = lags[len(lags) // 2] if lags else None

    align = {
        "N_EVENTS": len(ev),
        "N_EVENTS_WITH_TICK_ALIGNMENT": len(aligned),
        "EVENTS_WITH_TICK_ALIGNMENT_PCT": pct(len(aligned), len(ev)),
        "N_FIRST_TICK_BEYOND_5S": len(no5s),
        "N_EVENTS_IN_TICK_DATA_GAPS": len(gaps),
        "GAP_EVENT_IDS": [e["event_id"] for e in gaps],
        "SLOW_5S_EVENT_IDS": [e["event_id"] for e in no5s],
        "MAX_POST_EVENT_TICK_LAG_MS": max_lag,
        "MEDIAN_POST_EVENT_TICK_LAG_MS": median_lag,
    }

    cov = rows(os.path.join(OUT, "tick_store_month_coverage.csv"))
    low_months = [r["month"] for r in cov if int(r["days_covered"]) < 20]

    # cross-check: extracted FOMC rate changes vs ALFRED DFEDTARU (current
    # series used ONLY as an independent sanity check of change dates).
    # File has no header: columns are observation_date,DFEDTARU.
    with open(os.path.join(BASE, "source_manifests", "dfedtaru_current.csv"),
              encoding="utf-8") as f:
        dft = [(r[0], float(r[1])) for r in csv.reader(f) if r]
    changes = []  # effective dates where the target upper bound moved
    prev_d, prev_v = None, None
    for d, v in dft:
        if prev_v is not None and v != prev_v:
            changes.append((d, prev_v, v))
        prev_d, prev_v = d, v
    hike_check = []
    for e in fomc_sched:
        if e["rate_change_bp"] not in ("", None) and int(e["rate_change_bp"]) != 0:
            d = datetime.fromisoformat(e["release_date"]).date()
            eff = [c for c in changes
                   if 0 <= (datetime.fromisoformat(c[0]).date() - d).days <= 2]
            hike_check.append({
                "event": e["event_id"], "change_bp": e["rate_change_bp"],
                "dfedtaru_change_within_2d": eff[0] if eff else None})
    mismatches = [h for h in hike_check if h["dfedtaru_change_within_2d"] is None]

    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "discovery_range": "2010-01-01 inclusive .. 2019-01-01 exclusive",
        "NFP": nfp,
        "CPI": cpi,
        "FOMC": fomc,
        "TICK_ALIGNMENT": align,
        "TICK_STORE_LOW_COVERAGE_MONTHS": low_months,
        "FOMC_DFEDTARU_CROSSCHECK": {
            "n_nonzero_changes_checked": len(hike_check),
            "n_mismatched": len(mismatches),
            "mismatches": mismatches,
            "all_changes_dates": [c[0] for c in changes],
        },
        "CONSENSUS_DATA_STATUS": "NOT_AVAILABLE_FREE_RELIABLY",
        "issues": {
            "NFP": [e["event_id"] for e in fam["NFP"]
                    if e["timestamp_grade"] != "EXACT_SCHEDULE_PAGE"],
            "CPI": [e["event_id"] for e in fam["CPI"]
                    if e["timestamp_grade"] != "EXACT_SCHEDULE_PAGE"],
        },
    }
    with open(os.path.join(OUT, "quality_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1)
    print(json.dumps(report, indent=1)[:3000])
    print("wrote quality_report.json")


if __name__ == "__main__":
    main()
