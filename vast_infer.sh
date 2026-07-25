#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# vast_infer.sh — Quick llama.cpp inference on vast.ai
#
# USAGE:
#   ./vast_infer.sh [--offer <ID>] [--destroy]
#
# What it does:
#   1. Rents an RTX 4090 instance
#   2. Installs llama.cpp (CUDA build)
#   3. Downloads base model GGUF (Q4_K_M, ~1GB)
#   4. Downloads LoRA adapter from HuggingFace
#   5. Merges adapter into base GGUF
#   6. Starts llama-server (OpenAI-compatible API)
#   7. Prints the API endpoint for testing
# =============================================================================

OFFER_ID=""
DESTROY_AFTER=false
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --offer) OFFER_ID="$2"; shift 2 ;;
        --destroy) DESTROY_AFTER=true; shift ;;
        --help|-h)
            echo "Usage: $0 [--offer <ID>] [--destroy]"
            echo "  --offer <ID>  Specific offer ID to rent"
            echo "  --destroy     Destroy instance after testing"
            exit 0
            ;;
        *) OFFER_ID="$1"; shift ;;
    esac
done

# Auto-find cheapest offer if not specified
if [[ -z "$OFFER_ID" ]]; then
    echo "[vast_infer] Finding cheapest RTX 4090 offer..."
    OFFER_ID=$(vastai search offers "num_gpus=1 gpu_name=RTX_4090" --order "dph-asc" 2>/dev/null \
        | sed 's/\x1b\[[0-9;]*m//g' \
        | grep "^ " | head -1 | awk '{print $2}')
    echo "[vast_infer] Using offer: $OFFER_ID"
fi

# Step 1: Rent instance
echo "[vast_infer] Renting instance $OFFER_ID..."
vastai create instance "$OFFER_ID" \
    --image "pytorch/pytorch:2.4.0-cuda12.1-cudnn9-devel" \
    --disk 20 --ssh

# Wait for running
echo "[vast_infer] Waiting for instance to be ready..."
for i in $(seq 1 30); do
    STATUS=$(vastai show instances 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' \
        | grep "^ " | head -1 | awk '{print $3}')
    if [[ "$STATUS" == "running" ]]; then
        echo "[vast_infer] Instance is running!"
        break
    fi
    sleep 10
done

# Get SSH details
INSTANCE_INFO=$(vastai show instances 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | grep "^  1")
INSTANCE_ID=$(echo "$INSTANCE_INFO" | awk '{print $2}')
SSH_HOST=$(echo "$INSTANCE_INFO" | awk '{print $10}')
SSH_PORT=$(echo "$INSTANCE_INFO" | awk '{print $11}')

echo "[vast_infer] Instance: $INSTANCE_ID"
echo "[vast_infer] SSH: root@$SSH_HOST -p $SSH_PORT"

# Cleanup handler
cleanup() {
    if [[ "$DESTROY_AFTER" == "true" ]]; then
        echo "[vast_infer] Destroying instance..."
        echo "y" | vastai destroy instance "$INSTANCE_ID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Step 2: Setup llama.cpp + download models
echo "[vast_infer] Setting up llama.cpp and downloading models..."
ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" root@"$SSH_HOST" '
set -e

# Install dependencies
apt-get update -qq && apt-get install -y -qq build-essential cmake git 2>/dev/null
pip install huggingface_hub gguf 2>/dev/null

# Clone and build llama.cpp
cd /tmp
git clone --depth 1 https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release -j$(nproc)

# Download base model GGUF (Q4_K_M, ~1GB)
echo "=== Downloading base model ==="
python3 -c "
from huggingface_hub import hf_hub_download
hf_hub_download(
    repo_id=\"Qwen/Qwen2.5-1.5B-Instruct-GGUF\",
    filename=\"qwen2.5-1.5b-instruct-q4_k_m.gguf\",
    local_dir=\"/tmp/models\"
)
print(\"Base model downloaded!\")
"

# Download LoRA adapter from HuggingFace
echo "=== Downloading LoRA adapter ==="
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id=\"usurachai/zendesk-support-qwen2.5-1.5b-lora\",
    local_dir=\"/tmp/adapter\"
)
print(\"Adapter downloaded!\")
"

# Step 3: Merge adapter into GGUF
echo "=== Merging adapter into GGUF ==="
python3 /tmp/llama.cpp/convert_lora_to_gguf \
    --base /tmp/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
    --lora /tmp/adapter \
    --outfile /tmp/models/zendesk-lora.gguf

echo "=== Merged GGUF created ==="
ls -lh /tmp/models/zendesk-lora.gguf

# Step 4: Start llama-server
echo "=== Starting llama-server ==="
nohup /tmp/llama.cpp/build/bin/llama-server \
    -m /tmp/models/zendesk-lora.gguf \
    --host 0.0.0.0 \
    --port 8080 \
    -ngl 99 \
    --chat-template chatml \
    > /tmp/llama-server.log 2>&1 &

sleep 3
echo "=== Server started ==="
cat /tmp/llama-server.log | tail -5

echo ""
echo "=== API ENDPOINT ==="
echo "http://localhost:8080"
echo ""
echo "Test with:"
echo "  curl http://localhost:8080/v1/chat/completions \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"model\":\"model\",\"messages\":[{\"role\":\"user\",\"content\":\"How to reset password?\"}]}'"
echo ""
echo "Or open in browser:"
echo "  http://$SSH_HOST:8080"
' 2>&1

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  llama-server is running!"
echo ""
echo "  SSH:   ssh -p $SSH_PORT root@$SSH_HOST"
echo "  API:   http://$SSH_HOST:8080"
echo "  Docs:  http://$SSH_HOST:8080/docs"
echo ""
echo "  Test from your MacBook:"
echo "    curl http://$SSH_HOST:8080/v1/chat/completions \\"
echo "      -H \"Content-Type: application/json\" \\"
echo "      -d '{\"model\":\"model\",\"messages\":[{\"role\":\"user\",\"content\":\"สวัสดี ต้องการความช่วยเหลือ\"}]}'"
echo ""
echo "  Instance: $INSTANCE_ID"
echo "  Cost:     ~\$0.36/hr (RTX 4090)"
echo "════════════════════════════════════════════════════════════════"

# Keep alive for user interaction
if [[ "$DESTROY_AFTER" == "false" ]]; then
    echo ""
    echo "Instance will stay alive. Destroy with:"
    echo "  vastai destroy instance $INSTANCE_ID"
    echo ""
    echo "Press Ctrl+C to destroy and exit."
    wait
fi
