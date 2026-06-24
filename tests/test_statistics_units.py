from bench.scoring.aggregate_scores import _compute_per_plugin_breakdown, compute_group_stats
from bench.scoring.compute_statistics import (
    _clustered_paired_delta_ci,
    _normalized_totals_by_unit,
    _paired_total_deltas,
    filter_scores,
)


def _score(model, group, replicate, task, score, maximum=10):
    return {
        "model_id": model,
        "group_id": group,
        "replicate": replicate,
        "task_id": task,
        "score": score,
        "max_score": maximum,
        "passed": score >= maximum * 0.7,
        "metrics": {},
    }


def test_totals_do_not_mix_models_with_same_replicate_number():
    scores = [
        _score("model-a", "G3", 1, "T01", 10),
        _score("model-b", "G3", 1, "T01", 0),
    ]

    assert sorted(_normalized_totals_by_unit(scores)) == [0.0, 100.0]
    stats = compute_group_stats(scores)
    assert stats["total_score_mean"] == 50.0
    assert stats["total_score_std"] > 0


def test_paired_delta_matches_on_model_and_replicate():
    scores = [
        _score("model-a", "G3", 1, "T01", 10),
        _score("model-a", "G1", 1, "T01", 0),
        _score("model-b", "G3", 1, "T01", 0),
        _score("model-b", "G1", 1, "T01", 10),
    ]

    assert sorted(_paired_total_deltas(scores, "G3", "G1")) == [-100.0, 100.0]
    effect = _clustered_paired_delta_ci(scores, "G3", "G1", n_bootstrap=200)
    assert effect["mean"] == 0.0
    assert effect["n_models"] == 2
    assert effect["wins"] == 1
    assert effect["losses"] == 1


def test_incomplete_task_pairs_are_excluded():
    scores = [
        _score("model-a", "G3", 1, "T01", 10),
        _score("model-a", "G3", 1, "T02", 10),
        _score("model-a", "G1", 1, "T01", 0),
    ]

    assert _paired_total_deltas(scores, "G3", "G1") == []
    effect = _clustered_paired_delta_ci(scores, "G3", "G1", n_bootstrap=20)
    assert effect["n_samples"] == 0
    assert effect["excluded_incomplete_pairs"] == 1


def test_score_filter_can_isolate_registered_task_ids():
    scores = [
        _score("model-a", "G3", 1, "T01", 10),
        _score("model-a", "G3", 1, "T51", 10),
    ]

    filtered = filter_scores(scores, task_ids=["T01"])

    assert [score["task_id"] for score in filtered] == ["T01"]


def test_per_plugin_breakdown_uses_canonical_score_field():
    scores = [
        {
            **_score("model-a", "G3", 1, "T01", 8, maximum=10),
            "plugin": "rnaseq_expression",
        }
    ]

    breakdown = _compute_per_plugin_breakdown(scores)

    assert breakdown["rnaseq_expression"]["G3"]["mean"] == 80.0
