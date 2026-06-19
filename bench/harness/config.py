"""
ABI-Bench v0.5 — Centralised configuration module.

Single source of truth for all ``ABI_BENCH_*`` environment variables.
Precedence: **os.environ > .env file > hardcoded default**.

Usage::

    from bench.harness.config import load_bench_config, validate_config

    config = load_bench_config(Path("bench/.env"))
    for warning in validate_config(config):
        print(f"WARNING: {warning}")
    client = OpenAI(api_key=config.api_key, base_url=config.api_base)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List


class Provider(Enum):
    """Supported LLM providers and their SDK routing."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    GLM = "glm"
    KIMI = "kimi"
    MIMO = "mimo"
    OPENAI_COMPATIBLE = "openai-compatible"

# ── Env var names (canonical constants) ─────────────────────────────────────

ENV_API_KEY = "ABI_BENCH_API_KEY"
ENV_API_BASE = "ABI_BENCH_API_BASE"
ENV_MODEL = "ABI_BENCH_MODEL"
ENV_MAX_TOKENS = "ABI_BENCH_MAX_TOKENS"
ENV_TEMPERATURE = "ABI_BENCH_TEMPERATURE"
ENV_MAX_RETRIES = "ABI_BENCH_MAX_RETRIES"
ENV_RETRY_BASE_DELAY = "ABI_BENCH_RETRY_BASE_DELAY"
ENV_RETRY_MAX_DELAY = "ABI_BENCH_RETRY_MAX_DELAY"
ENV_PROVIDER = "ABI_BENCH_PROVIDER"
ENV_REASONING = "ABI_BENCH_REASONING"
ENV_THINKING_BUDGET = "ABI_BENCH_THINKING_BUDGET"
ENV_REASONING_EFFORT = "ABI_BENCH_REASONING_EFFORT"


@dataclass
class BenchConfig:
    """Typed configuration container for ABI-Bench agent runs."""

    api_key: str = ""
    api_base: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    max_tokens: int = 8000
    temperature: float = 0.0
    max_retries: int = 3
    retry_base_delay_seconds: float = 2.0
    retry_max_delay_seconds: float = 60.0

    # Provider routing (v0.6: multi-provider native SDK support)
    provider: Provider = Provider.DEEPSEEK
    reasoning: bool = False
    thinking_budget: int = 0
    reasoning_effort: str = ""

    @property
    def is_anthropic(self) -> bool:
        return self.provider == Provider.ANTHROPIC

    @property
    def is_google(self) -> bool:
        return self.provider == Provider.GOOGLE

    @property
    def uses_openai_sdk(self) -> bool:
        return self.provider in (
            Provider.OPENAI, Provider.DEEPSEEK, Provider.QWEN,
            Provider.GLM, Provider.KIMI, Provider.MIMO,
            Provider.OPENAI_COMPATIBLE,
        )


# ── Dotenv loader ───────────────────────────────────────────────────────────

def load_dotenv(path: str | Path) -> dict:
    """Load key=value pairs from a dotenv file into a dict.

    Returns an empty dict if the file does not exist or cannot be read.
    Does **not** mutate ``os.environ`` — callers decide how to merge.
    """
    result: dict = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'").strip('"')
                    if key not in result:
                        result[key] = value
    except OSError:
        pass
    return result


# ── Provider resolution ────────────────────────────────────────────────────

def _resolve_provider(raw: str) -> Provider:
    """Map a raw env/dotenv string to a Provider enum member.

    Returns ``Provider.DEEPSEEK`` when *raw* is empty or unrecognised.
    """
    if not raw or not raw.strip():
        return Provider.DEEPSEEK
    raw_lower = raw.strip().lower()
    try:
        return Provider(raw_lower)
    except ValueError:
        return Provider.DEEPSEEK


# ── Config loader ───────────────────────────────────────────────────────────

def load_bench_config(dotenv_path: str | Path | None = None) -> BenchConfig:
    """Load the full benchmark configuration.

    Precedence (highest to lowest):
        1. ``os.environ`` (already set in the process)
        2. ``.env`` file at *dotenv_path*
        3. hardcoded defaults

    When *dotenv_path* is ``None``, the file is looked up relative to this
    module: ``{PROJECT_ROOT}/bench/.env``.
    """
    if dotenv_path is None:
        dotenv_path = Path(__file__).resolve().parent.parent / ".env"

    dotenv_vars = load_dotenv(dotenv_path)

    def _get(key: str, default: str = "") -> str:
        """Return *key* from os.environ, dotenv, or *default*."""
        return os.environ.get(key) or dotenv_vars.get(key, default)

    return BenchConfig(
        api_key=_get(ENV_API_KEY, ""),
        api_base=_get(ENV_API_BASE, "https://api.deepseek.com"),
        model=_get(ENV_MODEL, "deepseek-v4-pro"),
        max_tokens=int(_get(ENV_MAX_TOKENS, "8000")),
        temperature=float(_get(ENV_TEMPERATURE, "0.0")),
        max_retries=int(_get(ENV_MAX_RETRIES, "3")),
        retry_base_delay_seconds=float(_get(ENV_RETRY_BASE_DELAY, "2.0")),
        retry_max_delay_seconds=float(_get(ENV_RETRY_MAX_DELAY, "60.0")),
        provider=_resolve_provider(_get(ENV_PROVIDER, "")),
        reasoning=_get(ENV_REASONING, "").lower() == "true",
        thinking_budget=int(_get(ENV_THINKING_BUDGET, "0") or "0"),
        reasoning_effort=_get(ENV_REASONING_EFFORT, ""),
    )


# ── Validation ──────────────────────────────────────────────────────────────

def validate_config(config: BenchConfig) -> List[str]:
    """Return a list of human-readable warnings for suspicious config values.

    These are **non-fatal** — callers should print them but not abort.
    """
    warnings: List[str] = []

    if not config.model or not config.model.strip():
        warnings.append(
            f"{ENV_MODEL} is empty — the API call will fail. "
            f"Set {ENV_MODEL} to a valid model identifier."
        )

    if config.api_base and "://" not in config.api_base:
        warnings.append(
            f"{ENV_API_BASE}='{config.api_base}' is missing a protocol. "
            f"Use 'https://your-endpoint.com/v1' or 'http://localhost:11434/v1'."
        )

    if config.temperature < 0.0 or config.temperature > 2.0:
        warnings.append(
            f"{ENV_TEMPERATURE}={config.temperature} is outside the typical "
            f"range [0.0, 2.0]. Some APIs may reject this value."
        )

    if config.max_tokens < 256:
        warnings.append(
            f"{ENV_MAX_TOKENS}={config.max_tokens} is very low. "
            f"Consider at least 1024 for meaningful benchmark runs."
        )

    if config.provider == Provider.GOOGLE or config.provider == Provider.ANTHROPIC:
        if not config.api_key:
            warnings.append(
                f"{ENV_PROVIDER}='{config.provider.value}' requires {ENV_API_KEY} "
                f"to be set. Native SDK calls will fail without an API key."
            )

    if config.reasoning and not config.thinking_budget and not config.reasoning_effort:
        warnings.append(
            f"{ENV_REASONING}=true but neither {ENV_THINKING_BUDGET} nor "
            f"{ENV_REASONING_EFFORT} is set. Reasoning parameters will not "
            f"be injected into API calls."
        )

    return warnings
