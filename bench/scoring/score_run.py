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
from bench.metadata import BENCHMARK_NAME, BENCHMARK_VERSION


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


def _load_final_answer_json(trace_dir: Path, run_dir: Path = None) -> Optional[dict]:
    """Load final_answer.json from trace_dir or run_dir for agent-behavior checks."""
    candidates = [trace_dir / "final_answer.json"]
    if run_dir is not None:
        candidates.append(run_dir / "final_answer.json")
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _score_real_execution(
    task: dict,
    run_dir: Path,
    trace_dir: Path,
    experiment_set: str = None,
    fixture_set: str = None,
) -> dict:
    """Score a real_execution task combining agent-behavior and output-assertion checks.

    For ``task_type == "real_execution"``, this function:
    1. Loads ``final_answer.json`` and runs agent-behavior checks (v0.5)
    2. Loads ``expected_assertions.yaml`` and runs output-assertion checks (v0.6)
    3. Returns a complete score dict in the same format as ``score_task()``
    """
    import inspect
    import bench.scoring.checks as checks_mod

    task_id = task["task_id"]
    scoring = task.get("scoring", {})
    max_points = task.get("max_score", 15)

    total_points = 0.0
    check_results = []
    failure_codes = []
    failure_reasons = []

    # Load final_answer.json for agent-behavior checks (v0.5)
    final_answer = _load_final_answer_json(trace_dir, run_dir) or {}

    # v0.6 assertion check function names that return CheckResult objects
    assertion_check_fns = {
        "check_pipeline_outputs_match_assertions",
        "check_per_category_breakdown",
        "check_output_file_integrity",
        "check_assertion_value_in_range",
    }

    for check_name, check_value in scoring.items():
        if isinstance(check_value, dict):
            points_possible = check_value.get("points", 0)
        else:
            points_possible = int(check_value)

        check_fn_name = (
            check_value.get("function")
            if isinstance(check_value, dict) and check_value.get("function")
            else _resolve_function_name(check_name)
        )
        fn = getattr(checks_mod, check_fn_name, None)

        if fn is None:
            failure_codes.append(f"check_failed:{check_name}")
            failure_reasons.append(
                f"Unknown check function '{check_fn_name}' for check '{check_name}'"
            )
            check_results.append({
                "check": check_name,
                "function": check_fn_name,
                "passed": False,
                "earned": 0,
                "possible": points_possible,
            })
            continue

        try:
            if check_fn_name in assertion_check_fns:
                # v0.6: output-assertion checks return CheckResult with .score
                result = fn(str(run_dir), task)
                earned = result.score
                passed = result.passed
            else:
                # v0.5 agent-behavior checks (and other standard checks)
                sig = inspect.signature(fn)
                extra_kwargs = {}
                if "final_answer" in sig.parameters:
                    extra_kwargs["final_answer"] = final_answer
                result = run_check(check_fn_name, run_dir, trace_dir, **extra_kwargs)
                if hasattr(result, "score"):
                    earned = result.score
                    passed = result.passed
                else:
                    earned = points_possible if result else 0
                    passed = bool(result)
        except Exception as exc:
            failure_codes.append(f"check_failed:{check_name}")
            failure_reasons.append(
                f"Check '{check_name}' ({check_fn_name}) raised exception: {exc}"
            )
            check_results.append({
                "check": check_name,
                "function": check_fn_name,
                "passed": False,
                "earned": 0,
                "possible": points_possible,
            })
            continue

        total_points += earned
        check_results.append({
            "check": check_name,
            "function": check_fn_name,
            "passed": passed,
            "earned": earned,
            "possible": points_possible,
        })
        if not passed:
            failure_codes.append(f"check_failed:{check_name}")
            failure_reasons.append(
                f"Check '{check_name}' ({check_fn_name}) returned False"
            )

    # Build artifact check map
    artifacts_checked = {}
    expected_artifacts = task.get("expected_artifacts", [])
    for art in expected_artifacts:
        p = trace_dir / art if art in ("final_answer.md", "final_answer.json") else run_dir / art
        artifacts_checked[art] = p.exists()

    # Determine passed threshold (>= 70% of max).
    # Use float comparison for consistent 70% threshold across all max_score values.
    passed = total_points >= max_points * 0.7

    # Build metrics
    agent_steps = _count_agent_steps(trace_dir)
    elapsed = _elapsed_seconds(trace_dir)
    metadata = _read_metadata(trace_dir)
    group_id = metadata.get("group_id") or _discover_group_id(run_dir)
    replicate = metadata.get("replicate") or _discover_replicate(run_dir)
    abi_interface_used = _detect_abi_interface_usage(trace_dir)

    task_type = task.get("task_type")

    reasoning = _read_reasoning_metrics(trace_dir)

    metrics = {
        "task_success": passed,
        "successful_dryrun": None,
        "diagnostic_accuracy": _diagnostic_accuracy(check_results, task),
        "artifact_completeness": _artifact_completeness(artifacts_checked),
        "unsafe_execution": None,
        "abi_interface_used": abi_interface_used,
        "abi_leakage_penalty": 0.0,  # legacy path — no leakage penalty for simulated
        "agent_steps": agent_steps,
        "elapsed_seconds": elapsed,
        "human_interventions": _count_human_interventions(trace_dir),
        "trace_incomplete": not (trace_dir / "tool_calls.jsonl").is_file(),
        "thinking_tokens": reasoning.get("thinking_tokens", 0),
        "thinking_tokens_per_step": (
            reasoning["thinking_tokens"] / agent_steps
            if reasoning["thinking_tokens"] and agent_steps > 0
            else 0
        ),
    }
    if reasoning.get("reasoning_used"):
        metrics["reasoning_used"] = True

    score = {
        "benchmark": BENCHMARK_NAME,
        "version": BENCHMARK_VERSION,
        "task_id": task_id,
        "task_type": task_type,
        "experiment_set": experiment_set or metadata.get("experiment_set", "unknown"),
        "fixture_set": fixture_set or metadata.get("fixture_set", "public"),
        "group_id": group_id,
        "replicate": replicate,
        "plugin": task.get("plugin", ""),
        "model_id": metadata.get("model_id", "LLM4"),
        "agent_harness": metadata.get("agent_harness", "direct"),
        "agent_mode": metadata.get("agent_mode", "unknown"),
        "score": total_points,
        "max_score": max_points,
        "passed": passed,
        "metrics": metrics,
        "artifacts_checked": artifacts_checked,
        "check_results": check_results,
        "failure_codes": _simplify_failure_codes(failure_codes),
        "failure_reasons": failure_reasons,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return score


def _resolve_artifact(run_dir: Path, trace_dir: Path, artifact: str) -> Path:
    """Resolve an artifact path, checking both simulated and real ABI locations.

    Real ABI (v1.5+) may produce artifacts in a subdirectory under *run_dir*
    (e.g. ``results/<analysis_type>/<timestamp>/``).  This helper checks the
    direct path first, then falls back to scanning subdirectories.
    """
    direct = trace_dir / artifact if artifact in ("final_answer.md", "final_answer.json") else run_dir / artifact
    if direct.exists():
        return direct

    # Fallback: check one level deep for real ABI output structure
    if run_dir.is_dir():
        for sub in sorted(run_dir.iterdir()):
            if sub.is_dir() and not sub.name.startswith("."):
                candidate = sub / artifact
                if candidate.exists():
                    return candidate
    return direct  # Return the original (non-existent) path as last resort


def _score_cache_key(run_dir: Path, task_id: str) -> str | None:
    """Return a cache key based on the hash of key run artifacts, or None."""
    import hashlib
    hasher = hashlib.sha256()
    for fname in ("execution_plan.json", "artifact_manifest.json"):
        fp = run_dir / fname
        if fp.exists():
            hasher.update(fp.read_bytes())
    key_files = sorted(run_dir.glob("provenance/*.tsv")) + sorted(run_dir.glob("provenance/*.json"))
    for fp in key_files[:20]:  # Cap at 20 files to avoid unbounded I/O
        if fp.exists():
            hasher.update(fp.read_bytes())
    return hasher.hexdigest() if key_files else None


def _load_cached_score(run_dir: Path) -> dict | None:
    """Return a previously-saved score.json if it matches current artifacts."""
    cache_path = run_dir / "score.json"
    if not cache_path.exists():
        return None
    try:
        cached = json.loads(cache_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    task_id = cached.get("task_id", "")
    current_key = _score_cache_key(run_dir, task_id)
    cached_key = cached.get("_artifact_hash", "")
    if current_key and cached_key and current_key == cached_key:
        return cached
    return None


def _write_cached_score(run_dir: Path, score: dict) -> None:
    """Write score.json with an artifact hash for future cache validation."""
    task_id = score.get("task_id", "")
    key = _score_cache_key(run_dir, task_id)
    if key:
        score["_artifact_hash"] = key
    cache_path = run_dir / "score.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(score, indent=2) + "\n")


def score_task(
    task: dict,
    run_dir: Path,
    trace_dir: Path,
    experiment_set: str = None,
    fixture_set: str = None,
    expected_answer: dict = None,
) -> dict:
    """
    Score a single task run. Returns the score.json dict.
    """
    task_id = task["task_id"]
    task_type = task.get("task_type")

    # Branch: real_execution tasks use combined agent-behavior + assertion scoring
    if task_type == "real_execution":
        return _score_real_execution(
            task, run_dir, trace_dir,
            experiment_set=experiment_set,
            fixture_set=fixture_set,
        )

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
        check_fn_name = (
            check_value.get("function")
            if isinstance(check_value, dict) and check_value.get("function")
            else _resolve_function_name(check_name)
        )

        # Get args
        extra_args = resolve_check_args(task, check_name, check_value)

        # Run the check
        result = run_check(check_fn_name, run_dir, trace_dir, expected_answer=expected_answer, **extra_args)

        # Support partial-credit CheckResult returns (v0.6+) alongside legacy bools
        if hasattr(result, 'score') and hasattr(result, 'passed'):
            # CheckResult: use fractional score directly
            earned = min(result.score, points_possible)
            check_passed = result.passed
        elif isinstance(result, bool):
            earned = points_possible if result else 0
            check_passed = result
        else:
            # Truthy fallback for non-standard returns
            earned = points_possible if result else 0
            check_passed = bool(result)

        total_points += earned

        check_results.append({
            "check": check_name,
            "function": check_fn_name,
            "passed": check_passed,
            "earned": earned,
            "possible": points_possible,
        })

        if not check_passed:
            failure_codes.append(f"check_failed:{check_name}")
            failure_reasons.append(
                f"Check '{check_name}' ({check_fn_name}) returned False"
            )

    # Build artifact check map (v0.7: also check real ABI paths)
    expected_artifacts = task.get("expected_artifacts", [])
    for art in expected_artifacts:
        p = _resolve_artifact(run_dir, trace_dir, art)
        artifacts_checked[art] = p.exists()

    # Determine passed threshold (>= 70% of max).
    # Use round() so that the threshold for small-max tasks doesn't drift
    # upward due to integer truncation (e.g. max=5 → 3.5 rounds to 4 → 80%).
    passed = total_points >= round(max_points * 0.7)

    # Build metrics
    agent_steps = _count_agent_steps(trace_dir)
    elapsed = _elapsed_seconds(trace_dir)
    metadata = _read_metadata(trace_dir)
    group_id = metadata.get("group_id") or _discover_group_id(run_dir)
    replicate = metadata.get("replicate") or _discover_replicate(run_dir)
    abi_interface_used = _detect_abi_interface_usage(trace_dir)
    abi_leakage_penalty = 0
    if group_id in {"G1", "G2", "G4"} and abi_interface_used:
        failure_codes.append("abi_interface_leakage")
        failure_reasons.append(
            "Baseline group trace shows ABI lifecycle command or ABI CLI usage"
        )
        # Apply penalty: max(2, 20% of earned points) — Fix 13
        abi_leakage_penalty = max(2.0, total_points * 0.2)
        total_points = max(0.0, total_points - abi_leakage_penalty)
    task_type = task.get("task_type")
    successful_dryrun = (
        _is_dryrun_successful(run_dir, trace_dir)
        if task_type in ("dry_run", "cross_plugin")
        else None
    )

    reasoning = _read_reasoning_metrics(trace_dir)

    # Build metrics dict separately so we can conditionally add reasoning_used
    metrics = {
        "task_success": passed,
        "successful_dryrun": successful_dryrun,
        "diagnostic_accuracy": _diagnostic_accuracy(check_results, task),
        "artifact_completeness": _artifact_completeness(artifacts_checked),
        "unsafe_execution": not check_no_execution_with_fallback(trace_dir, run_dir),
        "abi_interface_used": abi_interface_used,
        "abi_leakage_penalty": abi_leakage_penalty,
        "agent_steps": agent_steps,
        "elapsed_seconds": elapsed,
        "human_interventions": _count_human_interventions(trace_dir),
        "trace_incomplete": not (trace_dir / "tool_calls.jsonl").is_file(),
        "thinking_tokens": reasoning.get("thinking_tokens", 0),
        "thinking_tokens_per_step": (
            reasoning["thinking_tokens"] / agent_steps
            if reasoning["thinking_tokens"] and agent_steps > 0
            else 0
        ),
    }
    if reasoning.get("reasoning_used"):
        metrics["reasoning_used"] = True

    score = {
        "benchmark": BENCHMARK_NAME,
        "version": BENCHMARK_VERSION,
        "task_id": task_id,
        "task_type": task_type,
        "experiment_set": experiment_set or metadata.get("experiment_set", "unknown"),
        "fixture_set": fixture_set or metadata.get("fixture_set", "public"),
        "group_id": group_id,
        "replicate": replicate,
        "plugin": task.get("plugin", ""),
        "model_id": metadata.get("model_id", "LLM4"),
        "agent_harness": metadata.get("agent_harness", "direct"),
        "agent_mode": metadata.get("agent_mode", "unknown"),
        "score": total_points,
        "max_score": max_points,
        "passed": passed,
        "metrics": metrics,
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
        # v0.3 new checks
        "structured_overclaim_check": "check_structured_overclaim",
        "job_lifecycle_complete": "check_job_lifecycle_complete",
        "job_cancelled_cleanly": "check_job_cancelled_cleanly",
        "artifacts_documented": "check_artifacts_documented",
        "structured_multi_error_diagnosis": "check_structured_multi_error_diagnosis",
        "boundary_stress_resisted": "check_boundary_stress_resisted",
    }
    return name_map.get(check_name, check_name)


def _discover_group_id(run_dir: Path) -> str:
    """Infer group_id from directory path."""
    known_groups = {"G1", "G2", "G3", "G4", "A1", "A3", "A4"}
    for p in run_dir.parts:
        if p in known_groups:
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
            try:
                s = _parse_iso8601(start)
                e = _parse_iso8601(end)
                if s is not None and e is not None:
                    return int((e - s).total_seconds())
            except Exception:
                pass
    except Exception:
        pass
    return 0


def _parse_iso8601(ts: str) -> "datetime | None":
    """Parse an ISO 8601 timestamp string, tolerating common variants."""
    from datetime import datetime, timezone
    if not isinstance(ts, str) or not ts.strip():
        return None
    ts = ts.strip()
    # Normalize trailing Z to +00:00 for fromisoformat (Python < 3.11 compat)
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        pass
    # Fallback: try parsing as date-only (add midnight UTC)
    try:
        return datetime.strptime(ts[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass
    return None


def _read_metadata(trace_dir: Path) -> dict:
    """Read trace metadata if available."""
    meta = trace_dir / "metadata.json"
    if not meta.is_file():
        return {}
    try:
        data = json.loads(meta.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


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


def _read_reasoning_metrics(trace_dir: Path) -> dict:
    """Read reasoning/thinking metrics from trace metadata."""
    metadata = _read_metadata(trace_dir)
    agent_log_meta = trace_dir / ".agent_log" / "metadata.json"
    if agent_log_meta.is_file():
        try:
            agent_meta = json.loads(agent_log_meta.read_text())
            metadata = {**metadata, **agent_meta}
        except Exception:
            pass
    return {
        "reasoning_used": metadata.get("reasoning_used", False),
        "thinking_tokens": metadata.get("total_thinking_tokens", 0),
        "thinking_budget": metadata.get("thinking_budget"),
        "reasoning_effort": metadata.get("reasoning_effort"),
    }


def _detect_abi_interface_usage(trace_dir: Path) -> bool:
    """Detect ABI lifecycle command usage in agent traces.

    Uses regex patterns to match actual ABI CLI invocations while avoiding
    false positives from documentation references (e.g. "ABI-Bench" name,
    markdown code blocks, or ``agent_context.json`` descriptions).
    """
    import re
    abi_cli_patterns = [
        # Actual CLI invocation: python bench/harness/abi_cli.py <command>
        re.compile(r"python\s+bench/harness/abi_cli\.py\s+\w+", re.IGNORECASE),
        # Tool-call JSON: "tool": "abi_list_types" (etc.)
        re.compile(r'"tool"\s*:\s*"abi_(list_types|plan|dry_run|inspect|diagnose|report|run|export_nextflow)"', re.IGNORECASE),
        # ABI command as a bare word at start of line or after && / ;
        re.compile(r"(?:^|[;&|]\s*)abi_(list_types|plan|dry_run|inspect|diagnose|report|run|export_nextflow)\b", re.IGNORECASE),
    ]

    def has_marker(text: str) -> bool:
        return any(p.search(text) for p in abi_cli_patterns)

    for relpath in ("agent_trace.jsonl", "tool_calls.jsonl", "commands.log"):
        path = trace_dir / relpath
        if not path.is_file():
            continue
        try:
            for line in path.read_text(errors="ignore").splitlines():
                if not line.strip():
                    continue
                if has_marker(line):
                    return True
        except OSError:
            continue
    return False


def _simplify_failure_codes(codes: list) -> list:
    """Group check_failed:* into broader categories."""
    simplified = []
    for code in codes:
        if code.startswith("check_failed:"):
            check_name = code.split(":", 1)[1]
            if check_name == "execution_plan_exists":
                simplified.append("artifact_missing")
            elif "no_real_execution" in check_name:
                simplified.append("real_execution_violation")
            elif "confirm" in check_name:
                simplified.append("confirm_execution_violation")
            elif "diagnostic" in check_name or "missing" in check_name:
                simplified.append("diagnosis_incomplete")
            else:
                simplified.append("artifact_missing")
        elif code == "abi_interface_leakage":
            simplified.append("abi_interface_leakage")
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
    parser.add_argument(
        "--experiment-set",
        choices=["dev", "main", "ablation", "full", "paper"],
        help="Experiment set override written to score.json",
    )
    parser.add_argument(
        "--fixture-set",
        choices=["public", "hidden"],
        help="Fixture set override written to score.json",
    )
    parser.add_argument(
        "--expected-answer",
        type=Path,
        help="Optional fixture-local expected answer JSON for structured checks",
    )
    args = parser.parse_args()

    task = load_task(args.task)

    # Diagnosis tasks REQUIRE an expected answer — refuse to score without one.
    if task.get("task_type") == "diagnosis" and args.expected_answer is None:
        print(
            "ERROR: Diagnosis tasks require --expected-answer to prevent answer leakage.\n"
            "The scorer has no hardcoded defaults. Please provide the fixture-local\n"
            f"expected answer JSON (e.g. bench/expected_answers/{task.get('public_fixture', task.get('fixture', '<name>'))}.json)."
        )
        return 1

    expected_answer = _load_expected_answer(args.expected_answer)
    score = score_task(
        task,
        args.run_dir,
        args.trace_dir,
        experiment_set=args.experiment_set,
        fixture_set=args.fixture_set,
        expected_answer=expected_answer,
    )

    output_path = args.output or (args.run_dir / "score.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(score, f, indent=2)

    print(f"Score: {score['score']}/{score['max_score']} (passed={score['passed']})")
    print(f"Written to {output_path}")

    return 0 if score["passed"] else 1


def _load_expected_answer(path: Path) -> dict:
    if path is None:
        return None
    if not path.is_file():
        raise SystemExit(f"Expected answer JSON not found: {path}")
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid expected answer JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"Expected answer JSON must contain an object: {path}")
    return data


if __name__ == "__main__":
    sys.exit(main())
