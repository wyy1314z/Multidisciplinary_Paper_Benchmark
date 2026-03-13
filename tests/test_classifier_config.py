"""Tests for configuration loading."""

import os
import tempfile

import pytest
import yaml

from crossdisc_extractor.classifier.config import LLMConfig, load_config


class TestLLMConfig:
    def test_valid_config(self):
        cfg = LLMConfig(model_name="test", api_base="http://localhost", api_key="sk-test")
        assert cfg.model_name == "test"

    def test_empty_model_name(self):
        with pytest.raises(ValueError, match="model_name"):
            LLMConfig(model_name="", api_base="http://localhost", api_key="sk-test")

    def test_empty_api_base(self):
        with pytest.raises(ValueError, match="api_base"):
            LLMConfig(model_name="test", api_base="", api_key="sk-test")

    def test_empty_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            LLMConfig(model_name="test", api_base="http://localhost", api_key="")

    def test_invalid_temperature(self):
        with pytest.raises(ValueError, match="temperature"):
            LLMConfig(
                model_name="test", api_base="http://localhost",
                api_key="sk-test", temperature=3.0,
            )

    def test_negative_max_retries(self):
        with pytest.raises(ValueError, match="max_retries"):
            LLMConfig(
                model_name="test", api_base="http://localhost",
                api_key="sk-test", max_retries=-1,
            )


class TestLoadConfig:
    def test_load_from_yaml(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
        config_data = {
            "llm": {"model_name": "test-model", "api_base": "http://test-api"},
            "taxonomy": {"path": "data/test.json"},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = load_config(str(config_file))
        assert cfg.llm.model_name == "test-model"
        assert cfg.llm.api_base == "http://test-api"

    def test_env_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
        monkeypatch.setenv("OPENAI_MODEL", "env-model")
        monkeypatch.setenv("OPENAI_BASE_URL", "http://env-api")

        config_data = {
            "llm": {"model_name": "yaml-model", "api_base": "http://yaml-api"},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = load_config(str(config_file))
        assert cfg.llm.model_name == "env-model"
        assert cfg.llm.api_base == "http://env-api"

    def test_cli_override(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-key")

        config_data = {
            "llm": {"model_name": "yaml-model", "api_base": "http://yaml-api"},
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))

        cfg = load_config(str(config_file), model_name="cli-model")
        assert cfg.llm.model_name == "cli-model"
