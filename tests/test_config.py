"""Tests for configuration loading and base model support."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.common.config import (
    DEFAULT_BASE_MODEL,
    _reset_config,
    get_base_model,
    get_inference_config,
    get_training_config,
    load_config,
    validate_model_config,
)


@pytest.fixture(autouse=True)
def reset_config():
    """Reset config cache before each test."""
    _reset_config()
    yield
    _reset_config()


class TestLoadConfig:
    """Tests for load_config()."""

    def test_load_default_config(self):
        """Load config from default path."""
        cfg = load_config()
        assert "training" in cfg
        assert "inference" in cfg
        assert "export" in cfg

    def test_load_custom_config(self):
        """Load config from custom path."""
        config_path = str(Path(__file__).parent.parent / "config" / "config.yaml")
        cfg = load_config(config_path)
        assert "training" in cfg

    def test_singleton_cache(self):
        """Second call returns same object."""
        cfg1 = load_config()
        cfg2 = load_config()
        assert cfg1 is cfg2


class TestGetBaseModel:
    """Tests for get_base_model()."""

    def test_returns_training_base_model(self):
        """Return base_model from training section."""
        model = get_base_model("training")
        assert model == "unsloth/Qwen2.5-1.5B-Instruct"

    def test_returns_inference_base_model(self):
        """Return base_model from inference section."""
        model = get_base_model("inference")
        assert model == "unsloth/Qwen2.5-1.5B-Instruct"

    def test_fallback_to_default(self):
        """Fallback to DEFAULT_BASE_MODEL when key missing."""
        _reset_config()
        with patch("src.common.config.load_config") as mock_load:
            mock_load.return_value = {"training": {}}
            model = get_base_model("training")
            assert model == DEFAULT_BASE_MODEL


class TestEnvVarOverride:
    """Tests for ZENDESK_BASE_MODEL env var override."""

    def test_base_model_from_env(self):
        """ZENDESK_BASE_MODEL overrides YAML value."""
        _reset_config()
        with patch.dict(os.environ, {"ZENDESK_BASE_MODEL": "custom/model-7b"}):
            cfg = load_config()
            assert cfg["training"]["base_model"] == "custom/model-7b"
            assert cfg["inference"]["base_model"] == "custom/model-7b"

    def test_env_var_empty_string(self):
        """Empty env var does NOT override YAML value."""
        _reset_config()
        with patch.dict(os.environ, {"ZENDESK_BASE_MODEL": ""}):
            cfg = load_config()
            assert cfg["training"]["base_model"] == "unsloth/Qwen2.5-1.5B-Instruct"


class TestResetConfig:
    """Tests for _reset_config()."""

    def test_reset_clears_cache(self):
        """_reset_config() clears the singleton cache."""
        cfg1 = load_config()
        _reset_config()
        cfg2 = load_config()
        assert cfg1 is not cfg2


class TestValidateModelConfig:
    """Tests for validate_model_config()."""

    def test_valid_config_passes(self):
        """No errors on matching config."""
        training_cfg = {"base_model": "model/a"}
        inference_cfg = {"base_model": "model/a"}
        warnings = validate_model_config(training_cfg, inference_cfg)
        assert warnings == []

    def test_empty_training_model_raises(self):
        """ValueError on empty training base_model."""
        training_cfg = {"base_model": ""}
        inference_cfg = {"base_model": "model/a"}
        with pytest.raises(ValueError, match="training.base_model cannot be empty"):
            validate_model_config(training_cfg, inference_cfg)

    def test_empty_inference_model_raises(self):
        """ValueError on empty inference base_model."""
        training_cfg = {"base_model": "model/a"}
        inference_cfg = {"base_model": ""}
        with pytest.raises(ValueError, match="inference.base_model cannot be empty"):
            validate_model_config(training_cfg, inference_cfg)

    def test_whitespace_only_model_raises(self):
        """ValueError on whitespace-only base_model."""
        training_cfg = {"base_model": "   "}
        inference_cfg = {"base_model": "model/a"}
        with pytest.raises(ValueError, match="training.base_model cannot be empty"):
            validate_model_config(training_cfg, inference_cfg)

    def test_mismatch_warns(self):
        """Warning on training != inference."""
        training_cfg = {"base_model": "model/a"}
        inference_cfg = {"base_model": "model/b"}
        warnings = validate_model_config(training_cfg, inference_cfg)
        assert len(warnings) == 1
        assert "differs" in warnings[0]
