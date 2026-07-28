# Qwen2.5-7B-Instruct LoRA Fine-Tuning Report

**Date:** 2026-07-28  
**Status:** ✅ Successful — adapter published on HuggingFace

## 1. Summary

Successfully fine-tuned **Qwen2.5-7B-Instruct** on 1,808 Thai Zendesk customer support conversations using LoRA (Unsloth). Training completed in ~28 minutes on an RTX 4090 (vast.ai) at a total cost of ~$0.19. The adapter weights are published on HuggingFace.

| Metric | Value |
|--------|-------|
| Base model | `unsloth/Qwen2.5-7B-Instruct` |
| Adapter | `usurachai/zendesk-support-qwen2.5-7b-lora` |
| Fine-tuning method | QLoRA (4-bit) |
| Adapter size | 161 MB |
| Training duration | 28 minutes |
| Total cost | ~$0.19 |
| GPU | NVIDIA RTX 4090 (24 GB VRAM) |

---

## 2. Dataset

| Split | Examples | Ratio |
|-------|----------|-------|
| Training | 1,808 | 90% |
| Validation | 206 | 10% |
| **Total** | **2,014** | 100% |

Source: Historical Zendesk Facebook Messenger (Sunshine Conversations) conversations, exported via `run_export.py` and cleaned via `run_prepare.py`.

### Quality Pipeline
- PII redaction (phone → `[phone]`, email → `[email]`)
- Canned message deduplication (max 3 copies per template)
- Thai filler particle cleaning (ครับ/ค่ะ/ฮะ/นะครับ/etc)
- Sentence-level deduplication (configurable filter list)
- URL replacement → `[link]`
- Attachment metadata stripping → `[image]`
- min_message_length: 10 chars
- Dataset quality score: **90/100**

---

## 3. Training Configuration

### Model Architecture

| Parameter | Value |
|-----------|-------|
| Quantization | 4-bit (BNB) |
| LoRA rank (`r`) | 16 |
| LoRA alpha | 16 |
| LoRA dropout | 0.1 |
| Target modules | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| Trainable params | 18,464,768 / 1,562,179,072 (**1.18%**) |
| Precision | bf16 (Ampere+ GPU) |

### Training Hyperparameters

| Parameter | Value |
|-----------|-------|
| Epochs | 2 |
| Total steps | 226 |
| Per-device batch | 4 |
| Gradient accumulation | 4 |
| Effective batch size | 16 |
| Learning rate | 2e-4 (cosine schedule) |
| Warmup steps | 10 |
| Weight decay | 0.01 |
| Max seq length | 2,048 tokens |
| Logging steps | 1 |
| Eval steps | 50 |
| Save steps | 100 (disabled via monkey-patch, see §7) |

### Infrastructure

| Component | Detail |
|-----------|--------|
| GPU | NVIDIA RTX 4090 (24 GB VRAM) |
| Platform | vast.ai |
| Region | Texas, US |
| Network | 7,201 Mbps net_up |
| Instance type | `pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime` |
| Disk | 50 GB |
| Cost | $0.4144/hr |
| Dependencies | Unsloth 2026.7.4, PEFT 0.19.1, TRL 0.24.0, Transformers latest |

---

## 4. Loss Curves

### Training Loss (per step, 226 steps)

```
Step  1:  loss=2.18  (warmup start)
Step  5:  loss=2.39  (peak — cosine warmup)
Step 10:  loss=1.84  (warmup complete)
Step 20:  loss=1.67
Step 30:  loss=1.48
Step 50:  loss=1.32
Step 80:  loss=1.18
Step 100: loss=1.06
Step 120: loss=1.02
Step 140: loss=0.98
Step 160: loss=0.95
Step 180: loss=0.93
Step 200: loss=0.91
Step 226: loss=0.90  (final)
```

### Eval Loss (per 50 steps)

| Step | Eval Loss | Epoch |
|------|-----------|-------|
| 50 | 1.211 | 0.44 |
| 100 | 1.009 | 0.88 |
| 150 | 0.937 | 1.33 |
| 200 | 0.906 | 1.77 |
| 226 | 0.900 | 2.00 |

**Trend:** Monotonically decreasing loss with no signs of overfitting. The eval loss gradient is flattening (0.906 → 0.900 in the final 26 steps), suggesting continued training may yield diminishing returns.

---

## 5. Adapter Artifacts

| File | Size | Description |
|------|------|-------------|
| `adapter_model.safetensors` | 161 MB | LoRA weight matrices (r=16, 7 modules) |
| `adapter_config.json` | 1.3 KB | PEFT config (rank, alpha, target modules, etc.) |
| `tokenizer.json` | 10.9 MB | Qwen2.5 tokenizer (same as base) |
| `tokenizer_config.json` | 4.4 KB | Tokenizer config |
| `chat_template.jinja` | 2.5 KB | Qwen chat template |
| `README.md` | 5.3 KB | Auto-generated model card |
| `training_args.bin` | 692 B | Training args (not fully serialized — see §7) |

**HuggingFace:** https://huggingface.co/usurachai/zendesk-support-qwen2.5-7b-lora  
**Visibility:** Public  
**Usage score:** 173.0 MB

---

## 6. Timeline

| Phase | Duration | Cumulative |
|-------|----------|------------|
| Instance boot (Docker pull) | ~3 min | 3 min |
| Dependency install (uv sync) | ~5 min | 8 min |
| First training attempt (crash — missing gcc) | ~2 min | 10 min |
| Install gcc/g++ | ~2 min | 12 min |
| Second training run (step 1–100, then pickle crash) | ~7 min | 19 min |
| Resume from checkpoint-100 (step 100–226) | ~9 min | 28 min |
| Download adapter + destroy instance | ~1 min | 29 min |
| **Total wall time** | **~29 min** | |

---

## 7. Known Issues

### Pickle Error on `training_args.bin` (Resolved)

**Root cause:** Unsloth's `unsloth_compiled_cache/` bytecode compilation duplicates the `trl.trainer.sft_config.SFTConfig` class in memory. When `transformers.Trainer._save()` calls `torch.save(self.args, "training_args.bin")`, pickle detects the class identity mismatch and raises:

```
_pickle.PicklingError: Can't pickle <class 'trl.trainer.sft_config.SFTConfig'>:
    it's not the same object as trl.trainer.sft_config.SFTConfig
```

**Impact:** Only `training_args.bin` is affected. The adapter weights (`adapter_model.safetensors`) save correctly. The `training_args.bin` file is not needed for inference.

**Fix:** A monkey-patch in `src/trainer.py` intercepts the pickle error and skips only `training_args.bin` saves, allowing checkpoints and final save to complete normally.

### 7B Model Disk Requirements

The 7B model download is ~14 GB. With dependencies, Docker image, and workspace, the minimum disk is **50 GB**. The first attempt failed with the default 20 GB.

---

## 8. Comparison: 1.5B vs 7B

| Dimension | Qwen2.5-1.5B | Qwen2.5-7B |
|-----------|-------------|-------------|
| **Adapter size** | 71 MB | 161 MB |
| **Training time** (RTX 4090, 2 epochs) | ~10 min | ~28 min |
| **Training cost** | ~$0.05 | ~$0.19 |
| **GPU VRAM** (4-bit) | ~4 GB | ~16 GB |
| **Min disk** | 30 GB | 50 GB |
| **Inference** (CPU, Q4_K_M GGUF) | ~2-5 tok/s | ~1-2 tok/s |
| **Inference** (Mac 16 GB) | ✅ Works | ❌ OOM |
| **Inference** (Mac 32 GB) | ✅ Works | ✅ Works |
| **HuggingFace** | [usurachai/zendesk-support-qwen2.5-1.5b-lora](https://huggingface.co/usurachai/zendesk-support-qwen2.5-1.5b-lora) | [usurachai/zendesk-support-qwen2.5-7b-lora](https://huggingface.co/usurachai/zendesk-support-qwen2.5-7b-lora) |

---

## 9. Usage

Load the adapter for inference:

```python
from unsloth import FastLanguageModel
from peft import PeftModel

model, tokenizer = FastLanguageModel.from_pretrained(
    "unsloth/Qwen2.5-7B-Instruct",
    load_in_4bit=True,
    max_seq_length=2048,
)

model = PeftModel.from_pretrained(model, "usurachai/zendesk-support-qwen2.5-7b-lora")

# Inference
messages = [
    {"role": "system", "content": "You are a helpful, polite customer support agent for a Thai company. Respond in Thai."},
    {"role": "user", "content": "สั่งของไปแล้วยังไม่ได้รับเลยครับ"},
]
inputs = tokenizer.apply_chat_template(messages, return_tensors="pt").to("cuda")
outputs = model.generate(inputs, max_new_tokens=512, temperature=0.7, top_p=0.9)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
```

---

## 10. Lessons Learned

| Issue | Fix | Documented In |
|-------|-----|---------------|
| 20 GB disk insufficient for 7B | Default → **50 GB** | `vast_run.sh`, `train.md` |
| Docker devel image too large (~15 GB) | Switch to **runtime** image (~8 GB) | `vast_run.sh` |
| 90s boot timeout unrealistic | **15 min** timeout | `vast_run.sh` |
| Budget machines slow to pull Docker | Filter by **net_up > 2000 Mbps** | `train.md` |
| Missing C compiler on runtime image | Install `gcc`/`g++` via apt (or use devel) | `train.md` |
| Unsloth compiled cache pickle error | Monkey-patch `torch.save` for `training_args.bin` | `src/trainer.py`, `train.md` |