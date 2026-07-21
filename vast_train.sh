#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# vast_train.sh — Run Unsloth LoRA fine-tuning on a vast.ai instance
#
# USAGE:
#   This script is uploaded to a vast.ai instance and executed as the docker
#   command. When training finishes, the process exits → instance stops →
#   billing stops.
#
# SETUP (run once from your local machine):
#   1. tar czf zendesk_exporter.tar.gz --exclude=data/raw --exclude=.git \
#        --exclude=__pycache__ --exclude='*.pyc' -C /path/to/zendesk_exporter .
#   2. vastai copy <instance_id> ./zendesk_exporter.tar.gz /workspace/
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

echo "[vast_train] Training complete. Exiting — instance will stop."