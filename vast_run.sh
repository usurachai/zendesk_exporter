#!/usr/bin/env bash
# =============================================================================
# vast_run.sh — Local orchestration for vast.ai fine-tuning
#
# Automates the full lifecycle: rent → upload → train → download → cleanup.
# No manual intervention needed — run it and come back when it finishes.
#
# USAGE:
#   ./vast_run.sh <INSTANCE_ID>              # Run on an already-rented instance
#   ./vast_run.sh --rent <INSTANCE_ID>       # Rent + run + auto-destroy
#   ./vast_run.sh --rent <INSTANCE_ID> --disk 50  # Override disk size (default: 50)
#
# PREREQUISITES:
#   - vastai CLI installed and configured (API key with credits)
#   - Tarball at /tmp/zendesk_exporter.tar.gz (auto-created if missing)
#   - Dataset prepared: data/train.jsonl + data/valid.jsonl
#
# WHAT IT DOES:
#   1. Creates tarball if missing
#   2. (If --rent) Rents the instance with pytorch image + SSH
#   3. Waits for instance to be reachable
#   4. Uploads tarball to /workspace/
#   5. Runs vast_train.sh via vastai exec (blocks until training completes)
#   6. Downloads adapter weights to ./adapters/
#   7. (If --rent) Destroys the instance to stop billing
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
TARBALL="${TARBALL:-/tmp/zendesk_exporter.tar.gz}"
LOCAL_ADAPTER_DIR="$PROJECT_ROOT/adapters"
LOCAL_RECORDS_DIR="$PROJECT_ROOT/runs"
REMOTE_WORKSPACE="/workspace/zendesk_exporter"

# --- Config ---
RENT_MODE=false
INSTANCE_ID=""
DISK_GB=50
IMAGE="pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --rent) RENT_MODE=true; shift ;;
        --disk) DISK_GB="$2"; shift 2 ;;
        --help|-h)
            sed -n '/^# USAGE:/,/^$/p' "$0" | head -n -1
            exit 0
            ;;
        *)
            if [[ -z "$INSTANCE_ID" ]]; then
                INSTANCE_ID="$1"
            else
                echo "ERROR: Unexpected argument: $1"
                exit 1
            fi
            shift
            ;;
    esac
done

if [[ -z "$INSTANCE_ID" ]]; then
    echo "ERROR: Instance ID required."
    echo "Usage: $0 [--rent] [--disk N] <INSTANCE_ID>"
    exit 1
fi

# --- Step 0: Create tarball if missing ---
if [[ ! -f "$TARBALL" ]]; then
    echo "[vast_run] Creating tarball at $TARBALL..."
    cd "$PROJECT_ROOT"
    tar czf "$TARBALL" \
        --exclude=data/raw \
        --exclude=.git \
        --exclude=__pycache__ \
        --exclude='*.pyc' \
        --exclude=.venv \
        --exclude=.ruff_cache \
        --exclude=.pytest_cache \
        --exclude=.pi-subagents \
        .
    echo "[vast_run] Tarball created: $(du -h "$TARBALL" | cut -f1)"
else
    echo "[vast_run] Using existing tarball: $TARBALL ($(du -h "$TARBALL" | cut -f1))"
fi

# --- Step 1: (Optional) Rent instance ---
if $RENT_MODE; then
    echo "[vast_run] Renting instance $INSTANCE_ID (disk=${DISK_GB}GB, image=${IMAGE})..."
    vastai create instance "$INSTANCE_ID" \
        --image "$IMAGE" \
        --disk "$DISK_GB" \
        --ssh

    echo "[vast_run] Waiting for instance to be ready..."
    for i in $(seq 1 60); do
        STATUS=$(vastai show instances 2>/dev/null | grep "^$INSTANCE_ID" | awk '{print $3}' || true)
        if [[ "$STATUS" == "running" ]]; then
            echo "[vast_run] Instance $INSTANCE_ID is running."
            break
        fi
        if [[ "$STATUS" == "error" ]]; then
            echo "[vast_run] ERROR: Instance entered error state."
            exit 1
        fi
        sleep 15
    done

    # Final check
    STATUS=$(vastai show instances 2>/dev/null | grep "^$INSTANCE_ID" | awk '{print $3}' || true)
    if [[ "$STATUS" != "running" ]]; then
        echo "[vast_run] ERROR: Instance did not become running after 15 minutes."
        echo "[vast_run] You can check status with: vastai show instances"
        echo "[vast_run] Or manually continue once it's ready."
        exit 1
    fi

    # Wait for SSH to be ready
    echo "[vast_run] Waiting for SSH connectivity..."
    sleep 10
fi

# --- Cleanup handler ---
CLEANUP_DONE=false
cleanup() {
    if $CLEANUP_DONE; then return; fi
    CLEANUP_DONE=true
    echo ""
    echo "[vast_run] Signal received. Cleaning up..."

    # Try to download whatever was saved
    if vastai show instances 2>/dev/null | grep -q "^$INSTANCE_ID"; then
        echo "[vast_run] Attempting to download partial weights before cleanup..."
        mkdir -p "$LOCAL_ADAPTER_DIR"
        mkdir -p "$LOCAL_RECORDS_DIR"
        vastai copy C."$INSTANCE_ID":$REMOTE_WORKSPACE/adapters/ local:"$LOCAL_ADAPTER_DIR/" 2>/dev/null || true
        vastai copy C."$INSTANCE_ID":/workspace/run_record.tar.gz local:"$LOCAL_RECORDS_DIR/" 2>/dev/null || true
    fi

    if $RENT_MODE; then
        echo "[vast_run] Destroying instance $INSTANCE_ID..."
        vastai destroy instance "$INSTANCE_ID" 2>/dev/null || true
        echo "[vast_run] Instance destroyed. Billing stopped."
    fi
    exit 1
}
trap cleanup SIGINT SIGTERM

# --- Step 2: Upload tarball ---
echo "[vast_run] Uploading tarball to instance $INSTANCE_ID..."
vastai copy local:"$TARBALL" C."$INSTANCE_ID":/workspace/
echo "[vast_run] Upload complete."

# --- Step 3: Run training (blocks until done) ---
echo "[vast_run] Starting training on instance $INSTANCE_ID..."
echo "[vast_run] This will take ~30-45 minutes. Billing: ~\$0.13-0.19 for RTX 4090."
echo "[vast_run] Training log:"
echo "───────────────────────────────────────────────────────────────────────────────"
ssh -o ConnectTimeout=10 root@ssh9.vast.ai -p $(vastai show instances 2>/dev/null | grep "^$INSTANCE_ID" | awk '{print $5}' || echo 22) "bash $REMOTE_WORKSPACE/vast_train.sh" || TRAIN_EXIT=$?
echo "───────────────────────────────────────────────────────────────────────────────"

if [[ -n "${TRAIN_EXIT:-}" && $TRAIN_EXIT -ne 0 ]]; then
    echo "[vast_run] WARNING: Training exited with code $TRAIN_EXIT. Attempting to download partial weights..."
fi

# --- Step 4: Download adapter weights ---
echo "[vast_run] Downloading adapter weights..."
mkdir -p "$LOCAL_ADAPTER_DIR"

# Try the compressed tarball first (faster, single file)
TARBALL_DOWNLOADED=false
if vastai copy C."$INSTANCE_ID":/workspace/adapters.tar.gz local:"$LOCAL_ADAPTER_DIR/" 2>/dev/null; then
    echo "[vast_run] Adapter tarball downloaded."
    TARBALL_DOWNLOADED=true
    # Extract it
    cd "$PROJECT_ROOT"
    tar xzf "$LOCAL_ADAPTER_DIR/adapters.tar.gz" -C "$LOCAL_ADAPTER_DIR/" 2>/dev/null || true
    rm -f "$LOCAL_ADAPTER_DIR/adapters.tar.gz"
    cd "$PROJECT_ROOT"
fi

# Fallback: try directory copy
if ! $TARBALL_DOWNLOADED; then
    if vastai copy C."$INSTANCE_ID":$REMOTE_WORKSPACE/adapters/ local:"$LOCAL_ADAPTER_DIR/" 2>&1; then
        echo "[vast_run] Adapter weights downloaded to: $LOCAL_ADAPTER_DIR"
    else
        echo "[vast_run] WARNING: Failed to download adapter weights."
        echo "  The instance may still have the data. Try manually:"
        echo "    vastai copy C.$INSTANCE_ID:$REMOTE_WORKSPACE/adapters/ local:./adapters/"
    fi
fi

# Show result
if [[ -d "$LOCAL_ADAPTER_DIR/lora_adapter" ]]; then
    echo "[vast_run] Adapter saved to: $LOCAL_ADAPTER_DIR/lora_adapter/"
    ls -lh "$LOCAL_ADAPTER_DIR/lora_adapter/"
elif [[ -d "$LOCAL_ADAPTER_DIR" ]] && [[ -n "$(ls -A "$LOCAL_ADAPTER_DIR" 2>/dev/null)" ]]; then
    echo "[vast_run] Adapter files:"
    ls -lh "$LOCAL_ADAPTER_DIR/"
else
    echo "[vast_run] WARNING: No adapter files found in download."
fi

# --- Step 5: Download run record ---
RUN_TIMESTAMP=$(date -u +%Y-%m-%dT%H-%M-%SZ)
mkdir -p "$LOCAL_RECORDS_DIR"
RUN_DIR="$LOCAL_RECORDS_DIR/${RUN_TIMESTAMP}"
mkdir -p "$RUN_DIR"

echo "[vast_run] Downloading run record..."
if vastai copy C."$INSTANCE_ID":/workspace/run_record.tar.gz local:"$RUN_DIR/" 2>/dev/null; then
    echo "[vast_run] Run record tarball downloaded."
    cd "$PROJECT_ROOT"
    tar xzf "$RUN_DIR/run_record.tar.gz" -C "$RUN_DIR/" 2>/dev/null || true
    rm -f "$RUN_DIR/run_record.tar.gz"
    cd "$PROJECT_ROOT"
    echo "[vast_run] Run record saved to: $RUN_DIR"
    ls -lh "$RUN_DIR/"
else
    echo "[vast_run] WARNING: Failed to download run record. The remote instance may have stopped before saving it."
fi

# --- Step 6: (Optional) Destroy instance ---
if $RENT_MODE; then
    echo "[vast_run] Destroying instance $INSTANCE_ID (stopping billing)..."
    vastai destroy instance "$INSTANCE_ID"
    echo "[vast_run] Instance destroyed. Billing stopped."
fi

echo ""
echo "[vast_run] ==============================================="
echo "[vast_run]  ALL DONE"
echo "[vast_run] ==============================================="
echo "[vast_run]  Adapter: $LOCAL_ADAPTER_DIR/lora_adapter/"
if [[ -d "$LOCAL_ADAPTER_DIR/lora_adapter" ]]; then
    echo "[vast_run]  Size:    $(du -sh "$LOCAL_ADAPTER_DIR/lora_adapter" | cut -f1)"
fi
if [[ -f "$RUN_DIR/run_summary.json" ]]; then
    echo "[vast_run]  Run record: $RUN_DIR"
fi
echo "[vast_run] ==============================================="
