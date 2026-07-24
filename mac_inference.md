# Inference on MacBook M1 (16 GB RAM)

Run the fine-tuned Zendesk support model locally on Apple Silicon.
The 1.5B model fits easily in 16 GB RAM (~4 GB used).

## Prerequisites

- macOS 13+ on Apple Silicon (M1/M2/M3)
- Homebrew installed
- ~5 GB free disk space

---

## Option A: Ollama (Recommended — Easiest)

### 1. Install Ollama

```bash
brew install ollama
```

### 2. Download Base Model as GGUF

```bash
# Create models directory
mkdir -p ~/models

# Download Q4_K_M quantized version (~1 GB, good quality/speed balance)
curl -L -o ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  https://huggingface.co/unsloth/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf
```

### 3. Download LoRA Adapter as GGUF

```bash
# Clone llama.cpp for conversion scripts
git clone --depth 1 https://github.com/ggml-org/llama.cpp.git /tmp/llama-src

# Install dependencies
pip3 install torch transformers numpy sentencepiece protobuf huggingface_hub

# Download adapter from HuggingFace
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('usurachai/zendesk-support-qwen2.5-1.5b-lora', local_dir='~/models/adapter')
"

# Download base model for conversion
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('unsloth/Qwen2.5-1.5B-Instruct', local_dir='~/models/qwen-base')
"

# Convert adapter to GGUF
python3 /tmp/llama-src/convert_lora_to_gguf.py \
  ~/models/adapter \
  --outfile ~/models/adapter-lora.gguf \
  --outtype f16 \
  --base ~/models/qwen-base
```

### 4. Create Modelfile

```bash
cat > ~/models/Modelfile << 'EOF'
FROM ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf

# System prompt
SYSTEM """You are a helpful, polite customer support agent for a Thai company.
Follow the company's support SOP. Ask for missing information before
troubleshooting. Escalate when appropriate. Respond in Thai."""

# LoRA adapter (if Ollama supports it)
# ADAPTER ~/models/adapter-lora.gguf
EOF
```

### 5. Create and Run Model

```bash
# Create model in Ollama
ollama create zendesk-support -f ~/models/Modelfile

# Run interactive chat
ollama run zendesk-support
```

**Note:** Ollama does not natively support LoRA adapters yet. The guide above
creates a base model. For full LoRA support, use Option B (llama.cpp).

---

## Option B: llama.cpp (Full LoRA Support)

### 1. Install llama.cpp

```bash
brew install llama.cpp
```

### 2. Download Models

```bash
mkdir -p ~/models

# Download GGUF base model
curl -L -o ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  https://huggingface.co/unsloth/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/Qwen2.5-1.5B-Instruct-Q4_K_M.gguf

# Download and convert LoRA adapter (see Option A, step 3)
```

### 3. Run with LoRA Adapter

```bash
# Interactive chat with LoRA
llama-cli \
  -m ~/models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  --lora ~/models/adapter-lora.gguf \
  --chat-template chatml \
  -i \
  -t 8 \
  --temp 0.7
```

**Flags:**
- `-m`: base model GGUF
- `--lora`: adapter GGUF
- `--chat-template chatml`: use Qwen chat format
- `-i`: interactive mode
- `-t 8`: use 8 CPU threads (M1 has 8 cores)
- `--temp 0.7`: temperature

---

## Option C: LM Studio (GUI)

### 1. Install LM Studio

Download from https://lmstudio.ai (free, macOS native app)

### 2. Load Model

1. Open LM Studio
2. Search for `Qwen2.5-1.5B-Instruct`
3. Download the Q4_K_M version (~1 GB)
4. Load the model

### 3. Load LoRA Adapter

1. Go to the model settings
2. Click "Load LoRA" or "Adapter"
3. Select the converted `adapter-lora.gguf` file
4. The adapter will be applied to the base model

### 4. Chat

Type your message in the chat window and press Enter.

---

## Option D: Python with transformers + PEFT

For development/testing with the full HuggingFace stack:

### 1. Install Dependencies

```bash
# Create virtual environment
python3 -m venv ~/zendesk-env
source ~/zendesk-env/bin/activate

# Install packages (CPU-only for Mac)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers peft huggingface_hub sentencepiece
```

### 2. Run Inference

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# Load base model
model_id = "unsloth/Qwen2.5-1.5B-Instruct"
base_model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype="auto",
    device_map="cpu"
)

# Load adapter
model = PeftModel.from_pretrained(
    base_model,
    "usurachai/zendesk-support-qwen2.5-1.5b-lora"
)

# Load tokenizer
tokenizer = AutoTokenizer.from_pretrained(model_id)

# Generate response
messages = [
    {"role": "system", "content": "You are a Thai customer support agent."},
    {"role": "user", "content": "เข้าแอปไม่ได้ค่ะ"}
]

text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
inputs = tokenizer(text, return_tensors="pt")

outputs = model.generate(**inputs, max_new_tokens=256, temperature=0.7)
print(tokenizer.decode(outputs[0], skip_special_tokens=True))
```

---

## Performance Comparison

| Method | Speed | RAM Usage | LoRA Support | Ease of Use |
|--------|-------|-----------|--------------|-------------|
| Ollama | Fast | ~4 GB | No (base only) | Easiest |
| llama.cpp | Fast | ~4 GB | Yes | Medium |
| LM Studio | Fast | ~4 GB | Yes | Easy (GUI) |
| Python | Slow | ~6 GB | Yes | Development |

---

## Recommendation

For **quick testing**, use **Ollama** (Option A) — it's the simplest.
The base model already captures most of the training signal.

For **full fidelity** with the LoRA adapter, use **llama.cpp** (Option B)
or **LM Studio** (Option C).