# Training — Remote Execution on vast.ai

Fine-tune Qwen2.5-1.5B-Instruct on the prepared dataset (`data/train.jsonl` + `data/valid.jsonl`) using Unsloth LoRA.

## Prerequisites

- [vast.ai](https://vast.ai) account with credits
- [vast CLI](https://vast.ai/docs/cli) installed locally:
  ```bash
  pip install vastai
  ```
- This repo cloned and pushed to GitHub (or local tarball ready)

---

## Quick Start (one-shot)

### 1. Pick a GPU

Search for a cost-effective GPU with enough VRAM:

```bash
vastai search offers 'cuda_arch >= 89 gpu_ram >= 16 num_gpus=1 reliability >= 0.95'
```

- **Recommended:** RTX 4090 (24 GB) or RTX 3090 — ~$0.30/hr
- Qwen2.5-1.5B uses ~6-8 GB VRAM with 4-bit LoRA
- Note the **instance ID** of your chosen offer

### 2. Create the tarball (on your machine)

Bundle the repo **without** raw data or git history:

```bash
cd /path/to/zendesk_exporter
tar czf /tmp/zendesk_exporter.tar.gz \
  --exclude=data/raw \
  --exclude=.git \
  --exclude=__pycache__ \
  --exclude='*.pyc' \
  .
```

### 3. Rent the instance

```bash
vastai create instance <INSTANCE_ID> \
  --image pytorch/pytorch:2.4.0-cuda12.1-cudnn8-devel \
  --disk 20 \
  --ssh
```

Wait for status to show `running`:

```bash
vastai show instances
```

### 4. Upload the tarball

```bash
vastai copy <INSTANCE_ID> /tmp/zendesk_exporter.tar.gz /workspace/
```

### 5. Run training (auto-stops when done)

```bash
vastai exec <INSTANCE_ID> "
  cd /workspace &&
  mkdir -p zendesk_exporter &&
  tar xzf zendesk_exporter.tar.gz -C zendesk_exporter/ &&
  cd zendesk_exporter &&
  pip install uv -q &&
  uv sync &&
  uv pip install -r requirements-train.txt -q &&
  uv run python run_train.py
"
```

**The instance stops automatically when the command exits** → no over-billing.

Estimated runtime: ~30-45 minutes for 3 epochs on RTX 4090 (~$0.15-0.30 total).

### 6. (Optional) Download the adapter before stopping

If you want the adapter weights, **run this in a separate terminal** during training, or modify the script to upload to a cloud bucket:

```bash
vastai copy <INSTANCE_ID> /workspace/zendesk_exporter/adapters/ ./adapters/
vastai destroy instance <INSTANCE_ID>
```

---

## Alternative: Using `vast_train.sh`

The repo includes [`vast_train.sh`](vast_train.sh) — a self-contained script that does steps 4-5:

```bash
# After renting the instance and uploading the tarball:
vastai exec <INSTANCE_ID> "bash /workspace/zendesk_exporter/vast_train.sh"
```

---

## Configuration

Edit [`config/config.yaml`](config/config.yaml) before training to adjust:

| Key | Default | Notes |
|-----|---------|-------|
| `base_model` | `unsloth/Qwen2.5-1.5B-Instruct` | Model to fine-tune |
| `max_seq_length` | `2048` | Max token length per example |
| `load_in_4bit` | `true` | 4-bit quantization (saves VRAM) |
| `bf16` | `true` | Use bf16 precision (more stable than fp16 on Ampere+ GPUs) |
| `lora_r` | `16` | LoRA rank |
| `learning_rate` | `2.0e-4` | Learning rate |
| `num_epochs` | `3` | Training epochs |
| `per_device_train_batch_size` | `4` | Batch size per GPU (reduce to 2 or 1 if OOM) |
| `gradient_accumulation_steps` | `4` | Gradient accumulation steps |
| `output_dir` | `adapters` | Where to save the LoRA adapter |

### CLI overrides

```bash
uv run python run_train.py --config /path/to/config.yaml --train /path/to/train.jsonl --valid /path/to/valid.jsonl
```

---

## Cost Optimization

| Action | Effect |
|--------|--------|
| RTX 4090 (~$0.30/hr) | ~$0.15-0.30 per run |
| Use `--disk 10` instead of 20 | Saves ~$0.001/hr |
| Pre-upload tarball before renting | Saves ~30s of billing |
| Instance auto-stops when script exits | No over-billing |
| Reduce `per_device_train_batch_size` | Lower VRAM = cheaper GPU tier |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `CUDA out of memory` | Reduce `per_device_train_batch_size` in config.yaml (4→2 or 1) |
| `No module named unsloth` | Ensure `uv pip install -r requirements-train.txt` ran successfully |
| Instance doesn't stop | Instance is in "continuous" mode → `vastai destroy instance <ID>` manually |
| `Connection refused` | Wait 30-60s for the instance to boot before `vastai exec` |
| `uv: command not found` | Run `pip install uv` first (already in the script) |
| Training is slow | Check GPU utilization: `vastai exec <ID> "nvidia-smi"` |