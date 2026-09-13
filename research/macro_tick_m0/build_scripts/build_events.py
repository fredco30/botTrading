#!/usr/bin/env python3
"""MACRO_TICK_M0: build the causal macro event dataset (2010-2018).

Inputs (source_manifests/, data_raw/alfred_vintages/ - see README):
  * BLS archived news-release indexes (actual release dates, official)
  * BLS yearly schedule pages (per-entry scheduled times, Eastern Time)
  * Fed FOMC statement extraction (official dates/times/ranges)
  * ALFRED vintage stores (PAYEMS, CPIAUCSL, CPILFESL)

Outputs (data/):
  macro_events_2010_2018.csv   - one row per event (git-safe)
  quality_report.json          - family coverage metrics + issues
"""
from __future__ import annotations

import csv
import json
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import macro_lib as M  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(BASE, "source_manifests")
RAW = os.path.join(BASE, "data_raw", "alfred_vintages")
OUT = os.path.join(BASE, "data")


def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- vintages
def load_vintage_store(parts, series):
    store = {}  # vintage_date -> {obs_date: value}
    for p in parts:
        data = load_json(p)
        for vdate, rec in data.items():
            col = rec["col"]
            if not col.startswith("observation_date," + series + "_"):
                raise ValueError(f"vintage mismatch for {series} {vdate}: {col[:60]}")
            col_vdate = col.split(series + "_")[1]
            if col_vdate != vdate.replace("-", ""):
                raise ValueError(
                    f"ALFRED returned vintage {col_vdate} for requested {vdate}")
            store[vdate] = {row.split(",")[0]: row.split(",")[1]
                            for row in rec["csv"] if row and "," in row}
    return store


def vintage_value(store, vintage_date, obs_ym):
    v = store.get(vintage_date)
    if v is None:
        return None
    return v.get(obs_ym + "-01")


# ---------------------------------------------------------------- BLS side
def build_bls_events(family, archive_index_path, sched_key, series_store_parts,
                     series_name, value_builder):
    archive = load_json(os.path.join(SRC, archive_index_path))
    sched = load_json(os.path.join(SRC, "bls_schedule_entries_2010_2018.json"))
    store = load_vintage_store(series_store_parts, series_name)

    # actual release dates sorted; include the pre-2010 previous release for
    # "previous value as known before" of the first 2010 event.
    releases = sorted({r["date"] for r in archive})
    if family == "NFP":
        releases = ["2009-12-04"] + releases
    else:
        releases = ["2009-12-16"] + releases

    events = []
    issues = []
    for r in archive:
        rel_date = date.fromisoformat(r["date"])
        ref = M.reference_period_from_label(r["label"])
        if ref is None:
            issues.append({"event": r["date"], "issue": "NO_REFERENCE_MONTH_IN_LABEL"})
            continue
        # per-entry scheduled time from the BLS schedule year pages
        year_page = str(rel_date.year)
        entry = None
        for e in sched.get(year_page, []):
            try:
                ed = datetime.strptime(e["date"], "%B %d, %Y").date()
            except ValueError:
                continue
            if ed == rel_date and sched_family_match(e["name"], family) \
                    and M.reference_period_from_label("for " + ref_label_fix(ref)) == ref:
                entry = e
                break
        if entry is None:
            issues.append({"event": r["date"],
                           "issue": "NO_SCHEDULE_ENTRY_TIME_FALLBACK_0830"})
            hhmm = "08:30"
            provenance = ("bls_family_standard_time_not_found_for_entry; "
                          "date from bls archive index; time fallback 08:30 ET")
        else:
            hhmm = M.parse_schedule_time(entry["time"])
            provenance = (f"bls_schedule/{year_page}/home.htm entry "
                          f"('{entry['time']} Eastern Time', "
                          f"weekday {entry['weekday']})")
        ts_utc = M.et_to_utc(rel_date, hhmm)
        ts_et = M.utc_to_et(ts_utc)
        rec = {
            "event_id": f"MACRO-{family}-{ref.replace('-', '')}",
            "family": family,
            "release_date": r["date"],
            "release_timestamp_et": ts_et.isoformat(),
            "release_timestamp_utc": ts_utc.isoformat().replace("+00:00", "Z"),
            "reference_period": ref,
            "label": r["label"],
            "archive_url": "https://www.bls.gov" + r["href"],
            "timestamp_provenance": provenance,
            "timestamp_grade": "EXACT_SCHEDULE_PAGE" if entry is not None
            else "FALLBACK_TIME_NOT_PER_ENTRY",
        }
        value_builder(rec, store, releases, r["date"], ref, issues)
        events.append(rec)
    return events, issues


def ref_label_fix(ref):
    ym = ref.split("-")
    names = list(M.MONTHS.items())
    name = next(n for n, mnum in names if mnum == int(ym[1]))
    return f"{name} {ym[0]}"


def sched_family_match(name, family):
    return ("Employment Situation" in name) if family == "NFP" \
        else ("Consumer Price Index" in name)


# ---------------------------------------------------------------- value builders
def nfp_values(rec, store, releases, rel_date, ref, issues):
    idx = releases.index(rel_date)
    prev_rel = releases[idx - 1] if idx > 0 else None
    next_rel = releases[idx + 1] if idx + 1 < len(releases) else None
    actual = vintage_value(store, rel_date, ref)
    prev = vintage_value(store, prev_rel, M.prev_month(ref)) if prev_rel else None
    rev = vintage_value(store, next_rel, ref) if next_rel else None
    rec.update({
        "actual_initial_payems_thousands": actual,
        "previous_published_payems_thousands": prev,
        "revision1_payems_thousands": rev,
        "revision1_available_at": next_rel,
        "value_source": ("ALFRED PAYEMS vintage "
                         f"{rel_date} (realtime_start=release date)"),
        "value_available_time_utc": rec["release_timestamp_utc"],
        "value_time_precision": "DATE_ONLY",
    })
    if actual is None:
        issues.append({"event": rec["event_id"], "issue": "VINTAGE_VALUE_MISSING"})
    if prev is None:
        issues.append({"event": rec["event_id"],
                       "issue": "PREVIOUS_VINTAGE_VALUE_MISSING"})


def cpi_values(rec, store, releases, rel_date, ref, issues):
    idx = releases.index(rel_date)
    prev_rel = releases[idx - 1] if idx > 0 else None
    actual = vintage_value(store, rel_date, ref)
    prev = vintage_value(store, prev_rel, M.prev_month(ref)) if prev_rel else None
    rec.update({
        "actual_initial_cpiaucsl_index": actual,
        "previous_published_cpiaucsl_index": prev,
        "value_source": ("ALFRED CPIAUCSL vintage "
                         f"{rel_date} (realtime_start=release date)"),
        "value_available_time_utc": rec["release_timestamp_utc"],
        "value_time_precision": "DATE_ONLY",
    })
    if actual is None:
        issues.append({"event": rec["event_id"], "issue": "VINTAGE_VALUE_MISSING"})


def cpi_core_values(rec, store, releases, rel_date, ref, issues):
    actual = vintage_value(store, rel_date, ref)
    prev_rel = releases[releases.index(rel_date) - 1] \
        if releases.index(rel_date) > 0 else None
    prev = vintage_value(store, prev_rel, M.prev_month(ref)) if prev_rel else None
    rec.update({
        "actual_initial_cpilfesl_index": actual,
        "previous_published_cpilfesl_index": prev,
        "core_value_source": ("ALFRED CPILFESL vintage "
                              f"{rel_date} (realtime_start=release date)"),
    })


# ---------------------------------------------------------------- FOMC side
def build_fomc_events():
    recs = load_json(os.path.join(SRC, "fomc_statements.json"))
    events, issues = [], []
    prev_after = None  # (low, high) prevailing range
    for r in sorted(recs, key=lambda x: x["date"]):
        d = date.fromisoformat(r["date"])
        time_info = M.parse_fomc_release_line(r.get("release_line_raw"))
        ranges = r.get("target_ranges_in_text") or []
        rng = None
        for rr in ranges:
            rng = (rr["low"], rr["high"])
            break
        if time_info:
            hhmm, tz = time_info
            if not M.tz_label_matches_date(tz, d):
                issues.append({"event": r["date"],
                               "issue": f"TZ_LABEL_MISMATCH_{tz}"})
            ts_utc = M.et_to_utc(d, hhmm)
            grade = "EXACT_STATEMENT_PAGE" \
                if r["release_time_source"] == "statement_page" \
                else "OFFICIAL_SAME_RELEASE_PACKAGE_PAGE"
            prov = (f"official page line '{r['release_line_raw']}' "
                    f"({r['release_time_source']})")
        else:
            hhmm = r["conventional_time_hhmm_non_official"]
            ts_utc = M.et_to_utc(d, hhmm)
            grade = "DATE_ONLY_OFFICIAL_TIME_UNAVAILABLE"
            prov = ("official page shows release DATE only (verified also in "
                    "era Wayback captures); timestamp uses NON-official "
                    f"convention {hhmm} ET and is flagged not exact")
        ev = {
            "event_id": f"MACRO-FOMC-{r['date'].replace('-', '')}",
            "family": "FOMC",
            "release_date": r["date"],
            "release_timestamp_utc": ts_utc.isoformat().replace("+00:00", "Z"),
            "reference_period": r["date"],
            "fomc_kind": r["kind"],
            "timestamp_grade": grade,
            "timestamp_provenance": prov,
            "statement_url": r["statement_url"],
            "value_available_time_utc": ts_utc.isoformat().replace("+00:00", "Z"),
            "value_time_precision": (
                "EXACT" if time_info else "CONVENTION_NON_OFFICIAL"),
            "target_before": None, "target_after": None, "rate_change_bp": None,
        }
        if r["kind"] == "scheduled":
            if rng is not None:
                ev["target_before"] = (
                    f"{prev_after[0]:g}-{prev_after[1]:g}%" if prev_after
                    else "DATA_UNAVAILABLE")
                ev["target_after"] = f"{rng[0]:g}-{rng[1]:g}%"
                if prev_after is not None:
                    ev["rate_change_bp"] = int(round((rng[1] - prev_after[1]) * 100))
                prev_after = rng
            else:
                ev["target_after"] = "DATA_UNAVAILABLE"
                if prev_after is not None:
                    ev["target_before"] = f"{prev_after[0]:g}-{prev_after[1]:g}%"
                issues.append({"event": r["date"],
                               "issue": "RATE_RANGE_NOT_EXTRACTED"})
        else:
            # unscheduled intermeeting statement: prevailing range unchanged
            # (no target sentence on the page); do not advance the chain.
            ev["rate_decision_note"] = (
                "unscheduled intermeeting statement; no federal funds target "
                "action in statement text")
            if prev_after is not None:
                ev["target_before"] = f"{prev_after[0]:g}-{prev_after[1]:g}%"
                ev["target_after"] = ev["target_before"]
                ev["rate_change_bp"] = 0
        events.append(ev)
    return events, issues


# ---------------------------------------------------------------- main
def main():
    os.makedirs(OUT, exist_ok=True)
    payems_parts = [os.path.join(RAW, f"alfred_vintages_PAYEMS_part{i}.json")
                    for i in (1, 2, 3)]
    cpia = [os.path.join(RAW, "alfred_vintages_CPIAUCSL.json")]
    cpif = [os.path.join(RAW, "alfred_vintages_CPILFESL.json")]

    nfp, nfp_issues = build_bls_events(
        "NFP", "bls_empsit_archive_index.json", "empsit", payems_parts,
        "PAYEMS", nfp_values)
    cpi, cpi_issues = build_bls_events(
        "CPI", "bls_cpi_archive_index.json", "cpi", cpia, "CPIAUCSL", cpi_values)
    # merge core CPI values into the CPI events
    core_store = load_vintage_store(cpif, "CPILFESL")
    for ev in cpi:
        rel = ev["release_date"]
        ref = ev["reference_period"]
        ev["actual_initial_cpilfesl_index"] = vintage_value(core_store, rel, ref)
        prev_rels = ["2009-12-16"] + sorted({
            r["date"] for r in load_json(os.path.join(SRC, "bls_cpi_archive_index.json"))})
        i = prev_rels.index(rel)
        prev_rel = prev_rels[i - 1] if i > 0 else None
        ev["previous_published_cpilfesl_index"] = (
            vintage_value(core_store, prev_rel, M.prev_month(ref))
            if prev_rel else None)

    fomc, fomc_issues = build_fomc_events()

    events = nfp + cpi + fomc
    events = M.dedupe_and_sort(events)
    M.assert_no_2019_plus(events)
    for e in events:
        M.assert_value_causality(e)

    # drop helper fields not meant for the dataset
    cols = ["event_id", "family", "release_date", "reference_period",
            "release_timestamp_utc", "timestamp_grade", "timestamp_provenance",
            "fomc_kind", "actual_initial_payems_thousands",
            "previous_published_payems_thousands", "revision1_payems_thousands",
            "revision1_available_at", "actual_initial_cpiaucsl_index",
            "previous_published_cpiaucsl_index",
            "actual_initial_cpilfesl_index", "previous_published_cpilfesl_index",
            "target_before", "target_after", "rate_change_bp",
            "rate_decision_note", "value_source", "core_value_source",
            "value_available_time_utc", "value_time_precision",
            "archive_url", "statement_url", "label"]
    events = [{k: e.get(k, "") for k in cols} for e in events]

    out_csv = os.path.join(OUT, "macro_events_2010_2018.csv")
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(events)

    # ------------------------------------------------ quality metrics
    def fam_metrics(fam, evs, value_field, sched_only=False):
        n = len(evs)
        n_exact = sum(1 for e in evs if "bls_schedule" in str(e["timestamp_provenance"])
                      or e.get("timestamp_grade") in
                      ("EXACT_STATEMENT_PAGE", "OFFICIAL_SAME_RELEASE_PACKAGE_PAGE"))
        n_val = sum(1 for e in evs if e.get(value_field) not in (None, "", "DATA_UNAVAILABLE"))
        return {
            "N_EXPECTED_EVENTS": 108 if fam in ("NFP", "CPI") else 72,
            "N_EVENTS_FOUND": n,
            "N_EXACT_TIMESTAMPS": n_exact,
            "N_VALUE_VINTAGES_FOUND": n_val,
        }

    q = {
        "generated_utc": datetime.utcnow().isoformat() + "Z",
        "NFP": fam_metrics("NFP", nfp, "actual_initial_payems_thousands"),
        "CPI": fam_metrics("CPI", cpi, "actual_initial_cpiaucsl_index"),
        "FOMC": {
            **fam_metrics("FOMC", fomc, "target_after"),
            "N_UNSCHEDULED": sum(1 for e in fomc if e["fomc_kind"] != "scheduled"),
            "N_DATE_ONLY_BLOCKER": sum(
                1 for e in fomc
                if e.get("timestamp_grade") == "DATE_ONLY_OFFICIAL_TIME_UNAVAILABLE"),
        },
        "issues": {
            "NFP": nfp_issues,
            "CPI": cpi_issues,
            "FOMC": fomc_issues,
        },
    }
    with open(os.path.join(OUT, "quality_report.json"), "w", encoding="utf-8") as f:
        json.dump(q, f, indent=1)

    print(f"events: {len(events)} (NFP {len(nfp)}, CPI {len(cpi)}, FOMC {len(fomc)})")
    print("wrote", out_csv)


if __name__ == "__main__":
    main()
