#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Agent Context Exporter

Generates the context bundle that will be provided to the agent
for a given task, group, and replicate. The output is a JSON manifest
describing what the agent sees (files, tools, docs).

Usage:
    python bench/harness/export_agent_context.py \
      --group G3 \
      --task T03 \
      --workspace bench/workspaces/G3/T03/replicate_01 \
      --output bench/workspaces/G3/T03/replicate_01/agent_context.json
"""

import argparse
import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def load_agent_profile(group_id: str) -> dict:
    """Load the agent profile YAML for a given group."""
    profile_map = {
        "G1": "G1_readme_shell.yaml",
        "G2": "G2_plain_tool_calling.yaml",
        "G3": "G3_abi_control_layer.yaml",
        "A1": "A1_no_provenance.yaml",
        "A3": "A3_no_diagnostic_hints.yaml",
        "A4": "A4_no_permission_model.yaml",
    }
    fname = profile_map.get(group_id)
    if not fname:
        print(f"ERROR: Unknown group_id '{group_id}'", file=sys.stderr)
        return None

    profile_path = PROJECT_ROOT / "bench" / "agent_profiles" / fname
    if not profile_path.is_file():
        print(f"ERROR: Profile not found: {profile_path}", file=sys.stderr)
        return None

    with open(profile_path) as f:
        return yaml.safe_load(f)


def load_task_definition(task_id: str) -> dict:
    """Load the task YAML definition."""
    task_files = {
        "T01": "T01_list_types.yaml",
        "T02": "T02_plan_plasmid.yaml",
        "T03": "T03_dryrun_plasmid.yaml",
        "T04": "T04_inspect_plasmid.yaml",
        "T05": "T05_missing_input.yaml",
        "T06": "T06_missing_resource.yaml",
        "T07": "T07_tool_not_found.yaml",
        "T08": "T08_permission_gated_run.yaml",
        "T09": "T09_plan_metatranscriptomics.yaml",
        "T10": "T10_dryrun_metatranscriptomics.yaml",
        "T11": "T11_inspect_metatranscriptomics.yaml",
        "T12": "T12_standard_tables_interpretation.yaml",
    }
    fname = task_files.get(task_id)
    if not fname:
        print(f"ERROR: Unknown task_id '{task_id}'", file=sys.stderr)
        return None

    task_path = PROJECT_ROOT / "bench" / "tasks" / fname
    with open(task_path) as f:
        return yaml.safe_load(f)


def export_context(
    group_id: str,
    task_id: str,
    workspace: Path,
    experiment_set: str = "dev",
    fixture_set: str = "public",
) -> dict:
    """Build the agent context manifest."""
    profile = load_agent_profile(group_id)
    task = load_task_definition(task_id)

    if profile is None or task is None:
        return None

    # List visible files in workspace
    workspace_files = []
    for f in workspace.rglob("*"):
        if f.is_file():
            workspace_files.append({
                "path": str(f.relative_to(workspace)),
                "size": f.stat().st_size,
            })

    context = {
        "benchmark": "ABI-Bench",
        "version": "0.1",
        "group_id": group_id,
        "task_id": task_id,
        "experiment_set": experiment_set,
        "fixture_set": fixture_set,
        "task_prompt": task.get("prompt", ""),
        "allowed_actions": task.get("allowed_actions", {}),
        "agent_profile": {
            "allowed_tools": profile.get("allowed_tools", []),
            "forbidden_tools": profile.get("forbidden_tools", []),
            "restricted_tools": profile.get("restricted_tools", {}),
            "required_behavior": profile.get("required_behavior", []),
            "rule": profile.get("rule", {}).get("description", ""),
        },
        "abi_interface": build_abi_interface(group_id, profile, task_id, experiment_set),
        "workspace_files": workspace_files,
        "expected_artifacts": task.get("expected_artifacts", []),
        "output_formats": build_output_formats(task),
        "max_agent_steps": task.get("max_agent_steps", 50),
        "timeout_minutes": task.get("timeout_minutes", 20),
    }

    return context


def build_output_formats(task: dict) -> dict:
    """Return schema documentation for expected output artifacts.

    This is provided to ALL groups so every agent knows WHAT to produce.
    The group differentiation is HOW they produce it (ABI CLI vs manual).
    """
    return {
        "execution_plan": {
            "path": "execution_plan.json",
            "schema_version": "abi-bench.plan.v1",
            "description": "A JSON file describing the analysis workflow",
            "required_fields": ["schema_version", "analysis_type", "steps"],
            "step_schema": {
                "step_id": "unique string identifier for this step",
                "tool_id": "tool identifier from the tool registry in config.yaml",
                "executable": "name of the executable or script",
                "command_template": "shell command with {placeholders}",
                "status": "one of: planned, dry_run, skipped, failed",
                "inputs": "list of input file paths",
                "outputs": "list of output file paths",
            },
        },
        "provenance": {
            "directory": "provenance/",
            "description": "Traceability artifacts recording what would be executed",
            "files": {
                "commands.tsv": "TSV with columns: step_id, tool_id, executable, command, status",
                "resolved_inputs.tsv": "TSV with columns: step_id, input_path, resolved_path, exists",
                "tool_versions.tsv": "TSV with columns: tool_id, executable, version, source",
                "resources.json": "JSON object mapping resource names to their resolved paths",
                "run_summary.json": "JSON with execution_mode, total_steps, status_counts",
                "progress.jsonl": "JSONL with one object per step: {step_id, status, timestamp}",
            },
        },
        "tables": {
            "directory": "tables/",
            "description": "Standard-format analysis output tables",
            "format": "TSV files with a header row",
            "metagenomic_plasmid": ["plasmid_annotations.tsv"],
            "metatranscriptomics": ["gene_expression.tsv (columns: gene_id, gene_name, ...)"],
        },
        "report": {
            "directory": "report/",
            "description": "Human-readable analysis report",
            "files": {
                "report.md": "Markdown report summarising the analysis",
                "report.html": "HTML version of the report",
            },
        },
        "artifact_manifest": {
            "path": "artifact_manifest.json",
            "description": "Machine-readable inventory of all produced artifacts",
            "required_fields": ["benchmark", "version", "task_id", "group_id",
                              "experiment_set", "fixture_set", "replicate", "artifacts"],
            "artifact_entry": {
                "path": "relative path to the artifact file",
                "type": "one of: execution_plan, provenance, table, report, diagnosis",
                "exists": "boolean indicating whether the file was produced",
                "size": "file size in bytes (0 if not produced)",
            },
        },
        "diagnosis": {
            "path": "final_answer.json",
            "schema_version": "abi-bench.final_answer.v1",
            "description": "Structured diagnosis output for fault-isolation tasks",
            "fields": {
                "schema_version": '"abi-bench.final_answer.v1"',
                "task_type": '"diagnosis"',
                "cause": 'one of: "missing_input", "missing_resource", "tool_not_found"',
                "sample_id": "affected sample identifier (for missing_input)",
                "field": "affected field name e.g. read1, read2 (for missing_input)",
                "path": "incorrect or missing path that caused the failure",
                "resource": "affected resource name (for missing_resource)",
                "config_key": "config.yaml key path (for missing_resource)",
                "tool_id": "affected tool identifier (for tool_not_found)",
                "executable": "expected executable name (for tool_not_found)",
                "env": "expected conda/virtual environment name (for tool_not_found)",
                "fix": "suggested corrective action",
                "fix_required": "boolean, true if a fix is needed",
                "confidence": 'one of: "high", "medium", "low"',
            },
        },
    }


def build_abi_interface(group_id: str, profile: dict, task_id: str, experiment_set: str) -> dict:
    """Expose callable ABI lifecycle commands only to ABI-enabled groups."""
    allowed_tools = profile.get("allowed_tools", [])
    abi_enabled = (
        group_id == "G3"
        or profile.get("base_profile") == "G3"
        or any(str(tool).startswith("abi_") for tool in allowed_tools)
    )
    if not abi_enabled:
        return {
            "available": False,
            "reason": "This group does not receive ABI lifecycle commands.",
        }

    cli = PROJECT_ROOT / "bench" / "harness" / "abi_cli.py"
    workspace_token = "{workspace}"
    analysis_token = "{analysis_type}"
    base = f"python {cli}"
    metadata_args = f"--task-id {task_id} --experiment-set {experiment_set}"
    return {
        "available": True,
        "cli": str(cli),
        "commands": {
            "list_types": f"python {cli} list-types",
            "plan": f"{base} plan --workspace {workspace_token} --group {group_id} --analysis-type {analysis_token} {metadata_args}",
            "dry_run": f"{base} dry-run --workspace {workspace_token} --group {group_id} --analysis-type {analysis_token} {metadata_args}",
            "inspect": f"{base} inspect --workspace {workspace_token} --group {group_id} {metadata_args}",
            "diagnose": f"{base} diagnose --workspace {workspace_token} --group {group_id} {metadata_args}",
            "report": f"{base} report --workspace {workspace_token} --group {group_id} --analysis-type {analysis_token} {metadata_args}",
            "run": f"{base} run --workspace {workspace_token} --group {group_id} --analysis-type {analysis_token} {metadata_args}",
        },
        "rules": [
            "Use dry-run for benchmark execution tasks.",
            "Do not execute real bioinformatics tools directly.",
            "The run command returns confirmation_required unless external confirmation is granted.",
        ],
        "removed_context": profile.get("removed_context", []),
    }


def main():
    parser = argparse.ArgumentParser(description="Export ABI-Bench agent context")
    parser.add_argument("--group", required=True, type=str, help="Group ID (G1/G2/G3/A1/A3/A4)")
    parser.add_argument("--task", required=True, type=str, help="Task ID (T01-T12)")
    parser.add_argument(
        "--experiment-set",
        choices=["dev", "main", "ablation", "full", "paper"],
        default="dev",
        help="Experiment set label for the exported context",
    )
    parser.add_argument(
        "--fixture-set",
        choices=["public", "hidden"],
        default="public",
        help="Fixture set label for the exported context",
    )
    parser.add_argument("--workspace", required=True, type=Path, help="Workspace directory")
    parser.add_argument("--output", type=Path, help="Output JSON path (default: workspace/agent_context.json)")
    args = parser.parse_args()

    context = export_context(args.group, args.task, args.workspace, args.experiment_set, args.fixture_set)
    if context is None:
        return 1

    output_path = args.output or (args.workspace / "agent_context.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(context, f, indent=2)

    print(f"Agent context written to {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
