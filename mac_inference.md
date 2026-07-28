# Inference on MacBook M1 (16 GB RAM)

Run the fine-tuned Zendesk support model locally on Apple Silicon.
The 1.5B adapter fits easily in 16 GB RAM (~4 GB used).

> **7B model note:** The 7B adapter requires ~16 GB in 4-bit — it works on 32 GB MacBooks
> but may run out of memory on 16 GB machines. For 16 GB Macs, stick with the 1.5B adapter.
> Both adapters are available on HuggingFace (see links below).

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

model = AutoModelForCausalLM.from_pretrained("unsloth/Qwen2.5-1.5B-Instruct")
model = PeftModel.from_pretrained(model, "usurachai/zendesk-support-qwen2.5-1.5b-lora")
tokenizer = AutoTokenizer.from_pretrained("unsloth/Qwen2.5-1.5B-Instruct")
# For 7B (32 GB Mac only):
# model = AutoModelForCausalLM.from_pretrained("unsloth/Qwen2.5-7B-Instruct")
# model = PeftModel.from_pretrained(model, "usurachai/zendesk-support-qwen2.5-7b-lora")
# tokenizer = AutoTokenizer.from_pretrained("unsloth/Qwen2.5-7B-Instruct")

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

**What happens:** The base model downloads on first run (~3 GB cached), and the adapter (81 MB) streams automatically from HuggingFace. No manual download needed. First run takes ~2 minutes, subsequent runs start instantly.

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
# 1.5B: usurachai/zendesk-support-qwen2.5-1.5b-lora (81 MB)
# 7B:   usurachai/zendesk-support-qwen2.5-7b-lora (173 MB — 32 GB Mac only)

# Option A: Stream from HuggingFace (no manual download needed)
# PEFT loads the adapter on-the-fly — skip this step entirely.

# Option B: Download and use locally
huggingface-cli download usurachai/zendesk-support-qwen2.5-1.5b-lora --local-dir ~/models/adapter
```

### 3. Run Inference

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Load base model
model = AutoModelForCausalLM.from_pretrained(
    "unsloth/Qwen2.5-1.5B-Instruct",
    torch_dtype="auto",
    device_map="cpu"
)

# Load adapter (streams from HuggingFace, or use local path)
model = PeftModel.from_pretrained(
    model,
    "usurachai/zendesk-support-qwen2.5-1.5b-lora"  # remote — streamed automatically
    # "~/models/adapter"                            # local — use this if downloaded
)

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained("unsloth/Qwen2.5-1.5B-Instruct")

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

**Performance:** ~10-15 tokens/sec on M1. Each response completes in 2-5 seconds.

---

## Option B: llama.cpp (GGUF — Full LoRA Support)

Best for running the adapter as a server or integrating with other tools.

### 1. Install llama.cpp

```bash
brew install llama.cpp
```

### 2. Download GGUF Base Model (~1 GB)

```bash
mkdir -p ~/models

# Option A: curl (simplest, follow redirects)
curl -L -o ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf

# Option B: huggingface-cli (more reliable, handles auth)
huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct-GGUF \
  qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --local-dir ~/models
```

### 3. Download Adapter and Convert to GGUF

```bash
# Download adapter
mkdir -p ~/models/adapter
huggingface-cli download usurachai/zendesk-support-qwen2.5-1.5b-lora --local-dir ~/models/adapter

# Download base model in HF format for converter
huggingface-cli download unsloth/Qwen2.5-1.5B-Instruct --local-dir ~/models/qwen-base

# Clone converter scripts
git clone --depth 1 https://github.com/ggml-org/llama.cpp.git /tmp/llama-src

# Install converter deps (transformers required by convert_lora_to_gguf.py)
pip install transformers huggingface_hub sentencepiece protobuf torch numpy

# Convert adapter
python3 /tmp/llama-src/convert_lora_to_gguf.py \
  ~/models/adapter \
  --outfile ~/models/adapter-lora.gguf \
  --outtype f16 \
  --base ~/models/qwen-base
```

### 4. Run with LoRA

```bash
# Interactive chat (interactive mode auto-enabled when chat template is available)
llama-cli \
  -m ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --lora ~/models/adapter-lora.gguf \
  --color \
  -t 8 \
  --temp 0.7

# Start a server (for API access)
llama-server \
  -m ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --lora ~/models/adapter-lora.gguf \
  --port 8080
```

**Flags explained:**
| Flag | Purpose |
|------|---------|
| `-m` | Base model GGUF file |
| `--lora` | Adapter GGUF file |
| `--color` | Colorize output (prompt vs generation) |
| `-t 8` | CPU threads (M1 has 8 cores) |
| `--temp 0.7` | Generation temperature |

---

## Option C: Ollama (Easiest — Base Model Only)

Ollama does **not** support LoRA adapters natively. Use this for testing the base model's out-of-box behavior.

```bash
brew install ollama

# Pull the 1.5B Q4_K_M GGUF (~1 GB)
ollama pull qwen2.5:1.5b

# Create a custom model with system prompt
cat > ~/models/Modelfile << 'EOF'
FROM qwen2.5:1.5b
SYSTEM """You are a helpful, polite customer support agent for a Thai company.
Follow the company's support SOP. Ask for missing information before
troubleshooting. Escalate when appropriate. Respond in Thai."""
EOF

ollama create zendesk-support -f ~/models/Modelfile
ollama run zendesk-support
```

**Note:** Without the LoRA adapter, the base model hasn't been fine-tuned on Zendesk data, so responses won't reflect the training.

---

## Option D: LM Studio (GUI — LoRA Supported)

1. Download [LM Studio](https://lmstudio.ai) (free, macOS native)
2. Search for `Qwen2.5-1.5B-Instruct` and download the Q4_K_M version
3. Download the adapter: `huggingface-cli download usurachai/zendesk-support-qwen2.5-1.5b-lora --local-dir ~/models/adapter`
4. Convert adapter to GGUF using llama.cpp (see Option B, step 3)
5. In LM Studio: load model → settings → "Load LoRA" → select `adapter-lora.gguf`

---

## Performance Comparison

| Method | Speed | RAM Usage | LoRA Support | Ease | Best For |
|--------|-------|-----------|--------------|------|----------|
| **Python + PEFT** | 10-15 tok/s | ~4 GB | ✅ Full | Easiest | Quick testing, scripting |
| **llama.cpp** | 15-20 tok/s | ~4 GB | ✅ Full | Medium | Server, high perf |
| **LM Studio** | 15-20 tok/s | ~4 GB | ✅ Full | Easy (GUI) | GUI browsing |
| **Ollama** | 15-20 tok/s | ~4 GB | ❌ No | Easiest | Base model only |

**Recommendation:** Start with **Python + PEFT** (Option A) — it's 3 lines of code, streams the adapter from HuggingFace, and requires no conversion. Move to llama.cpp if you need higher throughput or a server API.

---

## Download Reference

### Adapter (from HuggingFace)

| File | Size | Purpose |
|------|------|---------|
| `adapter_model.safetensors` | 70.5 MB | LoRA weights (rank=16, alpha=32) |
| `tokenizer.json` | 10.9 MB | Qwen2.5 tokenizer (must match base model) |
| `adapter_config.json` | 1.2 KB | LoRA hyperparameters |
| `chat_template.jinja` | 2.5 KB | Prompt template |
| `training_args.bin` | 692 B | Training config |

**Download command:**
```bash
huggingface-cli download usurachai/zendesk-support-qwen2.5-1.5b-lora --local-dir ./adapter
```

### Base Model (required for conversion only)

**HF format** (~3 GB, needed for `convert_lora_to_gguf.py`):
```bash
huggingface-cli download unsloth/Qwen2.5-1.5B-Instruct --local-dir ./qwen-base
```

**GGUF format** (~1 GB, for llama.cpp / Ollama):
```bash
curl -LO https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf
```