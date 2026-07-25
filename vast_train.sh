#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# vast_train.sh — Run Unsloth LoRA fine-tuning on a vast.ai instance
#
# USAGE:
#   This script runs on a vast.ai instance (uploaded via tarball, executed via
#   vastai exec). After training, it saves:
#     - Adapter weights to /workspace/adapters.tar.gz
#     - Run record (config, score, logs, state) to /workspace/run_record.tar.gz
#
#   For the fully automated workflow (upload → train → download → cleanup),
#   use vast_run.sh from your local machine instead.
# =============================================================================

echo "[vast_train] Starting setup..."
RUN_START=$(date +%s)

cd /workspace
mkdir -p zendesk_exporter
cd zendesk_exporter

# Extract the uploaded tarball
if [ -f /workspace/zendesk_exporter.tar.gz ]; then
    echo "[vast_train] Extracting zendesk_exporter.tar.gz..."
    tar xzf /workspace/zendesk_exporter.tar.gz -C /workspace/zendesk_exporter
    rm /workspace/zendesk_exporter.tar.gz
else
    echo "[vast_train] No tarball found — expecting repo to be pre-extracted."
fi

# Install uv if not present
if ! command -v uv &>/dev/null; then
    echo "[vast_train] Installing uv..."
    pip install uv -q
fi

# Sync dependencies
echo "[vast_train] Installing dependencies..."
uv sync --extra train

# Run training — capture stdout to a log file too
echo "[vast_train] Starting training..."
uv run python run_train.py 2>&1 | tee /workspace/training_output.log
TRAIN_EXIT=${PIPESTATUS[0]}

RUN_END=$(date +%s)
RUN_DURATION=$((RUN_END - RUN_START))

echo "[vast_train] Training exit code: $TRAIN_EXIT (duration: ${RUN_DURATION}s)"

# --- Create run record ---
echo "[vast_train] Creating run record..."
RUN_RECORD_DIR="/workspace/run_record"
mkdir -p "$RUN_RECORD_DIR"

# 1. Snapshot config
cp config/config.yaml "$RUN_RECORD_DIR/config.yaml" 2>/dev/null || echo "WARNING: config.yaml not found"

# 2. Snapshot data stats / score report
if command -v uv &>/dev/null && [ -f "run_score.py" ]; then
    uv run python run_score.py > "$RUN_RECORD_DIR/score_report.txt" 2>&1 || true
fi

# 3. Copy trainer_state.json from the latest checkpoint (if available)
# Checkpoint naming: checkpoint-N where N increases by save_steps
LATEST_CHECKPOINT=$(ls -d adapters/checkpoint-* 2>/dev/null | sort -t- -k2 -n | tail -1)
if [ -n "$LATEST_CHECKPOINT" ] && [ -f "$LATEST_CHECKPOINT/trainer_state.json" ]; then
    cp "$LATEST_CHECKPOINT/trainer_state.json" "$RUN_RECORD_DIR/trainer_state.json"
    echo "[vast_train] Copied trainer_state.json from $LATEST_CHECKPOINT"
fi

# 4. Copy training output log
if [ -f /workspace/training_output.log ]; then
    cp /workspace/training_output.log "$RUN_RECORD_DIR/training_output.log"
fi

# 5. Write run summary
cat > "$RUN_RECORD_DIR/run_summary.json" <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "duration_seconds": $RUN_DURATION,
  "exit_code": $TRAIN_EXIT,
  "python_version": "$(python3 --version 2>/dev/null || echo 'unknown')",
  "unsloth_version": "$(pip show unsloth 2>/dev/null | grep Version | awk '{print $2}' || echo 'unknown')",
  "train_examples": $(python3 -c "import json; lines=open('data/train.jsonl').readlines(); print(len(lines))" 2>/dev/null || echo 0),
  "valid_examples": $(python3 -c "import json; lines=open('data/valid.jsonl').readlines(); print(len(lines))" 2>/dev/null || echo 0)
}
EOF

echo "[vast_train] Run record created at $RUN_RECORD_DIR:"
ls -la "$RUN_RECORD_DIR/"

# --- Compress adapter weights ---
if [ -d "adapters" ] && [ "$(ls -A adapters/ 2>/dev/null)" ]; then
    echo "[vast_train] Compressing adapter weights..."
    tar czf /workspace/adapters.tar.gz -C /workspace/zendesk_exporter adapters/
    echo "[vast_train] Adapter tarball created: /workspace/adapters.tar.gz ($(du -h /workspace/adapters.tar.gz | cut -f1))"
else
    echo "[vast_train] WARNING: No adapter weights found at adapters/."
fi

# --- Compress run record ---
echo "[vast_train] Compressing run record..."
tar czf /workspace/run_record.tar.gz -C /workspace/run_record .
echo "[vast_train] Run record tarball created: /workspace/run_record.tar.gz ($(du -h /workspace/run_record.tar.gz | cut -f1))"

echo "[vast_train] Training complete. Exiting — instance will stop."