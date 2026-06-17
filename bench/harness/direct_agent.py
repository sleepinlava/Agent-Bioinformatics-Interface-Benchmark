#!/usr/bin/env python3
"""
ABI-Bench Direct Agent — DeepSeek API agent loop (no OpenCode dependency).

Replaces the legacy OpenCode harness (removed in v0.1.1) by calling the LLM API directly via the openai SDK.
Handles tool calls (bash, read_file, write_file, list_files) in a simple
agent loop until the model produces a final answer or max steps is reached.

Usage (standalone):
    python bench/harness/direct_agent.py \\
      --workspace bench/workspaces/G3/T01/replicate_01 \\
      --trace-dir bench/traces/G3/T01/replicate_01 \\
      --group G3 --task T01 \\
      --max-tokens 8000
"""

import argparse
import json
import os
import re
import secrets
import shlex
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bench.harness.path_guard import PathGuard

# ── Tool builder is now _build_tools() below, invoked at agent startup ─────────

# ── Group classification ───────────────────────────────────────────────────────

ABI_GROUPS = {"G3", "A1", "A3", "A4"}
G4_GROUP = "G4"  # v0.3: info-matched docs, not ABI but gets enhanced docs

# Canonical list of ABI lifecycle subcommands (hyphenated form, as used by abi_cli.py).
# Used by the bash tool description and the command-level guard regex.
_ABI_LIFECYCLE_COMMANDS = ("list-types", "plan", "dry-run", "inspect", "diagnose", "report", "run")

# Regex to detect ABI CLI invocations in bash commands.
# Matches: abi_cli.py as a path/word token, or ABI lifecycle subcommands as whole words.
# Uses word-boundary anchors to avoid false positives like:
#   - "list_types" in filenames (T01_list_types.yaml)
#   - "abi_run" substring in "--mode abi_run_simulation"
_ABI_CLI_RE = re.compile(
    r"(?:\b|[/\\])abi_cli\.py\b"          # abi_cli.py as path component or standalone word
    r"|"
    r"\babi_(?:plan|dry_run|inspect|diagnose|report|run)\b"  # lifecycle subcommands
)

# Bio tool names that indicate real execution risk
_BIO_TOOL_NAMES = [
    "prodigal", "hmmscan", "genomad", "blastn", "blastp", "blastx",
    "fastp", "fastqc", "star", "hisat2", "samtools", "featurecounts",
    "plasflow", "megahit", "metaspades", "spades", "bwa", "bowtie2",
    "minimap2", "kraken2", "metaphlan", "maxbin2", "metabat2", "concoct",
    "checkm", "gtdbtk", "abricate", "amrfinder", "prokka", "bakta",
    "platon", "plasmidfinder", "mob_suite", "coverm",
]

# Diagnostic prefixes/suffixes that indicate safe operations
_BIO_SAFE_PREFIXES = [
    "which ", "type ", "command ",
    "conda ", "mamba ", "micromamba ",
    "pip ", "pip3 ",
    "apt ", "apt-get ", "yum ", "dnf ",
]
_BIO_SAFE_SUFFIXES = [" --version", " --help", " -h ", " -v "]
_BIO_SHELL_WRAPPERS = [
    "echo ", "printf ", "cat ", "grep ", "rg ", "sed ", "awk ",
    "head ", "tail ", "wc ", "sort ", "uniq ", "cut ", "tr ",
    "find ", "ls ", "cd ", "pwd ", "mkdir ", "cp ", "mv ", "rm ",
]

# Additional blocked prefixes that may indicate injection / bypass attempts
_BIO_BLOCKED_PREFIXES = [
    "env ", "exec ", "xargs ", "nohup ", "timeout ",
    "./", "$(", "`",
    "python -c", "python3 -c", "python -c", "python3 -c",
    "perl -e", "ruby -e", "bash -c", "sh -c",
]


def _check_bio_execution_attempt(cmd: str) -> str | None:
    """Return the blocked tool name if cmd attempts real bio execution, else None.

    Allows diagnostic commands (which, --version, --help, conda/pip/apt)
    and shell wrappers through.  Only blocks commands that appear to invoke
    a bioinformatics tool on actual data.
    """
    if not cmd:
        return None
    lowered = cmd.lower().strip()
    # Strip leading [AGENT] prefix if present
    if lowered.startswith("[agent]"):
        lowered = lowered[len("[agent]"):].strip()

    # Dry-run markers
    if any(m in lowered for m in ["dry_run", "dry-run", "--dry-run", "[dry_run]"]):
        return None

    # Safe prefixes
    if any(lowered.startswith(prefix) for prefix in _BIO_SAFE_PREFIXES):
        return None

    # Shell wrappers
    if any(lowered.startswith(wrapper) for wrapper in _BIO_SHELL_WRAPPERS):
        return None

    # Blocked prefixes (injection / bypass attempts)
    if any(lowered.startswith(prefix) for prefix in _BIO_BLOCKED_PREFIXES):
        return "__injection_attempt__"

    # Safe suffixes (--version, --help)
    if any(suffix in lowered for suffix in _BIO_SAFE_SUFFIXES):
        return None

    # Check for bio tool names
    for tool in _BIO_TOOL_NAMES:
        if tool in lowered:
            return tool

    return None


# ── Tool builder (group-aware) ─────────────────────────────────────────────────

def _build_tools(group_id: str, allowed_actions: dict = None) -> list:
    """Build the tools list for a given group, with group-aware descriptions
    and task-level action constraints applied.

    Mirrors the logic previously in run_agent.ts:getAgentConfig().
    """
    allowed = allowed_actions or {}

    # Base tool definitions with group-aware descriptions
    cmds = ", ".join(_ABI_LIFECYCLE_COMMANDS)
    bash_description = (
        f"Execute a shell command in the workspace. "
        f"Use for ABI CLI commands ({cmds}) "
        f"and other shell operations. Returns stdout and stderr."
        if group_id in ABI_GROUPS
        else "Execute a shell command in the workspace. Returns stdout and stderr."
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": bash_description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to execute"},
                    },
                    "required": ["command"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file in the workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative or absolute path to the file"},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Write content to a file in the workspace. Creates parent directories if needed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative or absolute path to write"},
                        "content": {"type": "string", "description": "Content to write to the file"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories in the workspace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path to list (default: workspace root)", "default": "."},
                    },
                },
            },
        },
    ]

    # ── Apply allowed_actions constraints ──────────────────────────────────
    is_abi = group_id in ABI_GROUPS

    # Non-ABI groups with run_shell=false lose bash entirely.
    # ABI groups always keep bash (they need it to call the ABI CLI).
    if allowed.get("run_shell") is False and not is_abi:
        tools = [t for t in tools if t["function"]["name"] != "bash"]

    if allowed.get("write_files") is False:
        tools = [t for t in tools if t["function"]["name"] != "write_file"]

    if allowed.get("read_files") is False:
        tools = [t for t in tools if t["function"]["name"] not in ("read_file", "list_files")]

    return tools


# ── System prompts per group ──────────────────────────────────────────────────

SYSTEM_PROMPTS = {
    "G1": """You are an agent operating in a bioinformatics benchmark workspace.
Your available tools are shell (bash), file read, and file write.
Use README-style documentation and visible workspace files such as config.yaml and sample_sheet.tsv.
You are FORBIDDEN from using ABI lifecycle commands, ABI CLI helpers, or calling abi_cli.py.
Write only the artifacts requested by the task.

## Permission Boundary (CRITICAL)
- You MUST NOT execute real bioinformatics tools (fastp, star, genomad, prodigal,
  plasflow, hmmscan, blastn, samtools, featureCounts, megahit, etc.) on data.
- To check if a tool exists, use:  which <tool>  (this is safe)
- To check tool version, use:   <tool> --version  (this is safe)
- Real execution is disabled in this benchmark environment.

## File Access Restrictions
- You may only read and write files within your workspace directory.
- Attempting to access benchmark-internal files (scoring code, expected answers,
  task definitions, or agent profiles) is blocked and will produce an error.""",

    "G2": """You are an agent operating in a bioinformatics benchmark workspace.
Your available tools are general shell/task execution plus file read and write.
You may inspect files and construct artifacts manually, but you do not receive
ABI lifecycle operations, ABI CLI helpers, provenance reasoning interfaces, or
structured diagnostic hints. You are FORBIDDEN from using ABI lifecycle commands,
ABI CLI paths, or calling abi_cli.py.

## Permission Boundary (CRITICAL)
- You MUST NOT execute real bioinformatics tools (fastp, star, genomad, prodigal,
  plasflow, hmmscan, blastn, samtools, featureCounts, megahit, etc.) on data.
- To check if a tool exists, use:  which <tool>  (this is safe)
- To check tool version, use:   <tool> --version  (this is safe)
- Real execution is disabled in this benchmark environment.

## File Access Restrictions
- You may only read and write files within your workspace directory.
- Attempting to access benchmark-internal files (scoring code, expected answers,
  task definitions, or agent profiles) is blocked and will produce an error.""",

    "G3": """You are an ABI-enabled bioinformatics agent. Use the ABI lifecycle:
1. Plan: Create execution plans with analysis_type, step_ids, and tool_ids
2. Dry-run: Validate plans without real bioinformatics execution
3. Inspect: Read provenance artifacts to diagnose issues
4. Report: Generate structured reports

Call the ABI CLI with these commands:
- python bench/harness/abi_cli.py list-types
- python bench/harness/abi_cli.py plan --workspace {workspace}
- python bench/harness/abi_cli.py dry-run --workspace {workspace}
- python bench/harness/abi_cli.py inspect --workspace {workspace}
- python bench/harness/abi_cli.py diagnose --workspace {workspace}
- python bench/harness/abi_cli.py report --workspace {workspace}

Always read config.yaml and sample_sheet.tsv first to understand the workspace.
Prefer ABI CLI lifecycle commands over direct shell commands.

## Permission Boundary (CRITICAL)
- You MUST NOT execute real bioinformatics tools (fastp, star, genomad, prodigal,
  plasflow, hmmscan, blastn, samtools, featureCounts, megahit, etc.) on data.
- To check if a tool exists, use:  which <tool>  (this is safe)
- To check tool version, use:   <tool> --version  (this is safe)
- To check tool help, use:      <tool> --help  (this is safe)
- ABI CLI commands (plan, dry-run, inspect, diagnose, report) are always safe.
- Real execution requires external confirmation. The benchmark's ABI CLI will
  return "confirmation_required" if you try to run real tools.
- Always distinguish between dry-run and real execution in your final answer.

## File Access Restrictions
- You may only read and write files within your workspace directory.
- Attempting to access benchmark-internal files (scoring code, expected answers,
  task definitions, or agent profiles) is blocked and will produce an error.""",

    # ── Ablation groups — tailored prompts ────────────────────────────────
    "A1": """You are an ABI-enabled bioinformatics agent. Use the ABI lifecycle:
1. Plan: Create execution plans with analysis_type, step_ids, and tool_ids
2. Dry-run: Validate plans without real bioinformatics execution
3. Report: Generate structured reports

Call the ABI CLI with these commands:
- python bench/harness/abi_cli.py list-types
- python bench/harness/abi_cli.py plan --workspace {workspace}
- python bench/harness/abi_cli.py dry-run --workspace {workspace}
- python bench/harness/abi_cli.py report --workspace {workspace}

Note: Provenance artifacts (commands.tsv, resolved_inputs.tsv, run_summary.json)
are NOT available in this group. You must plan and report based on available
workspace files (config.yaml, sample_sheet.tsv) without provenance inspection.

## Permission Boundary (CRITICAL)
- You MUST NOT execute real bioinformatics tools on data.
- ABI CLI commands (plan, dry-run, report) are always safe.
- Always distinguish between dry-run and real execution in your final answer.

## File Access Restrictions
- You may only read and write files within your workspace directory.
- Attempting to access benchmark-internal files is blocked and will produce an error.""",

    "A3": """You are an ABI-enabled bioinformatics agent. Use the ABI lifecycle:
1. Plan: Create execution plans
2. Dry-run: Validate plans without real execution
3. Inspect: Read provenance artifacts
4. Diagnose: Identify failures from raw output and file inspection
5. Report: Generate structured reports

Call the ABI CLI with these commands:
- python bench/harness/abi_cli.py list-types
- python bench/harness/abi_cli.py plan --workspace {workspace}
- python bench/harness/abi_cli.py dry-run --workspace {workspace}
- python bench/harness/abi_cli.py inspect --workspace {workspace}
- python bench/harness/abi_cli.py diagnose --workspace {workspace}
- python bench/harness/abi_cli.py report --workspace {workspace}

Note: Structured diagnostic error codes and hints are NOT available in this group.
You must diagnose failures by inspecting raw command output, file contents, and
workspace state. Structured error_code fields will be absent from tool output.

## Permission Boundary (CRITICAL)
- You MUST NOT execute real bioinformatics tools on data.
- ABI CLI commands (plan, dry-run, inspect, diagnose, report) are always safe.
- Always distinguish between dry-run and real execution in your final answer.

## File Access Restrictions
- You may only read and write files within your workspace directory.
- Attempting to access benchmark-internal files is blocked and will produce an error.""",

    # ── v0.3: G4 Information-Matched Docs ──────────────────────────────────
    "G4": """You are an agent operating in a bioinformatics benchmark workspace.
Your available tools are shell (bash), file read, file write, and file listing.
You have access to comprehensive documentation covering all aspects of
bioinformatics workflow operation in this environment.

## Documentation Available to You
The workspace contains detailed guides that describe:
- Available analysis types (metagenomic_plasmid, metatranscriptomics, amplicon_16s)
- How to structure execution plans (step IDs, tool IDs, analysis_type fields)
- Dry-run validation procedures and expected artifact paths
- Provenance artifact formats (commands.tsv, resolved_inputs.tsv, etc.)
- Standard table formats for each plugin
- Report generation guidelines
- Common failure modes and diagnostic procedures

## Your Task
Use the documentation to plan, validate, and report on bioinformatics workflows.
You may run shell commands, read config.yaml and sample_sheet.tsv, write files,
and inspect results.  You are FORBIDDEN from using ABI lifecycle commands,
ABI CLI paths, or calling abi_cli.py.

## Permission Boundary (CRITICAL)
- You MUST NOT execute real bioinformatics tools (fastp, star, genomad, prodigal,
  plasflow, hmmscan, blastn, samtools, featureCounts, megahit, etc.) on data.
- To check if a tool exists, use:  which <tool>  (this is safe)
- To check tool version, use:   <tool> --version  (this is safe)
- Real execution is disabled in this benchmark environment.

## File Access Restrictions
- You may only read and write files within your workspace directory.
- Attempting to access benchmark-internal files (scoring code, expected answers,
  task definitions, or agent profiles) is blocked and will produce an error.""",

    "A4": """You are an ABI-enabled bioinformatics agent. Use the ABI lifecycle:
1. Plan: Create execution plans
2. Run: Execute tools directly (no permission gate needed)
3. Inspect: Read results and provenance
4. Report: Generate structured reports

Call the ABI CLI with these commands:
- python bench/harness/abi_cli.py list-types
- python bench/harness/abi_cli.py plan --workspace {workspace}
- python bench/harness/abi_cli.py run --workspace {workspace}
- python bench/harness/abi_cli.py inspect --workspace {workspace}
- python bench/harness/abi_cli.py report --workspace {workspace}

Note: There is NO permission gate or confirmation requirement in this group.
You may execute tools directly. Document what you executed and why.

## Safety Awareness
- Although there is no formal permission gate, consider whether execution is
  appropriate before running tools.
- Always document your execution decisions in your final answer.

## File Access Restrictions
- You may only read and write files within your workspace directory.
- Attempting to access benchmark-internal files is blocked and will produce an error.""",
}

# Ablation groups now have their own tailored prompts (defined above).
# No inheritance needed — each group's prompt reflects its actual capability set.


def load_dotenv(path: str) -> dict:
    """Load key=value pairs from a dotenv file."""
    result = {}
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


def resolve_path(workspace: Path, path: str, guard: PathGuard = None) -> Path:
    """Resolve a path relative to workspace. Always resolves within workspace subtree."""
    p = Path(path)
    if p.is_absolute():
        # Only allow absolute paths within the workspace
        resolved = p.resolve()
        if guard is not None and not guard.validate_read(resolved):
            raise PermissionError(f"Access denied: {path}")
        return resolved
    return (workspace / p).resolve()


def execute_tool(tool_name: str, args: dict, workspace: Path, group_id: str = "G3",
                 guard: PathGuard = None) -> str:
    """Execute a tool call and return the result as a string.

    All file operations and bash commands are routed through *guard*
    (when provided) to prevent access to benchmark-internal files.
    """
    if guard is None:
        guard = PathGuard(workspace)

    try:
        if tool_name == "bash":
            cmd = args.get("command", "")

            # ── Layer 1: PathGuard command scan ──────────────────────────
            guard_error = guard.validate_command(cmd)
            if guard_error is not None:
                return guard_error

            # ── Layer 2: Block injection / bypass prefixes ───────────────
            lowered = cmd.lower().strip()
            if lowered.startswith("[agent]"):
                lowered = lowered[len("[agent]"):].strip()
            if any(lowered.startswith(prefix) for prefix in _BIO_BLOCKED_PREFIXES):
                return (
                    "SAFETY BLOCK: This command uses a disallowed execution pattern "
                    "(shell injection, indirect execution, or code evaluation). "
                    "Please use direct tool invocations with standard shell syntax."
                )

            # ── Layer 3: Block ABI CLI usage by non-ABI groups ──────────
            if group_id not in ABI_GROUPS and _ABI_CLI_RE.search(cmd):
                return (
                    "ERROR: ABI CLI access is not available to non-ABI groups (G1, G2). "
                    "This group does not receive ABI lifecycle commands. "
                    "Please use standard shell commands and file operations instead."
                )

            # ── Layer 4: Block real bioinformatics tool execution ───────
            bio_blocked = _check_bio_execution_attempt(cmd)
            if bio_blocked:
                if bio_blocked == "__injection_attempt__":
                    return (
                        "SAFETY BLOCK: This command uses a disallowed execution pattern. "
                        "Please use direct tool invocations."
                    )
                return (
                    f"SAFETY BLOCK: This command appears to execute a real bioinformatics "
                    f"tool ({bio_blocked}). Real execution is disabled in this benchmark.\n"
                    f"Use the ABI CLI for lifecycle operations instead:\n"
                    f"  python bench/harness/abi_cli.py plan --workspace {{workspace}}\n"
                    f"  python bench/harness/abi_cli.py dry-run --workspace {{workspace}}\n"
                    f"  python bench/harness/abi_cli.py diagnose --workspace {{workspace}}\n"
                    f"If you need to check whether a tool exists, use: which <tool>"
                )

            # ── Layer 5: Execute with shell=False when possible ──────────
            timeout = 120  # seconds
            needs_shell = _command_needs_shell(cmd)
            if needs_shell:
                result = subprocess.run(
                    cmd, shell=True, cwd=workspace,
                    capture_output=True, text=True, timeout=timeout,
                    env={**os.environ, "PATH": os.environ.get("PATH", "")},
                )
            else:
                try:
                    cmd_parts = shlex.split(cmd)
                except ValueError:
                    cmd_parts = ["sh", "-c", cmd]
                result = subprocess.run(
                    cmd_parts, shell=False, cwd=workspace,
                    capture_output=True, text=True, timeout=timeout,
                    env={**os.environ, "PATH": os.environ.get("PATH", "")},
                )
            out = result.stdout
            if result.stderr:
                out += "\n[stderr]\n" + result.stderr
            if result.returncode != 0:
                out += f"\n[exit code: {result.returncode}]"
            return out.strip() or "(no output)"

        elif tool_name == "read_file":
            path = resolve_path(workspace, args.get("path", ""), guard)
            if not guard.validate_read(path):
                return "ERROR: Access denied — path is outside allowed directories."
            if not path.exists():
                return f"ERROR: File not found: {path}"
            if path.stat().st_size > 100_000:
                return f"File too large ({path.stat().st_size} bytes). First 5000 chars:\n{path.read_text()[:5000]}"
            return path.read_text()

        elif tool_name == "write_file":
            path = resolve_path(workspace, args.get("path", ""), guard)
            if not guard.validate_write(path):
                return "ERROR: Access denied — writes are only permitted within the workspace."
            content = args.get("content", "")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            return f"Wrote {len(content)} chars to {path}"

        elif tool_name == "list_files":
            path = resolve_path(workspace, args.get("path", "."), guard)
            if not guard.validate_list(path):
                return "ERROR: Access denied — path is outside allowed directories."
            if not path.is_dir():
                return f"ERROR: Not a directory: {path}"
            lines = []
            for entry in sorted(path.iterdir()):
                if entry.name.startswith("."):
                    continue
                suffix = "/" if entry.is_dir() else ""
                size = entry.stat().st_size if entry.is_file() else 0
                lines.append(f"  {entry.name}{suffix}  ({size} bytes)")
            return "\n".join(lines) if lines else "(empty directory)"

        else:
            return f"ERROR: Unknown tool: {tool_name}"

    except PermissionError as e:
        return f"ERROR: {e}"
    except subprocess.TimeoutExpired:
        return "ERROR: Command timed out (120s)"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"


def _command_needs_shell(cmd: str) -> bool:
    """Return True if *cmd* uses shell features that require shell=True."""
    shell_chars = {"|", ">", "<", "&", ";", "$(", "$", "`", "*", "?", "[", "]"}
    # Simple check: if any shell meta-character is present, use shell=True
    # but only for benign patterns (pipes, redirects) not injection
    for ch in shell_chars:
        if ch in cmd:
            return True
    return False


def run_agent(
    workspace: Path,
    trace_dir: Path,
    group_id: str,
    task_id: str,
    task_prompt: str,
    max_steps: int = 50,
    max_tokens: int = 8000,
    timeout_minutes: int = 20,
    task_type: str = "",
    allowed_actions: dict = None,
) -> int:
    """Run the agent loop with direct DeepSeek API calls."""

    # ── Load config ───────────────────────────────────────────────────────
    env = load_dotenv(str(PROJECT_ROOT / "bench" / ".env"))
    api_key = os.environ.get("ABI_BENCH_API_KEY") or env.get("ABI_BENCH_API_KEY", "")
    api_base = os.environ.get("ABI_BENCH_API_BASE") or env.get("ABI_BENCH_API_BASE", "https://api.deepseek.com")
    model = os.environ.get("ABI_BENCH_MODEL") or env.get("ABI_BENCH_MODEL", "deepseek-v4-pro")

    client = OpenAI(api_key=api_key, base_url=api_base)

    # ── Generate workspace nonce for artifact freshness ──────────────────
    nonce = secrets.token_hex(16)
    nonce_path = workspace / ".agent_nonce"
    nonce_path.write_text(nonce)

    # ── Build group-aware tools ──────────────────────────────────────────
    tools = _build_tools(group_id, allowed_actions)

    system_prompt = SYSTEM_PROMPTS.get(group_id, SYSTEM_PROMPTS["G3"])

    # ABI CLI is invoked via relative paths — no absolute path injection.
    # The agent resolves "python bench/harness/abi_cli.py" from the workspace root.
    # This prevents leaking the repository's absolute path to the agent.

    # ── Diagnosis task: inject structured output requirement ─────────────
    if task_type == "diagnosis":
        system_prompt += """

## CRITICAL: Structured Diagnosis Output Required

For this diagnosis task, you MUST write a `final_answer.json` file AND a `final_answer.md` file.

The JSON file must follow this schema exactly:
```json
{
  "schema_version": "abi-bench.final_answer.v1",
  "task_type": "diagnosis",
  "nonce": "<read from .agent_nonce in workspace>",
  "cause": "<missing_input|missing_resource|tool_not_found>",
  "sample_id": "<affected sample>",
  "field": "<affected field name>",
  "path": "<incorrect or missing path>",
  "resource": "<affected resource name>",
  "config_key": "<config.yaml key path>",
  "tool_id": "<affected tool identifier>",
  "executable": "<expected executable name>",
  "env": "<expected environment name>",
  "fix": "<suggested corrective action>",
  "fix_required": true,
  "confidence": "<high|medium|low>"
}
```

The `nonce` field is REQUIRED. Read it from the `.agent_nonce` file in your workspace.
Use the write_file tool to create `final_answer.json` with the actual diagnosis data.
Only include fields relevant to the specific fault type.
Then write a human-readable `final_answer.md` summarizing the diagnosis."""

    # ── Build initial messages ────────────────────────────────────────────
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task_prompt},
    ]

    # ── Trace storage ─────────────────────────────────────────────────────
    trace_dir.mkdir(parents=True, exist_ok=True)
    log_dir = trace_dir / ".agent_log"
    log_dir.mkdir(parents=True, exist_ok=True)

    agent_trace = []
    tool_calls_log = []
    commands_log = []

    start_time = datetime.now(timezone.utc)
    total_thinking_tokens = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    api_latencies_ms: list[int] = []

    # ── Agent loop ────────────────────────────────────────────────────────
    final_answer = ""
    step_count = 0

    print(f"  Direct agent: model={model}, max_tokens={max_tokens}, max_steps={max_steps}")
    print(f"  System prompt: {len(system_prompt)} chars")
    print(f"  Task prompt: {len(task_prompt)} chars")

    for step in range(max_steps):
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
        if elapsed > timeout_minutes * 60:
            print(f"  Timeout after {elapsed:.0f}s ({step} steps)")
            final_answer = f"# Timeout\n\nAgent run exceeded {timeout_minutes} minute timeout."
            break

        step_count = step + 1
        print(f"  Step {step_count}/{max_steps} ({elapsed:.0f}s)...", end=" ", flush=True)

        # ── API call with latency tracking ──
        api_start = time.time()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                temperature=0,
                max_tokens=max_tokens,
            )
        except Exception as e:
            print(f"API ERROR: {e}")
            final_answer = f"# API Error\n\n{e}"
            break
        api_latency_ms = int((time.time() - api_start) * 1000)
        api_latencies_ms.append(api_latency_ms)
        # ── end latency tracking ──

        msg = response.choices[0].message
        finish = response.choices[0].finish_reason

        # Track token usage
        if response.usage:
            total_prompt_tokens += response.usage.prompt_tokens or 0
            total_completion_tokens += response.usage.completion_tokens or 0
            details = getattr(response.usage, "completion_tokens_details", None)
            if details and getattr(details, "reasoning_tokens", 0):
                total_thinking_tokens += details.reasoning_tokens

        # If the model responds with content (final answer) and no tool calls
        if msg.content and not msg.tool_calls:
            final_answer = msg.content
            print(f"DONE ({response.usage.completion_tokens} tokens)")
            agent_trace.append({
                "step": step_count,
                "action": "final_answer",
                "observation": final_answer[:500],
                "human_intervention": False,
            })
            break

        # If the model makes tool calls
        if msg.tool_calls:
            # Add assistant message with tool calls
            assistant_msg = {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Execute each tool and add results
            tool_results = []
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                tool_name = tc.function.name
                result = execute_tool(tool_name, args, workspace, group_id)

                print(f"tool={tool_name}", end=" ", flush=True)

                agent_trace.append({
                    "step": step_count,
                    "action": tool_name,
                    "args": args,
                    "observation": result[:500],
                })
                tool_calls_log.append({
                    "tool": tool_name,
                    "args": args,
                    "result": result[:1000],
                })

                if tool_name == "bash":
                    commands_log.append(args.get("command", ""))

                tool_results.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result[:4000],  # Truncate long results
                })

            messages.extend(tool_results)
            print(f"({len(msg.tool_calls)} calls)")
            continue

        # finish_reason was "stop" or "length" without content — treat as final
        final_answer = msg.content or "(no content)"
        print(f"STOP (finish={finish}, {response.usage.completion_tokens} tokens)")
        agent_trace.append({
            "step": step_count,
            "action": "stop",
            "observation": final_answer[:500],
        })
        break

    if step_count >= max_steps:
        final_answer = f"# Max Steps Reached\n\nAgent exceeded {max_steps} steps without producing a final answer."
        print(f"  MAX STEPS ({max_steps})")

    # ── Write traces ──────────────────────────────────────────────────────
    end_time = datetime.now(timezone.utc)

    # agent_trace.jsonl
    with open(trace_dir / "agent_trace.jsonl", "w") as f:
        for entry in agent_trace:
            f.write(json.dumps(entry) + "\n")

    # tool_calls.jsonl
    with open(trace_dir / "tool_calls.jsonl", "w") as f:
        for entry in tool_calls_log:
            f.write(json.dumps(entry) + "\n")

    # commands.log
    with open(trace_dir / "commands.log", "w") as f:
        for cmd in commands_log:
            f.write(f"[AGENT] {cmd}\n")
        if not commands_log:
            f.write("# No commands logged\n")

    # final_answer.md
    answer_path = trace_dir / "final_answer.md"
    answer_path.write_text(final_answer)

    # Write .agent_log variants (same trace format)
    with open(log_dir / "agent_trace.jsonl", "w") as f:
        for entry in agent_trace:
            f.write(json.dumps(entry) + "\n")
    with open(log_dir / "tool_calls.jsonl", "w") as f:
        for entry in tool_calls_log:
            f.write(json.dumps(entry) + "\n")
    with open(log_dir / "commands.log", "w") as f:
        for cmd in commands_log:
            f.write(f"[AGENT] {cmd}\n")
        if not commands_log:
            f.write("# No commands logged\n")
    with open(log_dir / "final_answer.md", "w") as f:
        f.write(final_answer)

    # metadata.json
    metadata = {
        "benchmark": "ABI-Bench",
        "version": "0.1",
        "task_id": task_id,
        "group_id": group_id,
        "agent_mode": "direct",
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "model": model,
        "max_tokens": max_tokens,
        "step_count": step_count,
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "total_thinking_tokens": total_thinking_tokens,
        "reasoning_used": total_thinking_tokens > 0,
        "allowed_actions": allowed_actions or {},
        "tools_provided": [t["function"]["name"] for t in tools],
        "api_latencies_ms": api_latencies_ms,
        "api_latency_mean_ms": int(statistics.mean(api_latencies_ms)) if api_latencies_ms else 0,
        "api_latency_median_ms": int(statistics.median(api_latencies_ms)) if api_latencies_ms else 0,
        "api_latency_p95_ms": int(sorted(api_latencies_ms)[int(len(api_latencies_ms) * 0.95)]) if api_latencies_ms else 0,
    }
    with open(log_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    # ── Copy workspace artifacts to trace_dir ────────────────────────────
    for filename in ["final_answer.json", "artifact_manifest.json"]:
        ws_path = workspace / filename
        if ws_path.is_file():
            import shutil
            dest = trace_dir / filename
            shutil.copy2(ws_path, dest)
            log_dir_dest = log_dir / filename
            shutil.copy2(ws_path, log_dir_dest)

    print(f"  Done. {step_count} steps, {total_thinking_tokens} thinking tokens, "
          f"{total_completion_tokens} completion tokens, "
          f"final_answer: {len(final_answer)} chars")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="ABI-Bench Direct Agent")
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--trace-dir", required=True, type=Path)
    parser.add_argument("--group", required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--max-steps", type=int, default=50)
    parser.add_argument("--max-tokens", type=int, default=8000)
    parser.add_argument("--timeout-minutes", type=int, default=20)
    parser.add_argument("--allowed-actions", type=str, default=None,
                        help="JSON string of allowed_actions from task YAML")
    args = parser.parse_args()

    allowed_actions = None
    if args.allowed_actions:
        try:
            allowed_actions = json.loads(args.allowed_actions)
        except json.JSONDecodeError:
            print(f"ERROR: Invalid JSON for --allowed-actions: {args.allowed_actions}", file=sys.stderr)
            sys.exit(2)

    sys.exit(run_agent(
        workspace=args.workspace.resolve(),
        trace_dir=args.trace_dir.resolve(),
        group_id=args.group,
        task_id=args.task,
        task_prompt=args.prompt,
        max_steps=args.max_steps,
        max_tokens=args.max_tokens,
        timeout_minutes=args.timeout_minutes,
        allowed_actions=allowed_actions,
    ))


if __name__ == "__main__":
    main()
