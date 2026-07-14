#!/usr/bin/env bash
# run_batch.sh — Run N Gold questions starting from index M, in foreground.
# Usage: bash run_batch.sh <start_idx> <count>
# Each question runs in a fresh process. Progress saved to JSONL.

set -u
START_IDX="${1:-0}"
COUNT="${2:-5}"
DB_PATH="/tmp/gold_tc_batch.db"
JSONL_PATH="/home/z/my-project/download/gold_150_llm_active_results.jsonl"
SCRIPT="/home/z/my-project/scripts/ask_one.py"
REPO="/home/z/my-project/MaestroAgent/download/MaestroAgent/maestro-personal"

END_IDX=$((START_IDX + COUNT - 1))
echo "[batch] Running questions $((START_IDX+1))-$((END_IDX+1)) of 150"

for i in $(seq $START_IDX $END_IDX); do
  if [ $i -ge 150 ]; then
    echo "[batch] Reached 150, stopping"
    break
  fi
  T0=$(date +%s)
  cd "$REPO" && timeout 120 python3 -u "$SCRIPT" "$i" "$DB_PATH" "$JSONL_PATH" 2>&1 | tail -1
  RC=${PIPESTATUS[0]}
  T1=$(date +%s)
  ELAPSED=$((T1 - T0))
  if [ $RC -ne 0 ]; then
    echo "  [$((i+1))/150] FAILED rc=$RC (${ELAPSED}s)"
    echo "{\"idx\":$i,\"id\":\"q$i\",\"type\":\"unknown\",\"query\":\"\",\"score\":0.0,\"error\":\"rc=$RC\",\"llm_active\":false,\"elapsed\":$ELAPSED}" >> "$JSONL_PATH"
  fi
done

DONE=$(wc -l < "$JSONL_PATH" 2>/dev/null || echo 0)
echo "[batch] Done. Total completed: $DONE/150"
