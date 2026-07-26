"""Tests for config loading, env var overrides, validation, and singleton behaviour."""

import importlib
from pathlib import Path
from unittest import mock

import pytest
import yaml
from src.common import config as config_module


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure the config singleton is cleared before each test."""
    config_module._reset_config()
    yield
    config_module._reset_config()


@pytest.fixture
def temp_config_dir(tmp_path: Path):
    """Create a minimal config.yaml and .env in a temporary directory."""
    config_yml = tmp_path / "config.yaml"
    env_file = tmp_path / ".env"
    config_data = {
        "training": {
            "base_model": "unsloth/Qwen2.5-1.5B-Instruct",
            "max_seq_length": 2048,
        },
        "inference": {
            "base_model": "unsloth/Qwen2.5-1.5B-Instruct",
            "adapter_dir": "adapters",
        },
    }
    config_yml.write_text(yaml.dump(config_data), encoding="utf-8")
    env_file.write_text("ZENDESK_SUBDOMAIN=testsub\n", encoding="utf-8")
    return tmp_path


class TestLoadConfigDefaults:
    """Basic config loading behaviour."""

    def test_load_config_returns_expected_sections(self, temp_config_dir):
        cfg = config_module.load_config(str(temp_config_dir / "config.yaml"))
        assert "training" in cfg
        assert "inference" in cfg

    def test_load_config_custom_path(self, temp_config_dir):
        cfg = config_module.load_config(str(temp_config_dir / "config.yaml"))
        assert cfg["training"]["base_model"] == "unsloth/Qwen2.5-1.5B-Instruct"
        assert cfg["inference"]["base_model"] == "unsloth/Qwen2.5-1.5B-Instruct"

    def test_get_training_config_returns_training_section(self, temp_config_dir):
        cfg = config_module.get_training_config(str(temp_config_dir / "config.yaml"))
        assert cfg["base_model"] == "unsloth/Qwen2.5-1.5B-Instruct"
        assert cfg["max_seq_length"] == 2048

    def test_get_inference_config_returns_inference_section(self, temp_config_dir):
        config_module.load_config(str(temp_config_dir / "config.yaml"))
        cfg = config_module.get_inference_config()
        assert "base_model" in cfg
        assert "adapter_dir" in cfg


class TestGetBaseModel:
    """get_base_model helper."""

    def test_returns_training_base_model(self, temp_config_dir):
        config_module.load_config(str(temp_config_dir / "config.yaml"))
        assert (
            config_module.get_base_model("training")
            == "unsloth/Qwen2.5-1.5B-Instruct"
        )

    def test_fallback_to_default_when_key_missing(self, temp_config_dir):
        cfg = config_module.load_config(str(temp_config_dir / "config.yaml"))
        del cfg["training"]["base_model"]
        assert config_module.get_base_model("training") == config_module.DEFAULT_BASE_MODEL

    def test_fallback_to_default_when_section_missing(self, temp_config_dir):
        cfg = config_module.load_config(str(temp_config_dir / "config.yaml"))
        del cfg["training"]
        assert config_module.get_base_model("training") == config_module.DEFAULT_BASE_MODEL


class TestEnvVarOverride:
    """ZENDESK_BASE_MODEL env var override."""

    def test_base_model_env_var_overrides_both_sections(self, monkeypatch, temp_config_dir):
        monkeypatch.setenv("ZENDESK_BASE_MODEL", "meta-llama/Llama-3.2-3B")
        importlib.reload(config_module)
        with mock.patch.object(config_module, "PROJECT_ROOT", temp_config_dir):
            config_module._reset_config()
            cfg = config_module.load_config()
        assert cfg["training"]["base_model"] == "meta-llama/Llama-3.2-3B"
        assert cfg["inference"]["base_model"] == "meta-llama/Llama-3.2-3B"

    def test_empty_env_var_does_not_override(self, monkeypatch, temp_config_dir):
        monkeypatch.setenv("ZENDESK_BASE_MODEL", "")
        importlib.reload(config_module)
        with mock.patch.object(config_module, "PROJECT_ROOT", temp_config_dir):
            config_module._reset_config()
            cfg = config_module.load_config()
        assert cfg["training"]["base_model"] == "unsloth/Qwen2.5-1.5B-Instruct"


class TestResetConfig:
    """_reset_config singleton behaviour."""

    def test_reset_config_clears_singleton(self):
        config_module.load_config()
        assert config_module._config is not None
        config_module._reset_config()
        assert config_module._config is None

    def test_reset_config_allows_reload(self, temp_config_dir):
        cfg1 = config_module.load_config(str(temp_config_dir / "config.yaml"))
        config_module._reset_config()
        cfg2 = config_module.load_config(str(temp_config_dir / "config.yaml"))
        assert cfg1 is not cfg2
        assert cfg1 == cfg2


class TestValidateModelConfig:
    """validate_model_config warnings and errors."""

    def test_empty_training_model_raises(self):
        with pytest.raises(ValueError, match="training.base_model cannot be empty"):
            config_module.validate_model_config(
                {"base_model": ""}, {"base_model": "unsloth/Qwen2.5-1.5B-Instruct"}
            )

    def test_empty_inference_model_raises(self):
        with pytest.raises(ValueError, match="inference.base_model cannot be empty"):
            config_module.validate_model_config(
                {"base_model": "unsloth/Qwen2.5-1.5B-Instruct"}, {"base_model": "  "}
            )

    def test_mismatch_returns_warning(self):
        warnings = config_module.validate_model_config(
            {"base_model": "unsloth/Qwen2.5-7B-Instruct"},
            {"base_model": "unsloth/Qwen2.5-1.5B-Instruct"},
        )
        assert len(warnings) == 1
        assert "differs" in warnings[0]

    def test_valid_config_returns_no_warnings(self):
        warnings = config_module.validate_model_config(
            {"base_model": "unsloth/Qwen2.5-1.5B-Instruct"},
            {"base_model": "unsloth/Qwen2.5-1.5B-Instruct"},
        )
        assert warnings == []

    def test_missing_key_treated_as_empty(self):
        with pytest.raises(ValueError):
            config_module.validate_model_config(
                {}, {"base_model": "unsloth/Qwen2.5-1.5B-Instruct"}
            )
