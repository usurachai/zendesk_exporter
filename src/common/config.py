"""Configuration loader — merges YAML config with .env secrets."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

# Default base model for training and inference
DEFAULT_BASE_MODEL = "unsloth/Qwen2.5-7B-Instruct"

# Resolve project root relative to this file
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def _load_env() -> dict[str, str]:
    """Load .env from project root. Fall back gracefully if missing."""
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    # Treat empty string as None
    return {k: v if v else "" for k, v in os.environ.items()}


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and parse YAML config file."""
    with open(path, "r") as fh:
        return yaml.safe_load(fh) or {}


def _merge_secrets(cfg: dict[str, Any], env: dict[str, str]) -> dict[str, Any]:
    """Inject environment values. Override YAML null/default values with .env."""
    # Export section — override if YAML has null/empty or missing
    export_cfg = cfg.get("export", {})
    for yaml_key, env_key in [
        ("subdomain", "ZENDESK_SUBDOMAIN"),
        ("email", "ZENDESK_EMAIL"),
        ("api_token", "ZENDESK_API_TOKEN"),
    ]:
        env_val = env.get(env_key)
        if env_val:
            export_cfg[yaml_key] = env_val
        elif not export_cfg.get(yaml_key):
            export_cfg[yaml_key] = None

    # HuggingFace token
    cfg.setdefault("hf_token", env.get("HF_TOKEN"))

    # Base model override via environment variable
    base_model_env = env.get("ZENDESK_BASE_MODEL")
    if base_model_env:
        for section in ("training", "inference"):
            cfg.setdefault(section, {})["base_model"] = base_model_env

    return cfg


_config: dict[str, Any] | None = None


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load and cache merged configuration.

    Args:
        config_path: Optional override path to config YAML.

    Returns:
        Merged configuration dictionary.
    """
    global _config
    if _config is not None:
        return _config

    path = Path(config_path) if config_path else CONFIG_DIR / "config.yaml"
    yaml_cfg = _load_yaml(path)
    env = _load_env()
    _config = _merge_secrets(yaml_cfg, env)
    return _config


def get_export_config() -> dict[str, Any]:
    """Return export section of config."""
    return load_config().get("export", {})


def get_dataset_config() -> dict[str, Any]:
    """Return dataset section of config."""
    return load_config().get("dataset", {})


def get_training_config(config_path: str | None = None) -> dict[str, Any]:
    """Return training section of config."""
    return load_config(config_path).get("training", {})


def get_inference_config() -> dict[str, Any]:
    """Return inference section of config."""
    return load_config().get("inference", {})


def get_base_model(section: str = "training") -> str:
    """Return base model for the given section (training or inference).

    Priority: config YAML > DEFAULT_BASE_MODEL
    (env var ZENDESK_BASE_MODEL is applied in _merge_secrets)
    """
    cfg = load_config()
    return cfg.get(section, {}).get("base_model", DEFAULT_BASE_MODEL)


def _reset_config() -> None:
    """Clear the config cache. Useful for testing."""
    global _config
    _config = None


def validate_model_config(
    training_cfg: dict[str, Any],
    inference_cfg: dict[str, Any],
) -> list[str]:
    """Validate model configuration and return warnings.

    Args:
        training_cfg: Training config section.
        inference_cfg: Inference config section.

    Returns:
        List of warning messages.

    Raises:
        ValueError: If base_model is empty.
    """
    warnings = []
    training_model = training_cfg.get("base_model", "")
    inference_model = inference_cfg.get("base_model", "")

    if not training_model or not training_model.strip():
        raise ValueError("training.base_model cannot be empty")
    if not inference_model or not inference_model.strip():
        raise ValueError("inference.base_model cannot be empty")

    if training_model != inference_model:
        warnings.append(
            f"Training base_model ({training_model}) differs from "
            f"inference base_model ({inference_model}). "
            "The LoRA adapter is tied to the base model — mismatch will cause load failure."
        )

    return warnings
