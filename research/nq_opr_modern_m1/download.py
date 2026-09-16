"""NQ OPR MODERN M1 — gated year-by-year Databento acquisition (sections 3/4/5).

HARD GATE: refuses to run unless research/nq_opr_modern_m1/DATA_PURCHASE_AUTHORIZED
exists (created by explicit user authorization, 2026-09-16).

SPEND CAP: total campaign spend on batch jobs must stay under SPEND_CAP_USD=12.00
(self-imposed after the corrected estimate of 7.73 USD total; the user authorized
the exact dataset/range by name — the initially quoted 0.08 USD was a unit bug in
our own estimate script, documented in COST_GUARD_REPORT.md).

Layout: batch jobs return daily-split DBN files; each year lands in
E:\\ResearchData\\botTrading\\nq\\databento\\raw\\<year>\\*.dbn.zst (+condition.json).
Per-year metadata + per-file SHA256 go to manifest\\batch_job_<year>.json.
2026 is never requested; a defensive end-date guard is built in.
Never prints or exposes the API key.
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import databento

HERE = Path(__file__).parent
GATE = HERE / "DATA_PURCHASE_AUTHORIZED"
DATA_ROOT = Path(r"E:\ResearchData\botTrading\nq\databento")
RAW_DIR = DATA_ROOT / "raw"
META_DIR = DATA_ROOT / "manifest"

DATASET = "GLBX.MDP3"
SYMBOL = "NQ.v.0"
SCHEMA = "ohlcv-1m"
YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
HARD_END = "2026-01-01T00:00:00"  # exclusive, absolute — 2026 SEALED
SPEND_CAP_USD = 12.00
POLL_SECONDS = 20
MAX_POLLS = 120


def load_key_from_config() -> str | None:
    cfg = Path.home() / ".databento" / "config"
    if not cfg.exists():
        return os.environ.get("DATABENTO_API_KEY")
    for line in cfg.read_text().splitlines():
        line = line.strip()
        if line.startswith("key"):
            return line.split("=", 1)[1].strip().strip('"')
    return os.environ.get("DATABENTO_API_KEY")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(year, ydir: Path, job, meta_out: Path):
    files = sorted(ydir.glob("*.dbn.zst"))
    meta_out.write_text(json.dumps({
        "year": year,
        "dataset": DATASET, "symbol": SYMBOL, "schema": SCHEMA,
        "start": f"{year}-01-01T00:00:00",
        "end_exclusive": f"{year + 1}-01-01T00:00:00",
        "job_id": job.get("id"), "state": job.get("state"),
        "cost_usd": job.get("cost_usd"),
        "record_count": job.get("record_count"),
        "billed_size": job.get("billed_size"),
        "n_dbn_files": len(files),
        "total_bytes": sum(f.stat().st_size for f in files),
        "sha256_by_file": {f.name: sha256_file(f) for f in files},
    }, indent=2, default=str))


def main() -> int:
    if not GATE.exists():
        print("DATA_PURCHASE_AUTH_REQUIRED — gate file absent, refusing")
        return 1
    key = load_key_from_config()
    if not key:
        print("NO_API_KEY")
        return 2
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)
    client = databento.Historical(key=key)
    spent = 0.0

    for year in YEARS:
        start = f"{year}-01-01T00:00:00"
        end = f"{year + 1}-01-01T00:00:00"
        assert end <= HARD_END, "2026 seal violated"
        ydir = RAW_DIR / str(year)
        meta_out = META_DIR / f"batch_job_{year}.json"
        have_files = ydir.exists() and len(list(ydir.glob("*.dbn.zst"))) > 0
        if have_files and meta_out.exists():
            print(f"{year}: already present, skip")
            spent += json.loads(meta_out.read_text()).get("cost_usd") or 0.0
            continue

        # adopt an already-downloaded year whose manifest was lost (2020 case)
        if have_files and not meta_out.exists():
            prior = META_DIR / f"batch_job_{year}.raw.json"
            if prior.exists():
                job = json.loads(prior.read_text())
                write_manifest(year, ydir, job, meta_out)
                print(f"{year}: adopted existing files, cost=${job.get('cost_usd'):.4f}")
                spent += job.get("cost_usd") or 0.0
                continue

        if spent >= SPEND_CAP_USD:
            print(f"SPEND_CAP_REACHED spent=${spent:.2f} cap={SPEND_CAP_USD:.2f}")
            return 4
        print(f"{year}: submitting batch job...")
        job = client.batch.submit_job(
            dataset=DATASET,
            symbols=[SYMBOL],
            schema=SCHEMA,
            start=start,
            end=end,
            stype_in="continuous",
            encoding="dbn",
            compression="zstd",
        )
        job_id = job["id"]
        est = job.get("cost_usd")
        print(f"{year}: job {job_id} state={job['state']}"
              f" est={'$%.4f' % est if est is not None else 'n/a'}")
        for i in range(MAX_POLLS):
            if job["state"] in ("done", "expired"):
                break
            time.sleep(POLL_SECONDS)
            jobs = client.batch.list_jobs()
            job = [j for j in jobs if j["id"] == job_id][0]
            print(f"{year}: poll {i} state={job['state']}")
        if job["state"] != "done":
            print(f"{year}: JOB_NOT_DONE state={job['state']}")
            return 3
        (META_DIR / f"batch_job_{year}.raw.json").write_text(
            json.dumps(job, indent=2, default=str))
        ydir.mkdir(parents=True, exist_ok=True)
        client.batch.download(job_id=job_id, output_dir=str(ydir))
        cost = job.get("cost_usd") or 0.0
        spent += cost
        write_manifest(year, ydir, job, meta_out)
        print(f"{year}: done cost=${cost:.4f} cumulative=${spent:.2f}")

    print(f"ALL_YEARS_DONE total_spent=${spent:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
