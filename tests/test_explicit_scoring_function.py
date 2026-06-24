import json

from bench.scoring.score_run import score_task


def test_score_task_honors_explicit_function_override(tmp_path):
    run_dir = tmp_path / "run"
    trace_dir = tmp_path / "trace"
    run_dir.mkdir()
    trace_dir.mkdir()
    (trace_dir / "final_answer.json").write_text(
        json.dumps({"cause": "missing_resource", "resource": "genome_index"})
    )
    task = {
        "task_id": "T99",
        "task_type": "validation",
        "max_score": 2,
        "scoring": {
            "arbitrary_check_label": {
                "points": 2,
                "function": "check_json_contract",
                "args": {
                    "equals": {"cause": "missing_resource"},
                    "nonempty_paths": ["resource"],
                },
            }
        },
    }

    score = score_task(task, run_dir, trace_dir)

    assert score["score"] == 2
    assert score["check_results"][0]["function"] == "check_json_contract"


def test_explicit_function_override_fails_when_contract_is_wrong(tmp_path):
    run_dir = tmp_path / "run"
    trace_dir = tmp_path / "trace"
    run_dir.mkdir()
    trace_dir.mkdir()
    (trace_dir / "final_answer.json").write_text(json.dumps({"cause": "wrong"}))
    task = {
        "task_id": "T99",
        "task_type": "validation",
        "max_score": 1,
        "scoring": {
            "label_not_a_function": {
                "points": 1,
                "function": "check_json_contract",
                "args": {"equals": {"cause": "missing_resource"}},
            }
        },
    }

    score = score_task(task, run_dir, trace_dir)

    assert score["score"] == 0
