#!/usr/bin/env python3
"""
ABI-Bench v0.7 — Real ABI CLI Bridge.

Provides an adapter that calls the **real** ``abi`` CLI (from the ABI project at
``/home/bker/abi/``) instead of the simulated ``abi_cli.py``.  The bridge is
activated by setting the environment variable ``ABI_BENCH_USE_REAL_ABI=true``.

When real ABI is unavailable the bridge falls back gracefully — it returns
structured error envelopes so the agent can adapt, and the benchmark harness
can detect the fallback in scoring metadata.

Architecture::

    G3 Agent (direct_agent.py)
        │
        ├─ ABI_BENCH_USE_REAL_ABI=false (default)
        │     → abi_cli.py  (simulated, always available)
        │
        └─ ABI_BENCH_USE_REAL_ABI=true
              → abi_bridge.py  →  real ``abi`` CLI  →  JSON envelope
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ABI_PROJECT_ROOT = Path("/home/bker/abi")

# ── Env var ──────────────────────────────────────────────────────────────────

ENV_USE_REAL_ABI = "ABI_BENCH_USE_REAL_ABI"
ENV_ABI_BIN = "ABI_BENCH_ABI_BIN"  # Optional: path to ``abi`` executable


def use_real_abi() -> bool:
    """Return True if the real ABI CLI should be used."""
    return os.environ.get(ENV_USE_REAL_ABI, "").strip().lower() in ("true", "1", "yes")


def _find_abi_bin() -> str | None:
    """Locate the real ``abi`` executable.  Returns None if not found."""
    # 1. Explicit override
    explicit = os.environ.get(ENV_ABI_BIN, "").strip()
    if explicit:
        return explicit if Path(explicit).exists() else None

    # 2. In PATH
    found = shutil.which("abi")
    if found:
        return found

    # 3. Editable install: check the project's venv/bin/abi
    candidates = [
        ABI_PROJECT_ROOT / ".venv" / "bin" / "abi",
        ABI_PROJECT_ROOT / "venv" / "bin" / "abi",
        Path(sys.prefix) / "bin" / "abi",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return None


# ── Tool → CLI mapping ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class ABIToolMapping:
    """Maps a benchmark tool name to a real ``abi`` CLI invocation."""

    tool_name: str
    subcommand: list[str]  # e.g. ["list-types", "--output-json"]
    permission: str = "read_only"  # read_only | planning_write | execution


# Canonical mapping from benchmark agent-tool names to real ABI CLI commands.
# Each entry specifies the subcommand argv (after ``abi``) and the permission level.
ABI_TOOL_MAP: Dict[str, ABIToolMapping] = {
    "abi_list_types": ABIToolMapping(
        "abi_list_types",
        ["list-types", "--output-json"],
        "read_only",
    ),
    "abi_plan": ABIToolMapping(
        "abi_plan",
        ["plan", "--type", "{analysis_type}", "--output-json"],
        "planning_write",
    ),
    "abi_check": ABIToolMapping(
        "abi_check",
        ["check", "--type", "{analysis_type}", "--output-json"],
        "read_only",
    ),
    "abi_dry_run": ABIToolMapping(
        "abi_dry_run",
        ["dry-run", "--type", "{analysis_type}", "--output-json"],
        "planning_write",
    ),
    "abi_inspect": ABIToolMapping(
        "abi_inspect",
        ["inspect", "--result-dir", "{result_dir}", "--output-json"],
        "read_only",
    ),
    "abi_report": ABIToolMapping(
        "abi_report",
        ["report", "--result-dir", "{result_dir}", "--type", "{analysis_type}", "--output-json"],
        "planning_write",
    ),
    "abi_run": ABIToolMapping(
        "abi_run",
        ["run", "--type", "{analysis_type}", "--engine", "local", "--output-json"],
        "execution",
    ),
    "abi_query": ABIToolMapping(
        "abi_query",
        ["query", "--type", "{analysis_type}", "--what", "{what}", "--output-json"],
        "read_only",
    ),
    "abi_doctor_agent": ABIToolMapping(
        "abi_doctor_agent",
        ["doctor-agent", "--type", "{analysis_type}", "--output-json"],
        "read_only",
    ),
    "abi_check_resources": ABIToolMapping(
        "abi_check_resources",
        ["check-resources", "--type", "{analysis_type}", "--output-json"],
        "read_only",
    ),
    "abi_setup_resources": ABIToolMapping(
        "abi_setup_resources",
        ["setup-resources", "--type", "{analysis_type}", "--dry-run", "--output-json"],
        "planning_write",
    ),
    "abi_export_nextflow": ABIToolMapping(
        "abi_export_nextflow",
        ["export-nextflow", "--type", "{analysis_type}", "--output-json"],
        "planning_write",
    ),
    "abi_export_tools": ABIToolMapping(
        "abi_export_tools",
        ["export-tools", "--type", "{analysis_type}", "--format", "openai", "--output-json"],
        "read_only",
    ),
    "abi_validate_result": ABIToolMapping(
        "abi_validate_result",
        ["validate-result", "--result-dir", "{result_dir}", "--output-json"],
        "read_only",
    ),
    "abi_contract_lint": ABIToolMapping(
        "abi_contract_lint",
        ["contract-lint", "--type", "{analysis_type}", "--output-json"],
        "read_only",
    ),
}


def resolve_tool(tool_name: str) -> ABIToolMapping | None:
    """Return the CLI mapping for *tool_name* or None if unknown."""
    return ABI_TOOL_MAP.get(tool_name)


# ── JSON envelope parsing ────────────────────────────────────────────────────

@dataclass
class ABIEnvelope:
    """Parsed ABI JSON envelope (three-status contract)."""

    status: str  # "success" | "confirmation_required" | "error"
    raw: dict = field(default_factory=dict)
    command: str = ""
    error_code: str = ""
    error: str = ""
    diagnostic_hints: list = field(default_factory=list)


def parse_envelope(raw_stdout: str) -> ABIEnvelope:
    """Parse the three-status JSON envelope emitted by ``abi --output-json``."""
    try:
        data = json.loads(raw_stdout)
    except (json.JSONDecodeError, TypeError):
        return ABIEnvelope(
            status="error",
            error_code="parse_failed",
            error=f"Failed to parse ABI output as JSON: {raw_stdout[:200]}",
        )

    status = data.get("status", "error")
    return ABIEnvelope(
        status=status,
        raw=data,
        command=data.get("command", ""),
        error_code=data.get("error_code", ""),
        error=data.get("error", ""),
        diagnostic_hints=data.get("diagnostic_hints", []),
    )


# ── Command execution ────────────────────────────────────────────────────────

def run_abi_command(
    tool_name: str,
    args: dict | None = None,
    *,
    workspace: str | Path | None = None,
    timeout: int = 120,
) -> ABIEnvelope:
    """Execute a real ``abi`` CLI command and return the parsed envelope.

    Parameters
    ----------
    tool_name:
        The benchmark tool name (e.g. ``"abi_list_types"``).
    args:
        Template arguments to substitute into the command (e.g. ``analysis_type``,
        ``result_dir``, ``what``).  Unrecognised keys are silently ignored.
    workspace:
        If given, the command working directory is set to this path.
    timeout:
        Subprocess timeout in seconds.

    Returns
    -------
    ABIEnvelope
        Always returns a parsed envelope — errors are captured, not raised.
    """
    mapping = resolve_tool(tool_name)
    if mapping is None:
        return ABIEnvelope(
            status="error",
            error_code="unknown_tool",
            error=f"Unknown ABI tool: {tool_name}",
        )

    abi_bin = _find_abi_bin()
    if abi_bin is None:
        return ABIEnvelope(
            status="error",
            error_code="abi_not_found",
            error=(
                "Real ABI CLI is not installed or not on PATH. "
                "Install with: pip install -e /home/bker/abi  or set ABI_BENCH_ABI_BIN. "
                "To use the simulated CLI instead, unset ABI_BENCH_USE_REAL_ABI."
            ),
        )

    # Build argv with template substitution
    params = args or {}
    # Always inject workspace-relative paths
    if workspace is not None:
        params.setdefault("config_path", str(Path(workspace) / "config.yaml"))
        params.setdefault("sample_sheet", str(Path(workspace) / "sample_sheet.tsv"))
        params.setdefault("outdir", str(Path(workspace)))
        params.setdefault("result_dir", str(Path(workspace)))

    argv: list[str] = [abi_bin]
    for token in mapping.subcommand:
        # Simple {placeholder} substitution
        for key, value in params.items():
            placeholder = "{" + key + "}"
            if placeholder in token:
                token = token.replace(placeholder, str(value))
        argv.append(token)

    # Execute
    try:
        cwd = Path(workspace) if workspace else None
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env={**os.environ, "PATH": os.environ.get("PATH", "")},
        )
    except subprocess.TimeoutExpired:
        return ABIEnvelope(
            status="error",
            error_code="timeout",
            error=f"ABI command timed out after {timeout}s: {' '.join(argv)}",
        )
    except OSError as exc:
        return ABIEnvelope(
            status="error",
            error_code="os_error",
            error=f"Cannot execute ABI: {exc}",
        )

    # Parse output
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if not stdout and stderr:
        # CLI wrote to stderr but not stdout — treat as error
        return ABIEnvelope(
            status="error",
            error_code="empty_output",
            error=f"ABI produced no stdout. stderr: {stderr[:500]}",
        )

    envelope = parse_envelope(stdout)

    # Attach stderr to diagnostic hints for debugging
    if stderr and envelope.diagnostic_hints is not None:
        envelope.diagnostic_hints.append({"source": "stderr", "text": stderr[:1000]})

    return envelope


# ── Convenience helpers ──────────────────────────────────────────────────────

def abi_is_available() -> bool:
    """Check whether the real ABI CLI is callable."""
    return _find_abi_bin() is not None


def available_tools() -> list[str]:
    """Return the list of tool names supported by this bridge."""
    return list(ABI_TOOL_MAP.keys())


def diagnose_setup() -> dict:
    """Return diagnostic information about the ABI bridge configuration."""
    return {
        "use_real_abi": use_real_abi(),
        "abi_bin": _find_abi_bin(),
        "abi_project_root": str(ABI_PROJECT_ROOT),
        "available_tools": available_tools(),
        "tool_count": len(ABI_TOOL_MAP),
    }


# ── CLI for standalone testing ───────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ABI-Bench Real ABI Bridge")
    parser.add_argument("--diagnose", action="store_true", help="Print bridge diagnostics")
    parser.add_argument("--tool", type=str, help="Execute a single tool (e.g. abi_list_types)")
    parser.add_argument("--analysis-type", type=str, default="metagenomic_plasmid")
    parser.add_argument("--workspace", type=str, default=None)
    parser.add_argument("--result-dir", type=str, default=None)
    parser.add_argument("--what", type=str, default="stages",
                        help="Query target (for abi_query)")
    args = parser.parse_args()

    if args.diagnose:
        print(json.dumps(diagnose_setup(), indent=2))
    elif args.tool:
        params: dict[str, str] = {
            "analysis_type": args.analysis_type,
            "what": args.what,
        }
        if args.workspace:
            params["workspace"] = args.workspace
            params["result_dir"] = args.workspace
        if args.result_dir:
            params["result_dir"] = args.result_dir

        envelope = run_abi_command(args.tool, params, workspace=args.workspace)
        print(json.dumps(envelope.raw, indent=2))
    else:
        parser.print_help()
