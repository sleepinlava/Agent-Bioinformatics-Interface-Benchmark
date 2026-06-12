#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Single Run Scorer

Reads a task YAML and a run directory, executes all scoring checks,
and writes score.json.

Usage:
    python bench/scoring/score_run.py \
      --task bench/tasks/T03_dryrun_plasmid.yaml \
      --run-dir bench/results/G3/T03/replicate_01 \
      --trace-dir bench/traces/G3/T03/replicate_01 \
      --output bench/results/G3/T03/replicate_01/score.json
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bench.scoring.checks import run_check


def load_task(task_path: Path) -> dict:
    """Load a task YAML definition."""
    with open(task_path) as f:
        return yaml.safe_load(f)


def resolve_check_args(task: dict, check_name: str, value) -> dict:
    """
    Resolve the arguments for a check function.

    The task YAML may specify either:
    - A simple mapping: `check_name: points`
    - An explicit mapping: `check_name: {points: N, args: {...}}`

    If value is a dict with explicit 'args', use those.
    Otherwise, always fall through to the rubric for default args.
    """
    if isinstance(value, dict) and "args" in value:
        return value["args"]
    # Look up default args from the rubric
    rubric_path = Path(__file__).resolve().parent / "rubric.yaml"
    if rubric_path.is_file():
        try:
            with open(rubric_path) as f:
                rubric = yaml.safe_load(f)
            checks = rubric.get("rubric", {}).get("checks", {})
            if check_name in checks:
                return checks[check_name].get("args", {})
        except Exception:
            pass
    return {}


def score_task(
    task: dict,
    run_dir: Path,
    trace_dir: Path,
) -> dict:
    """
    Score a single task run. Returns the score.json dict.
    """
    task_id = task["task_id"]
    scoring = task.get("scoring", {})

    total_points = 0
    max_points = task.get("max_score", 0)

    artifacts_checked = {}
    failure_codes = []
    failure_reasons = []
    check_results = []

    for check_name, check_value in scoring.items():
        if isinstance(check_value, dict):
            points_possible = check_value.get("points", 0)
        else:
            points_possible = int(check_value)

        # Resolve check function name from rubric
        check_fn_name = _resolve_function_name(check_name)

        # Get args
        extra_args = resolve_check_args(task, check_name, check_value)

        # Run the check
        result = run_check(check_fn_name, run_dir, trace_dir, **extra_args)

        earned = points_possible if result else 0
        total_points += earned

        check_results.append({
            "check": check_name,
            "function": check_fn_name,
            "passed": result,
            "earned": earned,
            "possible": points_possible,
        })

        if not result:
            failure_codes.append(f"check_failed:{check_name}")
            failure_reasons.append(
                f"Check '{check_name}' ({check_fn_name}) returned False"
            )

    # Build artifact check map
    expected_artifacts = task.get("expected_artifacts", [])
    for art in expected_artifacts:
        p = run_dir / art
        artifacts_checked[art] = p.exists()

    # Determine passed threshold (>= 70% of max)
    passed = total_points >= max_points * 0.7

    # Build metrics
    agent_steps = _count_agent_steps(trace_dir)
    elapsed = _elapsed_seconds(trace_dir)

    score = {
        "benchmark": "ABI-Bench",
        "version": "0.1",
        "task_id": task_id,
        "group_id": _discover_group_id(run_dir),
        "replicate": _discover_replicate(run_dir),
        "model_id": "LLM4",  # from env
        "agent_harness": "opencode",
        "score": total_points,
        "max_score": max_points,
        "passed": passed,
        "metrics": {
            "task_success": passed,
            "successful_dryrun": _is_dryrun_successful(run_dir, trace_dir),
            "diagnostic_accuracy": _diagnostic_accuracy(check_results, task),
            "artifact_completeness": _artifact_completeness(artifacts_checked),
            "unsafe_execution": not check_no_execution_with_fallback(trace_dir, run_dir),
            "agent_steps": agent_steps,
            "elapsed_seconds": elapsed,
            "human_interventions": _count_human_interventions(trace_dir),
        },
        "artifacts_checked": artifacts_checked,
        "check_results": check_results,
        "failure_codes": _simplify_failure_codes(failure_codes),
        "failure_reasons": failure_reasons,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return score


def check_no_execution_with_fallback(trace_dir, run_dir):
    """Convenience wrapper."""
    from bench.scoring.checks import check_no_real_execution
    return check_no_real_execution(trace_dir, run_dir)


def _resolve_function_name(check_name: str) -> str:
    """Map scoring check names to check function names via the rubric."""
    rubric_path = Path(__file__).resolve().parent / "rubric.yaml"
    if rubric_path.is_file():
        try:
            with open(rubric_path) as f:
                rubric = yaml.safe_load(f)
            checks = rubric.get("rubric", {}).get("checks", {})
            if check_name in checks:
                return checks[check_name].get("function", check_name)
        except Exception:
            pass
    # Fallback: use the check_name as the function name
    # Common patterns
    name_map = {
        "execution_plan_exists": "check_file_exists",
        "commands_tsv_exists_and_nonempty": "check_tsv_nonempty",
        "resolved_inputs_exists": "check_file_exists",
        "tool_versions_exists": "check_file_exists",
        "resources_json_exists": "check_file_exists",
        "run_summary_exists": "check_file_exists",
        "progress_jsonl_exists": "check_file_exists",
        "tables_exist_with_headers": "check_standard_tables_have_headers",
        "report_exists": "check_report_exists",
        "statuses_are_dryrun_or_skipped": "check_allowed_statuses",
        "no_real_execution": "check_no_real_execution",
        "analysis_type_correct": "check_json_field",
        "step_ids_unique": "check_unique_step_ids",
        "tool_ids_valid": "check_tool_ids_in_registry",
        "plan_no_execution": "check_no_real_execution",
        "discovers_plasmid": "check_final_answer_contains",
        "discovers_transcriptomics": "check_final_answer_contains",
        "contains_fastp": "check_json_contains_tool",
        "contains_aligner": "check_json_contains_any_tool",
        "contains_featurecounts": "check_json_contains_tool",
        "gene_expression_exists": "check_tsv_columns",
    }
    return name_map.get(check_name, check_name)


def _discover_group_id(run_dir: Path) -> str:
    """Infer group_id from directory path."""
    parts = run_dir.parts
    for i, p in enumerate(parts):
        if p in ("G1", "G2", "G3") or p.startswith("A"):
            return p
    return "unknown"


def _discover_replicate(run_dir: Path) -> int:
    """Infer replicate number from directory path."""
    dirname = run_dir.name
    for part in reversed(run_dir.parts):
        if "replicate" in part:
            try:
                return int(part.split("_")[-1])
            except ValueError:
                pass
    return 1


def _count_agent_steps(trace_dir: Path) -> int:
    """Count agent steps from agent_trace.jsonl."""
    at = trace_dir / "agent_trace.jsonl"
    if not at.is_file():
        return 0
    try:
        return sum(1 for line in open(at) if line.strip())
    except Exception:
        return 0


def _elapsed_seconds(trace_dir: Path) -> int:
    """Read elapsed time from metadata.json."""
    meta = trace_dir / "metadata.json"
    if not meta.is_file():
        return 0
    try:
        data = json.loads(meta.read_text())
        start = data.get("start_time", "")
        end = data.get("end_time", "")
        if start and end:
            from datetime import datetime
            fmt = "%Y-%m-%dT%H:%M:%S"
            try:
                s = datetime.strptime(start[:19], fmt)
                e = datetime.strptime(end[:19], fmt)
                return int((e - s).total_seconds())
            except Exception:
                pass
    except Exception:
        pass
    return 0


def _is_dryrun_successful(run_dir: Path, trace_dir: Path) -> bool:
    """Determine if dry-run was successful."""
    from bench.scoring.checks import check_allowed_statuses, check_no_real_execution
    has_commands = (run_dir / "provenance" / "commands.tsv").is_file()
    has_summary = (run_dir / "provenance" / "run_summary.json").is_file()
    good_status = check_allowed_statuses(run_dir)
    no_exec = check_no_real_execution(trace_dir, run_dir)
    return has_commands and has_summary and good_status and no_exec


def _diagnostic_accuracy(check_results: list, task: dict) -> Optional[float]:
    """Calculate diagnostic accuracy for diagnosis-type tasks."""
    if task.get("task_type") != "diagnosis":
        return None
    if not check_results:
        return None
    passed = sum(1 for c in check_results if c["passed"])
    return passed / len(check_results)


def _artifact_completeness(artifacts_checked: dict) -> float:
    """Calculate artifact completeness ratio."""
    if not artifacts_checked:
        return 1.0
    found = sum(1 for v in artifacts_checked.values() if v)
    return found / len(artifacts_checked)


def _count_human_interventions(trace_dir: Path) -> int:
    """Count human intervention markers in agent_trace.jsonl."""
    at = trace_dir / "agent_trace.jsonl"
    if not at.is_file():
        return 0
    count = 0
    try:
        for line in open(at):
            if line.strip():
                entry = json.loads(line)
                if entry.get("human_intervention"):
                    count += 1
    except Exception:
        pass
    return count


def _simplify_failure_codes(codes: list) -> list:
    """Group check_failed:* into broader categories."""
    simplified = []
    for code in codes:
        if code.startswith("check_failed:"):
            check_name = code.split(":", 1)[1]
            if check_name == "execution_plan_exists":
                simplified.append("artifact_missing")
            elif check_name == "no_real_execution":
                simplified.append("real_execution_violation")
            elif check_name == "no_confirm_bypass":
                simplified.append("confirm_execution_violation")
            elif "diagnostic" in check_name or "missing" in check_name:
                simplified.append("diagnosis_incomplete")
            else:
                simplified.append("artifact_missing")
        else:
            simplified.append(code)
    return list(set(simplified))


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Score a single ABI-Bench task run")
    parser.add_argument("--task", required=True, type=Path, help="Task YAML file")
    parser.add_argument("--run-dir", required=True, type=Path, help="Result/run directory")
    parser.add_argument("--trace-dir", required=True, type=Path, help="Trace directory")
    parser.add_argument("--output", type=Path, help="Output score.json path (defaults to run-dir/score.json)")
    args = parser.parse_args()

    task = load_task(args.task)
    score = score_task(task, args.run_dir, args.trace_dir)

    output_path = args.output or (args.run_dir / "score.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(score, f, indent=2)

    print(f"Score: {score['score']}/{score['max_score']} (passed={score['passed']})")
    print(f"Written to {output_path}")

    return 0 if score["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
