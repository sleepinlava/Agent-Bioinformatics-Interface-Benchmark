#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Score Aggregator

Collects individual score.json files across all groups/tasks/replicates
and produces leaderboard.tsv and summary.json.

Usage:
    python bench/scoring/aggregate_scores.py \
      --results bench/results \
      --output bench/results/leaderboard.tsv \
      --summary bench/results/summary.json
"""

import argparse
import json
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

EXPECTED_GROUPS = {
    "main": ["G1", "G2", "G3"],
    "ablation": ["G3", "A1", "A3", "A4"],
    "full": ["G1", "G2", "G3"],
    "dev": ["G1", "G2", "G3", "A1", "A3", "A4"],
}

EXPECTED_TASKS = {
    "main": ["T01", "T02", "T03", "T05", "T06", "T08", "T09", "T10"],
    "ablation": ["T03", "T04", "T05", "T06", "T07", "T08"],
    "full": ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12"],
}


def collect_scores(results_dir: Path) -> list[dict]:
    """Collect all score.json files from the results directory tree."""
    scores = []
    for score_file in results_dir.rglob("score.json"):
        try:
            with open(score_file) as f:
                scores.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: Failed to read {score_file}: {e}", file=sys.stderr)
    return scores


def filter_scores(
    scores: list[dict],
    experiment_set: str | None = None,
    fixture_set: str | None = None,
) -> list[dict]:
    """Filter score records by experiment_set and/or fixture_set if requested.

    When fixture_set is specified, only scores with an explicit matching
    ``fixture_set`` field are included — scores that lack the field entirely
    are excluded (consistent with claim_preflight.py and compute_statistics.py).
    """
    if experiment_set is not None:
        scores = [s for s in scores if s.get("experiment_set", "unknown") == experiment_set]
    if fixture_set is not None:
        scores = [s for s in scores if s.get("fixture_set") == fixture_set]
    return scores


def group_by(scores: list[dict], key: str) -> dict:
    """Group score dicts by a top-level key."""
    grouped = defaultdict(list)
    for s in scores:
        val = s.get(key, "unknown")
        grouped[val].append(s)
    return dict(grouped)


def compute_group_stats(group_scores: list[dict]) -> dict:
    """Compute aggregate statistics for a group's scores."""
    if not group_scores:
        return {
            "total_score_mean": None,
            "total_score_std": None,
            "total_score_median": None,
            "task_success_rate": None,
            "successful_dryrun_rate": None,
            "diagnostic_accuracy": None,
            "unsafe_execution_rate": None,
            "artifact_completeness_mean": None,
            "median_agent_steps": None,
            "score_count": 0,
        }

    normalized = _normalized_totals_by_replicate(group_scores)

    passed = [s["passed"] for s in group_scores]
    dryrun_successes = [
        s.get("metrics", {}).get("successful_dryrun", False)
        for s in group_scores
        if _is_dryrun_score(s)
        and s.get("metrics", {}).get("successful_dryrun") is not None
    ]
    diag_accs = [
        s.get("metrics", {}).get("diagnostic_accuracy")
        for s in group_scores
        if s.get("metrics", {}).get("diagnostic_accuracy") is not None
    ]
    unsafe = [
        s.get("metrics", {}).get("unsafe_execution", False)
        for s in group_scores
    ]
    completeness = [
        s.get("metrics", {}).get("artifact_completeness", 0)
        for s in group_scores
    ]
    agent_steps = [
        s.get("metrics", {}).get("agent_steps", 0)
        for s in group_scores
    ]

    return {
        "total_score_mean": round(statistics.mean(normalized), 2) if normalized else None,
        "total_score_std": round(statistics.stdev(normalized), 2) if len(normalized) >= 2 else 0.0,
        "total_score_median": round(statistics.median(normalized), 2) if normalized else None,
        "task_success_rate": round(sum(passed) / len(passed), 3) if passed else None,
        "successful_dryrun_rate": round(sum(dryrun_successes) / len(dryrun_successes), 3) if dryrun_successes else None,
        "diagnostic_accuracy": round(statistics.mean(diag_accs), 3) if diag_accs else None,
        "unsafe_execution_rate": round(sum(unsafe) / len(unsafe), 3) if unsafe else None,
        "artifact_completeness_mean": round(statistics.mean(completeness), 3) if completeness else None,
        "median_agent_steps": int(statistics.median(agent_steps)) if agent_steps else None,
        "score_count": len(group_scores),
    }


def _normalized_totals_by_replicate(scores: list[dict]) -> list[float]:
    """Return total benchmark score per replicate, normalized to 100."""
    by_rep = defaultdict(list)
    for s in scores:
        by_rep[s.get("replicate", 1)].append(s)

    normalized = []
    for rep_scores in by_rep.values():
        score_sum = sum(s.get("score", 0) for s in rep_scores)
        max_sum = sum(s.get("max_score", 0) for s in rep_scores)
        normalized.append((score_sum / max_sum * 100) if max_sum > 0 else 0)
    return normalized


def _is_dryrun_score(score: dict) -> bool:
    """Identify dry-run task score records, including older score.json files."""
    return score.get("task_type") == "dry_run" or score.get("task_id") in {"T03", "T10"}


def compute_per_task_scores(scores: list[dict]) -> list[dict]:
    """Compute per-task breakdown across replicates."""
    by_task = group_by(scores, "task_id")
    rows = []
    for task_id in sorted(by_task.keys()):
        task_scores = by_task[task_id]
        for ts in task_scores:
            rows.append({
                "experiment_set": ts.get("experiment_set", "unknown"),
                "fixture_set": ts.get("fixture_set", "public"),
                "group_id": ts.get("group_id", "unknown"),
                "task_id": ts.get("task_id", task_id),
                "replicate": ts.get("replicate", 1),
                "score": ts["score"],
                "max_score": ts["max_score"],
                "passed": ts["passed"],
                "failure_codes": ";".join(ts.get("failure_codes", [])),
            })
    return rows


def build_summary(scores: list[dict], experiment_set: str | None = None, fixture_set: str | None = None) -> dict:
    """Build the summary.json structure."""
    by_group = group_by(scores, "group_id")
    groups = expected_groups_for(experiment_set)

    groups_stats = {}
    for gid in groups:
        gscores = by_group.get(gid, [])
        groups_stats[gid] = compute_group_stats(gscores)

    # Compute claim support
    g1 = groups_stats.get("G1", {})
    g2 = groups_stats.get("G2", {})
    g3 = groups_stats.get("G3", {})

    claim_support = {
        "G3_beats_G1": None,
        "G3_beats_G2": None,
        "G3_unsafe_execution_zero": None,
        "cross_plugin_dryrun_success": None,
    }

    if g3.get("total_score_mean") is not None and g1.get("total_score_mean") is not None:
        claim_support["G3_beats_G1"] = (
            g3["total_score_mean"] - g1["total_score_mean"] >= 20
        )
    if g3.get("total_score_mean") is not None and g2.get("total_score_mean") is not None:
        claim_support["G3_beats_G2"] = (
            g3["total_score_mean"] - g2["total_score_mean"] >= 12
        )
    if g3.get("total_score_mean") is not None:
        claim_support["G3_min_total_score"] = g3["total_score_mean"] >= 80
    else:
        claim_support["G3_min_total_score"] = None
    if g3.get("diagnostic_accuracy") is not None:
        claim_support["G3_min_diagnostic_accuracy"] = g3["diagnostic_accuracy"] >= 0.75
    else:
        claim_support["G3_min_diagnostic_accuracy"] = None
    if g3.get("unsafe_execution_rate") is not None:
        claim_support["G3_unsafe_execution_zero"] = g3["unsafe_execution_rate"] == 0

    # Cross-plugin dry-run: check T03 and T10 both passed in G3
    g3scores = by_group.get("G3", [])
    t03_success = _all_dryrun_successful(g3scores, "T03")
    t10_success = _all_dryrun_successful(g3scores, "T10")
    claim_support["cross_plugin_dryrun_success"] = t03_success and t10_success

    criteria = [
        claim_support.get("G3_min_total_score"),
        claim_support.get("G3_beats_G1"),
        claim_support.get("G3_beats_G2"),
        claim_support.get("G3_min_diagnostic_accuracy"),
        claim_support.get("G3_unsafe_execution_zero"),
        claim_support.get("cross_plugin_dryrun_success"),
    ]
    claim_support["primary_claim_supported"] = all(c is True for c in criteria)

    return {
        "benchmark": "ABI-Bench",
        "version": "0.1",
        "commit": _current_commit(),
        "model_id": _common_value(scores, "model_id", "mixed"),
        "agent_harness": _common_value(scores, "agent_harness", "mixed"),
        "experiment_set": experiment_set or "all",
        "fixture_set": fixture_set or _common_value(scores, "fixture_set", "mixed"),
        "replicates": _estimate_replicates(scores),
        "groups": groups_stats,
        "completeness": build_completeness_report(scores, experiment_set, fixture_set),
        "claim_support": claim_support,
    }


def expected_groups_for(experiment_set: str | None) -> list[str]:
    if experiment_set in EXPECTED_GROUPS:
        return EXPECTED_GROUPS[experiment_set]
    return ["G1", "G2", "G3", "A1", "A3", "A4"]


def expected_tasks_for(experiment_set: str | None, observed: list[str]) -> list[str]:
    if experiment_set in EXPECTED_TASKS:
        return EXPECTED_TASKS[experiment_set]
    return sorted(observed)


def build_completeness_report(
    scores: list[dict],
    experiment_set: str | None = None,
    fixture_set: str | None = None,
) -> dict:
    """Report missing groups, tasks, and replicates for the selected experiment set."""
    observed_groups = sorted({s.get("group_id", "unknown") for s in scores})
    observed_tasks = sorted({s.get("task_id", "unknown") for s in scores})
    observed_fixture_sets = sorted({s.get("fixture_set", "public") for s in scores})
    expected_groups = expected_groups_for(experiment_set)
    expected_tasks = expected_tasks_for(experiment_set, observed_tasks)

    replicates_by_key = defaultdict(set)
    for s in scores:
        replicates_by_key[(s.get("group_id"), s.get("task_id"))].add(s.get("replicate", 1))
    expected_replicates = sorted({s.get("replicate", 1) for s in scores}) or [1]

    missing = []
    for group_id in expected_groups:
        for task_id in expected_tasks:
            present = replicates_by_key.get((group_id, task_id), set())
            missing_reps = [rep for rep in expected_replicates if rep not in present]
            if missing_reps:
                missing.append({
                    "group_id": group_id,
                    "task_id": task_id,
                    "missing_replicates": missing_reps,
                })

    unknown_groups = [gid for gid in observed_groups if gid not in expected_groups]
    fixture_set_mixed = len(observed_fixture_sets) > 1
    return {
        "expected_groups": expected_groups,
        "observed_groups": observed_groups,
        "missing_groups": [gid for gid in expected_groups if gid not in observed_groups],
        "unknown_groups": unknown_groups,
        "expected_tasks": expected_tasks,
        "observed_tasks": observed_tasks,
        "missing_tasks": [tid for tid in expected_tasks if tid not in observed_tasks],
        "expected_replicates": expected_replicates,
        "missing_runs": missing,
        "observed_fixture_sets": observed_fixture_sets,
        "fixture_set_mixed": fixture_set_mixed,
        "complete": not missing and not unknown_groups and not fixture_set_mixed,
    }


def _all_dryrun_successful(scores: list[dict], task_id: str) -> bool:
    task_scores = [s for s in scores if s.get("task_id") == task_id]
    if not task_scores:
        return False
    vals = []
    for s in task_scores:
        metric = s.get("metrics", {}).get("successful_dryrun")
        vals.append(bool(metric) if metric is not None else bool(s.get("passed")))
    return all(vals)


def _current_commit() -> str:
    repo = Path(__file__).resolve().parent.parent.parent
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        dirty = subprocess.run(
            ["git", "diff", "--quiet"],
            cwd=repo,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ).returncode != 0
        return f"{commit}-dirty" if dirty else commit
    except Exception:
        return "unknown"


def _common_value(scores: list[dict], key: str, default: str) -> str:
    vals = {s.get(key) for s in scores if s.get(key)}
    if len(vals) == 1:
        return vals.pop()
    return default


def _estimate_replicates(scores: list[dict]) -> int:
    """Estimate replicate count by max replicate seen per task per group."""
    by_key = defaultdict(set)
    for s in scores:
        key = (s.get("group_id"), s.get("task_id"))
        by_key[key].add(s.get("replicate", 1))
    vals = [len(v) for v in by_key.values()]
    return max(vals) if vals else 0


def generate_leaderboard_tsv(summary: dict, output_path: Path):
    """Write leaderboard.tsv."""
    headers = [
        "group_id", "total_score_mean", "total_score_std", "task_success_rate",
        "successful_dryrun_rate", "diagnostic_accuracy", "unsafe_execution_rate",
        "artifact_completeness", "median_agent_steps",
    ]
    with open(output_path, "w") as f:
        f.write("\t".join(headers) + "\n")
        for gid in summary["groups"].keys():
            gs = summary["groups"].get(gid, {})
            if gs.get("score_count", 0) == 0:
                continue
            row = [
                gid,
                str(gs.get("total_score_mean", "NA")),
                str(gs.get("total_score_std", "NA")),
                str(gs.get("task_success_rate", "NA")),
                str(gs.get("successful_dryrun_rate", "NA")),
                str(gs.get("diagnostic_accuracy", "NA")),
                str(gs.get("unsafe_execution_rate", "NA")),
                str(gs.get("artifact_completeness_mean", "NA")),
                str(gs.get("median_agent_steps", "NA")),
            ]
            f.write("\t".join(row) + "\n")


def generate_per_task_tsv(per_task: list[dict], output_path: Path):
    """Write per_task_scores.tsv."""
    if not per_task:
        return
    headers = ["experiment_set", "fixture_set", "group_id", "task_id", "replicate", "score", "max_score", "passed", "failure_codes"]
    with open(output_path, "w") as f:
        f.write("\t".join(headers) + "\n")
        for row in per_task:
            f.write("\t".join([
                row["experiment_set"],
                row["fixture_set"],
                row["group_id"],
                row["task_id"],
                str(row["replicate"]),
                str(row["score"]),
                str(row["max_score"]),
                str(row["passed"]).lower(),
                row["failure_codes"],
            ]) + "\n")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Aggregate ABI-Bench scores")
    parser.add_argument("--results", required=True, type=Path, help="Results directory")
    parser.add_argument("--output", required=True, type=Path, help="Output leaderboard.tsv path")
    parser.add_argument("--summary", type=Path, help="Output summary.json path")
    parser.add_argument("--per-task", type=Path, help="Output per_task_scores.tsv path")
    parser.add_argument(
        "--experiment-set",
        choices=["dev", "main", "ablation", "full"],
        help="Only aggregate score files from this experiment set",
    )
    parser.add_argument(
        "--fixture-set",
        choices=["public", "hidden"],
        help="Only aggregate score files from this fixture set",
    )
    args = parser.parse_args()

    # Warn if fixture_set is mixed and no filter specified
    all_scores = collect_scores(args.results)
    scores = filter_scores(all_scores, args.experiment_set, args.fixture_set)
    print(f"Collected {len(all_scores)} score files from {args.results}")
    if args.experiment_set:
        print(f"Filtered to {len(scores)} score files for experiment_set={args.experiment_set}")
    if args.fixture_set:
        print(f"Filtered to {len(scores)} score files for fixture_set={args.fixture_set}")

    # Check for mixed fixture sets in the filtered scores
    observed_fixture_sets = {s.get("fixture_set", "public") for s in scores}
    if len(observed_fixture_sets) > 1:
        print(f"WARNING: Multiple fixture sets in aggregation: {observed_fixture_sets}")
        print("  Consider using --fixture-set to filter, or run separate aggregations per fixture set.")

    if not scores:
        print("No scores found. Generate scores first with score_run.py.")
        return 1

    summary = build_summary(scores, experiment_set=args.experiment_set, fixture_set=args.fixture_set)
    per_task = compute_per_task_scores(scores)

    # Write leaderboard
    generate_leaderboard_tsv(summary, args.output)
    print(f"Leaderboard written to {args.output}")

    # Write summary
    summary_path = args.summary or (args.output.parent / "summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Summary written to {summary_path}")

    # Write per-task scores
    if args.per_task:
        generate_per_task_tsv(per_task, args.per_task)
        print(f"Per-task scores written to {args.per_task}")

    # Print main results
    print("\n=== ABI-Bench v0.1 Leaderboard ===")
    fs_info = f" [fixture_set={args.fixture_set}]" if args.fixture_set else ""
    print(f"Experiment set: {args.experiment_set or 'all'}{fs_info}")
    for gid in ["G1", "G2", "G3"]:
        gs = summary["groups"].get(gid, {})
        if gs.get("score_count", 0) == 0:
            print(f"  {gid}: (no scores)")
            continue
        print(f"  {gid}: {gs['total_score_mean']} ± {gs['total_score_std']} "
              f"(success={gs['task_success_rate']}, dryrun={gs['successful_dryrun_rate']}, "
              f"diag_acc={gs['diagnostic_accuracy']}, unsafe={gs['unsafe_execution_rate']})")

    print("\nClaim support:", summary.get("claim_support", {}))

    return 0


if __name__ == "__main__":
    sys.exit(main())
