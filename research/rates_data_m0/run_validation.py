"""Convert raw DBN month files to parquet, run full validation, and write
quality reports + roll audit to E: (and small reports into the repo)."""
import csv
import json
import sys
from pathlib import Path

import pandas as pd

import databento

import validation as V

DATA_ROOT = Path(r"E:\ResearchData\botTrading\rates\databento")
RAW_DIR = DATA_ROOT / "raw"
PARQUET_DIR = DATA_ROOT / "parquet"
META_DIR = DATA_ROOT / "metadata"
REPORT_DIR = Path(__file__).parent / "reports"
SYMBOLS = ["ZT", "ZF", "ZN"]


def raw_files() -> list[Path]:
    return sorted(RAW_DIR.glob("glbx-mdp3-*.ohlcv-1m.dbn.zst"))


def load_all() -> pd.DataFrame:
    """Decode every monthly DBN file once; returns all symbols concatenated
    with a 'symbol' column (ZT/ZF/ZN) resolved via roll_map instrument ids."""
    cache = PARQUET_DIR / "all_symbols.parquet"
    if cache.exists():
        return pd.read_parquet(cache)
    frames = []
    for f in raw_files():
        df = databento.DBNStore.from_file(str(f)).to_df()
        df.columns = [str(c) for c in df.columns]
        df["symbol"] = df["symbol"].str.split(".").str[0]
        frames.append(df)
    out = pd.concat(frames)
    out.index = pd.to_datetime(out.index, utc=True)
    out = out.sort_index()
    out.to_parquet(cache)
    return out


def load_bars(sym: str, all_df: pd.DataFrame | None = None) -> pd.DataFrame:
    out = PARQUET_DIR / f"{sym}.parquet"
    if out.exists():
        return pd.read_parquet(out)
    df = (all_df if all_df is not None else load_all())
    df = df[df["symbol"] == sym].copy()
    df.index = pd.to_datetime(df.index, utc=True)
    df = df[~df.index.duplicated(keep="first")].sort_index()
    df.to_parquet(out)
    return df


def main() -> int:
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    roll_map = {}
    with (META_DIR / "roll_map.csv").open() as fh:
        for row in csv.DictReader(fh):
            roll_map.setdefault(row["symbol"], []).append(row)

    eurusd_minutes = load_eurusd_minutes()
    all_df = load_all()
    summary = {}
    audit_rows = []
    for sym in SYMBOLS:
        df = load_bars(sym, all_df)
        inst_col = "instrument_id" if "instrument_id" in df.columns else None
        base = df[["open", "high", "low", "close", "volume"] + ([inst_col] if inst_col else [])].copy()
        gaps = V.unexpected_gaps(base)
        all_g = V.all_gaps(base)
        gap_counts = {}
        for g in all_g:
            gap_counts[g.kind] = gap_counts.get(g.kind, 0) + 1
        rolls = V.roll_gaps(base, roll_map.get(sym, []))
        for ev in rolls:
            audit_rows.append({
                "symbol": sym,
                "old_raw": ev.old_raw,
                "new_raw": ev.new_raw,
                "old_last_ts": ev.old_last_ts,
                "new_first_ts": ev.new_first_ts,
                "old_last_close": ev.old_last_close,
                "new_first_close": ev.new_first_close,
                "price_gap": ev.price_gap,
            })
        summary[sym] = {
            "N_RECORDS": len(df),
            "FIRST": str(df.index[0]),
            "LAST": str(df.index[-1]),
            "MISSING_DAYS": V.missing_days(df, "2010-06-06", "2019-01-01"),
            "DUPLICATE_TIMESTAMP_COUNT": V.duplicate_timestamp_count(base),
            "NON_MONOTONIC_COUNT": V.non_monotonic_count(base),
            "ZERO_VOLUME_COUNT": V.zero_volume_count(base),
            "OHLC_INVALID_COUNT": int(V.ohlc_invalid_mask(base).sum()),
            "NAN_COUNT": V.nan_count(base),
            "ROLL_INTERVAL_COUNT": len(roll_map.get(sym, [])),
            "RAW_CONTRACT_COUNT": len({r["raw_symbol"] for r in roll_map.get(sym, [])}),
            "UNEXPECTED_GAPS": len(gaps),
            "GAP_COUNTS_BY_KIND": gap_counts,
            "ALIGNMENT_PCT": round(100.0 * V.align_pct(eurusd_minutes, base), 2),
        }
        with (REPORT_DIR / f"{sym.lower()}_gaps.json").open("w") as fh:
            json.dump([{"start": str(g.start), "end": str(g.end), "minutes": g.minutes,
                        "kind": g.kind} for g in all_g], fh, indent=1)
        print(sym, json.dumps(summary[sym]))
        del df, base

    audit = pd.DataFrame(audit_rows)
    audit.to_csv(REPORT_DIR / "roll_audit.csv", index=False)
    # full audit lives on E:; keep a trimmed copy in repo
    audit.to_csv(META_DIR / "roll_audit.csv", index=False)
    with (REPORT_DIR / "validation_summary.json").open("w") as fh:
        json.dump(summary, fh, indent=1)
    print("DONE")
    return 0


def load_eurusd_minutes() -> set[pd.Timestamp]:
    import numpy as np
    root = Path(r"E:\ResearchData\botTrading\ticks\parquet\EURUSD")
    minutes = set()
    for f in sorted(root.rglob("*.parquet")):
        ts = pd.read_parquet(f, columns=["timestamp_utc"])["timestamp_utc"]
        t = pd.to_datetime(ts, utc=True).values.astype("datetime64[m]")
        minutes.update(pd.to_datetime(np.unique(t), utc=True))
    return minutes


if __name__ == "__main__":
    sys.exit(main())
