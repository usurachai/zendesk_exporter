# Zendesk AI Customer Support Fine-tuning Platform

Fine-tune Qwen2.5-1.5B-Instruct on historical Zendesk Facebook Messenger conversations using LoRA (Unsloth) to automate Level-1 Thai customer support responses.

**MVP — not a production chatbot.**

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
   run_train.py       →  adapters/lora_adapter/
        │
        ▼
   run_test.py        →  interactive CLI (→ Ollama for production)
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (Python package & project manager)
- CUDA-capable GPU (for training/inference)
- Zendesk account with API access

### 1. Install

```bash
git clone git@github.com:usurachai/zendesk_exporter.git
cd zendesk_exporter

# Create virtual environment and install core dependencies (export + dataset only)
uv venv
uv pip install -r requirements.txt
```

For training and inference, install the optional ML dependencies (**~280 MB download, requires CUDA GPU**):

```bash
uv pip install -r requirements-train.txt
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

### 3. Run the pipeline

```bash
# Step 1 — Export tickets (requires --start-date)
uv run python run_export.py --start-date 2026-06-01 --end-date 2026-06-30

# Step 2 — Build dataset
uv run python run_prepare.py

# Step 3 — Fine-tune
uv run python run_train.py

# Step 4 — Test interactively
uv run python run_test.py
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
├── config/
│   └── config.yaml          # All tunable parameters
├── data/
│   ├── raw/                 # Exported ticket JSON (gitignored)
│   ├── train.jsonl          # Unsloth-format training data
│   └── valid.jsonl          # Unsloth-format validation data
├── src/
│   ├── common/
│   │   ├── config.py        # YAML + .env loader
│   │   └── logger.py        # Structured logging
│   ├── exporter.py          # Zendesk Search API + Comments API export
│   ├── dataset.py           # Conversation builder + JSONL generator + cleanup
│   ├── trainer.py           # Unsloth LoRA fine-tuning
│   └── tester.py            # Interactive CLI inference
├── run_export.py            # Entry point: export
├── run_prepare.py           # Entry point: dataset
├── run_train.py             # Entry point: train
├── run_test.py              # Entry point: test
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
- Replaces raw URLs with `[link]` placeholder
- Redacts PII: phone numbers → `[phone]`, emails → `[email]` (safe patterns preserved)
- Deduplicates canned closing messages within conversations
- Strips trailing Thai filler particles (ครับ/ค่ะ/ฮะ/นะครับ/etc) — preserves mid-sentence
- Drops messages that are nothing but filler words ("ครับ", "ๆ", etc.)
- Dynamic canned detection: discovers template signatures via substring frequency analysis
- Cross-conversation canned dedup: keeps max N copies of any canned message
- Drops messages shorter than `min_message_length` (default: 3 chars)

**Standard pipeline:**
- Merges consecutive same-role messages
- Removes private notes and empty messages
- Splits into train/valid with configurable ratio and shuffle seed
- Injects system prompt

### 3. Trainer (`run_train.py`)

Fine-tunes Qwen2.5-1.5B-Instruct with LoRA using Unsloth.

- 4-bit quantization for memory efficiency
- Configurable LoRA rank, alpha, target modules
- Saves adapter to `adapters/lora_adapter/`
- Supports resume from checkpoint

### 4. Tester (`run_test.py`)

Interactive CLI to test the fine-tuned model.

- Loads base model + LoRA adapter
- Maintains conversation history
- `exit` / `quit` / `Ctrl+C` to end

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
| `max_sentence_count` | `5` | Drop sentences appearing more than N times |
| `clean_fillers` | `true` | Strip trailing filler particles (ครับ/ค่ะ/ฮะ/etc) |
| `drop_filler_only` | `true` | Drop messages that are nothing but filler words |
| `redact_pii` | `true` | Redact phone numbers and email addresses |
| `pii_safe_patterns` | `["support@..."]` | Patterns exempt from redaction |
| `min_message_length` | `3` | Skip messages shorter than N chars |
| `system_prompt` | *(Thai support agent)* | Injected into every sample |

### Training

| Key | Default | Description |
|-----|---------|-------------|
| `base_model` | `unsloth/Qwen2.5-1.5B-Instruct` | HuggingFace model ID |
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
| `base_model` | `unsloth/Qwen2.5-1.5B-Instruct` | Base model for inference |
| `max_new_tokens` | `512` | Max generation length |
| `temperature` | `0.7` | Sampling temperature |
| `top_p` | `0.9` | Nucleus sampling |

---

## Scope

**Included:** Facebook Messenger (Sunshine Conversations) only, Thai language, historical ticket export with full conversations, data quality cleanup, LoRA fine-tuning, local inference.

**Excluded:** RAG, FastAPI, CI/CD, MLOps, auto-reply, dashboard, multi-language.

---

## License

Internal use — not for redistribution.
