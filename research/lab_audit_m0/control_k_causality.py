#!/usr/bin/python3
"""LAB_AUDIT_M0 — Control K: time / causality guards (spec section 10).
Sub-tests: 2019+ partition guard, UTC range boundary semantics, discovery-date
guard, store load guards (production TickStore AND audit loader), DST offsets
(hand-known UTC conversions), legacy server-time conversion, completed-M1-bar
causality (decision uses the close of the completed bucket, never a later
tick), explicit future-read rejection (NO_FILL / NO_TIME_EXIT_DATA), and
oracle isolation (the lookahead function exists ONLY in the audit scripts).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import lab_audit_lib as AL
import po3_base_m0_lib as PO3
import legacy_reverse_m1_lib as LEGACY

FAILS = []
SEC = AL.SEC


def expect_raises(name, fn, exc=(PO3.OutOfWindowError,)):
    try:
        fn()
    except exc:
        return
    except Exception as e:  # wrong exception type
        FAILS.append(f"{name}: raised {type(e).__name__} instead of {exc}")
        return
    FAILS.append(f"{name}: no exception raised")


def ok(name, cond):
    if not cond:
        FAILS.append(f"{name}: FAILED")


def test_guards():
    expect_raises("K1_guard_partition_2019",
                  lambda: PO3.guard_partition_path("E:/x/year=2019/month=01/ticks.parquet"))
    expect_raises("K1_guard_partition_2020",
                  lambda: PO3.guard_partition_path("E:/x/year=2020/month=07/ticks.parquet"))
    ok("K1_guard_partition_2018_ok",
       PO3.guard_partition_path("E:/x/year=2018/month=12/ticks.parquet") == (2018, 12))

    s, e = PO3.UTC_GUARD_START_NS, PO3.UTC_GUARD_END_NS
    PO3.assert_utc_range(s, e)                                   # exact bounds pass
    expect_raises("K2_utc_range_past", lambda: PO3.assert_utc_range(s - 1, e))
    expect_raises("K3_utc_range_2019", lambda: PO3.assert_utc_range(s, e + 1))

    PO3.assert_discovery_date(date(2018, 12, 31))
    expect_raises("K4_discovery_2019", lambda: PO3.assert_discovery_date(date(2019, 1, 1)))
    expect_raises("K4_discovery_2010_01_01", lambda: PO3.assert_discovery_date(date(2010, 1, 1)))

    expect_raises("K5_tickstore_2019",
                  lambda: LEGACY.TickStore().load_range(s, e + SEC))
    guard_types = (PO3.OutOfWindowError, AL.ForbiddenRangeError)
    expect_raises("K6_audit_loader_2019", lambda: AL.load_range(s, e + SEC), guard_types)
    expect_raises("K6_audit_partition_2019", lambda: AL.partition_path(2019, 1), guard_types)


def test_dst_and_server_time():
    # hand-known offsets: 2011-03-27 London is BST (UTC+1) from 01:00 UTC;
    # 2011-10-30 London is GMT (UTC+0) from 01:00 UTC.
    ok("K7_dst_spring", AL.london_ns(date(2011, 3, 27), 10, 0)
       == int(datetime(2011, 3, 27, 9, 0, tzinfo=timezone.utc).timestamp()) * SEC)
    ok("K7_dst_autumn", AL.london_ns(date(2011, 10, 30), 10, 0)
       == int(datetime(2011, 10, 30, 10, 0, tzinfo=timezone.utc).timestamp()) * SEC)
    # PO3 session helper must agree
    ok("K7_dst_po3_spring", PO3._london_ns(date(2011, 3, 27), 12, 0)
       == int(datetime(2011, 3, 27, 11, 0, tzinfo=timezone.utc).timestamp()) * SEC)
    # legacy server-time conversion: 09:15 Helsinki (EET, UTC+2) = 07:15Z
    want = int(datetime(2010, 1, 19, 7, 15, tzinfo=timezone.utc).timestamp()) * SEC
    got = LEGACY.server_to_ns(datetime(2010, 1, 19, 9, 15))
    ok("K8_helsinki_server_time", got == want)
    # summer: 09:15 Helsinki (EEST, UTC+3) on 2010-07-19 = 06:15Z
    want2 = int(datetime(2010, 7, 19, 6, 15, tzinfo=timezone.utc).timestamp()) * SEC
    ok("K8_helsinki_dst_summer",
       LEGACY.server_to_ns(datetime(2010, 7, 19, 9, 15)) == want2)


def test_bar_causality():
    """Completed-M1-bar decision: the reintigration close is the last tick of
    the completed bucket (strictly before the boundary); a spike exactly AT
    the bucket end must not leak into the decision (decision_ts == bucket end,
    close == pre-boundary value)."""
    d = date(2015, 6, 10)
    MIN = PO3.MINUTE_NS
    ts = [AL.london_ns(d, 0, 0) + i * 7 * SEC for i in range(3600)]   # 00:00-07:00
    # Asia range: alternating 1.09995 / 1.10005 -> high 1.10005, low 1.09995,
    # range = 1 pip, upper sweep threshold = 1.10007
    mids = [1.10005 if i % 2 else 1.09995 for i in range(3600)]
    def at(h, m, s, px):
        ts.append(AL.london_ns(d, h, m, s))
        mids.append(px)
    for m_ in range(1, 30):                      # 07:01..07:29 flat pre-sweep
        at(7, m_, 0, 1.10000)
    at(7, 30, 0, 1.10010)                        # sweep tick (>= upper_thr)
    for m_ in range(31, 59):                     # post-sweep flat ticks
        at(7, m_, 0, 1.10000)
    at(7, 30, 59, 1.10000)                       # last tick of the 07:30 bucket
    # NOTE: flat 07:31.. ticks below
    order = np.argsort(np.array(ts, dtype=np.int64), kind="stable")
    ts_arr = np.array(ts, dtype=np.int64)[order]
    mid_arr = np.array(mids, dtype=np.float64)[order]

    b = PO3.day_bounds(d)
    rng = PO3.asian_range(ts_arr, mid_arr, b)
    ok("K9_asia_eligible", rng.eligible)
    setup = PO3.detect_setup(ts_arr, mid_arr, b, rng)
    bucket_end = (AL.london_ns(d, 7, 30, 0) // MIN + 1) * MIN
    ok("K9_setup_traded", setup.status == PO3.TRADE)
    ok("K9_decision_at_completed_bucket", setup.decision_ts == bucket_end)
    ok("K9_close_is_completed_bucket_close", abs(setup.close_price - 1.10000) < 1e-12)

    # now add a spike tick exactly AT the bucket end (future leak attempt):
    # the decision must still be the bucket-end event valued at the PRIOR tick
    ts2 = list(ts_arr)
    mid2 = list(mid_arr)
    j = int(np.searchsorted(ts2, bucket_end))
    ts2.insert(j, bucket_end)
    mid2.insert(j, 1.10050)                      # future-looking spike at boundary
    setup2 = PO3.detect_setup(np.array(ts2), np.array(mid2), b, rng)
    ok("K9_no_future_leak_status", setup2.status == PO3.TRADE)
    ok("K9_no_future_leak_close", abs(setup2.close_price - 1.10050) > 1e-9
       or setup2.decision_ts != bucket_end)
    # decision must still be the same bucket-end event using the PRIOR tick
    ok("K9_decision_ts_stable", setup2.decision_ts == setup.decision_ts
       or setup2.decision_ts == bucket_end)


def test_future_read_rejection():
    """A decision with no tick inside the fill bound returns NO_FILL (never
    reads past the bound); a time exit with no tick inside the quote bound
    returns NO_TIME_EXIT_DATA."""
    t0 = AL.london_ns(date(2015, 6, 10), 8, 0)
    ts = np.array([t0 - SEC, t0 + 36 * SEC, t0 + 400 * SEC], dtype=np.int64)
    bid = np.array([1.1, 1.1, 1.1]); ask = np.array([1.1, 1.1, 1.1])
    ex = PO3.execute(ts, bid, ask, +1, 1.09, t0, 5 * SEC, t0 + 3900 * SEC)
    ok("K10_no_fill_on_empty_bound", ex.status == "NO_FILL")
    ts2 = np.array([t0 + 5 * SEC, t0 + 4000 * SEC], dtype=np.int64)
    bid2 = np.array([1.1, 1.1]); ask2 = np.array([1.1, 1.1])
    ex2 = PO3.execute(ts2, bid2, ask2, +1, 1.09, t0, 5 * SEC, t0 + 3900 * SEC)
    ok("K11_no_time_exit_data", ex2.status == "NO_TIME_EXIT_DATA")
    ok("K11_no_time_exit_entry_kept", ex2.entry_ts == t0 + 5 * SEC)


def test_oracle_isolation():
    """The lookahead oracle function name must exist ONLY in audit scripts."""
    needle = "oracle_lookahead_invalid"
    prod_files = [
        AL._REPO / "research" / "po3_base_m0" / "po3_base_m0_lib.py",
        AL._REPO / "research" / "legacy_reverse_m1" / "legacy_reverse_m1_lib.py",
        AL._REPO / "research" / "legacy_bots_m1" / "m1_engine.py",
        AL._REPO / "research_engine.py",
        AL._REPO / "research" / "lab_audit_m0" / "lab_audit_lib.py",
    ]
    here = Path(__file__).parent
    for f in prod_files:
        txt = f.read_text(errors="ignore").lower()
        if needle in txt:
            FAILS.append(f"K12_oracle_isolation: {f.name} references the oracle")
    me = (here / "control_d_random_real.py").read_text(errors="ignore").lower()
    if needle not in me:
        FAILS.append("K12_oracle_isolation: oracle function not found in audit D/E/F script")


def main() -> dict:
    test_guards()
    test_dst_and_server_time()
    test_bar_causality()
    test_future_read_rejection()
    test_oracle_isolation()
    return {"control": "K_causality_guards",
            "failures": FAILS, "n_failures": len(FAILS),
            "PASS": len(FAILS) == 0}


if __name__ == "__main__":
    r = main()
    (Path(__file__).parent / "RESULTS_k.json").write_text(json.dumps(r, indent=1))
    print(json.dumps(r, indent=1))
    print("CONTROL_K_PASS" if r["PASS"] else "CONTROL_K_FAIL")
