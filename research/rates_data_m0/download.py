"""Poll the batch job, verify cost against the budget cap, then download once.

Data is stored OUTSIDE git under E:\\ResearchData\\botTrading\\rates\\databento.
Never prints the API key.
"""
import json
import sys
import time
from pathlib import Path

import databento

from estimate_cost import (BUDGET_CAP_USD, DATASET, END, SCHEMA, START, SYMBOLS,
                           load_key_from_config)

JOB_ID_FILE = Path(__file__).parent / "job_id.txt"
DATA_ROOT = Path(r"E:\ResearchData\botTrading\rates\databento")
RAW_DIR = DATA_ROOT / "raw"
META_DIR = DATA_ROOT / "metadata"
JOB_JSON = META_DIR / "batch_job.json"

POLL_SECONDS = 30
MAX_POLLS = 240  # ~2 hours


def get_job(client):
    jobs = client.batch.list_jobs()
    ours = [j for j in jobs if j["id"] == JOB_ID_FILE.read_text().strip()]
    if not ours:
        raise SystemExit(f"job {JOB_ID_FILE.read_text().strip()} not found")
    return ours[0]


def main() -> int:
    if not JOB_ID_FILE.exists():
        raise SystemExit("no job_id.txt; submit a job first")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    META_DIR.mkdir(parents=True, exist_ok=True)

    client = databento.Historical(key=load_key_from_config())
    job = get_job(client)

    for i in range(MAX_POLLS):
        print(f"poll {i}: state={job['state']} cost_usd={job['cost_usd']}")
        if job["state"] in ("done", "expired"):
            break
        time.sleep(POLL_SECONDS)
        job = get_job(client)

    JOB_JSON.write_text(json.dumps(job, indent=2))

    if job["state"] != "done":
        print(f"JOB_NOT_DONE state={job['state']}")
        return 3
    cost = job.get("cost_usd")
    if cost is not None and cost > BUDGET_CAP_USD:
        print(f"OVER_BUDGET cost_usd={cost:.2f} cap={BUDGET_CAP_USD:.2f} — NOT downloading")
        return 1
    print(f"ACTUAL_COST_USD={cost:.2f}" if cost is not None else "ACTUAL_COST_USD=UNEXPOSED")

    existing = sorted(RAW_DIR.glob("*.dbn.zst"))
    if existing:
        print(f"RAW_ALREADY_PRESENT n={len(existing)} — skipping download")
        return 0

    files = client.batch.list_files(job["id"])
    print(f"downloading {len(files)} files")
    for f in files:
        print("  ", f["filename"], (f.get("hashes") or {}).get("sha256", "")[:16])
        client.batch.download(job_id=job["id"], filename_to_download=f["filename"], output_dir=str(RAW_DIR))
    print(f"DOWNLOADED n={len(list(RAW_DIR.glob('*.dbn.zst')))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
