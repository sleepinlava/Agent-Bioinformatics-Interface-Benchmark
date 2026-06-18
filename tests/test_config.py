"""Tests for bench.harness.config — the centralised configuration module."""

import tempfile
from pathlib import Path

from bench.harness.config import (
    ENV_API_BASE,
    ENV_API_KEY,
    ENV_MAX_RETRIES,
    ENV_MAX_TOKENS,
    ENV_MODEL,
    ENV_PROVIDER,
    ENV_REASONING,
    ENV_TEMPERATURE,
    BenchConfig,
    load_bench_config,
    load_dotenv,
    validate_config,
)


class TestLoadDotenv:
    """Tests for the standalone dotenv loader."""

    def test_loads_simple_key_value(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY_ONE=value1\nKEY_TWO=value2\n")
            f.flush()
            result = load_dotenv(f.name)
        Path(f.name).unlink()
        assert result == {"KEY_ONE": "value1", "KEY_TWO": "value2"}

    def test_skips_comments_and_blanks(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("# This is a comment\n\nKEY=val\n  \n")
            f.flush()
            result = load_dotenv(f.name)
        Path(f.name).unlink()
        assert result == {"KEY": "val"}

    def test_strips_quotes(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write('KEY="quoted_value"\n')
            f.flush()
            result = load_dotenv(f.name)
        Path(f.name).unlink()
        assert result == {"KEY": "quoted_value"}

    def test_missing_file_returns_empty(self):
        result = load_dotenv("/nonexistent/path/.env")
        assert result == {}

    def test_first_key_wins_on_duplicate(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("KEY=first\nKEY=second\n")
            f.flush()
            result = load_dotenv(f.name)
        Path(f.name).unlink()
        assert result == {"KEY": "first"}


class TestLoadBenchConfig:
    """Tests for the main config loader with precedence."""

    def test_defaults_when_no_env_or_dotenv(self, monkeypatch):
        """All ABI_BENCH_* vars unset → use hardcoded defaults."""
        for var in [
            ENV_API_KEY, ENV_API_BASE, ENV_MODEL, ENV_MAX_TOKENS,
            ENV_TEMPERATURE, ENV_MAX_RETRIES, ENV_PROVIDER,
            ENV_REASONING,
        ]:
            monkeypatch.delenv(var, raising=False)

        config = load_bench_config("/nonexistent/.env")
        assert config.api_key == ""
        assert config.api_base == "https://api.deepseek.com"
        assert config.model == "deepseek-v4-pro"
        assert config.max_tokens == 8000
        assert config.temperature == 0.0
        assert config.max_retries == 3
        assert config.reasoning is False

    def test_env_overrides_default(self, monkeypatch):
        monkeypatch.setenv(ENV_MODEL, "llama-3.1-8b")
        monkeypatch.setenv(ENV_TEMPERATURE, "0.7")
        monkeypatch.delenv(ENV_API_KEY, raising=False)

        config = load_bench_config("/nonexistent/.env")
        assert config.model == "llama-3.1-8b"
        assert config.temperature == 0.7

    def test_env_overrides_dotenv(self, monkeypatch):
        monkeypatch.setenv(ENV_MODEL, "env-model")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(f"{ENV_MODEL}=dotenv-model\n")
            f.flush()
            config = load_bench_config(f.name)
        Path(f.name).unlink()
        assert config.model == "env-model"

    def test_dotenv_overrides_default(self, monkeypatch):
        monkeypatch.delenv(ENV_MODEL, raising=False)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write(f"{ENV_MODEL}=dotenv-model\n{ENV_TEMPERATURE}=0.3\n")
            f.flush()
            config = load_bench_config(f.name)
        Path(f.name).unlink()
        assert config.model == "dotenv-model"
        assert config.temperature == 0.3

    def test_int_conversion(self, monkeypatch):
        monkeypatch.setenv(ENV_MAX_TOKENS, "4096")
        monkeypatch.setenv(ENV_MAX_RETRIES, "5")
        monkeypatch.delenv(ENV_MODEL, raising=False)
        config = load_bench_config("/nonexistent/.env")
        assert config.max_tokens == 4096
        assert config.max_retries == 5

    def test_float_conversion(self, monkeypatch):
        monkeypatch.setenv(ENV_TEMPERATURE, "0.42")
        monkeypatch.delenv(ENV_MODEL, raising=False)
        config = load_bench_config("/nonexistent/.env")
        assert config.temperature == 0.42

    def test_reasoning_true(self, monkeypatch):
        monkeypatch.setenv(ENV_REASONING, "true")
        monkeypatch.delenv(ENV_MODEL, raising=False)
        config = load_bench_config("/nonexistent/.env")
        assert config.reasoning is True


class TestValidateConfig:
    """Tests for config warning generation."""

    def test_valid_config_no_warnings(self):
        config = BenchConfig(model="gpt-4o", api_base="https://api.openai.com/v1")
        assert validate_config(config) == []

    def test_empty_model_warns(self):
        config = BenchConfig(model="")
        warnings = validate_config(config)
        assert any("empty" in w.lower() for w in warnings)

    def test_whitespace_model_warns(self):
        config = BenchConfig(model="   ")
        warnings = validate_config(config)
        assert any("empty" in w.lower() for w in warnings)

    def test_missing_protocol_warns(self):
        config = BenchConfig(model="test", api_base="localhost:8080/v1")
        warnings = validate_config(config)
        assert any("protocol" in w.lower() for w in warnings)

    def test_temperature_out_of_range_warns(self):
        config = BenchConfig(model="test", temperature=5.0)
        warnings = validate_config(config)
        assert any("temperature" in w.lower() for w in warnings)

    def test_low_max_tokens_warns(self):
        config = BenchConfig(model="test", max_tokens=128)
        warnings = validate_config(config)
        assert any("max_tokens" in w.lower() or "low" in w.lower() for w in warnings)

    def test_anthropic_provider_warns(self):
        config = BenchConfig(model="test", provider="anthropic")
        warnings = validate_config(config)
        assert any("openai-compatible" in w.lower() or "sdk" in w.lower() for w in warnings)
