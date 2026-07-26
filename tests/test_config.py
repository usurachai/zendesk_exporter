"""Tests for config loading — path forwarding, overrides, validation."""

import tempfile
from pathlib import Path

import pytest

import src.common.config as config_mod


class TestGetTrainingConfig:
    """Verify training config loading and config_path forwarding."""

    def test_forwards_config_path(self, monkeypatch):
        """get_training_config(config_path) should load from the custom path."""
        # Reset config singleton cache before test
        monkeypatch.setattr(config_mod, "_config", None)

        # Create a temporary YAML config with a known value
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("training:\n")
            f.write('  base_model: "test/custom-model"\n')
            tmp_path = f.name

        try:
            training_cfg = config_mod.get_training_config(config_path=tmp_path)
            assert training_cfg["base_model"] == "test/custom-model"
        finally:
            Path(tmp_path).unlink()

    def test_returns_training_section(self, monkeypatch):
        """get_training_config() without path returns training section from default config."""
        monkeypatch.setattr(config_mod, "_config", None)
        training_cfg = config_mod.get_training_config()
        assert "base_model" in training_cfg
        assert "max_seq_length" in training_cfg
        assert "learning_rate" in training_cfg