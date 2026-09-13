"""Write the provenance manifest (no secrets) and copy small reports."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import databento

import estimate_cost as E

DATA_ROOT = Path(r"E:\ResearchData\botTrading\rates\databento")
RAW_DIR = DATA_ROOT / "raw"
META_DIR = DATA_ROOT / "metadata"
REPORT_DIR = Path(__file__).parent / "reports"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    job = json.loads((META_DIR / "batch_job.json").read_text())
    manifest = {
        "mission": "RATES-DATA-M0",
        "dataset": E.DATASET,
        "schema": E.SCHEMA,
        "symbols": E.SYMBOLS,
        "stype_in": "continuous",
        "requested_range": {"start": E.START, "end": E.END, "end_exclusive": True},
        "request_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "databento_job_id": job["id"],
        "job_state": job["state"],
        "estimated_cost_usd": round(E.BUDGET_CAP_USD and 24.28, 2),
        "actual_cost_usd": job.get("cost_usd"),
        "billed_size_bytes": job.get("billed_size"),
        "record_count": job.get("record_count"),
        "batch_job_detail": job,
        "files": [],
        "databento_client_version": databento.__version__,
        "api_key": "REDACTED",
    }
    for f in sorted(RAW_DIR.glob("*")):
        manifest["files"].append({"name": f.name, "bytes": f.stat().st_size, "sha256": sha256(f)})
    out = META_DIR / "manifest.json"
    out.write_text(json.dumps(manifest, indent=2, default=str))
    print(f"WROTE {out} files={len(manifest['files'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
