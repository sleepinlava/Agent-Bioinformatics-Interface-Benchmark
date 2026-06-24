"""Canonical benchmark metadata shared by runners and scorers."""

from pathlib import Path

import yaml

SPEC_PATH = Path(__file__).resolve().parent / "BENCHMARK_SPEC.yaml"


def _load_version() -> str:
    try:
        with open(SPEC_PATH) as f:
            return str((yaml.safe_load(f) or {}).get("benchmark", {}).get("version", "unknown"))
    except (OSError, yaml.YAMLError):
        return "unknown"


BENCHMARK_NAME = "ABI-Bench"
BENCHMARK_VERSION = _load_version()
