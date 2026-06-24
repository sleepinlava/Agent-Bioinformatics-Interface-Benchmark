#!/usr/bin/env python3
"""Audit ABI-Bench for design defects before an experiment is launched.

The audit deliberately separates fatal structural defects from threats to
validity.  It is deterministic and does not need model or tool execution.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
TASK_DIR = PROJECT_ROOT / "bench" / "tasks"
FIXTURE_DIRS = (
    PROJECT_ROOT / "bench" / "fixtures",
    PROJECT_ROOT / "bench" / "fixtures_hidden",
)
EXPECTED_DIR = PROJECT_ROOT / "bench" / "expected_answers"
SUITES_PATH = PROJECT_ROOT / "bench" / "evaluation_suites.yaml"
RUBRIC_PATH = PROJECT_ROOT / "bench" / "scoring" / "rubric.yaml"

_TREATMENT_PATTERN = re.compile(
    r"(?i)(?:\bABI\b|abi_cli|abi[-_ ]?(?:plan|dry[-_ ]?run|inspect|report|"
    r"query|doctor|run|list[-_ ]?types)|--confirm-execution)"
)


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    subject: str
    message: str


def _points(scoring: dict) -> float:
    return sum(
        value.get("points", 0) if isinstance(value, dict) else value
        for value in scoring.values()
    )


def _nested(data: dict, dotted: str):
    current = data
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _fixture_root(name: str) -> Path | None:
    for root in FIXTURE_DIRS:
        candidate = root / name
        if candidate.is_dir():
            return candidate
    return None


def _missing_resource_fixture_findings(task_id: str, fixture_name: str) -> list[Finding]:
    """Verify fixture truth is isolated and agrees with its expected answer."""
    findings = []
    fixture = _fixture_root(fixture_name)
    expected_path = EXPECTED_DIR / f"{fixture_name}.json"
    if fixture is None or not expected_path.is_file():
        findings.append(Finding(
            "error", "expected_answer_missing", task_id,
            f"diagnosis fixture {fixture_name!r} has no expected answer",
        ))
        return findings
    expected = json.loads(expected_path.read_text())
    if expected.get("cause") != "missing_resource":
        return findings
    config_path = fixture / "config.yaml"
    if not config_path.is_file():
        findings.append(Finding("error", "fixture_config_missing", task_id, str(config_path)))
        return findings
    config = yaml.safe_load(config_path.read_text()) or {}
    key = expected.get("config_key")
    expected_value = expected.get("path")
    if not key or _nested(config, key) != expected_value:
        findings.append(Finding(
            "error", "expected_answer_config_mismatch", task_id,
            f"{fixture_name}: {key!r} does not resolve to {expected_value!r}",
        ))
    elif (fixture / expected_value).exists():
        findings.append(Finding(
            "error", "expected_missing_resource_exists", task_id,
            f"{fixture_name}: expected missing path exists: {expected_value}",
        ))

    # A missing-resource fixture must not accidentally contain missing inputs.
    sheet = fixture / "sample_sheet.tsv"
    if sheet.is_file():
        rows = list(csv.DictReader(sheet.read_text().splitlines(), delimiter="\t"))
        for row in rows:
            for field in ("read1", "read2"):
                value = row.get(field)
                if value and not (fixture / value).is_file():
                    findings.append(Finding(
                        "error", "confounded_missing_input", task_id,
                        f"{fixture_name}: {field} also missing for {row.get('sample_id', '?')}: {value}",
                    ))
    for sample in config.get("samples", []) if isinstance(config.get("samples"), list) else []:
        for field in ("read1", "read2"):
            value = sample.get(field)
            if value and not (fixture / value).is_file():
                findings.append(Finding(
                    "error", "confounded_missing_input", task_id,
                    f"{fixture_name}: inline sample {field} also missing: {value}",
                ))
    return findings


def load_tasks(task_dir: Path = TASK_DIR) -> dict[str, dict]:
    tasks: dict[str, dict] = {}
    for path in sorted(task_dir.glob("*.yaml")):
        with open(path) as f:
            task = yaml.safe_load(f) or {}
        task_id = task.get("task_id")
        if task_id in tasks:
            raise ValueError(f"Duplicate task_id {task_id!r}: {path}")
        task["_path"] = str(path)
        tasks[task_id] = task
    return tasks


def load_suites(path: Path = SUITES_PATH) -> dict[str, dict]:
    with open(path) as f:
        return (yaml.safe_load(f) or {}).get("suites", {})


def audit_benchmark(
    task_dir: Path = TASK_DIR,
    suites_path: Path = SUITES_PATH,
) -> dict:
    findings: list[Finding] = []
    tasks = load_tasks(task_dir)
    suites = load_suites(suites_path)
    rubric = yaml.safe_load(RUBRIC_PATH.read_text()) or {}
    rubric_checks = rubric.get("rubric", {}).get("checks", {})
    from bench.scoring.checks import _FUNCTION_REGISTRY

    for task_id, task in tasks.items():
        subject = task_id or task.get("_path", "unknown")
        if not task_id or not re.fullmatch(r"T\d{2}", task_id):
            findings.append(Finding("error", "invalid_task_id", subject, "task_id must match TNN"))

        declared = task.get("max_score", 0)
        computed = _points(task.get("scoring", {}))
        if declared != computed:
            findings.append(Finding(
                "error", "score_budget_mismatch", subject,
                f"max_score={declared}, but scoring checks sum to {computed}",
            ))

        fixture = task.get("fixture")
        if fixture and not any((root / fixture).is_dir() for root in FIXTURE_DIRS):
            findings.append(Finding(
                "error", "fixture_missing", subject, f"fixture {fixture!r} does not exist",
            ))

        expected = task.get("expected_artifacts", [])
        if len(expected) != len(set(expected)):
            findings.append(Finding(
                "error", "duplicate_expected_artifact", subject,
                "expected_artifacts contains duplicate paths",
            ))

        if task.get("task_type") == "diagnosis":
            fixture_names = {
                name for name in (
                    task.get("public_fixture") or task.get("fixture"),
                    task.get("hidden_fixture"),
                ) if name
            }
            for fixture_name in sorted(fixture_names):
                findings.extend(_missing_resource_fixture_findings(subject, fixture_name))

        keyword_points = 0
        for check_name, value in task.get("scoring", {}).items():
            explicit_function = value.get("function") if isinstance(value, dict) else None
            function_name = explicit_function or rubric_checks.get(check_name, {}).get("function", check_name)
            points = value.get("points", 0) if isinstance(value, dict) else value
            if function_name == "check_final_answer_contains":
                keyword_points += points
            if function_name not in _FUNCTION_REGISTRY:
                findings.append(Finding(
                    "error", "unknown_scoring_function", subject,
                    f"{check_name!r} resolves to unknown function {function_name!r}",
                ))
        if declared and keyword_points / declared > 0.5:
            findings.append(Finding(
                "warning", "keyword_dominated_scoring", subject,
                f"{keyword_points}/{declared} points can be earned through keyword presence",
            ))

    membership = Counter()
    for suite_name, suite in suites.items():
        suite_tasks = suite.get("tasks", [])
        if len(suite_tasks) != len(set(suite_tasks)):
            findings.append(Finding(
                "error", "duplicate_suite_task", suite_name, "suite contains duplicate task IDs",
            ))
        for task_id in suite_tasks:
            membership[task_id] += 1
            if task_id not in tasks:
                findings.append(Finding(
                    "error", "unknown_suite_task", suite_name, f"unknown task {task_id}",
                ))

        if suite.get("claim_role") in {"primary_causal", "causal_robustness"}:
            required_groups = {"G1", "G2", "G3", "G4"}
            actual_groups = set(suite.get("groups", []))
            if actual_groups != required_groups:
                findings.append(Finding(
                    "error", "invalid_causal_groups", suite_name,
                    f"primary causal suite groups must be {sorted(required_groups)}",
                ))
            for task_id in suite_tasks:
                task = tasks.get(task_id)
                if task and _TREATMENT_PATTERN.search(task.get("prompt", "")):
                    findings.append(Finding(
                        "error", "treatment_named_in_causal_prompt", task_id,
                        "primary causal prompt names ABI or an ABI-specific command",
                    ))

    uncovered = sorted(task_id for task_id in tasks if not membership[task_id])
    if uncovered:
        findings.append(Finding(
            "warning", "tasks_outside_suites", "evaluation_suites.yaml",
            f"tasks not assigned to any suite: {', '.join(uncovered)}",
        ))

    severity_counts = Counter(item.severity for item in findings)
    return {
        "schema_version": "abi-bench.audit.v1",
        "tasks_checked": len(tasks),
        "suites_checked": len(suites),
        "passed": severity_counts["error"] == 0,
        "summary": {
            "errors": severity_counts["error"],
            "warnings": severity_counts["warning"],
        },
        "findings": [asdict(item) for item in findings],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ABI-Bench design and manifests")
    parser.add_argument("--output", type=Path, help="Optional JSON report path")
    parser.add_argument(
        "--strict", action="store_true",
        help="Return non-zero when structural or causal-validity errors are found",
    )
    args = parser.parse_args()

    report = audit_benchmark()
    rendered = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 1 if args.strict and not report["passed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
