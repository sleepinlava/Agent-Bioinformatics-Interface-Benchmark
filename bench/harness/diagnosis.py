"""
ABI-Bench v0.1 — Shared diagnosis utilities.

Used by both the simulated agent runner (run_task.py) and the ABI lifecycle
CLI (abi_cli.py) to produce deterministic workspace diagnoses.  Keeping the
logic here avoids duplication and ensures the two code paths stay consistent.
"""

import csv
import json
from pathlib import Path

import yaml


def load_config_safe(workspace: Path) -> dict:
    """Load config.yaml from workspace, returning {} on any failure."""
    config_path = workspace / "config.yaml"
    if not config_path.is_file():
        return {}
    try:
        data = yaml.safe_load(config_path.read_text())
    except (OSError, yaml.YAMLError) as e:
        print(f"WARNING: Failed to parse config.yaml: {e}")
        return {}
    if not isinstance(data, dict):
        print(f"WARNING: config.yaml is not a mapping, got {type(data).__name__}")
        return {}
    return data


def diagnose_workspace_structured(workspace: Path) -> dict:
    """
    Inspect the workspace for injected faults and return a structured diagnosis.

    Checks (in order):
      1. Sample sheet for paths containing ``/missing/`` → missing_input
      2. Config resources for paths containing ``/missing/`` → missing_resource
      3. Config tools for ``not installed`` marker or plasflow → tool_not_found

    Returns a dict with schema_version, task_type, cause, and all diagnostic
    fields (sample_id, field, path, resource, config_key, tool_id, executable,
    env, fix, confidence).
    """
    config = load_config_safe(workspace)
    sample_sheet_rel = str(config.get("samples", {}).get("sample_sheet", "sample_sheet.tsv"))
    sample_sheet = workspace / sample_sheet_rel

    # 1. Check sample sheet for missing input paths
    if sample_sheet.is_file():
        try:
            with open(sample_sheet) as f:
                reader = csv.DictReader(f, delimiter="\t")
                for row in reader:
                    for field, value in row.items():
                        if isinstance(value, str) and "/missing/" in value:
                            return {
                                "schema_version": "abi-bench.final_answer.v1",
                                "task_type": "diagnosis",
                                "cause": "missing_input",
                                "sample_id": row.get("sample_id", "unknown"),
                                "field": field,
                                "path": value,
                                "resource": "",
                                "config_key": "",
                                "tool_id": "",
                                "executable": "",
                                "env": "",
                                "fix": (
                                    f"Update sample_sheet.tsv to point "
                                    f"{row.get('sample_id', 'the sample')} "
                                    f"{field} to an existing input file."
                                ),
                                "confidence": "high",
                            }
        except (OSError, csv.Error) as e:
            print(f"WARNING: Failed to read sample sheet for diagnosis: {e}")

    # 2. Check config resources for missing paths
    for name, meta in config.get("resources", {}).items():
        path = meta.get("path", "") if isinstance(meta, dict) else ""
        if "/missing/" in str(path):
            return {
                "schema_version": "abi-bench.final_answer.v1",
                "task_type": "diagnosis",
                "cause": "missing_resource",
                "sample_id": "",
                "field": "",
                "path": str(path),
                "resource": name,
                "config_key": f"resources.{name}.path",
                "tool_id": "",
                "executable": "",
                "env": "",
                "fix": "Point the config to an installed local resource; do not download automatically.",
                "confidence": "high",
            }

    # 3. Check config tools for "not installed" markers
    for tool_id, meta in config.get("tools", {}).items():
        text = json.dumps(meta).lower() if isinstance(meta, dict) else ""
        if "not installed" in text or tool_id == "plasflow":
            executable = meta.get("executable", tool_id) if isinstance(meta, dict) else tool_id
            env = meta.get("env", "") if isinstance(meta, dict) else ""
            return {
                "schema_version": "abi-bench.final_answer.v1",
                "task_type": "diagnosis",
                "cause": "tool_not_found",
                "sample_id": "",
                "field": "",
                "path": "",
                "resource": "",
                "config_key": "",
                "tool_id": tool_id,
                "executable": executable,
                "env": env,
                "fix": f"Install {executable} in the {env or 'expected'} Conda environment before real execution.",
                "confidence": "high",
            }

    # 4. No faults detected
    return {
        "schema_version": "abi-bench.final_answer.v1",
        "task_type": "diagnosis",
        "cause": "none",
        "sample_id": "",
        "field": "",
        "path": "",
        "resource": "",
        "config_key": "",
        "tool_id": "",
        "executable": "",
        "env": "",
        "fix": "No injected missing input, missing resource, or missing tool was detected.",
        "confidence": "medium",
    }


def format_diagnosis_markdown(diagnosis: dict) -> str:
    """Render a structured diagnosis dict as markdown text."""
    cause = str(diagnosis.get("cause", "unknown")).replace("_", " ")
    lines = ["# Diagnostic Report", "", f"Cause: {cause}"]
    for key in ("sample_id", "field", "path", "resource", "config_key",
                "tool_id", "executable", "env"):
        value = diagnosis.get(key)
        if value:
            lines.append(f"{key}: {value}")
    fix = diagnosis.get("fix")
    if fix:
        lines.append(f"fix: {fix}")
    return "\n".join(lines) + "\n"
