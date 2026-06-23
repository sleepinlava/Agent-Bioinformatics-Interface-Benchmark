"""Tests for abi_bridge.py — real ABI CLI integration."""

import json
import os
import sys
from pathlib import Path

import pytest

# Ensure bench/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bench"))
from bench.harness.abi_bridge import (
    ABI_TOOL_MAP,
    ABIToolMapping,
    ABIEnvelope,
    parse_envelope,
    resolve_tool,
    available_tools,
    diagnose_setup,
)


class TestABIToolMapping:
    def test_all_15_tools_registered(self):
        assert len(ABI_TOOL_MAP) == 15

    def test_resolve_known_tool(self):
        m = resolve_tool("abi_list_types")
        assert m is not None
        assert m.tool_name == "abi_list_types"
        assert m.permission == "read_only"

    def test_resolve_unknown_tool(self):
        assert resolve_tool("nonexistent_tool") is None

    def test_abi_plan_is_planning_write(self):
        m = resolve_tool("abi_plan")
        assert m.permission == "planning_write"

    def test_abi_run_is_execution(self):
        m = resolve_tool("abi_run")
        assert m.permission == "execution"

    def test_abi_query_subcommand(self):
        m = resolve_tool("abi_query")
        assert "query" in m.subcommand
        assert "{analysis_type}" in " ".join(m.subcommand)
        assert "{what}" in " ".join(m.subcommand)

    def test_abi_query_is_read_only(self):
        m = resolve_tool("abi_query")
        assert m.permission == "read_only"


class TestParseEnvelope:
    def test_success_envelope(self):
        raw = json.dumps({"status": "success", "command": "list_types", "result": {"types": ["a", "b"]}})
        env = parse_envelope(raw)
        assert env.status == "success"
        assert env.command == "list_types"

    def test_error_envelope(self):
        raw = json.dumps({
            "status": "error", "command": "plan",
            "error_code": "missing_input", "error": "Cannot find input file",
            "diagnostic_hints": [{"severity": "error", "code": "missing_input"}],
        })
        env = parse_envelope(raw)
        assert env.status == "error"
        assert env.error_code == "missing_input"
        assert len(env.diagnostic_hints) == 1

    def test_confirmation_required_envelope(self):
        raw = json.dumps({"status": "confirmation_required", "command": "run", "result": {}})
        env = parse_envelope(raw)
        assert env.status == "confirmation_required"

    def test_invalid_json(self):
        env = parse_envelope("not json at all")
        assert env.status == "error"
        assert env.error_code == "parse_failed"

    def test_missing_status_field(self):
        env = parse_envelope(json.dumps({"result": "ok"}))
        assert env.status == "error"


class TestAvailableTools:
    def test_returns_list(self):
        tools = available_tools()
        assert isinstance(tools, list)
        assert "abi_list_types" in tools
        assert "abi_query" in tools


class TestDiagnoseSetup:
    def test_returns_dict(self):
        d = diagnose_setup()
        assert isinstance(d, dict)
        assert "use_real_abi" in d
        assert "abi_bin" in d
        assert "available_tools" in d
        assert "tool_count" in d
        assert d["tool_count"] == 15


class TestUseRealAbiFlag:
    def test_defaults_to_false(self, monkeypatch):
        monkeypatch.delenv("ABI_BENCH_USE_REAL_ABI", raising=False)
        from bench.harness.abi_bridge import use_real_abi
        assert use_real_abi() is False

    def test_true_enables(self, monkeypatch):
        monkeypatch.setenv("ABI_BENCH_USE_REAL_ABI", "true")
        from bench.harness.abi_bridge import use_real_abi
        assert use_real_abi() is True

    def test_one_enables(self, monkeypatch):
        monkeypatch.setenv("ABI_BENCH_USE_REAL_ABI", "1")
        from bench.harness.abi_bridge import use_real_abi
        assert use_real_abi() is True
