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


class TestAnthropicMessageConversion:
    """Tests for _openai_messages_to_anthropic."""

    def test_simple_user_message(self):
        """User with string content becomes text content block."""
        from direct_agent import _openai_messages_to_anthropic

        messages = [{"role": "user", "content": "Hello, world!"}]
        result = _openai_messages_to_anthropic(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == [{"type": "text", "text": "Hello, world!"}]

    def test_system_message_skipped(self):
        """System messages are excluded from the converted list."""
        from direct_agent import _openai_messages_to_anthropic

        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hi"},
        ]
        result = _openai_messages_to_anthropic(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_assistant_with_tool_calls_openai_format(self):
        """Assistant with OpenAI-format tool_calls becomes tool_use blocks."""
        from direct_agent import _openai_messages_to_anthropic

        messages = [{
            "role": "assistant",
            "content": "Let me check that.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": '{"command": "ls"}',
                    },
                },
                {
                    "id": "call_2",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "config.yaml"}',
                    },
                },
            ],
        }]
        result = _openai_messages_to_anthropic(messages)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        blocks = result[0]["content"]
        assert len(blocks) == 3  # text + 2 tool_use

        assert blocks[0]["type"] == "text"
        assert blocks[0]["text"] == "Let me check that."

        assert blocks[1]["type"] == "tool_use"
        assert blocks[1]["id"] == "call_1"
        assert blocks[1]["name"] == "bash"
        assert blocks[1]["input"] == {"command": "ls"}

        assert blocks[2]["type"] == "tool_use"
        assert blocks[2]["id"] == "call_2"
        assert blocks[2]["name"] == "read_file"
        assert blocks[2]["input"] == {"path": "config.yaml"}

    def test_assistant_with_tool_calls_unified_format(self):
        """Assistant with Anthropic-unified tool_calls becomes tool_use blocks."""
        from direct_agent import _openai_messages_to_anthropic

        messages = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "name": "bash", "arguments": {"command": "ls"}},
            ],
        }]
        result = _openai_messages_to_anthropic(messages)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        blocks = result[0]["content"]
        assert len(blocks) == 1  # no text, just tool_use
        assert blocks[0]["type"] == "tool_use"
        assert blocks[0]["name"] == "bash"
        assert blocks[0]["input"] == {"command": "ls"}

    def test_tool_message_converts_to_user_tool_result(self):
        """Tool role becomes user role with tool_result block."""
        from direct_agent import _openai_messages_to_anthropic

        messages = [{"role": "tool", "tool_call_id": "call_1", "content": "file contents"}]
        result = _openai_messages_to_anthropic(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["content"] == [{
            "type": "tool_result",
            "tool_use_id": "call_1",
            "content": "file contents",
        }]

    def test_multiple_tool_messages_merge_into_one_user_message(self):
        """Consecutive tool messages merge into a single user message."""
        from direct_agent import _openai_messages_to_anthropic

        messages = [
            {"role": "tool", "tool_call_id": "call_1", "content": "result 1"},
            {"role": "tool", "tool_call_id": "call_2", "content": "result 2"},
            {"role": "tool", "tool_call_id": "call_3", "content": "result 3"},
        ]
        result = _openai_messages_to_anthropic(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        blocks = result[0]["content"]
        assert len(blocks) == 3
        assert blocks[0]["tool_use_id"] == "call_1"
        assert blocks[1]["tool_use_id"] == "call_2"
        assert blocks[2]["tool_use_id"] == "call_3"

    def test_full_multi_turn_conversation(self):
        """A complete multi-turn conversation with tool usage."""
        from direct_agent import _openai_messages_to_anthropic

        messages = [
            {"role": "system", "content": "You are an agent."},
            {"role": "user", "content": "Plan a workflow."},
            {
                "role": "assistant",
                "content": "I will check the config.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "config.yaml"}'},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "analysis_type: metagenomic_plasmid"},
            {
                "role": "assistant",
                "content": "Config loaded. Let me plan.",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "bash", "arguments": '{"command": "abi plan"}'},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "call_2", "content": "Plan created."},
            {"role": "assistant", "content": "The plan is ready."},
        ]
        result = _openai_messages_to_anthropic(messages)

        # Should be: user, assistant, user (tool results), assistant, user (tool result), assistant
        assert len(result) == 6

        assert result[0]["role"] == "user"
        assert result[0]["content"][0]["text"] == "Plan a workflow."

        assert result[1]["role"] == "assistant"
        assert result[1]["content"][1]["type"] == "tool_use"
        assert result[1]["content"][1]["name"] == "read_file"

        assert result[2]["role"] == "user"
        assert result[2]["content"][0]["type"] == "tool_result"

        assert result[3]["role"] == "assistant"
        assert result[3]["content"][1]["type"] == "tool_use"

        assert result[4]["role"] == "user"
        assert result[4]["content"][0]["type"] == "tool_result"

        assert result[5]["role"] == "assistant"
        assert result[5]["content"][0]["type"] == "text"
        assert result[5]["content"][0]["text"] == "The plan is ready."

    def test_empty_content_handled(self):
        """Empty or missing content fields produce valid blocks."""
        from direct_agent import _openai_messages_to_anthropic

        messages = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "name": "bash", "arguments": {}},
            ]},
            {"role": "tool", "tool_call_id": "c1", "content": ""},
        ]
        result = _openai_messages_to_anthropic(messages)

        assert len(result) == 3
        assert result[0]["content"][0]["text"] == ""
        assert result[2]["content"][0]["content"] == ""

    def test_assistant_without_tool_calls(self):
        """Assistant message with only text, no tool_calls."""
        from direct_agent import _openai_messages_to_anthropic

        messages = [{"role": "assistant", "content": "Here is the answer."}]
        result = _openai_messages_to_anthropic(messages)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == [{"type": "text", "text": "Here is the answer."}]


class TestGoogleMessageConversion:
    """Tests for _openai_messages_to_google."""

    def test_simple_user_message(self):
        """User message becomes user role with text part."""
        from direct_agent import _openai_messages_to_google

        messages = [{"role": "user", "content": "Hello!"}]
        result = _openai_messages_to_google(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert result[0]["parts"] == [{"text": "Hello!"}]

    def test_system_message_skipped(self):
        """System messages are excluded."""
        from direct_agent import _openai_messages_to_google

        messages = [
            {"role": "system", "content": "System prompt."},
            {"role": "user", "content": "Hi"},
        ]
        result = _openai_messages_to_google(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"

    def test_assistant_with_tool_calls_openai_format(self):
        """Assistant with tool_calls becomes model role with function_call parts."""
        from direct_agent import _openai_messages_to_google

        messages = [{
            "role": "assistant",
            "content": "Running command.",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": '{"command": "ls"}',
                    },
                },
            ],
        }]
        result = _openai_messages_to_google(messages)

        assert len(result) == 1
        assert result[0]["role"] == "model"
        parts = result[0]["parts"]
        assert len(parts) == 2  # text + function_call
        assert parts[0] == {"text": "Running command."}
        assert parts[1] == {
            "function_call": {"name": "bash", "args": {"command": "ls"}},
        }

    def test_assistant_with_tool_calls_unified_format(self):
        """Assistant with unified-format tool_calls becomes function_call parts."""
        from direct_agent import _openai_messages_to_google

        messages = [{
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1", "name": "bash", "arguments": {"command": "ls"}},
            ],
        }]
        result = _openai_messages_to_google(messages)

        assert len(result) == 1
        assert result[0]["role"] == "model"
        parts = result[0]["parts"]
        assert len(parts) == 1  # just function_call, no text
        assert parts[0] == {
            "function_call": {"name": "bash", "args": {"command": "ls"}},
        }

    def test_tool_message_with_known_call_id(self):
        """Tool message with a call_id seen earlier gets function_response."""
        from direct_agent import _openai_messages_to_google

        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "call_1", "name": "bash", "arguments": {"command": "ls"}},
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "file1 file2"},
        ]
        result = _openai_messages_to_google(messages)

        assert len(result) == 2
        assert result[1]["role"] == "user"
        assert result[1]["parts"] == [{
            "function_response": {
                "name": "bash",
                "response": {"content": "file1 file2"},
            },
        }]

    def test_tool_message_with_unknown_call_id(self):
        """Tool message with no prior call_id falls back to 'unknown' name."""
        from direct_agent import _openai_messages_to_google

        messages = [
            {"role": "tool", "tool_call_id": "nonexistent", "content": "result"},
        ]
        result = _openai_messages_to_google(messages)

        assert len(result) == 1
        assert result[0]["parts"][0]["function_response"]["name"] == "unknown"

    def test_full_multi_turn_conversation(self):
        """Complete multi-turn conversation with tool usage."""
        from direct_agent import _openai_messages_to_google

        messages = [
            {"role": "system", "content": "You are an agent."},
            {"role": "user", "content": "Plan a workflow."},
            {
                "role": "assistant",
                "content": "Let me check.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path": "c.yaml"}'},
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "call_1", "content": "data"},
            {"role": "assistant", "content": "Done."},
        ]
        result = _openai_messages_to_google(messages)

        assert len(result) == 4  # user, model, user (tool_result), model
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "model"
        assert result[2]["role"] == "user"
        assert result[3]["role"] == "model"

        # Verify function_response name lookup worked
        assert result[2]["parts"][0]["function_response"]["name"] == "read_file"

    def test_empty_content_handled(self):
        """Empty content produces valid parts."""
        from direct_agent import _openai_messages_to_google

        messages = [
            {"role": "user", "content": ""},
            {"role": "tool", "tool_call_id": "c1", "content": ""},
        ]
        result = _openai_messages_to_google(messages)

        assert len(result) == 2
        assert result[0]["parts"] == [{"text": ""}]
        assert result[1]["parts"][0]["function_response"]["response"]["content"] == ""
