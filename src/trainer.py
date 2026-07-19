"""Trainer — fine-tune Qwen2.5-1.5B-Instruct with LoRA via Unsloth.

Functional Requirements:
  FR-301: Load base model
  FR-302: Load dataset
  FR-303: Train with LoRA
  FR-304: Save adapter
  FR-305: Resume training
"""

import argparse
import sys
from pathlib import Path
from typing import Any

from src.common.config import get_training_config, load_config
from src.common.logger import get_logger

logger = get_logger(__name__)


def _load_model_and_tokenizer(cfg: dict[str, Any]) -> tuple[Any, Any]:
    """Load base model and tokenizer with Unsloth optimizations — FR-301."""
    try:
        from unsloth import FastLanguageModel  # type: ignore[import-untyped]
    except ImportError:
        logger.error(
            "Unsloth is not installed. Run: pip install unsloth"
        )
        raise

    base_model = cfg.get("base_model", "unsloth/Qwen2.5-1.5B-Instruct")
    max_seq_length = cfg.get("max_seq_length", 2048)
    load_in_4bit = cfg.get("load_in_4bit", True)

    logger.info("Loading base model: %s (4bit=%s)", base_model, load_in_4bit)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_length,
        load_in_4bit=load_in_4bit,
    )

    logger.info("Model loaded successfully.")
    return model, tokenizer


def _apply_lora(model: Any, cfg: dict[str, Any]) -> Any:
    """Apply LoRA adapters — FR-303."""
    from unsloth import FastLanguageModel  # type: ignore[import-untyped]

    lora_r = cfg.get("lora_r", 16)
    lora_alpha = cfg.get("lora_alpha", 16)
    lora_dropout = cfg.get("lora_dropout", 0.0)
    target_modules = cfg.get(
        "target_modules",
        ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    use_rslora = cfg.get("use_rslora", False)

    logger.info("Applying LoRA: r=%d, alpha=%d, targets=%s", lora_r, lora_alpha, target_modules)

    model = FastLanguageModel.get_peft_model(
        model,
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        target_modules=target_modules,
        use_rslora=use_rslora,
    )

    return model


def _load_dataset(cfg: dict[str, Any]) -> Any:
    """Load train/valid JSONL as HuggingFace Dataset — FR-302."""
    from datasets import load_dataset  # type: ignore[import-untyped]

    data_dir = Path(cfg.get("dataset_dir", "data"))
    train_path = str(data_dir / "train.jsonl")
    valid_path = str(data_dir / "valid.jsonl")

    if not Path(train_path).exists():
        logger.error("train.jsonl not found at %s. Run run_prepare.py first.", train_path)
        raise FileNotFoundError(f"Missing training data: {train_path}")

    logger.info("Loading dataset from %s", data_dir)
    dataset = load_dataset(
        "json",
        data_files={"train": train_path, "validation": valid_path},
    )

    logger.info(
        "Dataset loaded: %d train / %d validation",
        len(dataset.get("train", [])),
        len(dataset.get("validation", [])),
    )
    return dataset


def _format_example(example: dict[str, Any], tokenizer: Any) -> dict[str, Any]:
    """Format a single chat example into tokenized tensors."""
    messages = example["messages"]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )
    tokenized = tokenizer(
        text,
        truncation=True,
        max_length=2048,
        padding=False,
    )
    return {
        "input_ids": tokenized["input_ids"],
        "attention_mask": tokenized["attention_mask"],
        "labels": tokenized["input_ids"].copy(),
    }


def run_training(
    config_path: str | None = None,
    train_path: str | None = None,
    valid_path: str | None = None,
) -> dict[str, Any]:
    """Execute LoRA fine-tuning.

    Args:
        config_path: Optional override for config YAML.
        train_path: Optional override path to train.jsonl.
        valid_path: Optional override path to valid.jsonl.

    Returns:
        Summary dict with training results.
    """
    cfg = get_training_config()

    # Step 1: Load model + tokenizer — FR-301
    model, tokenizer = _load_model_and_tokenizer(cfg)

    # Step 2: Apply LoRA — FR-303
    model = _apply_lora(model, cfg)

    # Step 3: Load dataset — FR-302
    dataset = _load_dataset(cfg)

    # Step 4: Format dataset
    def _fmt(ex: dict[str, Any]) -> dict[str, Any]:
        return _format_example(ex, tokenizer)

    train_ds = dataset["train"].map(_fmt, remove_columns=dataset["train"].column_names)
    valid_ds = dataset["validation"].map(_fmt, remove_columns=dataset["validation"].column_names)

    logger.info("Train samples: %d, Valid samples: %d", len(train_ds), len(valid_ds))

    # Step 5: Training args
    from transformers import TrainingArguments  # type: ignore[import-untyped]
    from trl import SFTTrainer  # type: ignore[import-untyped]

    output_dir = cfg.get("output_dir", "adapters")
    num_epochs = cfg.get("num_epochs", 3)
    per_device_batch = cfg.get("per_device_train_batch_size", 4)
    grad_accum = cfg.get("gradient_accumulation_steps", 4)
    learning_rate = cfg.get("learning_rate", 2.0e-4)
    warmup_steps = cfg.get("warmup_steps", 5)
    logging_steps = cfg.get("logging_steps", 1)
    save_steps = cfg.get("save_steps", 100)

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=per_device_batch,
        per_device_eval_batch_size=per_device_batch,
        gradient_accumulation_steps=grad_accum,
        learning_rate=learning_rate,
        warmup_steps=warmup_steps,
        logging_steps=logging_steps,
        save_steps=save_steps,
        evaluation_strategy="steps",
        eval_steps=save_steps,
        save_total_limit=3,
        load_best_model_at_end=True,
        fp16=True,
        report_to="none",
        resume_from_checkpoint=cfg.get("resume_from_checkpoint") is not None,  # FR-305
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=valid_ds,
    )

    # Step 6: Train
    logger.info("Starting training: %d epochs, lr=%s", num_epochs, learning_rate)
    trainer.train(resume_from_checkpoint=cfg.get("resume_from_checkpoint"))  # FR-305

    # Step 7: Save adapter — FR-304
    adapter_path = Path(output_dir) / "lora_adapter"
    logger.info("Saving LoRA adapter to %s", adapter_path)
    model.save_pretrained(adapter_path)
    tokenizer.save_pretrained(adapter_path)

    logger.info("Training complete. Adapter saved to %s", adapter_path)
    return {
        "status": "completed",
        "adapter_path": str(adapter_path),
        "epochs": num_epochs,
    }
