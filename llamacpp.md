# Inference - Testing with llama.cpp

Test the fine-tuned LoRA adapter locally using llama.cpp (CPU inference, no GPU needed).

> **Model choice:** The 1.5B adapter (~35 MB) runs well on any CPU with ~5 GB RAM.
> The 7B adapter can also be used but requires ~8 GB RAM for the Q4_K_M GGUF and
> runs at ~1-2 tokens/sec on CPU. For the 7B adapter, substitute `Qwen2.5-7B`
> for `Qwen2.5-1.5B` in all commands below.

## Prerequisites

- Linux x86_64 (Ubuntu 22.04+)
- ~5 GB free disk (base model + adapter + tools)
- Python 3.10+ (for conversion scripts)
- git, curl, unzip

---

## 1. Install llama.cpp

Download pre-built binary (no compilation needed):

```bash
mkdir -p ~/.local/bin ~/.local/lib

# Download latest release
curl -fsSL -o /tmp/llama.tar.gz \
  https://github.com/ggml-org/llama.cpp/releases/download/b10107/llama-b10107-bin-ubuntu-x64.tar.gz

# Extract binaries and libraries
tar xzf /tmp/llama.tar.gz -C /tmp
cp /tmp/llama-b10107-bin-ubuntu-x64/llama-* ~/.local/bin/
cp /tmp/llama-b10107-bin-ubuntu-x64/lib*.so* ~/.local/lib/

# Add to PATH (add to ~/.bashrc for persistence)
export PATH="$HOME/.local/bin:$PATH"
export LD_LIBRARY_PATH="$HOME/.local/lib:$LD_LIBRARY_PATH"

# Verify
llama-cli --version
```

---

## 2. Download Base Model

Download the Qwen2.5-1.5B-Instruct base model (~3 GB):

```bash
pip install huggingface_hub

python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('unsloth/Qwen2.5-1.5B-Instruct', local_dir='models/qwen-base')
print('Base model downloaded to models/qwen-base/')
"
```

---

## 3. Convert Base Model to GGUF

llama.cpp requires GGUF format. Convert the HuggingFace model:

```bash
# Install converter dependencies
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers numpy sentencepiece protobuf

# Clone llama.cpp source (for conversion scripts)
git clone --depth 1 https://github.com/ggml-org/llama.cpp.git /tmp/llama-src

# Convert to GGUF (F16, ~3 GB output)
python3 /tmp/llama-src/convert_hf_to_gguf.py \
  models/qwen-base \
  --outfile models/qwen-base-f16.gguf \
  --outtype f16
```

---

## 4. Convert LoRA Adapter to GGUF

Convert the trained adapter (from adapters/lora_adapter/):

```bash
python3 /tmp/llama-src/convert_lora_to_gguf.py \
  adapters/lora_adapter \
  --outfile models/adapter.gguf \
  --outtype f16 \
  --base models/qwen-base

echo 'Adapter converted (~35 MB)'
```

---

## 5. Run Inference

### Interactive Chat

> **Important:** Run from the llama.cpp binary directory (libs must be in cwd)

```bash
cd /path/to/llama-b10107-bin-ubuntu-x64

./llama-cli \
  -m /path/to/models/qwen-base-f16.gguf \
  --lora /path/to/models/adapter.gguf \
  -p "<im_start>system
You are a helpful, polite customer support agent for a Thai company.
Follow the company's support SOP. Ask for missing information before
troubleshooting. Escalate when appropriate. Respond in Thai.<im_end>" \
  -n 150 --temp 0.7 -t 4
```

**Flags:**
- -m: base model GGUF path
- --lora: adapter GGUF path
- -p: prompt with chat template
- -n 150: max tokens to generate
- --temp 0.7: temperature
- -t 4: CPU threads

### Single-Shot Query (no chat)

```bash
./llama-cli \
  -m models/qwen-base-f16.gguf \
  --lora models/adapter.gguf \
  -p "Your question here" \
  -n 100 --no-display-prompt --temp 0.7
```

---

## 6. Verify Adapter is Loaded

When the adapter loads correctly, llama-cli will print:

```
load_model: applying lora adapter from models/adapter.gguf
```

If you see errors about shape mismatch, the adapter may have been
trained with a different base model version.

---

## Performance Notes

- CPU-only inference on Qwen2.5-1.5B: ~2-5 tokens/sec (slow)
- CPU-only inference on Qwen2.5-7B (Q4_K_M GGUF): ~1-2 tokens/sec (very slow)
- For faster testing, use a GPU instance on vast.ai with the adapter
- The adapter (~35 MB) is much smaller than the full model (~3 GB)
- Quantized models (Q4/Q8) are faster but may reduce quality

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| no backends are loaded | Run from the llama.cpp binary directory (libs must be in cwd) |
| cannot open shared object | Ensure LD_LIBRARY_PATH includes ~/.local/lib |
| Slow generation | Normal for CPU; use vast.ai GPU for faster inference |
| Adapter shape mismatch | Ensure adapter was trained on the same base model version |
| Empty output | Check prompt format matches Qwen chat template |
