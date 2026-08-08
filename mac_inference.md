# Inference on MacBook M1

Run the fine-tuned Zendesk support model locally on Apple Silicon (M1/M2/M3/M4).

The repo's primary model is now **Qwen2.5-7B-Instruct**. The 7B adapter delivers significantly
better response quality than the 1.5B adapter, at the cost of higher RAM/disk.

> **RAM guidance — pick the right adapter:**
> - **7B adapter** (`usurachai/zendesk-support-qwen2.5-7b-lora`, **161 MB**): best quality, but
>   requires **~16 GB in 4-bit**. Comfortable on **32 GB Macs**; will likely **OOM on 16 GB** machines.
> - **1.5B adapter** (`usurachai/zendesk-support-qwen2.5-1.5b-lora`, **81 MB**): uses ~4 GB, runs on
>   any 16 GB Mac. Lower quality but still useful for quick testing.
>
> Both adapters are on HuggingFace (see links below). If your Mac has 16 GB RAM, start with 1.5B.

---

## Quick Start (3 commands)

```bash
# 1. Install dependencies
pip install torch transformers peft huggingface_hub sentencepiece

# 2. Save this script as infer.py
cat > infer.py << 'PYEOF'
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import torch

# === Pick ONE model line below (uncomment your choice) ===
# 7B — recommended quality, ~16 GB RAM, 32 GB Macs:
model = AutoModelForCausalLM.from_pretrained("unsloth/Qwen2.5-7B-Instruct")
model = PeftModel.from_pretrained(model, "usurachai/zendesk-support-qwen2.5-7b-lora")
tokenizer = AutoTokenizer.from_pretrained("unsloth/Qwen2.5-7B-Instruct")
# 1.5B — 16 GB Macs:
# model = AutoModelForCausalLM.from_pretrained("unsloth/Qwen2.5-1.5B-Instruct")
# model = PeftModel.from_pretrained(model, "usurachai/zendesk-support-qwen2.5-1.5b-lora")
# tokenizer = AutoTokenizer.from_pretrained("unsloth/Qwen2.5-1.5B-Instruct")

messages = [
    {"role": "system", "content": "You are a polite customer support agent for a Thai company."},
    {"role": "user", "content": "เข้าแอปไม่ได้ค่ะ"}
]
text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(text, return_tensors="pt")
outputs = model.generate(**inputs, max_new_tokens=256, temperature=0.7)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
PYEOF

# 3. Run it
python3 infer.py
```

**What happens:** The base model downloads on first run (7B ~14 GB / 1.5B ~3 GB cached). The adapter
(161 MB for 7B, 81 MB for 1.5B) streams automatically from HuggingFace. No manual download needed.
First run takes longer (model download + load); subsequent runs start faster.

---

## Option A: Python + PEFT (Simplest — No Conversion)

The adapter loads directly from HuggingFace. The base model is cached locally after first run.

### 1. Install Dependencies

```bash
python3 -m venv ~/zendesk-env
source ~/zendesk-env/bin/activate

# CPU-only for Mac
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers peft huggingface_hub sentencepiece
```

### 2. Download the Adapter (optional — PEFT can stream it)

```bash
# HuggingFace repos:
# 7B:   usurachai/zendesk-support-qwen2.5-7b-lora (161 MB — 32 GB Mac recommended)
# 1.5B: usurachai/zendesk-support-qwen2.5-1.5b-lora (81 MB — 16 GB Mac)

# Option A: Stream from HuggingFace (no manual download needed)
# PEFT loads the adapter on-the-fly — skip this step entirely.

# Option B: Download and use locally (7B example)
huggingface-cli download usurachai/zendesk-support-qwen2.5-7b-lora --local-dir ~/models/adapter
```

### 3. Run Inference

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Load base model (change model name for 1.5B)
base = "unsloth/Qwen2.5-7B-Instruct"          # 7B (32 GB Mac)
# base = "unsloth/Qwen2.5-1.5B-Instruct"      # 1.5B (16 GB Mac)

model = AutoModelForCausalLM.from_pretrained(
    base,
    torch_dtype="auto",
    device_map="cpu"
)

# Load adapter (streams from HuggingFace, or use local path)
adapter = "usurachai/zendesk-support-qwen2.5-7b-lora"   # 7B
# adapter = "usurachai/zendesk-support-qwen2.5-1.5b-lora" # 1.5B
# adapter = "~/models/adapter"                            # local — if downloaded

model = PeftModel.from_pretrained(model, adapter)

tokenizer = AutoTokenizer.from_pretrained(base)

# Chat
messages = [
    {"role": "system", "content": "You are a helpful, polite customer support agent for a Thai company. Follow the company's support SOP. Ask for missing information before troubleshooting. Escalate when appropriate. Respond in Thai."},
    {"role": "user", "content": "เข้าแอปไม่ได้ค่ะ ใส่วันเกิดผิด"}
]

text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(text, return_tensors="pt")

outputs = model.generate(**inputs, max_new_tokens=256, temperature=0.7, top_p=0.9)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
```

**Performance:** ~3-6 tok/s on M1 for 7B (4-bit), ~10-15 tok/s for 1.5B. A full response takes
a few seconds to tens of seconds depending on model and machine.

---

## Option B: llama.cpp (GGUF — Full LoRA Support)

Best for running the adapter as a server or integrating with other tools.

### 1. Install llama.cpp

```bash
brew install llama.cpp
```

### 2. Download GGUF Base Model

```bash
mkdir -p ~/models

# 7B (~4.7 GB) — recommended quality:
curl -L -o ~/models/qwen2.5-7b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf

# 1.5B (~1 GB) — for 16 GB Macs:
# curl -L -o ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
#   https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf

# Alternative: huggingface-cli (more reliable, handles auth)
# huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF \
#   qwen2.5-7b-instruct-q4_k_m.gguf --local-dir ~/models
```

### 3. Download Adapter and Convert to GGUF

```bash
# Download adapter (7B example)
mkdir -p ~/models/adapter
huggingface-cli download usurachai/zendesk-support-qwen2.5-7b-lora --local-dir ~/models/adapter

# Download base model in HF format for converter (7B ~14 GB)
huggingface-cli download unsloth/Qwen2.5-7B-Instruct --local-dir ~/models/qwen-base

# Clone converter scripts
git clone --depth 1 https://github.com/ggml-org/llama.cpp.git /tmp/llama-src

# Install converter deps (transformers required by convert_lora_to_gguf.py)
pip install transformers huggingface_hub sentencepiece protobuf torch numpy

# Convert adapter (base model must match the adapter's base)
python3 /tmp/llama-src/convert_lora_to_gguf.py \
  ~/models/adapter \
  --outfile ~/models/adapter-lora.gguf \
  --outtype f16 \
  --base ~/models/qwen-base
```

### 4. Run with LoRA

```bash
# Interactive chat (interactive mode auto-enabled when chat template is available)
# Use the 7B GGUF below, or swap in the 1.5B GGUF for 16 GB Macs.
llama-cli \
  -m ~/models/qwen2.5-7b-instruct-q4_k_m.gguf \
  --lora ~/models/adapter-lora.gguf \
  --color \
  -t 8 \
  --temp 0.7

# Start a server (for API access); use -ngl for GPU offload on Apple Silicon (Metal)
# On Apple Silicon, add: -ngl 64  (offload to GPU; reduce if RAM-constrained)
llama-server \
  -m ~/models/qwen2.5-7b-instruct-q4_k_m.gguf \
  --lora ~/models/adapter-lora.gguf \
  --port 8080 \
  -ngl 64
```

**Flags explained:**
| Flag | Purpose |
|------|---------|
| `-m` | Base model GGUF file |
| `--lora` | Adapter GGUF file |
| `--color` | Colorize output (prompt vs generation) |
| `-t 8` | CPU threads (M1 has 8 cores) |
| `--temp 0.7` | Generation temperature |
| `-ngl 64` | GPU layers offloaded to Metal (Apple Silicon only; omit if RAM-constrained) |

> **llama-server + Metal on Mac:** llama.cpp builds with Metal to offload layers to the M-series GPU.
> For 7B on 16 GB of unified memory, reduce `-ngl` (e.g. `-ngl 24`) to avoid swapping. On 32 GB
> machines you can offload all layers. If you get out-of-memory or extreme slowness, lower `-ngl`
> or fall back to the 1.5B model.

---

## Option C: Ollama (Easiest — Base Model Only)

Ollama does **not** support LoRA adapters natively. Use this for testing the base model's
out-of-box behavior.

```bash
brew install ollama

# Pull the model (7B Q4_K_M ~4.7 GB; use qwen2.5:1.5b for 16 GB Macs)
ollama pull qwen2.5:7b

# Create a custom model with system prompt
cat > ~/models/Modelfile << 'EOF'
FROM qwen2.5:7b
SYSTEM """You are a helpful, polite customer support agent for a Thai company.
Follow the company's support SOP. Ask for missing information before
troubleshooting. Escalate when appropriate. Respond in Thai."""
EOF

ollama create zendesk-support -f ~/models/Modelfile
ollama run zendesk-support
```

**Note:** Without the LoRA adapter, the base model hasn't been fine-tuned on Zendesk data, so
responses won't reflect the training.

---

## Option D: LM Studio (GUI — LoRA Supported)

1. Download [LM Studio](https://lmstudio.ai) (free, macOS native)
2. Search for `Qwen2.5-7B-Instruct` and download the Q4_K_M version (or `Qwen2.5-1.5B-Instruct` for 16 GB Macs)
3. Download the adapter: `huggingface-cli download usurachai/zendesk-support-qwen2.5-7b-lora --local-dir ~/models/adapter`
4. Convert adapter to GGUF using llama.cpp (see Option B, step 3)
5. In LM Studio: load model → settings → "Load LoRA" → select `adapter-lora.gguf`

---

## Performance Comparison

| Method | Speed (7B) | Speed (1.5B) | RAM (7B) | RAM (1.5B) | LoRA | Ease | Best For |
|--------|-----------|--------------|----------|------------|------|------|----------|
| **Python + PEFT** | 3-6 tok/s | 10-15 tok/s | ~16 GB | ~4 GB | ✅ | Easiest | Quick testing, scripting |
| **llama.cpp** | 4-8 tok/s (Metal) | 15-20 tok/s | ~16 GB | ~4 GB | ✅ | Medium | Server, high perf |
| **LM Studio** | 4-8 tok/s (Metal) | 15-20 tok/s | ~16 GB | ~4 GB | ✅ | Easy (GUI) | GUI browsing |
| **Ollama** | 4-8 tok/s (Metal) | 15-20 tok/s | ~16 GB | ~4 GB | ❌ | Easiest | Base model only |

**Recommendation:** If you have a **32 GB Mac** (or just want the best quality), start with
**Python + PEFT** (Option A) with the **7B adapter** — 3 lines of code, streams from HuggingFace,
no conversion. On a **16 GB Mac**, use the **1.5B adapter** with Option A, then move to llama.cpp
(Option B) for higher throughput or a server API.

---

## Download Reference

### Adapter (from HuggingFace)

| Model | Repo | Adapter Size |
|-------|------|--------------|
| 7B (recommended) | `usurachai/zendesk-support-qwen2.5-7b-lora` | 161 MB |
| 1.5B (16 GB Mac) | `usurachai/zendesk-support-qwen2.5-1.5b-lora` | 81 MB |

**Download commands:**
```bash
# 7B
huggingface-cli download usurachai/zendesk-support-qwen2.5-7b-lora --local-dir ./adapter-7b

# 1.5B
huggingface-cli download usurachai/zendesk-support-qwen2.5-1.5b-lora --local-dir ./adapter-1.5b
```

Each adapter contains:
| File | Size | Purpose |
|------|------|---------|
| `adapter_model.safetensors` | 161 MB (7B) / 70.5 MB (1.5B) | LoRA weights (rank=16, alpha=32) |
| `tokenizer.json` | 10.9 MB | Qwen2.5 tokenizer (must match base model) |
| `adapter_config.json` | 1.3 KB | LoRA hyperparameters |
| `chat_template.jinja` | 2.5 KB | Prompt template |
| `training_args.bin` | 692 B | Training config |

### Base Model (required for conversion only)

**HF format** (for `convert_lora_to_gguf.py`):
```bash
# 7B (~14 GB)
huggingface-cli download unsloth/Qwen2.5-7B-Instruct --local-dir ./qwen-base-7b

# 1.5B (~3 GB)
huggingface-cli download unsloth/Qwen2.5-1.5B-Instruct --local-dir ./qwen-base-1.5b
```

**GGUF format** (for llama.cpp / Ollama):
```bash
# 7B (~4.7 GB)
curl -LO https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/main/qwen2.5-7b-instruct-q4_k_m.gguf

# 1.5B (~1 GB)
curl -LO https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf
```
