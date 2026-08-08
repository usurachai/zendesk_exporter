# Zendesk AI Customer Support Fine-tuning Platform

Fine-tune Qwen2.5-7B-Instruct (or Qwen2.5-1.5B-Instruct) on historical Zendesk Facebook Messenger conversations using LoRA (Unsloth) to automate Level-1 Thai customer support responses.

**MVP — not a production chatbot.**


---

## Trained Models

LoRA adapters trained on historical Zendesk Facebook Messenger conversations, available on HuggingFace:

| Model | Adapter | Size | Training | Eval Loss |
|-------|---------|------|----------|-----------|
| Qwen2.5-7B-Instruct | **[usurachai/zendesk-support-qwen2.5-7b-lora](https://huggingface.co/usurachai/zendesk-support-qwen2.5-7b-lora)** | 161 MB | 2 epochs, 226 steps, 28 min (RTX 4090) | 2.70 → 0.90 |
| Qwen2.5-1.5B-Instruct | **[usurachai/zendesk-support-qwen2.5-1.5b-lora](https://huggingface.co/usurachai/zendesk-support-qwen2.5-1.5b-lora)** | 71 MB | 3 epochs | 2.35 → 1.69 |

### Load from HuggingFace

```python
from unsloth import FastLanguageModel
from peft import PeftModel

# Load base model in 4-bit
model, tokenizer = FastLanguageModel.from_pretrained(
    "unsloth/Qwen2.5-7B-Instruct",
    load_in_4bit=True,
)

# Attach LoRA adapter
model = PeftModel.from_pretrained(model, "usurachai/zendesk-support-qwen2.5-7b-lora")
```

### Run locally

- **MacBook M1**: See [mac_inference.md](mac_inference.md) (Python+PEFT, Ollama, llama.cpp, LM Studio) — 7B runs on 16 GB Macs via GGUF (Q4_K_M ~7-9 GB); 7B via Python+PEFT needs 32 GB; 1.5B fits any machine
- **Linux CPU**: See [llamacpp.md](llamacpp.md) (llama.cpp with LoRA support)
- **Remote GPU**: See [train.md](train.md) (vast.ai training + inference)

---

## Architecture

```
Zendesk Search API + Comments API
        │
        ▼
   run_export.py      →  data/raw/ticket_*.json
        │
        ▼
   run_prepare.py     →  data/train.jsonl + data/valid.jsonl
        │
        ▼
   run_score.py       →  quality report  (optional)
        │
        ▼
   run_train.py       →  adapters/lora_adapter/  (via vast.ai GPU)
        │                     see: train.md
        ▼
   run_test.py        →  interactive CLI
                         see: llamacpp.md, mac_inference.md
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package & project manager)
- Zendesk account with API access
- [vast CLI](https://vast.ai/docs/cli) (for remote GPU training)

### 1. Install

```bash
git clone git@github.com:usurachai/zendesk_exporter.git
cd zendesk_exporter

# Create virtual environment and install core dependencies (export + dataset + tests + lint)
uv sync
```

For training and inference, include the optional ML dependencies (**~280 MB download, requires CUDA GPU**):

```bash
uv sync --extra train
```

> **Note:** `uv` manages the virtual environment automatically. All `uv run` commands below execute inside `.venv` — no manual activation needed.

### 2. Configure

```bash
cp .env.example .env
```

Fill in your Zendesk credentials:

```env
ZENDESK_SUBDOMAIN=yourcompany
ZENDESK_EMAIL=agent@yourcompany.com
ZENDESK_API_TOKEN=your_api_token
```

Override defaults in `config/config.yaml` as needed (date ranges, channel ID, agent names, cleanup toggles, LoRA params).

#### Base Model Configuration

The base model is configurable via three layers (highest priority first):

```bash
# 1. CLI flag (highest priority)
uv run python run_train.py --base_model unsloth/Qwen2.5-7B-Instruct

# 2. Environment variable
ZENDESK_BASE_MODEL=unsloth/Qwen2.5-7B-Instruct uv run python run_train.py

# 3. Edit config/config.yaml (default behavior)
# training:
#     base_model: "unsloth/Qwen2.5-7B-Instruct"
```

Supported models include any Unsloth-compatible HuggingFace model (Qwen2.5, Llama, Mistral, Gemma).

> **Note**: Config value changes (like switching base_model) do NOT require test updates. Tests are decoupled from specific config values.

### 3. Run the pipeline

```bash
# Step 1 — Export tickets (requires --start-date)
uv run python run_export.py --start-date 2026-06-01 --end-date 2026-06-30

# Step 2 — Analyze sentence frequencies & discover filter candidates
uv run python run_prepare.py --analyze

# Step 3 — Build dataset (after configuring filter_sentences)
uv run python run_prepare.py

# Step 4 — Fine-tune (on vast.ai GPU, see train.md)
./vast_run.sh

# Step 5 — Test interactively (see llamacpp.md or mac_inference.md)
uv run python run_test.py

# Run tests
uv run python -m pytest tests/ -v
```

Or activate the venv and run directly:

```bash
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows

python run_export.py --start-date 2026-06-01 --end-date 2026-06-30
python run_prepare.py
python run_train.py
python run_test.py
```

---

## Project Structure

```
zendesk_exporter/
├── AGENTS.md                 # Project instructions for subagents (auto-loaded by pi)
├── config/
│   └── config.yaml          # All tunable parameters
├── data/
│   ├── raw/                 # Exported ticket JSON (gitignored)
│   ├── train.jsonl          # Unsloth-format training data
│   └── valid.jsonl          # Unsloth-format validation data
├── .github/
│   ├── SDLC.md              # Agent-driven SDLC overview
│   ├── WORKFLOW.md          # Concrete subagent workflow (finding → issue → branch → code → PR → review → merge)
│   ├── pull_request_template.md
│   ├── ISSUE_TEMPLATE/agent_handoff.md
│   └── workflows/ci.yml
├── src/
│   ├── common/
│   │   ├── config.py        # YAML + .env loader
│   │   └── logger.py        # Structured logging
│   ├── exporter.py          # Zendesk Search API + Comments API export
│   ├── dataset.py           # Conversation builder + JSONL generator + cleanup
│   ├── score_dataset.py     # Dataset quality scorer (5 dimensions)
│   ├── trainer.py           # Unsloth LoRA fine-tuning
│   └── tester.py            # Interactive CLI inference
├── run_export.py            # Entry point: export
├── run_prepare.py           # Entry point: dataset
├── run_score.py             # Entry point: dataset quality scorer
├── run_train.py             # Entry point: train
├── run_test.py              # Entry point: test
├── vast_run.sh              # Remote training orchestrator (vast.ai)
├── vast_train.sh            # Training script (runs inside vast.ai instance)
├── llamacpp.md              # Inference guide: llama.cpp (Linux CPU)
├── mac_inference.md         # Inference guide: MacBook M1 (Ollama/llama.cpp/LM Studio)
├── tests/
│   ├── fixtures.py           # Sample Zendesk tickets for testing
│   └── test_dataset.py       # 63 tests for dataset preparation
├── .env.example             # Required secrets template
├── requirements.txt         # Core deps (export + dataset)
├── requirements-train.txt   # Optional ML deps (training + inference)
└── spec.md                  # Full functional specification
```

---

## Modules

### 1. Exporter (`run_export.py`)

Exports Facebook Messenger (Sunshine Conversations) tickets with full conversation history.

- **Phase 1 — Search API**: finds tickets by channel (`via:sunshine_conversations_facebook_messenger`) and date range, 100 tickets/page
- **Phase 2 — Comments API**: fetches full conversation for each ticket concurrently (5 workers, configurable)
- `--start-date` / `--end-date` CLI args for date-range exports (ISO format: `YYYY-MM-DD`)
- Resumes from interruption via checkpoint of completed ticket IDs
- Rate-limit retry with exponential backoff
- Saves one JSON file per ticket to `data/raw/`

### 2. Dataset Builder (`run_prepare.py`)

Converts raw tickets into Unsloth-format conversation data with quality cleanup.

**Sunshine Conversations support** — handles the `author_id=-1` format where speaker names are embedded in message bodies as `(HH:MM:SS) Name: message`:
- Extracts customer name from private `"Conversation with <Name>"` comment
- Parses speaker from each message timestamp prefix
- Classifies using configurable agent name whitelist (`dataset.agent_names`)
- Splits multi-message Zendesk comments into individual turns

**Quality cleanup** (all configurable toggles):
- Strips attachment metadata (`.jpeg\nURL:...\nType:...\nSize:...` → `[image]`)
- Replaces raw URLs with `[link]` placeholder (URLs protected from downstream processing when `clean_urls: false`)
- Redacts PII: phone numbers → `[phone]`, emails → `[email]` (safe patterns preserved)
- Strips trailing Thai filler particles (ครับ/ค่ะ/ฮะ/นะครับ/etc) — preserves mid-sentence
- Drops messages that are nothing but filler words ("ครับ", "ๆ", etc.)
- **Dynamic canned detection**: discovers template signatures via substring frequency analysis, no hardcoded patterns
- **Per-signature canned dedup**: keeps max N copies per template (not globally)
- **Canned suffix stripping**: removes repeated closing templates from end of messages, keeps unique prefix
- **Sentence filtering** (config-driven): `--analyze` mode discovers over-represented sentences, user curates filter list in config
- Drops messages shorter than `min_message_length` (default: 10 chars)

**Standard pipeline:**
- Merges consecutive same-role messages
- Removes private notes and empty messages
- Splits into train/valid with configurable ratio and shuffle seed
- Injects system prompt

### 3. Trainer (`run_train.py`)

Fine-tunes Qwen2.5-7B-Instruct (or Qwen2.5-1.5B-Instruct) with LoRA using Unsloth.

- 4-bit quantization for memory efficiency
- Configurable LoRA rank, alpha, target modules
- `--train` / `--valid` CLI flags to override train.jsonl / valid.jsonl paths
- `max_seq_length` read from config (no hardcoded truncation window)
- Saves adapter to `adapters/lora_adapter/`
- Supports resume from checkpoint

**Remote training:** Use `./vast_run.sh` to orchestrate training on vast.ai GPU (rent → upload → train → download → destroy). See [train.md](train.md) for details.

### 4. Scorer (`run_score.py`)

Evaluates dataset quality across 5 dimensions (0-100 scale):

| Dimension | Weight | What It Checks |
|-----------|--------|----------------|
| Pipeline Integrity | 15 pts | All pipeline stages executed successfully |
| Content Safety | 20 pts | No PII, raw URLs, or attachment metadata in final data |
| Cleaning & Dedup | 25 pts | Effective deduplication, no garbled fragments, canned detection (regex-based garbling avoids false positives) |
| Dataset Fitness | 25 pts | Valid train/valid split, min message length, system prompt injection |
| Config Engineering | 15 pts | Sensible config values and toggles (logging score reflects actual logger setup) |

```bash
uv run python run_score.py
```

Passing threshold: **70/100**.

### 5. Tester (`run_test.py`)

Interactive CLI to test the fine-tuned model (requires GPU or CPU with enough RAM).

- Loads base model + LoRA adapter
- System prompt read from `inference.system_prompt` in config (matches training prompt)
- Maintains conversation history
- `exit` / `quit` / `Ctrl+C` to end

**Other inference options:**
- **llama.cpp** (CPU, Linux): [llamacpp.md](llamacpp.md) — convert adapter to GGUF, run with `llama-cli`
- **MacBook M1**: [mac_inference.md](mac_inference.md) — Ollama, llama.cpp, LM Studio, or Python (7B fits 16 GB via GGUF Q4_K_M)
- **HuggingFace**: Load adapter directly from `usurachai/zendesk-support-qwen2.5-7b-lora` (7B) or `usurachai/zendesk-support-qwen2.5-1.5b-lora` (1.5B)

---

## Configuration Reference

All tunable parameters in `config/config.yaml`. Secrets go in `.env` (never committed).

### Export

| Key | Default | Description |
|-----|---------|-------------|
| `subdomain` | *(from .env)* | Zendesk subdomain |
| `start_time` | `null` | Default start date (ISO, overridden by `--start-date`) |
| `end_time` | `null` | Default end date (ISO, overridden by `--end-date`) |
| `channel_id` | `sunshine_conversations_facebook_messenger` | Zendesk `via:` channel ID |
| `max_retries` | `5` | Rate-limit retry count |
| `retry_backoff_base` | `2` | Exponential backoff seconds |
| `max_pages` | `5000` | Safety limit (total API calls) |
| `comment_concurrency` | `5` | Parallel comment fetch workers |
| `output_dir` | `data/raw` | Ticket JSON output directory |
| `checkpoint_file` | `data/export_cursor.json` | Resume state |

### Dataset

| Key | Default | Description |
|-----|---------|-------------|
| `input_dir` | `data/raw` | Raw ticket JSON directory |
| `output_dir` | `data` | JSONL output directory |
| `train_ratio` | `0.9` | Train/valid split proportion |
| `shuffle_seed` | `42` | Reproducible shuffle |
| `agent_names` | `["Kissadakron...", "Surachai...", "Support Team"]` | Known agent names for Sunshine classification |
| `clean_attachments` | `true` | Strip attachment metadata (`→ [image]`) |
| `clean_urls` | `true` | Replace raw URLs (`→ [link]`) |
| `dedupe_canned` | `true` | Remove repeated canned closing messages |
| `dedupe_exact` | `true` | Cross-conversation exact duplicate removal |
| `max_duplicate_count` | `3` | Keep max N copies of identical messages |
| `dedupe_sentences` | `true` | Sentence-level dedup across conversations |
| `filter_sentences` | `[]` | Exact sentences or phrase substrings to filter (see `--analyze`) |
| `clean_fillers` | `true` | Strip trailing filler particles (ครับ/ค่ะ/ฮะ/etc) |
| `drop_filler_only` | `true` | Drop messages that are nothing but filler words |
| `redact_pii` | `true` | Redact phone numbers and email addresses |
| `pii_safe_patterns` | `["support@..."]` | Patterns exempt from redaction |
| `min_message_length` | `10` | Skip messages shorter than N chars |
| `system_prompt` | *(Thai support agent)* | Injected into every sample |

**Dataset scoring:**
```bash
uv run python run_score.py
```
Outputs a per-dimension quality report and final score (passing: 70/100).

**Test suite:**
```bash
uv run python -m pytest tests/ -v
# 63 tests — dataset builder, cleanup, dedup, scoring
```

**Sentence filtering workflow:**
```bash
# 1. Analyze sentence frequencies to discover candidates
uv run python run_prepare.py --analyze

# 2. Add chosen sentences to filter_sentences in config.yaml:
#    filter_sentences:
#      - "หากพี่มนุษย์ต้องการสอบถามข้อมูลเพิ่มเติม..."
#      - "ทุกความคิดเห็นของพี่มนุษย์สำคัญต่อเรา..."

# 3. Run prepare — chosen sentences are filtered
uv run python run_prepare.py
```

### Training

| Key | Default | Description |
|-----|---------|-------------|
| `base_model` | `unsloth/Qwen2.5-7B-Instruct` | HuggingFace model ID |
| `max_seq_length` | `2048` | Token context window |
| `load_in_4bit` | `true` | 4-bit quantization |
| `lora_r` | `16` | LoRA rank |
| `lora_alpha` | `16` | LoRA alpha |
| `lora_dropout` | `0.0` | LoRA dropout |
| `num_epochs` | `3` | Training epochs |
| `learning_rate` | `2.0e-4` | Learning rate |
| `per_device_train_batch_size` | `4` | Batch size |
| `gradient_accumulation_steps` | `4` | Gradient accumulation |
| `output_dir` | `adapters` | Adapter save directory |

### Inference

| Key | Default | Description |
|-----|---------|-------------|
| `adapter_dir` | `adapters/lora_adapter` | LoRA adapter path |
| `base_model` | `unsloth/Qwen2.5-7B-Instruct` | Base model for inference |
| `max_new_tokens` | `512` | Max generation length |
| `temperature` | `0.7` | Sampling temperature |
| `top_p` | `0.9` | Nucleus sampling |
| `system_prompt` | *(Thai support agent)* | System prompt (must match training prompt to avoid train/serve skew) |

---

## Scope

**Included:** Facebook Messenger (Sunshine Conversations) only, Thai language, historical ticket export with full conversations, data quality cleanup, LoRA fine-tuning, local inference.

**Excluded:** RAG, FastAPI, CI/CD, MLOps, auto-reply, dashboard, multi-language.

---

## Development

This repo follows an **agent-driven SDLC** — see [`.github/SDLC.md`](.github/SDLC.md) for the full workflow (risk tiers, self-healing review loops, nightly triage pipeline).

- **Workflow guideline**: [`.github/WORKFLOW.md`](.github/WORKFLOW.md) — concrete step-by-step instructions for subagents (finding → issue → branch → worker → commit → PR → reviewer → merge). Includes mandatory pre-merge verification requiring APPROVED review before merge. DT2 lightweight path available for config/docs changes.
- **Project instructions**: [`AGENTS.md`](AGENTS.md) — auto-loaded by pi at startup, tells subagents how to work in this repo.
- **Agent communication**: [`docs/INTERCOM.md`](docs/INTERCOM.md) — comprehensive guide for real-time agent-to-agent communication via intercom. See also [`docs/INTERCOM_CHEATSHEET.md`](docs/INTERCOM_CHEATSHEET.md) for quick reference.
- **CI**: [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs syntax check + the full test suite on every PR to `main`.
- **PR template**: [`.github/pull_request_template.md`](.github/pull_request_template.md) ensures every change has evidence attached.
- **Issue template**: [`.github/ISSUE_TEMPLATE/agent_handoff.md`](.github/ISSUE_TEMPLATE/agent_handoff.md) enables self-contained subagent handoff.

---

## License

Internal use — not for redistribution.
