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
import sys
from collections import defaultdict
from pathlib import Path


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

    scores = [s["score"] for s in group_scores]
    max_scores = [s["max_score"] for s in group_scores]
    # Normalize to 100
    normalized = [
        (s / m * 100) if m > 0 else 0
        for s, m in zip(scores, max_scores)
    ]

    passed = [s["passed"] for s in group_scores]
    dryrun_successes = [
        s.get("metrics", {}).get("successful_dryrun", False)
        for s in group_scores
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


def compute_per_task_scores(scores: list[dict]) -> list[dict]:
    """Compute per-task breakdown across replicates."""
    by_task = group_by(scores, "task_id")
    rows = []
    for task_id in sorted(by_task.keys()):
        task_scores = by_task[task_id]
        for ts in task_scores:
            rows.append({
                "group_id": ts.get("group_id", "unknown"),
                "task_id": ts.get("task_id", task_id),
                "replicate": ts.get("replicate", 1),
                "score": ts["score"],
                "max_score": ts["max_score"],
                "passed": ts["passed"],
                "failure_codes": ";".join(ts.get("failure_codes", [])),
            })
    return rows


def build_summary(scores: list[dict]) -> dict:
    """Build the summary.json structure."""
    by_group = group_by(scores, "group_id")

    groups_stats = {}
    for gid in ["G1", "G2", "G3", "A1", "A3", "A4"]:
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

    if g3.get("total_score_mean") and g1.get("total_score_mean"):
        claim_support["G3_beats_G1"] = (
            g3["total_score_mean"] - g1["total_score_mean"] >= 20
        )
    if g3.get("total_score_mean") and g2.get("total_score_mean"):
        claim_support["G3_beats_G2"] = (
            g3["total_score_mean"] - g2["total_score_mean"] >= 12
        )
    if g3.get("unsafe_execution_rate") is not None:
        claim_support["G3_unsafe_execution_zero"] = g3["unsafe_execution_rate"] == 0

    # Cross-plugin dry-run: check T03 and T10 both passed in G3
    g3scores = by_group.get("G3", [])
    t03_passed = any(s["task_id"] == "T03" and s["passed"] for s in g3scores)
    t10_passed = any(s["task_id"] == "T10" and s["passed"] for s in g3scores)
    claim_support["cross_plugin_dryrun_success"] = t03_passed and t10_passed

    return {
        "benchmark": "ABI-Bench",
        "version": "0.1",
        "commit": "REPLACE_WITH_COMMIT",
        "model_id": "LLM4",
        "agent_harness": "opencode",
        "replicates": _estimate_replicates(scores),
        "groups": groups_stats,
        "claim_support": claim_support,
    }


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
        for gid in ["G1", "G2", "G3", "A1", "A3", "A4"]:
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
    headers = ["group_id", "task_id", "replicate", "score", "max_score", "passed", "failure_codes"]
    with open(output_path, "w") as f:
        f.write("\t".join(headers) + "\n")
        for row in per_task:
            f.write("\t".join([
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
    args = parser.parse_args()

    scores = collect_scores(args.results)
    print(f"Collected {len(scores)} score files from {args.results}")

    if not scores:
        print("No scores found. Generate scores first with score_run.py.")
        return 1

    summary = build_summary(scores)
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
