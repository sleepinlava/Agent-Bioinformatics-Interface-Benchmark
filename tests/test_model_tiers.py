"""Tests for model tier loading from bench/model_tiers.yaml."""

import tempfile
from pathlib import Path

import yaml

from bench.harness.run_multi_model import _load_model_tiers as _load_tiers_multi
from bench.scoring.compute_statistics import _load_model_tier_map as _load_tier_map


class TestLoadModelTiers:
    """Test YAML-based and fallback tier loading."""

    def test_loads_from_yaml_file(self):
        """Loading from a valid YAML file returns the expected tiers."""
        yaml_content = {
            "tiers": {
                "strong": {"description": "top models", "models": ["m1", "m2"]},
                "weak": {"description": "small models", "models": ["m3"]},
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            f.flush()
            result = _load_tiers_multi(Path(f.name))
        Path(f.name).unlink()

        assert "strong" in result
        assert "weak" in result
        assert "all" in result
        assert result["strong"]["models"] == ["m1", "m2"]
        assert result["weak"]["models"] == ["m3"]
        assert set(result["all"]["models"]) == {"m1", "m2", "m3"}

    def test_fallback_when_yaml_missing(self):
        """When the YAML file is missing, the built-in fallback is used."""
        result = _load_tiers_multi(Path("/nonexistent/model_tiers.yaml"))
        assert "strong" in result
        assert "medium" in result
        assert "weak" in result
        assert "all" in result
        assert "gpt-4o" in result["strong"]["models"]
        assert "qwen2.5-7b" in result["weak"]["models"]

    def test_fallback_when_yaml_corrupt(self):
        """When the YAML is malformed, fallback to built-in."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("{{{ bad yaml [[[\n")
            f.flush()
            result = _load_tiers_multi(Path(f.name))
        Path(f.name).unlink()

        assert "strong" in result
        assert "gpt-4o" in result["strong"]["models"]

    def test_custom_model_in_yaml_is_recognized(self):
        """A user-added model in the YAML appears in the tier."""
        yaml_content = {
            "tiers": {
                "strong": {"models": ["gpt-4o"]},
                "custom_tier": {"description": "my models", "models": ["my-local-model:7b"]},
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            f.flush()
            result = _load_tiers_multi(Path(f.name))
        Path(f.name).unlink()

        assert "custom_tier" in result
        assert "my-local-model:7b" in result["custom_tier"]["models"]
        assert "my-local-model:7b" in result["all"]["models"]


class TestLoadModelTierMap:
    """Test model→tier mapping for scaffolding analysis."""

    def test_loads_flat_map_from_yaml(self):
        """The tier map is a flat {model: tier} dict."""
        yaml_content = {
            "tiers": {
                "strong": {"models": ["m1", "m2"]},
                "weak": {"models": ["m3"]},
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(yaml_content, f)
            f.flush()
            result = _load_tier_map(Path(f.name))
        Path(f.name).unlink()

        assert result == {"m1": "strong", "m2": "strong", "m3": "weak"}

    def test_fallback_when_yaml_missing(self):
        """Missing YAML falls back to built-in map."""
        result = _load_tier_map(Path("/nonexistent/model_tiers.yaml"))
        assert result.get("gpt-4o") == "strong"
        assert result.get("qwen2.5-7b") == "weak"
        assert result.get("nonexistent-model") is None

    def test_empty_yaml_falls_back(self):
        """Empty YAML (no tiers) falls back to built-in."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("tiers: {}\n")
            f.flush()
            result = _load_tier_map(Path(f.name))
        Path(f.name).unlink()

        assert result.get("gpt-4o") == "strong"
