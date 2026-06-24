from pathlib import Path

import yaml

from bench.validation.audit_benchmark import audit_benchmark


def _write_task(directory: Path, *, prompt: str = "Produce an execution plan.", max_score: int = 1):
    task = {
        "task_id": "T01",
        "task_type": "planning",
        "fixture": "",
        "max_score": max_score,
        "prompt": prompt,
        "expected_artifacts": ["execution_plan.json"],
        "scoring": {"execution_plan_exists": 1},
    }
    (directory / "T01_task.yaml").write_text(yaml.safe_dump(task))


def _write_suites(path: Path):
    data = {
        "suites": {
            "causal": {
                "claim_role": "primary_causal",
                "groups": ["G1", "G2", "G3", "G4"],
                "tasks": ["T01"],
            }
        }
    }
    path.write_text(yaml.safe_dump(data))


def test_repository_audit_has_no_errors():
    report = audit_benchmark()
    assert report["passed"], report["findings"]
    assert report["tasks_checked"] == 61
    assert report["suites_checked"] == 7
    assert report["summary"] == {"errors": 0, "warnings": 0}


def test_audit_rejects_treatment_name_in_causal_prompt(tmp_path):
    task_dir = tmp_path / "tasks"
    task_dir.mkdir()
    _write_task(task_dir, prompt="Use ABI plan to produce an execution plan.")
    suites = tmp_path / "suites.yaml"
    _write_suites(suites)

    report = audit_benchmark(task_dir, suites)

    assert not report["passed"]
    assert any(f["code"] == "treatment_named_in_causal_prompt" for f in report["findings"])


def test_audit_rejects_score_budget_mismatch(tmp_path):
    task_dir = tmp_path / "tasks"
    task_dir.mkdir()
    _write_task(task_dir, max_score=2)
    suites = tmp_path / "suites.yaml"
    _write_suites(suites)

    report = audit_benchmark(task_dir, suites)

    assert any(f["code"] == "score_budget_mismatch" for f in report["findings"])
