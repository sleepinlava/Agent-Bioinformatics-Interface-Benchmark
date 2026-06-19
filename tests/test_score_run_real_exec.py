"""Tests for real_execution task scoring in score_run.py."""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# Allow importing from bench/scoring
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bench", "scoring"))
from score_run import (  # noqa: E402
    _score_real_execution,
    _load_final_answer_json,
    score_task,
    load_task,
)


class TestLoadFinalAnswerJson:
    def test_loads_from_trace_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_dir = Path(tmp) / "trace"
            trace_dir.mkdir()
            data = {"schema_version": "abi-bench.final_answer.v1", "pipeline_completed": True}
            (trace_dir / "final_answer.json").write_text(json.dumps(data))

            result = _load_final_answer_json(trace_dir)
            assert result == data

    def test_falls_back_to_run_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_dir = Path(tmp) / "trace"
            run_dir = Path(tmp) / "run"
            trace_dir.mkdir()
            run_dir.mkdir()
            data = {"pipeline_completed": False}
            (run_dir / "final_answer.json").write_text(json.dumps(data))

            result = _load_final_answer_json(trace_dir, run_dir)
            assert result == data

    def test_returns_none_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_dir = Path(tmp) / "trace"
            trace_dir.mkdir()
            result = _load_final_answer_json(trace_dir)
            assert result is None

    def test_handles_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace_dir = Path(tmp) / "trace"
            trace_dir.mkdir()
            (trace_dir / "final_answer.json").write_text("not json")

            result = _load_final_answer_json(trace_dir)
            assert result is None


class TestScoreRealExecution:
    def _make_real_exec_task(self, tmp: str, final_answer: dict = None, assertions: dict = None):
        """Create task YAML and run/trace dirs for a real_execution task."""
        run_dir = Path(tmp) / "run"
        trace_dir = Path(tmp) / "trace"
        run_dir.mkdir()
        trace_dir.mkdir()

        # Write task YAML
        task = {
            "task_id": "T31",
            "task_type": "real_execution",
            "plugin": "metagenomic_plasmid",
            "max_score": 15,
            "scoring": {
                "pipeline_completed": {"points": 3, "function": "check_pipeline_completed"},
                "assertions_validated": {"points": 6, "function": "check_assertions_validated"},
                "discrepancy_analyzed": {"points": 4, "function": "check_discrepancy_analyzed"},
                "provenance_quality": {"points": 2, "function": "check_provenance_quality"},
            },
        }
        task_path = Path(tmp) / "task.yaml"
        with open(task_path, "w") as f:
            yaml.dump(task, f)

        # Write final_answer.json
        if final_answer is not None:
            (trace_dir / "final_answer.json").write_text(json.dumps(final_answer))

        # Write expected_assertions.yaml if provided
        if assertions is not None:
            (run_dir / "expected_assertions.yaml").write_text(yaml.dump(assertions))

        # Write trace metadata
        (trace_dir / "metadata.json").write_text(json.dumps({
            "group_id": "G3",
            "replicate": 1,
            "model_id": "test-model",
        }))

        return task, run_dir, trace_dir

    def test_scores_successful_real_execution(self):
        """All v0.5 agent checks pass and v0.6 assertions pass."""
        with tempfile.TemporaryDirectory() as tmp:
            final_answer = {
                "schema_version": "abi-bench.final_answer.v1",
                "pipeline_completed": True,
                "exit_code": 0,
                "assertions": {"total": 10, "passed": 8, "failed": 2},
                "discrepancy_summary": "Two assertions failed due to empty contig fields in test fixture.",
                "failed_assertions": [
                    {
                        "assertion": "min_cds",
                        "expected": 100,
                        "actual": 0,
                        "analysis": "Empty CDS count due to dry-run placeholder genome.",
                    },
                ],
                "provenance_accessible": True,
            }
            task, run_dir, trace_dir = self._make_real_exec_task(tmp, final_answer=final_answer)

            score = _score_real_execution(task, run_dir, trace_dir)

            assert score["task_id"] == "T31"
            assert score["task_type"] == "real_execution"
            assert score["max_score"] == 15
            # All 4 agent checks pass: 3 + 6 + 4 + 2 = 15
            assert score["score"] == 15
            assert score["passed"] is True
            assert len(score["check_results"]) == 4

            # Verify each check
            by_name = {c["check"]: c for c in score["check_results"]}
            assert by_name["pipeline_completed"]["passed"] is True
            assert by_name["pipeline_completed"]["earned"] == 3
            assert by_name["assertions_validated"]["passed"] is True
            assert by_name["assertions_validated"]["earned"] == 6
            assert by_name["discrepancy_analyzed"]["passed"] is True
            assert by_name["discrepancy_analyzed"]["earned"] == 4
            assert by_name["provenance_quality"]["passed"] is True
            assert by_name["provenance_quality"]["earned"] == 2

    def test_scores_failing_agent_checks(self):
        """Agent checks fail when final_answer is missing or incomplete."""
        with tempfile.TemporaryDirectory() as tmp:
            # Empty final_answer — all v0.5 checks should fail
            final_answer = {}
            task, run_dir, trace_dir = self._make_real_exec_task(tmp, final_answer=final_answer)

            score = _score_real_execution(task, run_dir, trace_dir)

            assert score["score"] == 0
            assert score["passed"] is False
            assert all(not c["passed"] for c in score["check_results"])

    def test_scores_partial_agent_checks(self):
        """Some agent checks pass, some fail."""
        with tempfile.TemporaryDirectory() as tmp:
            final_answer = {
                "pipeline_completed": True,
                "exit_code": 0,
                # assertions_validated will fail (no assertions section)
                # discrepancy_analyzed will fail (no discrepancy_summary or failed_assertions)
                # provenance_quality will fail (no provenance_accessible)
            }
            task, run_dir, trace_dir = self._make_real_exec_task(tmp, final_answer=final_answer)

            score = _score_real_execution(task, run_dir, trace_dir)

            # Only pipeline_completed passes: 3/15
            assert score["score"] == 3
            assert score["passed"] is False  # 3/15 = 20% < 70%

            by_name = {c["check"]: c for c in score["check_results"]}
            assert by_name["pipeline_completed"]["passed"] is True
            assert by_name["assertions_validated"]["passed"] is False
            assert by_name["discrepancy_analyzed"]["passed"] is False
            assert by_name["provenance_quality"]["passed"] is False

    def test_combines_assertion_checks_when_present(self):
        """When scoring includes v0.6 assertion checks, they are evaluated."""
        with tempfile.TemporaryDirectory() as tmp:
            final_answer = {
                "pipeline_completed": True,
                "exit_code": 0,
                "assertions": {"total": 3, "passed": 2, "failed": 1},
                "discrepancy_summary": "One assertion failed: min_contigs expected >= 50, got 12.",
                "provenance_accessible": True,
            }
            # Create a task with both v0.5 and v0.6 checks
            task = {
                "task_id": "T32",
                "task_type": "real_execution",
                "plugin": "metagenomic_plasmid",
                "max_score": 25,
                "scoring": {
                    "pipeline_completed": {"points": 3, "function": "check_pipeline_completed"},
                    "assertions_validated": {"points": 6, "function": "check_assertions_validated"},
                    "discrepancy_analyzed": {"points": 4, "function": "check_discrepancy_analyzed"},
                    "provenance_quality": {"points": 2, "function": "check_provenance_quality"},
                    "check_pipeline_outputs_match_assertions": {"points": 8, "function": "check_pipeline_outputs_match_assertions"},
                    "check_per_category_breakdown": {"points": 2, "function": "check_per_category_breakdown"},
                },
            }
            run_dir = Path(tmp) / "run"
            trace_dir = Path(tmp) / "trace"
            run_dir.mkdir()
            trace_dir.mkdir()
            (trace_dir / "final_answer.json").write_text(json.dumps(final_answer))
            (trace_dir / "metadata.json").write_text(json.dumps({"group_id": "G3"}))

            # Create expected_assertions.yaml with passing assertions
            results_dir = run_dir / "results" / "bench-test"
            prov_dir = results_dir / "provenance"
            os.makedirs(prov_dir)
            # Write commands.tsv (3 data rows for min_commands >= 3 assertion)
            (prov_dir / "commands.tsv").write_text(
                "step_id\ttool_id\tstatus\nexit_code\n"
                "qc_fastp\tfastp\tsuccess\t0\n"
                "assembly\tmegahit\tsuccess\t0\n"
                "prodigal\tprodigal\tsuccess\t0\n"
            )
            (prov_dir / "run_summary.json").write_text(json.dumps({"total_steps": 3}))

            assertions = {
                "metagenomic_plasmid": {
                    "provenance": {"min_commands": 2, "run_summary_exists": True},
                }
            }
            (run_dir / "expected_assertions.yaml").write_text(yaml.dump(assertions))

            score = _score_real_execution(task, run_dir, trace_dir)

            # All v0.5 checks pass: 3+6+4+2 = 15
            # v0.6 assertion checks also run and should pass
            assert len(score["check_results"]) == 6

            by_name = {c["check"]: c for c in score["check_results"]}
            assert by_name["pipeline_completed"]["passed"] is True
            assert by_name["check_pipeline_outputs_match_assertions"]["passed"] is True
            assert by_name["check_per_category_breakdown"]["passed"] is True

    def test_unknown_check_function_handled_gracefully(self):
        """Unknown check function names produce a failure but don't crash."""
        with tempfile.TemporaryDirectory() as tmp:
            final_answer = {"pipeline_completed": True, "exit_code": 0}
            task = {
                "task_id": "T99",
                "task_type": "real_execution",
                "plugin": "test",
                "max_score": 5,
                "scoring": {
                    "nonexistent_check": {"points": 5, "function": "check_does_not_exist"},
                },
            }
            run_dir = Path(tmp) / "run"
            trace_dir = Path(tmp) / "trace"
            run_dir.mkdir()
            trace_dir.mkdir()
            (trace_dir / "final_answer.json").write_text(json.dumps(final_answer))
            (trace_dir / "metadata.json").write_text(json.dumps({"group_id": "G3"}))

            score = _score_real_execution(task, run_dir, trace_dir)

            assert score["score"] == 0
            assert score["passed"] is False
            assert len(score["check_results"]) == 1
            assert score["check_results"][0]["passed"] is False
            assert "Unknown check function" in score["failure_reasons"][0]

    def test_assertion_check_exception_handled_gracefully(self):
        """Exception in assertion check produces a failure but doesn't crash."""
        with tempfile.TemporaryDirectory() as tmp:
            final_answer = {
                "pipeline_completed": True,
                "exit_code": 0,
                "assertions": {"total": 1, "passed": 0, "failed": 1},
                "discrepancy_summary": "Test summary with enough length for discrepancy check.",
                "provenance_accessible": True,
            }
            task = {
                "task_id": "T33",
                "task_type": "real_execution",
                "plugin": "test",
                "max_score": 23,
                "scoring": {
                    "pipeline_completed": {"points": 3, "function": "check_pipeline_completed"},
                    "assertions_validated": {"points": 6, "function": "check_assertions_validated"},
                    "discrepancy_analyzed": {"points": 4, "function": "check_discrepancy_analyzed"},
                    "provenance_quality": {"points": 2, "function": "check_provenance_quality"},
                    "check_pipeline_outputs_match_assertions": {"points": 8, "function": "check_pipeline_outputs_match_assertions"},
                },
            }
            run_dir = Path(tmp) / "run"
            trace_dir = Path(tmp) / "trace"
            run_dir.mkdir()
            trace_dir.mkdir()
            (trace_dir / "final_answer.json").write_text(json.dumps(final_answer))
            (trace_dir / "metadata.json").write_text(json.dumps({"group_id": "G3"}))

            # No expected_assertions.yaml — the assertion check should handle this
            score = _score_real_execution(task, run_dir, trace_dir)

            # v0.5 checks should all pass
            # v0.6 check should fail gracefully (no expected_assertions.yaml)
            assert len(score["check_results"]) == 5

            by_name = {c["check"]: c for c in score["check_results"]}
            assert by_name["pipeline_completed"]["passed"] is True
            assert by_name["check_pipeline_outputs_match_assertions"]["passed"] is False

    def test_score_task_branches_to_real_execution(self):
        """score_task() delegates to _score_real_execution for real_execution task_type."""
        with tempfile.TemporaryDirectory() as tmp:
            final_answer = {
                "pipeline_completed": True,
                "exit_code": 0,
                "assertions": {"total": 2, "passed": 2, "failed": 0},
                "discrepancy_summary": "All assertions passed successfully. No discrepancies found.",
                "provenance_accessible": True,
            }
            task = {
                "task_id": "T31",
                "task_type": "real_execution",
                "plugin": "metagenomic_plasmid",
                "max_score": 15,
                "scoring": {
                    "pipeline_completed": {"points": 3, "function": "check_pipeline_completed"},
                    "assertions_validated": {"points": 6, "function": "check_assertions_validated"},
                    "discrepancy_analyzed": {"points": 4, "function": "check_discrepancy_analyzed"},
                    "provenance_quality": {"points": 2, "function": "check_provenance_quality"},
                },
            }
            run_dir = Path(tmp) / "run"
            trace_dir = Path(tmp) / "trace"
            run_dir.mkdir()
            trace_dir.mkdir()
            (trace_dir / "final_answer.json").write_text(json.dumps(final_answer))
            (trace_dir / "metadata.json").write_text(json.dumps({"group_id": "G3"}))

            score = score_task(task, run_dir, trace_dir)

            assert score["task_type"] == "real_execution"
            assert score["score"] == 15
            assert score["passed"] is True
            assert len(score["check_results"]) == 4

    def test_score_task_skips_real_exec_branch_for_other_types(self):
        """score_task() does NOT use real_exec branch for non-real_exec task types."""
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "T01",
                "task_type": "discovery",
                "plugin": "metagenomic_plasmid",
                "max_score": 10,
                "scoring": {
                    "execution_plan_exists": 2,
                },
            }
            run_dir = Path(tmp) / "run"
            trace_dir = Path(tmp) / "trace"
            run_dir.mkdir()
            trace_dir.mkdir()
            (trace_dir / "metadata.json").write_text(json.dumps({"group_id": "G1"}))

            score = score_task(task, run_dir, trace_dir)

            # Should use standard scoring, not real_exec
            assert score["task_type"] == "discovery"
            # execution_plan.json doesn't exist, so score should be 0
            assert score["score"] == 0

    def test_minimal_task_without_final_answer(self):
        """Scoring works even when final_answer.json is completely missing."""
        with tempfile.TemporaryDirectory() as tmp:
            task = {
                "task_id": "T31",
                "task_type": "real_execution",
                "plugin": "metagenomic_plasmid",
                "max_score": 15,
                "scoring": {
                    "pipeline_completed": {"points": 3, "function": "check_pipeline_completed"},
                },
            }
            run_dir = Path(tmp) / "run"
            trace_dir = Path(tmp) / "trace"
            run_dir.mkdir()
            trace_dir.mkdir()
            (trace_dir / "metadata.json").write_text(json.dumps({"group_id": "G3"}))

            score = _score_real_execution(task, run_dir, trace_dir)

            # check_pipeline_completed should fail with empty final_answer
            assert score["check_results"][0]["passed"] is False
            assert score["score"] == 0
