#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# vast_train.sh — Run Unsloth LoRA fine-tuning on a vast.ai instance
#
# USAGE:
#   This script runs on a vast.ai instance (uploaded via tarball, executed via
#   vastai exec). After training, it compresses the adapter weights so the
#   local vast_run.sh can download them efficiently.
#
#   For the fully automated workflow (upload → train → download → cleanup),
#   use vast_run.sh from your local machine instead.
# =============================================================================

echo "[vast_train] Starting setup..."

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

# Run training
echo "[vast_train] Starting training..."
uv run python run_train.py 2>&1

# Compress adapter weights for faster download
if [ -d "adapters" ] && [ "$(ls -A adapters/ 2>/dev/null)" ]; then
    echo "[vast_train] Compressing adapter weights..."
    tar czf /workspace/adapters.tar.gz -C /workspace/zendesk_exporter adapters/
    echo "[vast_train] Adapter tarball created: /workspace/adapters.tar.gz ($(du -h /workspace/adapters.tar.gz | cut -f1))"
else
    echo "[vast_train] WARNING: No adapter weights found at adapters/."
fi

echo "[vast_train] Training complete. Exiting — instance will stop."