"""NQ OPR MODERN M1 — gated year-by-year Databento acquisition (section 3/4/5).

HARD GATE: refuses to run unless research/nq_opr_modern_m1/DATA_PURCHASE_AUTHORIZED
exists (created ONLY by explicit user authorization of the ~$0.08 purchase).

Downloads GLBX.MDP3 / NQ.v.0 / ohlcv-1m per calendar year 2020..2025 into
E:\\ResearchData\\botTrading\\nq\\databento\\raw\\ (original dbn.zst preserved),
with per-year batch-job metadata + SHA256 under manifest\\.
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

    for year in YEARS:
        start = f"{year}-01-01T00:00:00"
        end = f"{year + 1}-01-01T00:00:00"
        assert end <= HARD_END, "2026 seal violated"
        out = RAW_DIR / f"glbx-mdp3-{year}.ohlcv-1m.dbn.zst"
        meta_out = META_DIR / f"batch_job_{year}.json"
        if out.exists() and meta_out.exists():
            print(f"{year}: already present, skip")
            continue
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
        est = job.get('cost_usd')
        est_s = f"${est:.4f}" if est is not None else "n/a"
        print(f"{year}: job {job_id} state={job['state']} est={est_s}")
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
        try:
            client.batch.download(
                job_id=job_id, output_dir=str(RAW_DIR),
                filename=out.name,
            )
        except TypeError:
            client.batch.download(job_id=job_id, output_dir=str(RAW_DIR))
            cand = list(RAW_DIR.glob(f"{job_id}*"))
            if cand:
                cand[0].rename(out)
        digest = sha256_file(out)
        meta_out.write_text(json.dumps({
            "year": year,
            "dataset": DATASET, "symbol": SYMBOL, "schema": SCHEMA,
            "start": start, "end_exclusive": end,
            "job_id": job_id, "state": job["state"],
            "cost_usd": job.get("cost_usd"),
            "record_count": job.get("record_count"),
            "file": str(out),
            "size_bytes": out.stat().st_size,
            "sha256": digest,
        }, indent=2, default=str))
        print(f"{year}: done  {out.stat().st_size} bytes  sha256={digest[:16]}...")

    print("ALL_YEARS_DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
