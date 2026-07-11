# Zendesk AI Customer Support Fine-tuning Platform

Fine-tune Qwen2.5-1.5B-Instruct on historical Zendesk Facebook Messenger conversations using LoRA (Unsloth) to automate Level-1 Thai customer support responses.

**MVP — not a production chatbot.**

---

## Architecture

```
Zendesk Incremental Export API
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
- CUDA-capable GPU (for training/inference)
- Zendesk account with API access

### 1. Install

```bash
git clone git@github.com:YOUR_USER/zendesk_exporter.git
cd zendesk_exporter
pip install -r requirements.txt
```

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

Override defaults in `config/config.yaml` as needed (ratios, model name, LoRA params).

### 3. Run the pipeline

```bash
# Step 1 — Export tickets
python run_export.py

# Step 2 — Build dataset
python run_prepare.py

# Step 3 — Fine-tune
python run_train.py

# Step 4 — Test interactively
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
│   ├── exporter.py          # Zendesk incremental export
│   ├── dataset.py           # Conversation builder + JSONL generator
│   ├── trainer.py           # Unsloth LoRA fine-tuning
│   └── tester.py            # Interactive CLI inference
├── run_export.py            # Entry point: export
├── run_prepare.py           # Entry point: dataset
├── run_train.py             # Entry point: train
├── run_test.py              # Entry point: test
├── .env.example             # Required secrets template
├── requirements.txt
└── spec.md                  # Full functional specification
```

---

## Modules

### 1. Exporter (`run_export.py`)

Exports Facebook Messenger tickets from Zendesk via the Incremental Export API.

- Saves one JSON file per ticket to `data/raw/`
- Handles rate limiting (exponential backoff, configurable retries)
- Resumes from interruption via checkpoint cursor
- Stores all public comments with metadata

### 2. Dataset Builder (`run_prepare.py`)

Converts raw tickets into Unsloth-format conversation data.

- Identifies customer vs agent by `requester_id`
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

All tunable parameters in `config/config.yaml`:

| Section | Key | Default | Description |
|---------|-----|---------|-------------|
| `export` | `incremental` | `true` | Use Zendesk incremental API |
| `export` | `max_retries` | `5` | Rate-limit retry count |
| `export` | `retry_backoff_base` | `2` | Exponential backoff seconds |
| `dataset` | `train_ratio` | `0.9` | Train/valid split proportion |
| `dataset` | `shuffle_seed` | `42` | Reproducible shuffle |
| `dataset` | `system_prompt` | *(Thai support agent)* | Injected into every sample |
| `training` | `base_model` | `unsloth/Qwen2.5-1.5B-Instruct` | HuggingFace model ID |
| `training` | `lora_r` | `16` | LoRA rank |
| `training` | `num_epochs` | `3` | Training epochs |
| `training` | `learning_rate` | `2.0e-4` | Learning rate |
| `inference` | `max_new_tokens` | `512` | Max generation length |
| `inference` | `temperature` | `0.7` | Sampling temperature |

Secrets go in `.env` (never committed).

---

## Scope

**Included:** Facebook Messenger only, Thai language, historical ticket export, LoRA fine-tuning, local inference.

**Excluded:** RAG, FastAPI, CI/CD, MLOps, auto-reply, dashboard, multi-language.

---

## License

Internal use — not for redistribution.
