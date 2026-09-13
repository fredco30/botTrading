#!/bin/bash
# TICK-M1 finalizer: run AFTER the first full download pass completes.
# 1. Re-run the downloader until convergence (each pass is resumable and only
#    fetches files that are absent/f failed in previous passes).
# 2. Verify .missing markers once (repairs false 404 markers).
# 3. Build all month partitions 2010-01 .. 2018-12.
# 4. Run the full frozen Discovery screen.
set -u
cd "$(dirname "$0")"
ROOT="E:\\ResearchData\\botTrading\\ticks"

echo "=== finalize: repair passes ==="
prev_new=1
for attempt in 1 2 3 4 5 6; do
  log=$(python download_ticks.py --symbol EURUSD --start 2010-01-01 --end 2019-01-01 \
        --data-root "$ROOT" --workers 12 --pace 0.20 --retries 6 --progress-every 5000 2>&1 | tail -1)
  echo "pass $attempt: $log"
  # count actually-fetched files (ok+empty+missing) in the last pass summary
  new=$(echo "$log" | grep -o "'ok': [0-9]*" | grep -o "[0-9]*" | paste -sd+ | bc 2>/dev/null || echo 0)
  fail=$(echo "$log" | grep -o '"hard_fail": [0-9]*' | grep -o "[0-9]*$")
  if [ "${fail:-1}" = "0" ]; then
    echo "converged (hard_fail=0) after pass $attempt"
    break
  fi
  if [ "$new" = "0" ] && [ "$attempt" -ge 2 ]; then
    echo "no progress and hard_fail=$fail remains; stopping repair loop"
    break
  fi
done

echo "=== finalize: verify missing markers ==="
python download_ticks.py --symbol EURUSD --start 2010-01-01 --end 2019-01-01 \
  --data-root "$ROOT" --verify-missing

echo "=== finalize: build parquet ==="
python build_parquet.py --symbol EURUSD --start 2010-01 --end 2019-01 --data-root "$ROOT"

echo "=== finalize: full discovery run ==="
python run_discovery.py --start 2010-01 --end 2019-01 --data-root "$ROOT" \
  --out tick_m1_results.json

echo "=== finalize: DONE ==="
