# Functional Specification

# Zendesk AI Customer Support Fine-tuning Platform

Version: 0.1 (MVP)

---

# 1. Project Overview

## Objective

Develop a simple, maintainable pipeline that transforms historical Zendesk Facebook Messenger conversations into a high-quality dataset for fine-tuning a Small Language Model (SLM) using Unsloth.

The first MVP focuses only on producing a working fine-tuned model as quickly as possible.

This project is **NOT** intended to build a production AI chatbot yet.

---

# 2. Business Goal

Replace repetitive Level-1 customer support responses with an AI model that learns from historical support conversations.

The AI should:

- Reply similarly to experienced support agents
- Follow company support SOP
- Ask for missing information before troubleshooting
- Escalate appropriately
- Answer common FAQs
- Respond politely and professionally in Thai

---

# 3. Success Criteria

The MVP is considered successful when:

- Zendesk conversations are exported successfully.
- Dataset is generated in Unsloth format.
- Qwen2.5-1.5B-Instruct is fine-tuned successfully.
- Model produces useful responses for support scenarios.
- Human evaluators agree the response quality is acceptable.

---

# 4. Project Scope

Included

- Facebook Messenger only
- Thai language
- Historical ticket export
- Dataset preparation
- LoRA fine-tuning
- Local inference

Excluded

- RAG
- FastAPI
- CI/CD
- MLOps
- Automatic reply
- Dashboard
- Multi-language support

---

# 5. System Architecture

```
Zendesk
      │
      ▼
Export Ticket
      │
      ▼
Raw JSON
      │
      ▼
Dataset Builder
      │
      ▼
train.jsonl
valid.jsonl
      │
      ▼
Unsloth
      │
      ▼
LoRA Adapter
      │
      ▼
Ollama
```

---

# 6. Technology Stack

| Component         | Technology            |
| ----------------- | --------------------- |
| Language          | Python 3.11           |
| Dataset           | JSON                  |
| Training Dataset  | JSONL                 |
| Fine Tune         | Unsloth               |
| Base Model        | Qwen2.5-1.5B-Instruct |
| Inference         | Ollama                |
| Version Control   | Git                   |
| Configuration     | YAML                  |
| Secret Management | .env                  |

---

# 7. Project Structure

```
zendesk-ai/

config/

data/
    raw/
    train.jsonl
    valid.jsonl

logs/

src/

    common/
        config.py
        logger.py

    exporter.py
    dataset.py
    trainer.py
    tester.py

run_export.py
run_prepare.py
run_train.py
run_test.py
```

---

# 8. Functional Modules

---

## Module 1

### Zendesk Exporter

### Purpose

Export Facebook Messenger conversations from Zendesk.

### Input

Zendesk Incremental Export API

### Process

- Retrieve tickets
- Retrieve comments
- Retrieve metadata
- Save JSON

### Output

```
data/raw/

ticket_1001.json

ticket_1002.json
```

---

### Functional Requirements

FR-001

Export ticket metadata.

---

FR-002

Export ticket comments.

---

FR-003

Support Incremental Export API.

---

FR-004

Retry when rate limited.

---

FR-005

Save one JSON file per ticket.

---

FR-006

Store all public comments.

---

FR-007

Support resume after interruption.

---

---

## Module 2

Dataset Builder

### Purpose

Convert Zendesk ticket into conversation format.

### Input

```
ticket_x.json
```

Output

Conversation object.

Example

```json
{
    "ticket_id": 1001,

    "conversation": [
        {
            "role": "human",
            "content": "..."
        },

        {
            "role": "assistant",
            "content": "..."
        }
    ]
}
```

---

### Functional Requirements

FR-101

Identify customer using requester_id.

---

FR-102

Identify agent using author_id.

---

FR-103

Merge consecutive messages.

---

FR-104

Remove private notes.

---

FR-105

Remove empty messages.

---

FR-106

Preserve conversation order.

---

FR-107

Generate conversation statistics.

---

## Module 3

Dataset Generator

Purpose

Generate Unsloth dataset.

Input

Conversation objects.

Output

```
train.jsonl

valid.jsonl
```

---

Functional Requirements

FR-201

Split dataset.

---

FR-202

Random shuffle.

---

FR-203

Generate JSONL.

---

FR-204

Support configurable train ratio.

---

FR-205

Preserve message role.

---

Example

```json
{
    "messages": [
        {
            "role": "system",
            "content": "..."
        },

        {
            "role": "user",
            "content": "..."
        },

        {
            "role": "assistant",
            "content": "..."
        }
    ]
}
```

---

## Module 4

Trainer

Purpose

Fine tune Qwen2.5-1.5B.

Input

```
train.jsonl
```

Output

LoRA Adapter.

---

Functional Requirements

FR-301

Load base model.

---

FR-302

Load dataset.

---

FR-303

Train with LoRA.

---

FR-304

Save adapter.

---

FR-305

Resume training.

---

## Module 5

Tester

Purpose

Interactive testing.

Input

Customer question.

Output

Model response.

---

Functional Requirements

FR-401

Load model.

---

FR-402

Load adapter.

---

FR-403

Interactive CLI.

---

FR-404

Exit gracefully.

---

# 9. Configuration

Configuration File

```
config/config.yaml
```

Contains

- Export settings
- Dataset settings
- Training settings

Secrets stored in

```
.env
```

Contains

- API Token
- Email
- Password

---

# 10. Data Flow

```
Zendesk

↓

Raw Ticket

↓

Conversation Builder

↓

Training Dataset

↓

Unsloth

↓

Adapter

↓

Ollama
```

---

# 11. Coding Standards

- Python 3.11+
- Type Hint
- Docstring
- Logging
- No hardcoded values
- Configuration driven
- One responsibility per module

---

# 12. Non-functional Requirements

Performance

- Export 2,000 tickets within one hour.

---

Reliability

- Resume after interruption.

---

Maintainability

- Configuration separated from source code.
- Modular architecture.
- No duplicated logic.

---

Portability

Runs on:

- Windows
- Linux
- macOS

---

Security

- API Token stored in .env
- No secret committed to Git

---

# 13. MVP Roadmap

## Sprint 1

Deliverable

- Export JSON

---

## Sprint 2

Deliverable

- Dataset Builder

---

## Sprint 3

Deliverable

- Fine Tune

---

## Sprint 4

Deliverable

- Local Testing

---

# 14. Future Enhancements (Out of Scope)

- RAG
- Knowledge Base Integration
- FastAPI
- Zendesk AI Suggestion
- Human Feedback Loop
- Multi-language Support
- Conversation Quality Scoring
- Dashboard
- Automatic Evaluation
- Model Version Management

---

# 15. Acceptance Criteria

The project will be accepted when:

- Successfully exports approximately 2,000 Facebook Messenger tickets.
- Generates valid Unsloth JSONL datasets.
- Fine-tunes Qwen2.5-1.5B-Instruct without errors.
- Produces coherent Thai customer support responses.
- Demonstrates behavior aligned with:
    - Company support SOP
    - Professional support tone
    - Information gathering before troubleshooting
    - FAQ answering
    - Appropriate escalation
- Can be executed end-to-end using the four entry-point scripts:
    - `run_export.py`
    - `run_prepare.py`
    - `run_train.py`
    - `run_test.py`
