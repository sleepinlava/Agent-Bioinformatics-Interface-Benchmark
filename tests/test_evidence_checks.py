import json

import yaml

from bench.scoring.checks import (
    CheckResult,
    check_command_trace_evidence,
    check_cross_review_comparison,
    check_dual_runtime_comparison_evidence,
    check_json_contract,
    check_json_expected_records,
    check_no_large_download,
    check_plan_revision_artifacts,
    check_provenance_audit_evidence,
    check_reported_paths_exist,
    check_yaml_config_evidence,
)


def _answer(trace_dir, data):
    trace_dir.mkdir(parents=True, exist_ok=True)
    (trace_dir / "final_answer.json").write_text(json.dumps(data))


def test_json_contract_requires_structured_values(tmp_path):
    trace = tmp_path / "trace"
    _answer(trace, {"task_type": "audit", "checks": [{"valid": True}]})

    assert check_json_contract(
        trace,
        required_paths=["checks"],
        equals={"task_type": "audit"},
        min_items={"checks": 1},
    )
    assert not check_json_contract(trace, equals={"task_type": "planning"})


def test_json_contract_supports_order_insensitive_discovery_lists(tmp_path):
    trace = tmp_path / "trace"
    _answer(trace, {"plugins": ["wgs", "rnaseq", "plasmid"]})

    assert check_json_contract(
        trace,
        unordered_equals={"plugins": ["plasmid", "wgs", "rnaseq"]},
    )


def test_expected_records_reject_keyword_only_or_wrong_ground_truth(tmp_path):
    trace = tmp_path / "trace"
    _answer(trace, {"checks": [{"check": "shannon", "value": 9.9, "evidence": "shannon"}]})

    assert not check_json_expected_records(
        trace,
        list_path="checks",
        key_field="check",
        required_fields=["value", "evidence"],
        expected_records={"shannon": {"value": 3.2}},
    )


def test_reported_paths_are_cross_checked_with_size_and_inventory(tmp_path):
    run_dir = tmp_path / "run"
    trace = tmp_path / "trace"
    figures = run_dir / "figures"
    figures.mkdir(parents=True)
    figure = figures / "plot.svg"
    figure.write_text("<svg/>")
    _answer(trace, {"figures": [{"path": "figures/plot.svg", "size": figure.stat().st_size}]})

    assert check_reported_paths_exist(
        trace, run_dir, "figures", size_field="size", require_all_workspace_files="figures/*"
    )
    _answer(trace, {"figures": [{"path": "../../outside", "size": 0}]})
    assert not check_reported_paths_exist(trace, run_dir, "figures", size_field="size")


def test_command_evidence_uses_trace_not_final_answer(tmp_path):
    trace = tmp_path / "trace"
    trace.mkdir()
    (trace / "commands.log").write_text("abi-sciplot lint --spec figure.yaml\n")

    assert check_command_trace_evidence(trace, required_patterns=[r"sciplot\s+lint"])
    assert not check_command_trace_evidence(trace, required_patterns=[r"from-step\s+assembly"])


def test_download_safety_check_fails_closed_without_trace(tmp_path):
    assert not check_no_large_download(tmp_path)

    (tmp_path / "tool_calls.jsonl").write_text(
        json.dumps({"tool": "bash", "args": {"command": "ls resources"}}) + "\n"
    )
    assert check_no_large_download(tmp_path)


def test_yaml_repair_check_reads_material_config_change(tmp_path):
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"spades": {"kmers": "21,33,55"}}))

    assert check_yaml_config_evidence(
        tmp_path, forbidden_substrings={"spades.kmers": ["155"]}
    )
    assert not check_yaml_config_evidence(
        tmp_path, equals={"spades.kmers": "21,33,55,155"}
    )


def test_dual_runtime_check_treats_equal_empty_figures_as_invalid(tmp_path):
    run_dir = tmp_path / "run"
    trace = tmp_path / "trace"
    for runtime in ("local_run", "docker_run"):
        root = run_dir / "results" / runtime
        (root / "provenance").mkdir(parents=True)
        (root / "tables").mkdir()
        (root / "figures").mkdir()
        (root / "provenance" / "commands.tsv").write_text("step\nqc\n")
        (root / "tables" / "plasmid_annotations.tsv").write_text("id\np1\n")
        (root / "figures" / "plasmid_map.png").write_bytes(b"")
    _answer(trace, {
        "command_comparison": {"match": True},
        "table_comparison": {"match": True},
        "figure_comparison": {"match": False},
        "substantially_equivalent": False,
        "rationale": "Figure artifacts are empty.",
    })

    assert check_dual_runtime_comparison_evidence(trace, run_dir)


def test_plan_revision_requires_two_different_parseable_plans(tmp_path):
    run_dir = tmp_path / "run"
    trace = tmp_path / "trace"
    plans = run_dir / "plans"
    plans.mkdir(parents=True)
    (plans / "original_plan.json").write_text(json.dumps({"steps": [{"id": "qc"}]}))
    (plans / "revised_plan.json").write_text(
        json.dumps({"steps": [{"id": "qc"}, {"id": "report"}]})
    )
    _answer(trace, {
        "reviewer_findings": [{"id": 1}],
        "revisions_made": ["add report"],
        "original_step_count": 1,
        "revised_step_count": 2,
    })

    assert check_plan_revision_artifacts(trace, run_dir)


def test_cross_review_requires_supplied_review_ids(tmp_path):
    run_dir = tmp_path / "run"
    trace = tmp_path / "trace"
    reviews = run_dir / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "review_a.json").write_text(json.dumps({"review_id": "review_a"}))
    (reviews / "review_b.json").write_text(json.dumps({"review_id": "review_b"}))
    _answer(trace, {
        "source_reviews": ["review_a", "review_b"],
        "robust_findings": ["dry-run only"],
        "model_dependent_findings": [],
        "uncertainty_sources": ["missing checksums"],
        "confidence_summary": "High confidence in execution status.",
    })

    assert check_cross_review_comparison(trace, run_dir)
    _answer(trace, {
        "source_reviews": ["imagined_review"],
        "robust_findings": ["dry-run only"],
        "model_dependent_findings": [],
        "uncertainty_sources": ["missing checksums"],
        "confidence_summary": "High",
    })
    assert not check_cross_review_comparison(trace, run_dir)


def test_legacy_check_result_constructor_remains_supported():
    result = CheckResult(True, score_on_pass=2, details="ok")

    assert result.passed
    assert result.score == 2
    assert result.details == {"message": "ok"}


def test_provenance_audit_matches_incomplete_fixture(tmp_path):
    fixture = tmp_path / "fixture"
    provenance = fixture / "provenance"
    provenance.mkdir(parents=True)
    (provenance / "commands.tsv").write_text("step_id\ttool_id\tstatus\nqc\tfastp\tdry_run\n")
    (provenance / "resolved_inputs.tsv").write_text(
        "input_id\tpath\tstatus\nreads\tPLACEHOLDER:reads.fastq\tmissing\n"
    )
    (provenance / "tool_versions.tsv").write_text("tool_id\tversion\nfastp\t0.23\n")
    (provenance / "progress.jsonl").write_text(
        json.dumps({"step_id": "qc", "status": "dry_run", "timestamp": None}) + "\n"
    )
    (provenance / "run_summary.json").write_text(
        json.dumps({"total_steps": 1, "dry_run": 1, "skipped": 0, "failed": 0})
    )
    trace = tmp_path / "trace"
    _answer(trace, {
        "checks": [
            {"dimension": "commands", "valid": False},
            {"dimension": "resolved_inputs", "valid": False},
            {"dimension": "tool_versions", "valid": True},
            {"dimension": "checksums", "valid": False},
            {"dimension": "progress", "valid": False},
            {"dimension": "run_summary", "valid": True},
        ],
        "overall_complete": False,
    })

    assert check_provenance_audit_evidence(trace, fixture)
