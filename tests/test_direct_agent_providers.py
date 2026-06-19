"""Tests for multi-provider support in direct_agent.py."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench", "harness"))
from config import BenchConfig, Provider


class TestProviderRouting:
    def test_config_supports_anthropic_provider(self):
        config = BenchConfig(
            provider=Provider.ANTHROPIC,
            api_key="test-key",
            model="claude-sonnet-4-6",
        )
        assert config.provider == Provider.ANTHROPIC
        assert config.is_anthropic is True

    def test_config_supports_google_provider(self):
        config = BenchConfig(
            provider=Provider.GOOGLE,
            api_key="test-key",
            model="gemini-2.5-flash",
        )
        assert config.provider == Provider.GOOGLE
        assert config.is_google is True

    def test_config_supports_openai_compatible(self):
        config = BenchConfig(
            provider=Provider.OPENAI_COMPATIBLE,
            api_key="test-key",
            model="llama3.1:8b",
            api_base="http://localhost:11434/v1",
        )
        assert config.provider == Provider.OPENAI_COMPATIBLE


class TestAnthropicToolConversion:
    def test_openai_tool_schema_converts_to_anthropic(self):
        """Verify OpenAI-format tool schemas convert to Anthropic format."""
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "bash",
                    "description": "Run a shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string"}
                        },
                        "required": ["command"],
                    },
                },
            }
        ]
        from direct_agent import _openai_tools_to_anthropic
        anthropic_tools = _openai_tools_to_anthropic(openai_tools)

        assert len(anthropic_tools) == 1
        assert anthropic_tools[0]["name"] == "bash"
        assert anthropic_tools[0]["input_schema"]["type"] == "object"

    def test_anthropic_response_converts_to_unified(self):
        """Verify Anthropic response blocks convert to unified format."""
        from direct_agent import _anthropic_response_to_unified
        anthropic_block = type("obj", (object,), {
            "type": "tool_use",
            "id": "tool_001",
            "name": "bash",
            "input": {"command": "ls"},
        })()

        unified = _anthropic_response_to_unified([anthropic_block])

        assert len(unified) == 1
        assert unified[0]["name"] == "bash"
        assert unified[0]["arguments"] == {"command": "ls"}
