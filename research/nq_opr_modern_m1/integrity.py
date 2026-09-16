"""Per-year data integrity + roll audit for NQ ohlcv-1m (mission sections 6/8).

Writes:
  E:\\...\\nq\\databento\\manifest\\integrity_by_year.json
  E:\\...\\nq\\databento\\manifest\\roll_audit.csv  (per ET day: contract supplier)
  research/nq_opr_modern_m1/integrity_by_year.json (copy for git)
Reads roll_map.csv (symbology) to name contracts per day.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA_ROOT = Path(r"E:\ResearchData\botTrading\nq\databento")
RAW_DIR = DATA_ROOT / "raw"
PQ_DIR = DATA_ROOT / "parquet"
META_DIR = DATA_ROOT / "manifest"
GIT_DIR = Path(__file__).parent
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
ET = "America/New_York"
TICK = 0.25


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_year(year: int) -> pd.DataFrame:
    df = pd.read_parquet(PQ_DIR / f"nq_1m_{year}.parquet")
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df.sort_values("ts").reset_index(drop=True)


def main() -> int:
    META_DIR.mkdir(parents=True, exist_ok=True)
    roll = pd.read_csv(META_DIR / "roll_map.csv", parse_dates=["start_date", "end_date"])

    def raw_symbol_for_day(d: pd.Timestamp):
        m = roll[(roll["start_date"].dt.tz_localize(None) <= d.tz_localize(None))
                 & (d.tz_localize(None) <= roll["end_date"].dt.tz_localize(None))]
        return m["raw_symbol"].iloc[0] if len(m) else None

    report = {}
    audit_rows = []
    for year in YEARS:
        df = load_year(year)
        ts = df["ts"]
        et = ts.dt.tz_convert(ET)
        et_date = et.dt.date
        hm = et.dt.hour * 100 + et.dt.minute
        rth = (hm >= 930) & (hm < 1600)

        dup = int(df.duplicated(subset=["ts", "instrument_id"]).sum())
        nonmono = int((ts.diff().dt.total_seconds() < 0).sum())
        bad_px = int(((df["close"] <= 0) | (df["open"] <= 0) | (df["high"] <= 0)
                      | (df["low"] <= 0) | (df["high"] < df["low"])
                      | (df["close"] < df["low"] - 1e-9)
                      | (df["close"] > df["high"] + 1e-9)).sum())
        # off-grid prices (tick violations)
        offgrid = int((np.round(df["close"] / TICK) * TICK - df["close"]).abs()
                      .gt(1e-6).sum())

        # RTH session minutes per trading day (days having >=1 RTH bar)
        rth_counts = df[rth].groupby(et_date[rth]).size()
        full_days = int((rth_counts >= 389).sum())
        short_days = {str(k): int(v) for k, v in rth_counts[rth_counts < 389].items()}
        missing_min = int((390 - rth_counts).clip(lower=0).sum())

        # per-day contract supplier (from data itself: instrument_id)
        day_iid = df[rth].groupby(et_date[rth])["instrument_id"].agg(
            lambda s: sorted(s.unique().tolist()))
        straddle = {str(k): v for k, v in day_iid.items() if len(v) > 1}
        iid_to_raw = {}
        for _, r in roll.iterrows():
            iid_to_raw[int(r["instrument_id"])] = r["raw_symbol"]
        for d, iids in day_iid.items():
            named = [iid_to_raw.get(i, f"UNK_{i}") for i in iids]
            audit_rows.append({
                "date": d.isoformat(), "year": year,
                "raw_symbols": "|".join(named),
                "n_rth_bars": int(rth_counts.get(d, 0)),
                "straddle": len(iids) > 1,
            })

        report[str(year)] = {
            "ROWS_1M": int(len(df)),
            "FIRST_TIMESTAMP": str(ts.iloc[0]),
            "LAST_TIMESTAMP": str(ts.iloc[-1]),
            "TRADING_DAYS_RTH": int(len(rth_counts)),
            "FULL_RTH_DAYS(>=389min)": full_days,
            "SHORT_RTH_DAYS(<389min)": short_days,
            "DUPLICATES": dup,
            "NON_MONOTONIC": nonmono,
            "ZERO_OR_INVALID_PRICES": bad_px,
            "OFFGRID_PRICES_0.25": offgrid,
            "MISSING_SESSION_MINUTES": missing_min,
            "SESSION_STRADDLE_DAYS": straddle,
            "INSTRUMENTS_SEEN": sorted(df["instrument_id"].unique().tolist()),
            "ROLLS_IN_YEAR": int(((roll["start_date"].dt.year == year)
                                  & (roll["start_date"].dt.tz_localize(None)
                                     >= pd.Timestamp(f"{year}-01-01"))).sum()),
            "SHA256_RAW": {k: v for k, v in json.loads(
                (META_DIR / f"batch_job_{year}.json").read_text()
            )["sha256_by_file"].items()} if (META_DIR / f"batch_job_{year}.json").exists() else None,
        }
        print(year, json.dumps({k: v for k, v in report[str(year)].items()
                                if k != "SHA256_RAW"}, default=str)[:400])

    (META_DIR / "integrity_by_year.json").write_text(json.dumps(report, indent=1))
    (GIT_DIR / "integrity_by_year.json").write_text(json.dumps(report, indent=1))
    au = pd.DataFrame(audit_rows)
    au.to_csv(META_DIR / "roll_audit.csv", index=False)
    n_straddle = int(au["straddle"].sum())
    print(f"roll_audit rows={len(au)} straddle_days={n_straddle}")
    print("INTEGRITY_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
