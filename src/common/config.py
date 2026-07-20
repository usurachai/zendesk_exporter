"""Configuration loader — merges YAML config with .env secrets."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

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
