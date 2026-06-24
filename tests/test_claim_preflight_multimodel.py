from bench.scoring.claim_preflight import PreflightReport, _check_completeness, _check_quality


def _score(model, group, task, replicate, score=1):
    return {
        "model_id": model,
        "group_id": group,
        "task_id": task,
        "replicate": replicate,
        "score": score,
        "max_score": 1,
        "agent_mode": "direct",
    }


def test_multimodel_completeness_is_checked_per_model():
    scores = [
        _score(model, group, task, replicate)
        for model in ("model-a", "model-b")
        for group in ("G1", "G3")
        for task in ("T01", "T02")
        for replicate in (1, 2)
    ]
    report = PreflightReport()

    _check_completeness(scores, report, ["G1", "G3"], ["T01", "T02"], 2)

    assert report.all_passed(), report.errors


def test_missing_model_group_cell_fails_completeness():
    scores = [
        _score("model-a", "G1", "T01", 1),
        _score("model-a", "G3", "T01", 1),
        _score("model-b", "G1", "T01", 1),
    ]
    report = PreflightReport()

    _check_completeness(scores, report, ["G1", "G3"], ["T01"], 1)

    assert not report.all_passed()
    assert any("model-b" in error and "G3" in error for error in report.errors)


def test_zero_score_is_valid_and_retained():
    report = PreflightReport()

    _check_quality([_score("model-a", "G1", "T01", 1, score=0)], report, True)

    assert report.all_passed(), report.errors
    assert any("zero-score" in warning for warning in report.warnings)


def test_extra_task_cannot_contaminate_registered_suite():
    scores = [
        _score("model-a", "G1", "T01", 1),
        _score("model-a", "G3", "T01", 1),
        _score("model-a", "G1", "T99", 1),
        _score("model-a", "G3", "T99", 1),
    ]
    report = PreflightReport()

    _check_completeness(scores, report, ["G1", "G3"], ["T01"], 1)

    assert not report.all_passed()
    assert any("T99" in error for error in report.errors)
