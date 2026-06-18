"""Tests for retry logic in bench.harness.direct_agent.

Uses mocking to simulate API failures without real network calls.
"""

from pathlib import Path
from unittest import mock

from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    RateLimitError,
)

from bench.harness.config import BenchConfig

# ── Helpers ────────────────────────────────────────────────────────────────

def _make_config(**overrides) -> BenchConfig:
    """Build a BenchConfig with defaults suitable for unit testing."""
    defaults = {
        "model": "test-model",
        "api_key": "sk-test",
        "api_base": "https://test.example.com/v1",
        "max_tokens": 1024,
        "temperature": 0.0,
        "max_retries": 2,
        "retry_base_delay_seconds": 0.01,
        "retry_max_delay_seconds": 0.1,
    }
    defaults.update(overrides)
    return BenchConfig(**defaults)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestRetryOnTransientErrors:
    """Retry is triggered on transient / retryable errors."""

    @mock.patch("bench.harness.direct_agent.OpenAI")
    def test_retry_on_connection_error(self, mock_openai):
        """APIConnectionError should trigger retry, then succeed."""
        from bench.harness.direct_agent import run_agent

        mock_client = mock_openai.return_value
        # Fail once, succeed on retry
        mock_client.chat.completions.create.side_effect = [
            APIConnectionError(request=mock.Mock()),
            mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content="final", tool_calls=None))],
                usage=mock.Mock(prompt_tokens=10, completion_tokens=5, completion_tokens_details=None),
            ),
        ]

        with mock.patch("bench.harness.direct_agent.load_bench_config") as mock_cfg:
            mock_cfg.return_value = _make_config()
            with mock.patch("bench.harness.direct_agent.validate_config", return_value=[]):
                with mock.patch("bench.harness.direct_agent.secrets.token_hex", return_value="deadbeef"):
                    with mock.patch("bench.harness.direct_agent.Path.mkdir"):
                        with mock.patch("builtins.open", mock.mock_open()):
                            import tempfile
                            with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as tr:
                                result = run_agent(
                                    workspace=Path(ws),
                                    trace_dir=Path(tr),
                                    group_id="G3",
                                    task_id="T01",
                                    task_prompt="test prompt",
                                    max_steps=3,
                                    max_tokens=1024,
                                )

        # Should have been called twice (fail + retry)
        assert mock_client.chat.completions.create.call_count == 2
        assert result == 0

    @mock.patch("bench.harness.direct_agent.OpenAI")
    def test_retry_on_rate_limit(self, mock_openai):
        """RateLimitError should trigger retry, then succeed."""
        from bench.harness.direct_agent import run_agent

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.side_effect = [
            RateLimitError(message="rate limited", response=mock.Mock(status_code=429), body=None),
            mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content="final", tool_calls=None))],
                usage=mock.Mock(prompt_tokens=10, completion_tokens=5, completion_tokens_details=None),
            ),
        ]

        with mock.patch("bench.harness.direct_agent.load_bench_config") as mock_cfg:
            mock_cfg.return_value = _make_config()
            with mock.patch("bench.harness.direct_agent.validate_config", return_value=[]):
                with mock.patch("bench.harness.direct_agent.secrets.token_hex", return_value="deadbeef"):
                    with mock.patch("bench.harness.direct_agent.Path.mkdir"):
                        with mock.patch("builtins.open", mock.mock_open()):
                            import tempfile
                            with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as tr:
                                result = run_agent(
                                    workspace=Path(ws),
                                    trace_dir=Path(tr),
                                    group_id="G3",
                                    task_id="T01",
                                    task_prompt="test prompt",
                                    max_steps=3,
                                    max_tokens=1024,
                                )

        assert mock_client.chat.completions.create.call_count == 2
        assert result == 0

    @mock.patch("bench.harness.direct_agent.OpenAI")
    def test_retry_on_timeout(self, mock_openai):
        """APITimeoutError should trigger retry."""
        from bench.harness.direct_agent import run_agent

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.side_effect = [
            APITimeoutError(request=mock.Mock()),
            mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content="final", tool_calls=None))],
                usage=mock.Mock(prompt_tokens=10, completion_tokens=5, completion_tokens_details=None),
            ),
        ]

        with mock.patch("bench.harness.direct_agent.load_bench_config") as mock_cfg:
            mock_cfg.return_value = _make_config()
            with mock.patch("bench.harness.direct_agent.validate_config", return_value=[]):
                with mock.patch("bench.harness.direct_agent.secrets.token_hex", return_value="deadbeef"):
                    with mock.patch("bench.harness.direct_agent.Path.mkdir"):
                        with mock.patch("builtins.open", mock.mock_open()):
                            import tempfile
                            with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as tr:
                                result = run_agent(
                                    workspace=Path(ws),
                                    trace_dir=Path(tr),
                                    group_id="G3",
                                    task_id="T01",
                                    task_prompt="test prompt",
                                    max_steps=3,
                                    max_tokens=1024,
                                )

        assert mock_client.chat.completions.create.call_count == 2
        assert result == 0

    @mock.patch("bench.harness.direct_agent.OpenAI")
    def test_retry_on_500_server_error(self, mock_openai):
        """HTTP 500 should trigger retry."""
        from bench.harness.direct_agent import run_agent

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.side_effect = [
            APIStatusError(message="server error", response=mock.Mock(status_code=500), body=None),
            mock.Mock(
                choices=[mock.Mock(message=mock.Mock(content="final", tool_calls=None))],
                usage=mock.Mock(prompt_tokens=10, completion_tokens=5, completion_tokens_details=None),
            ),
        ]

        with mock.patch("bench.harness.direct_agent.load_bench_config") as mock_cfg:
            mock_cfg.return_value = _make_config()
            with mock.patch("bench.harness.direct_agent.validate_config", return_value=[]):
                with mock.patch("bench.harness.direct_agent.secrets.token_hex", return_value="deadbeef"):
                    with mock.patch("bench.harness.direct_agent.Path.mkdir"):
                        with mock.patch("builtins.open", mock.mock_open()):
                            import tempfile
                            with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as tr:
                                result = run_agent(
                                    workspace=Path(ws),
                                    trace_dir=Path(tr),
                                    group_id="G3",
                                    task_id="T01",
                                    task_prompt="test prompt",
                                    max_steps=3,
                                    max_tokens=1024,
                                )

        assert mock_client.chat.completions.create.call_count == 2
        assert result == 0


class TestNoRetryOnPermanentErrors:
    """Authentication and client errors should NOT trigger retry."""

    @mock.patch("bench.harness.direct_agent.OpenAI")
    def test_no_retry_on_authentication_error(self, mock_openai):
        """AuthenticationError should fail immediately."""
        from bench.harness.direct_agent import run_agent

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.side_effect = AuthenticationError(
            message="bad api key", response=mock.Mock(status_code=401), body=None
        )

        with mock.patch("bench.harness.direct_agent.load_bench_config") as mock_cfg:
            mock_cfg.return_value = _make_config()
            with mock.patch("bench.harness.direct_agent.validate_config", return_value=[]):
                with mock.patch("bench.harness.direct_agent.secrets.token_hex", return_value="deadbeef"):
                    with mock.patch("bench.harness.direct_agent.Path.mkdir"):
                        with mock.patch("builtins.open", mock.mock_open()):
                            import tempfile
                            with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as tr:
                                result = run_agent(
                                    workspace=Path(ws),
                                    trace_dir=Path(tr),
                                    group_id="G3",
                                    task_id="T01",
                                    task_prompt="test prompt",
                                    max_steps=3,
                                    max_tokens=1024,
                                )

        # Should only be called once (no retry)
        assert mock_client.chat.completions.create.call_count == 1
        assert result == 0  # Agent returns 0 even on error (writes error trace)

    @mock.patch("bench.harness.direct_agent.OpenAI")
    def test_no_retry_on_400_client_error(self, mock_openai):
        """HTTP 400 should fail immediately (not retried)."""
        from bench.harness.direct_agent import run_agent

        mock_client = mock_openai.return_value
        mock_client.chat.completions.create.side_effect = APIStatusError(
            message="bad request", response=mock.Mock(status_code=400), body=None
        )

        with mock.patch("bench.harness.direct_agent.load_bench_config") as mock_cfg:
            mock_cfg.return_value = _make_config()
            with mock.patch("bench.harness.direct_agent.validate_config", return_value=[]):
                with mock.patch("bench.harness.direct_agent.secrets.token_hex", return_value="deadbeef"):
                    with mock.patch("bench.harness.direct_agent.Path.mkdir"):
                        with mock.patch("builtins.open", mock.mock_open()):
                            import tempfile
                            with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as tr:
                                result = run_agent(
                                    workspace=Path(ws),
                                    trace_dir=Path(tr),
                                    group_id="G3",
                                    task_id="T01",
                                    task_prompt="test prompt",
                                    max_steps=3,
                                    max_tokens=1024,
                                )

        assert mock_client.chat.completions.create.call_count == 1
        assert result == 0  # Agent returns 0 even on error (writes error trace)


class TestMaxRetriesExhausted:
    """When all retries fail, the agent should stop and write an error."""

    @mock.patch("bench.harness.direct_agent.OpenAI")
    def test_all_retries_exhausted(self, mock_openai):
        """After max_retries+1 failures, agent writes error and returns."""
        from bench.harness.direct_agent import run_agent

        mock_client = mock_openai.return_value
        # max_retries=2, so 3 attempts total, all failing
        mock_client.chat.completions.create.side_effect = APIConnectionError(
            request=mock.Mock()
        )

        with mock.patch("bench.harness.direct_agent.load_bench_config") as mock_cfg:
            mock_cfg.return_value = _make_config(max_retries=2)
            with mock.patch("bench.harness.direct_agent.validate_config", return_value=[]):
                with mock.patch("bench.harness.direct_agent.secrets.token_hex", return_value="deadbeef"):
                    with mock.patch("bench.harness.direct_agent.Path.mkdir"):
                        with mock.patch("builtins.open", mock.mock_open()):
                            import tempfile
                            with tempfile.TemporaryDirectory() as ws, tempfile.TemporaryDirectory() as tr:
                                result = run_agent(
                                    workspace=Path(ws),
                                    trace_dir=Path(tr),
                                    group_id="G3",
                                    task_id="T01",
                                    task_prompt="test prompt",
                                    max_steps=3,
                                    max_tokens=1024,
                                )

        assert mock_client.chat.completions.create.call_count == 3
        assert result == 0  # Still returns 0 (error written to trace)
