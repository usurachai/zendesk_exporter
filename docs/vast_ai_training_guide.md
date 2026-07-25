# Remote Training on vast.ai — Lessons Learned

This document captures every issue we hit during remote training sessions and the exact fixes that worked. Read this BEFORE starting any vast.ai training run.

---

## Quick Start (What Actually Works)

```bash
# 1. Create tarball (exclude junk)
cd /home/surachai/dev/zendesk_exporter
tar czf /tmp/zendesk_exporter.tar.gz \
  --exclude='.git' --exclude='__pycache__' --exclude='.coverage' \
  --exclude='uv.lock' --exclude='node_modules' --exclude='.pi-subagents' \
  --exclude='adapters' --exclude='runs' --exclude='*.tar.gz' .

# 2. Find a GPU offer
vastai search offers "num_gpus=1 gpu_name=RTX_4090" --limit 10 --order "dph-asc"

# 3. Rent instance (MUST use -devel image)
vastai create instance <OFFER_ID> \
  --image "pytorch/pytorch:2.4.0-cuda12.1-cudnn9-devel" \
  --disk 20 --ssh

# 4. Wait for "running" status
vastai show instances

# 5. Upload via SSH pipe (NOT vastai copy to /workspace/)
cat /tmp/zendesk_exporter.tar.gz | \
  ssh -o StrictHostKeyChecking=no -p <SSH_PORT> root@ssh<vast.ai> \
  'cat > /tmp/zendesk_exporter.tar.gz'

# 6. Extract and install deps
ssh -p <SSH_PORT> root@ssh<vast.ai> '
  cd /tmp
  mkdir -p zendesk_exporter && cd zendesk_exporter
  tar xzf /tmp/zendesk_exporter.tar.gz
  rm -rf .venv .pytest_cache .ruff_cache logs
  pip install uv -q
  uv sync --extra train --no-dev
'

# 7. Run training
ssh -p <SSH_PORT> root@ssh<vast.ai> '
  cd /tmp/zendesk_exporter
  uv run python run_train.py
'

# 8. Download adapter
scp -P <SSH_PORT> -r root@ssh<vast.ai>:/tmp/zendesk_exporter/adapters/checkpoint-* \
  ./adapters/

# 9. Destroy instance
vastai destroy instance <INSTANCE_ID>
```

---

## Critical Issues & Fixes

### 1. Docker Image: MUST Use `-devel`

**Problem:** `pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime` lacks `gcc`/`g++`. Unsloth requires Triton compilation, which needs a C compiler.

**Error:**
```
error: Failed to install: torch-*.whl
Caused by: No space left on device (os error 28)
```
(Actually a Triton build failure, not disk space)

**Fix:** Always use the `-devel` image:
```bash
--image "pytorch/pytorch:2.4.0-cuda12.1-cudnn9-devel"
```

**Evidence:** PR #52 retrospective — first training run failed with `-runtime`, succeeded with `-devel`.

---

### 2. `/workspace/` Has Stale File Handles

**Problem:** The `/workspace/` directory on vast.ai instances uses an NFS-like mount that can develop stale file handles. Files written by `vastai copy` (rsync) appear as `??????????` in `ls -la` and are inaccessible by root SSH.

**Error:**
```
mv: cannot move '/root/zendesk_exporter.tar.gz' to '/workspace/zendesk_exporter.tar.gz': Stale file handle
scp: dest open "/workspace/zendesk_exporter.tar.gz": Failure
```

**Fix:** Write to `/tmp/` instead:
```bash
# Upload to /tmp/ (works reliably)
cat /tmp/zendesk_exporter.tar.gz | \
  ssh -p <PORT> root@ssh<vast.ai> 'cat > /tmp/zendesk_exporter.tar.gz'

# Extract to /tmp/ subdirectory
ssh -p <PORT> root@ssh<vast.ai> '
  mkdir -p /tmp/zendesk_exporter
  cd /tmp/zendesk_exporter
  tar xzf /tmp/zendesk_exporter.tar.gz
'
```

**Evidence:** Session 2026-07-25 — spent 20+ minutes fighting `/workspace/` stale handles before discovering `/tmp/` works.

---

### 3. `vastai copy` Uses Different User Than SSH

**Problem:** `vastai copy` uploads via rsync as `vastai_kaalia` user. Root SSH sees the file but can't read/write it (different UID permissions).

**Error:**
```
$ ls -la /workspace/zendesk_exporter.tar.gz
-????????? ? ?    ?      ?            ? zendesk_exporter.tar.gz
```

**Fix:** Use SSH pipe instead of `vastai copy`:
```bash
# This works (writes as root)
cat /tmp/zendesk_exporter.tar.gz | \
  ssh -p <PORT> root@ssh<vast.ai> 'cat > /tmp/zendesk_exporter.tar.gz'

# This fails (writes as vastai_kaalia, root can't access)
vastai copy local:/tmp/zendesk_exporter.tar.gz C.<ID>:/workspace/
```

**Alternative:** If you must use `vastai copy`, upload to `/root/` not `/workspace/`:
```bash
vastai copy local:/tmp/zendesk_exporter.tar.gz C.<ID>:/root/
```

---

### 4. Disk Space: 20GB Is Tight

**Problem:** The `-devel` image + PyTorch + CUDA packages consume ~12GB. With stale files from failed attempts, disk fills up.

**Error:**
```
error: Failed to install: torch-*.whl
Caused by: No space left on device (os error 28)
```

**Fix:** Clean up before installing:
```bash
ssh -p <PORT> root@ssh<vast.ai> '
  rm -rf /workspace/* 2>/dev/null
  rm -rf /tmp/zendesk_exporter/.venv 2>/dev/null
  df -h /  # Should show 15GB+ free
'
```

**Rule of thumb:** After cleanup, you need ~8GB free for the venv installation.

---

### 5. `vast_train.sh` Hardcodes `/workspace/`

**Problem:** The `vast_train.sh` script does `cd /workspace` and expects the repo at `/workspace/zendesk_exporter/`. If files are in `/tmp/`, the script fails.

**Error:**
```
[vast_train] No tarball found — expecting repo to be pre-extracted.
error: No `pyproject.toml` found in current directory
```

**Fix:** Run training commands directly instead of using `vast_train.sh`:
```bash
ssh -p <PORT> root@ssh<vast.ai> '
  cd /tmp/zendesk_exporter
  mkdir -p run_record
  uv run python run_score.py 2>&1 | tee run_record/score_report.txt
  uv run python run_train.py 2>&1 | tee run_record/training_output.log
'
```

**Alternative:** Update `vast_train.sh` to use `REMOTE_WORKSPACE` variable instead of hardcoded `/workspace`.

---

### 6. Unsloth Pickle Error (SFTConfig)

**Problem:** Unsloth's compiled cache overrides `trl.trainer.sft_config.SFTConfig`, causing `torch.save` to fail with a pickle error.

**Error:**
```
_pickle.PicklingError: Can't pickle <class 'trl.trainer.sft_config.SFTConfig'>:
it's not the same object as trl.trainer.sft_config.SFTConfig
```

**When it happens:** At checkpoint save time (when `save_steps` triggers).

**Fix:** Set `save_steps` > total training steps to skip intermediate checkpointing:
```yaml
# config/config.yaml
training:
  save_steps: 999  # Set higher than total steps
  eval_steps: 50   # Keep eval for monitoring
```

**Note:** The adapter weights (`adapter_model.safetensors`) save fine — only `training_args.bin` fails. The final checkpoint is still usable.

**Evidence:** Session 2026-07-25 — training completed 226/226 steps, eval_loss=1.034, but final checkpoint save failed with pickle error. Adapter weights were saved successfully.

---

### 7. `save_steps` Must Be Multiple of `eval_steps`

**Problem:** HuggingFace Trainer requires `save_steps` to be a round multiple of `eval_steps` when `load_best_model_at_end=True`.

**Error:**
```
ValueError: --load_best_model_at_end requires the saving steps to be a round
multiple of the evaluation steps, but found 999, which is not a round multiple of 50.
```

**Fix:** Either:
1. Set `save_steps` to a multiple of `eval_steps` (e.g., `save_steps: 500` with `eval_steps: 50`)
2. Or disable `load_best_model_at_end` in the config

---

### 8. `uv sync --no-cache` Takes 5+ Minutes

**Problem:** First-time installation downloads ~4GB of CUDA packages (torch, nccl, cudnn). No cache on fresh instances.

**Impact:** Adds 5-6 minutes to every training run.

**Mitigation:** Use `uv sync --extra train --no-dev` (without `--no-cache`) to allow caching if available:
```bash
uv sync --extra train --no-dev  # Faster if cache exists
```

**Alternative:** Pre-build a Docker image with deps installed (advanced).

---

### 9. `vastai execute` Only Works on Stopped Instances

**Problem:** `vastai execute` is for stopped instances only. For running instances, use SSH directly.

**Error:**
```
Failed with error 400: Execute command only avail on stopped instances.
```

**Fix:** Use SSH for all commands on running instances:
```bash
ssh -o StrictHostKeyChecking=no -p <PORT> root@ssh<vast.ai> '<command>'
```

---

## Instance Boot Sequence

1. **`vastai create instance`** → Returns instance ID
2. **Status: `loading`** → Docker image being pulled (5-10 min for `-devel`)
3. **Status: `running`** → Instance ready, SSH available
4. **SSH port open** → Verify with `nc -zv ssh<vast.ai> <PORT>`

**Monitoring:**
```bash
# Check status
vastai show instances 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g'

# Check SSH
nc -zv ssh<vast.ai> <PORT>

# Check GPU
ssh -p <PORT> root@ssh<vast.ai> 'nvidia-smi'
```

---

## Complete Workflow Example

```bash
#!/bin/bash
# Example: Full training run on vast.ai

set -e

# === CONFIG ===
PROJECT_DIR="/home/surachai/dev/zendesk_exporter"
TARBALL="/tmp/zendesk_exporter.tar.gz"
OFFER_ID="44386446"  # RTX 4090, $0.30/hr
IMAGE="pytorch/pytorch:2.4.0-cuda12.1-cudnn9-devel"

cd "$PROJECT_DIR"

# === STEP 1: Create tarball ===
echo "Creating tarball..."
tar czf "$TARBALL" \
  --exclude='.git' --exclude='__pycache__' --exclude='.coverage' \
  --exclude='uv.lock' --exclude='node_modules' --exclude='.pi-subagents' \
  --exclude='adapters' --exclude='runs' --exclude='*.tar.gz' .

# === STEP 2: Rent instance ===
echo "Renting instance $OFFER_ID..."
vastai create instance "$OFFER_ID" \
  --image "$IMAGE" \
  --disk 20 --ssh

# === STEP 3: Wait for running ===
echo "Waiting for instance to be ready..."
for i in $(seq 1 30); do
  STATUS=$(vastai show instances 2>/dev/null | grep "^[0-9]" | awk '{print $3}' | tr -d '[:space:]')
  if [[ "$STATUS" == "running" ]]; then
    echo "Instance is running!"
    break
  fi
  sleep 10
done

# === STEP 4: Get SSH details ===
INSTANCE_INFO=$(vastai show instances 2>/dev/null | sed 's/\x1b\[[0-9;]*m//g' | grep "^  1")
SSH_PORT=$(echo "$INSTANCE_INFO" | awk '{print $11}')
SSH_HOST=$(echo "$INSTANCE_INFO" | awk '{print $10}')
INSTANCE_ID=$(echo "$INSTANCE_INFO" | awk '{print $2}')

echo "SSH: root@$SSH_HOST -p $SSH_PORT"
echo "Instance: $INSTANCE_ID"

# === STEP 5: Upload via SSH pipe ===
echo "Uploading tarball..."
cat "$TARBALL" | \
  ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" root@"$SSH_HOST" \
  'cat > /tmp/zendesk_exporter.tar.gz'

# === STEP 6: Extract and install ===
echo "Setting up environment..."
ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" root@"$SSH_HOST" '
  set -e
  cd /tmp
  rm -rf zendesk_exporter
  mkdir -p zendesk_exporter
  cd zendesk_exporter
  tar xzf /tmp/zendesk_exporter.tar.gz
  rm -rf .venv .pytest_cache .ruff_cache logs
  pip install uv -q 2>/dev/null
  uv sync --extra train --no-dev
'

# === STEP 7: Run training ===
echo "Starting training..."
ssh -o StrictHostKeyChecking=no -p "$SSH_PORT" root@"$SSH_HOST" '
  set -e
  cd /tmp/zendesk_exporter
  mkdir -p run_record
  uv run python run_score.py 2>&1 | tee run_record/score_report.txt
  uv run python run_train.py 2>&1 | tee run_record/training_output.log
'

# === STEP 8: Download artifacts ===
echo "Downloading adapter..."
mkdir -p adapters/checkpoint-final
scp -o StrictHostKeyChecking=no -r -p "$SSH_PORT" \
  root@"$SSH_HOST":/tmp/zendesk_exporter/adapters/checkpoint-* \
  adapters/

echo "Downloading run record..."
mkdir -p "runs/$(date -u +%Y-%m-%dT%H-%M-%SZ)"
scp -o StrictHostKeyChecking=no -r -p "$SSH_PORT" \
  root@"$SSH_HOST":/tmp/zendesk_exporter/run_record/* \
  "runs/$(date -u +%Y-%m-%dT%H-%M-%SZ)/"

# === STEP 9: Upload to HuggingFace ===
echo "Uploading to HuggingFace..."
source .env
python3 -c "
from huggingface_hub import upload_folder
upload_folder(
    folder_path='adapters/checkpoint-final',
    repo_id='usurachai/zendesk-support-qwen2.5-1.5b-lora',
    repo_type='model',
    token='$HF_TOKEN',
    commit_message='update: retrained with $(wc -l < data/train.jsonl) examples'
)
"

# === STEP 10: Destroy instance ===
echo "Destroying instance..."
echo "y" | vastai destroy instance "$INSTANCE_ID"

echo "Done!"
```

---

## Troubleshooting Quick Reference

| Symptom | Cause | Fix |
|---------|-------|-----|
| `No module named unsloth` | Wrong image | Use `-devel` not `-runtime` |
| `Stale file handle` | `/workspace/` NFS issue | Write to `/tmp/` instead |
| `??????????` permissions | `vastai copy` user mismatch | Use SSH pipe, not `vastai copy` |
| `No space left on device` | Stale files consuming disk | `rm -rf /workspace/* /tmp/zendesk_exporter/.venv` |
| `No pyproject.toml found` | Wrong working directory | `cd /tmp/zendesk_exporter` not `/workspace/` |
| `PicklingError: SFTConfig` | Unsloth/TRL conflict | Set `save_steps` > total steps |
| `save_steps not multiple of eval_steps` | HF Trainer validation | Set `save_steps: 500` with `eval_steps: 50` |
| `uv sync` takes 5+ min | First-time CUDA download | Normal; use `--no-cache` only when needed |
| `Execute command only avail on stopped instances` | Wrong command | Use SSH, not `vastai execute` |

---

## Cost Estimation

| Component | Cost |
|-----------|------|
| RTX 4090 ($0.30/hr) | ~$0.05 for 10 min training |
| Instance boot (5-10 min) | ~$0.03-0.05 |
| Total per run | **~$0.10** |

---

## Last Updated

2026-07-25 — Based on training runs with 122 and 1808 examples.
