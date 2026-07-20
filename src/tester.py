"""Interactive Tester — chat with the fine-tuned model via Ollama.

Functional Requirements:
  FR-401: Load model
  FR-402: Load adapter
  FR-403: Interactive CLI
  FR-404: Exit gracefully
"""

import sys
from pathlib import Path
from typing import Any

from src.common.config import get_inference_config
from src.common.logger import get_logger

logger = get_logger(__name__)


def _load_model_for_inference(cfg: dict[str, Any]) -> Any:
    """Load base model + LoRA adapter for inference — FR-401, FR-402."""
    try:
        from unsloth import FastLanguageModel  # type: ignore[import-untyped]
    except ImportError:
        logger.error("Unsloth not installed. Run: pip install unsloth")
        raise

    base_model = cfg.get("base_model", "unsloth/Qwen2.5-1.5B-Instruct")
    adapter_dir = cfg.get("adapter_dir", "adapters/lora_adapter")
    max_seq_length = cfg.get("max_seq_length", 2048)

    if not Path(adapter_dir).exists():
        logger.error(
            "Adapter not found at %s. Run run_train.py first or check config.",
            adapter_dir,
        )
        raise FileNotFoundError(f"Missing adapter: {adapter_dir}")

    logger.info("Loading model: %s", base_model)
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=max_seq_length,
        load_in_4bit=True,
    )

    # FR-402: Load LoRA adapter
    logger.info("Loading LoRA adapter from %s", adapter_dir)
    model.load_adapter(adapter_dir)

    FastLanguageModel.for_inference(model)
    logger.info("Model ready for inference.")

    return model, tokenizer


def _generate_response(
    model: Any,
    tokenizer: Any,
    messages: list[dict[str, str]],
    cfg: dict[str, Any],
) -> str:
    """Generate a response for the given conversation — FR-401."""
    max_new_tokens = cfg.get("max_new_tokens", 512)
    temperature = cfg.get("temperature", 0.7)
    top_p = cfg.get("top_p", 0.9)

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    outputs = model.generate(
        **inputs,
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_p=top_p,
        do_sample=True,
    )

    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)
    return response.strip()


# ---------------------------------------------------------------
# Interactive CLI — FR-403, FR-404
# ---------------------------------------------------------------

def run_interactive(config_path: str | None = None) -> None:
    """Start an interactive chat session — FR-403, FR-404.

    Args:
        config_path: Optional override path to config YAML.
    """
    cfg = get_inference_config()
    if config_path:
        from src.common.config import load_config

        cfg = load_config(config_path).get("inference", {})

    print("=" * 60)
    print("  Zendesk AI Customer Support — Interactive Tester")
    print("  Type 'exit' or 'quit' to end the session.")
    print("=" * 60)
    print()

    model, tokenizer = _load_model_for_inference(cfg)

    system_prompt = cfg.get("system_prompt", "")

    history: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt}
    ]

    while True:
        try:
            user_input = input("คุณ: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # FR-404: Exit gracefully
        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye!")
            break

        history.append({"role": "user", "content": user_input})

        print("AI: ", end="", flush=True)
        response = _generate_response(model, tokenizer, history, cfg)
        print(response)
        print()

        history.append({"role": "assistant", "content": response})
