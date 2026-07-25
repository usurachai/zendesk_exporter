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

## 🚀 Quick Start (one-shot, fully automated)

Use `vast_run.sh` — a local orchestration script that handles the full lifecycle:
**rent → upload → train → download weights → destroy instance**.

No manual intervention needed. Run it and come back when it finishes.

### 1. Pick a GPU

Search for a cost-effective GPU with enough VRAM:

```bash
vastai search offers 'compute_cap >= 890 gpu_ram >= 16 num_gpus=1 reliability >= 0.95'
```

- **Recommended:** RTX 4090 (24 GB) or RTX 3090 — ~$0.30/hr
- Qwen2.5-1.5B uses ~6-8 GB VRAM with 4-bit LoRA
- Note the **instance ID** of your chosen offer

### 2. Run (rent + train + download + destroy)

```bash
./vast_run.sh --rent <INSTANCE_ID>
```

This single command:
1. Creates the tarball automatically (if not already at `/tmp/zendesk_exporter.tar.gz`)
2. Rents the instance with the pytorch image
3. Waits for it to be ready
4. Uploads the repo
5. Runs training (~30-45 min on RTX 4090)
6. Downloads the adapter weights to `./adapters/`
7. Destroys the instance to stop billing

**Cost:** ~$0.13-0.19 total for a 30-45 min run on RTX 4090.

### 3. (Optional) Use the adapter

The trained LoRA adapter is saved locally at:

```
adapters/lora_adapter/
```

You can load it for inference with:

```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/Qwen2.5-1.5B-Instruct",
    load_in_4bit=True,
)
model = FastLanguageModel.get_peft_model(model, ...)
# or use PeftModel.from_pretrained(model, "./adapters/lora_adapter")
```

---

## 🔧 Manual Workflow (step-by-step)

If you prefer to run each step manually:

### 1. Pick a GPU

```bash
vastai search offers 'compute_cap >= 890 gpu_ram >= 16 num_gpus=1 reliability >= 0.95'
```

### 2. Create the tarball (on your machine)

```bash
cd /path/to/zendesk_exporter
tar czf /tmp/zendesk_exporter.tar.gz \
  --exclude=data/raw \
  --exclude=.git \
  --exclude=__pycache__ \
  --exclude='*.pyc' \
  --exclude=.venv \
  .
```

### 3. Rent the instance

```bash
vastai create instance <INSTANCE_ID> \
  --image pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime \
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

### 5. Run training

```bash
./vast_run.sh <INSTANCE_ID>
```

This runs `vast_train.sh` on the instance, waits for completion, then downloads the adapter weights.

### 6. Destroy the instance

```bash
vastai destroy instance <INSTANCE_ID>
```

---

## 📦 Using `vast_train.sh` (on-instance script only)

If you already have a running instance with the tarball uploaded, you can run the training script directly:

```bash
vastai exec <INSTANCE_ID> "bash /workspace/zendesk_exporter/vast_train.sh"
```

The script compresses the trained adapter weights into `/workspace/adapters.tar.gz` on completion. Download them from your local machine:

```bash
vastai copy <INSTANCE_ID> /workspace/adapters.tar.gz ./adapters/
vastai destroy instance <INSTANCE_ID>
```

---

## ⚙️ Configuration

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

## 💰 Cost Optimization

| Action | Effect |
|--------|--------|
| RTX 4090 (~$0.30/hr) | ~$0.13-0.19 per run (30-45 min) |
| Use `vast_run.sh --rent` | Auto-destroys instance → no over-billing |
| Pre-create tarball before renting | Saves ~30s of billing |
| Reduce `per_device_train_batch_size` | Lower VRAM = cheaper GPU tier |

---

## 🔍 Troubleshooting

| Symptom | Fix |
|---------|-----|
| `CUDA out of memory` | Reduce `per_device_train_batch_size` in config.yaml (4→2 or 1) |
| `No module named unsloth` | Ensure `uv sync --extra train` ran successfully |
| Instance doesn't stop | `vastai destroy instance <ID>` manually |
| `Connection refused` | Wait 30-60s for the instance to boot before `vastai exec` |
| `uv: command not found` | Run `pip install uv` first (already in the script) |
| Training is slow | Check GPU utilization: `vastai exec <ID> "nvidia-smi"` |
| No weights downloaded | Check if training completed: `vastai exec <ID> "ls -la /workspace/adapters/"` |

---

## 📋 Training Run Archive

Every training run via `vast_run.sh` now saves a complete record under
`runs/<TIMESTAMP>/`. This preserves everything needed to reproduce or
investigate the result later:

| File | Contents |
|------|----------|
| `run_summary.json` | Timestamp, duration, exit code, train/valid counts |
| `config.yaml` | Snapshot of config at training time |
| `score_report.txt` | Dataset quality score (before training) |
| `training_output.log` | Full stdout from vast_train.sh |
| `trainer_state.json` | Per-step loss + eval loss curve |

**Why this matters:**
- Compare loss curves across runs to spot overfitting
- Reproduce any training session exactly (same config + same data)
- Debug "why did the model get worse?" without re-training
- Audit trail: know exactly what was trained, when, and on what data

See `runs/README.md` for details.
