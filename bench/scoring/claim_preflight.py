#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Claim Preflight Check

Checks that results are complete and consistent before a claim can be supported.
This must pass before setting primary_claim_supported=true in summary.json.

Usage:
    python bench/scoring/claim_preflight.py \\
      --results bench/results \\
      --experiment-set main \\
      --fixture-set public \\
      --min-replicates 3

For the paper-run claim workflow, use --fixture-set hidden instead.
Both values are valid; the choice depends on whether results were generated
with public or hidden fixtures.

Exit code 0 = preflight passed, 1 = preflight failed.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bench.harness.task_suites import load_suites, resolve_suite

PRIMARY_CAUSAL_TASKS = resolve_suite("causal_core_v0_8") or []

REQUIRED_GROUPS = {
    "main": ["G1", "G2", "G3", "G4"],
    "paper": ["G1", "G2", "G3", "G4"],
    "ablation": ["G3", "A1", "A3", "A4"],
}

REQUIRED_TASKS = {
    "main": PRIMARY_CAUSAL_TASKS,
    "paper": PRIMARY_CAUSAL_TASKS,
    "ablation": ["T03", "T04", "T05", "T06", "T07", "T08"],
}


def collect_scores(results_dir: Path) -> list[dict]:
    """Collect all score.json files."""
    scores = []
    for sf in results_dir.rglob("score.json"):
        try:
            with open(sf) as f:
                scores.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"WARNING: Failed to read {sf}: {e}", file=sys.stderr)
    return scores


def filter_scores(scores, experiment_set=None, fixture_set=None):
    """Filter scores by experiment_set and fixture_set."""
    if experiment_set:
        scores = [s for s in scores if s.get("experiment_set") == experiment_set]
    if fixture_set:
        scores = [s for s in scores if s.get("fixture_set") == fixture_set]
    return scores


class PreflightReport:
    def __init__(self):
        self.checks = []
        self.errors = []
        self.warnings = []

    def check(self, name: str, passed: bool, detail: str = ""):
        self.checks.append({"name": name, "passed": passed, "detail": detail})
        if not passed:
            self.errors.append(f"[{name}] {detail}")

    def warn(self, message: str):
        self.warnings.append(message)

    def all_passed(self) -> bool:
        return all(c["passed"] for c in self.checks)

    def print_report(self):
        print("\n" + "=" * 70)
        print("ABI-Bench Claim Preflight Report")
        print("=" * 70)

        for c in self.checks:
            status = "✓ PASS" if c["passed"] else "✗ FAIL"
            print(f"  {status}  {c['name']}")
            if c["detail"]:
                for line in c["detail"].split("\n"):
                    print(f"         {line}")

        if self.warnings:
            print("\nWarnings:")
            for w in self.warnings:
                print(f"  ⚠  {w}")

        if self.all_passed():
            print("\n✓ All preflight checks passed. Results are ready for claim evaluation.")
        else:
            print(f"\n✗ {len(self.errors)} preflight check(s) failed. Fix the above before claiming support.")

        print("=" * 70 + "\n")

    def to_dict(self):
        return {
            "passed": self.all_passed(),
            "checks": self.checks,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def run_preflight(
    results_dir: Path,
    experiment_set: str = "main",
    fixture_set: str = "public",
    min_replicates: int = 3,
    required_groups: list[str] = None,
    required_tasks: list[str] = None,
    require_same_agent_mode: bool = True,
    output_json: Path = None,
) -> PreflightReport:
    """Run all preflight checks and return the report."""
    report = PreflightReport()
    all_scores = collect_scores(results_dir)
    scores = filter_scores(all_scores, experiment_set=experiment_set, fixture_set=fixture_set)

    if required_groups is None:
        required_groups = REQUIRED_GROUPS.get(experiment_set, REQUIRED_GROUPS["main"])
    if required_tasks is None:
        required_tasks = REQUIRED_TASKS.get(experiment_set, REQUIRED_TASKS.get("main", []))

    if not scores:
        report.check("scores_exist", False,
                     f"No score files found in {results_dir} "
                     f"(experiment_set={experiment_set}, fixture_set={fixture_set})")
        report.print_report()
        return report

    report.check("scores_exist", True, f"Found {len(scores)} score file(s)")

    # ── Consistency checks ──────────────────────────────────────────────
    _check_consistency(scores, report, experiment_set, fixture_set)

    # ── Completeness checks ─────────────────────────────────────────────
    _check_completeness(scores, report, required_groups, required_tasks, min_replicates)

    # ── Quality checks ─────────────────────────────────────────────────
    _check_quality(scores, report, require_same_agent_mode)

    # ── Aggregate-specific checks ─────────────────────────────────────
    _check_aggregation_safety(scores, report, all_scores, experiment_set, fixture_set)

    report.print_report()

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"Preflight report written to {output_json}")

    return report


def _check_consistency(scores, report, experiment_set, fixture_set):
    """Check that metadata values are consistent across all scores."""
    meta_fields = {
        "experiment_set": "experiment_set",
        "fixture_set": "fixture_set",
        "agent_harness": "agent_harness",
        "agent_mode": "agent_mode",
    }
    for label, field in meta_fields.items():
        vals = {s.get(field) for s in scores if s.get(field) is not None}
        if len(vals) > 1:
            report.check(f"consistent_{label}", False,
                         f"Mixed {label} values: {vals}")
        elif len(vals) == 1:
            report.check(f"consistent_{label}", True, f"All {label} = {vals.pop()}")
        else:
            report.check(f"consistent_{label}", True, f"No {label} values found (may be ok)")

    models = sorted({s.get("model_id", "unknown") for s in scores})
    report.check(
        "model_ids_present",
        bool(models),
        f"Detected {len(models)} model(s): {models}",
    )

    # Specific check: experiment_set matches CLI arg
    if experiment_set:
        observed = {s.get("experiment_set") for s in scores}
        if observed != {experiment_set}:
            report.check("experiment_set_matches_cli", False,
                         f"CLI specified {experiment_set} but scores have {observed}")
        else:
            report.check("experiment_set_matches_cli", True,
                         f"All scores match CLI experiment_set={experiment_set}")

    # Specific check: fixture_set matches CLI arg
    if fixture_set:
        observed = {s.get("fixture_set") for s in scores}
        if observed != {fixture_set}:
            report.check("fixture_set_matches_cli", False,
                         f"CLI specified {fixture_set} but scores have {observed}")
        else:
            report.check("fixture_set_matches_cli", True,
                         f"All scores match CLI fixture_set={fixture_set}")


def _check_completeness(scores, report, required_groups, required_tasks, min_replicates):
    """Check every model × group × task randomized block is complete."""
    present = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for s in scores:
        model = s.get("model_id", "unknown")
        gid = s.get("group_id", "unknown")
        tid = s.get("task_id", "unknown")
        rep = s.get("replicate", 1)
        present[model][gid][tid].add(rep)

    models = sorted(present)

    # Check groups
    observed_groups = {
        gid for model_data in present.values() for gid in model_data
    }
    missing_groups = {
        (model, gid)
        for model in models
        for gid in required_groups
        if gid not in present[model]
    }
    unknown_groups = observed_groups - set(required_groups)
    observed_tasks = {
        tid
        for model_data in present.values()
        for group_data in model_data.values()
        for tid in group_data
    }
    extra_tasks = observed_tasks - set(required_tasks)

    if missing_groups:
        report.check("all_groups_present", False,
                     f"Missing model/group cells: {sorted(missing_groups)}")
    else:
        report.check("all_groups_present", True,
                     f"All {len(required_groups)} groups present for {len(models)} model(s)")

    if unknown_groups:
        report.check("no_unknown_groups", False,
                     f"Unknown groups in results: {sorted(unknown_groups)}. "
                     f"These will not appear in claim evaluation.")
    else:
        report.check("no_unknown_groups", True, "No unknown groups")

    report.check(
        "no_extra_tasks",
        not extra_tasks,
        "No tasks outside the registered suite"
        if not extra_tasks else f"Tasks outside the registered suite: {sorted(extra_tasks)}",
    )

    # Check tasks for each required group
    missing_task_cells = []
    for model in models:
        for gid in required_groups:
            group_tasks = set(present[model].get(gid, {}))
            for tid in set(required_tasks) - group_tasks:
                missing_task_cells.append((model, gid, tid))
    report.check(
        "all_tasks_present",
        not missing_task_cells,
        (
            f"All {len(required_tasks)} tasks present in every model/group cell"
            if not missing_task_cells
            else f"Missing {len(missing_task_cells)} model/group/task cells: {missing_task_cells[:10]}"
        ),
    )

    # Cross-group task uniformity
    required_task_set = set(required_tasks)
    task_sets = {
        (model, gid): set(present[model].get(gid, {})) & required_task_set
        for model in models for gid in required_groups
    }
    if len(set(frozenset(ts) for ts in task_sets.values())) > 1:
        lines = [f"  {model}/{gid}: {sorted(ts)}" for (model, gid), ts in sorted(task_sets.items())]
        report.check("cross_group_task_uniformity", False,
                     "Task sets differ across groups:\n" + "\n".join(lines))
    else:
        report.check("cross_group_task_uniformity", True,
                     f"All groups have identical task sets ({len(required_tasks)} tasks)")

    # Check replicates
    rep_counts = {}
    for model in models:
        for gid in required_groups:
            for tid in required_tasks:
                reps = present[model].get(gid, {}).get(tid, set())
                rep_counts[(model, gid, tid)] = len(reps)

    min_observed = min(rep_counts.values()) if rep_counts else 0
    max_observed = max(rep_counts.values()) if rep_counts else 0

    if min_observed < min_replicates:
        under_replicated = [cell for cell, n in rep_counts.items() if n < min_replicates]
        report.check("min_replicates", False,
                     f"Minimum {min_replicates} replicates required; "
                     f"observed {min_observed}-{max_observed}. "
                     f"Under-replicated: {len(under_replicated)} group/task combos")
    else:
        report.check("min_replicates", True,
                     f"All groups/tasks have ≥{min_replicates} replicates "
                     f"(observed {min_observed}-{max_observed})")

    # Cross-group replicate uniformity
    if min_observed != max_observed:
        report.check("cross_group_replicate_uniformity", False,
                     f"Replicate counts vary: {min_observed}–{max_observed}")
    else:
        report.check("cross_group_replicate_uniformity", True,
                     f"All groups have exactly {min_observed} replicates")


def _check_quality(scores, report, require_same_agent_mode):
    """Quality checks on the score data itself."""
    # Zero is a legitimate benchmark outcome. Reject only impossible ranges;
    # dropping zero-score runs would bias the estimated treatment effect upward.
    invalid_scores = [
        s for s in scores
        if not isinstance(s.get("score"), (int, float))
        or s.get("score", 0) < 0
        or s.get("score", 0) > s.get("max_score", 0)
    ]
    report.check(
        "score_values_in_range",
        not invalid_scores,
        "All scores are within [0, max_score]"
        if not invalid_scores else f"{len(invalid_scores)} score(s) are outside [0, max_score]",
    )
    zero_count = sum(s.get("score") == 0 for s in scores)
    if zero_count:
        report.warn(f"Retaining {zero_count} legitimate zero-score run(s) in the analysis")

    # Check agent_mode consistency
    if require_same_agent_mode:
        modes = {s.get("agent_mode") for s in scores if s.get("agent_mode")}
        if len(modes) > 1:
            report.check("uniform_agent_mode", False,
                         f"Mixed agent modes: {modes}. All groups should use the same mode.")
        elif len(modes) == 1:
            report.check("uniform_agent_mode", True, f"All scores use agent_mode={modes.pop()}")

    # Check that all scores have group_id, task_id, replicate
    missing_meta = [s for s in scores
                    if not all(k in s for k in ("group_id", "task_id", "replicate"))]
    if missing_meta:
        report.check("metadata_complete", False,
                     f"{len(missing_meta)} score(s) missing group_id/task_id/replicate")
    else:
        report.check("metadata_complete", True, "All scores have group_id, task_id, and replicate")


def _check_aggregation_safety(scores, report, all_scores, experiment_set, fixture_set):
    """Check that the filtered set is isolated from other experiments."""
    if not all_scores:
        return

    # Check that we're not accidentally mixing experiment sets
    filtered_count = len(scores)
    total_count = len(all_scores)
    if filtered_count < total_count:
        other_count = total_count - filtered_count
        report.check("filtered_isolation", True,
                     f"{filtered_count} scores match filter; {other_count} excluded "
                     f"(expected if multiple experiment/fixture sets exist)")
    else:
        report.check("filtered_isolation", True, "All scores match filter (single set detected)")

    # Check that all baseline scores don't have ABI CLI traces (G3-only capability)
    baseline_scores = [s for s in scores if s.get("group_id") in ("G1", "G2", "G4")]
    g3_scores = [s for s in scores if s.get("group_id") == "G3"]

    leaked = [
        s for s in baseline_scores
        if s.get("metrics", {}).get("abi_interface_used") is True
        or "abi_interface_leakage" in s.get("failure_codes", [])
    ]
    if leaked:
        examples = ", ".join(
            f"{s.get('group_id')}/{s.get('task_id')}/rep_{s.get('replicate')}"
            for s in leaked[:5]
        )
        report.check(
            "baseline_no_abi_usage",
            False,
            f"{len(leaked)} baseline score(s) used ABI interface: {examples}"
            + ("..." if len(leaked) > 5 else ""),
        )
    else:
        report.check("baseline_no_abi_usage", True, "No ABI interface usage detected in G1/G2/G4")

    if g3_scores:
        report.check("g3_has_scores", True, f"G3 has {len(g3_scores)} score(s)")
    else:
        report.check("g3_has_scores", False, "G3 has no scores — claim cannot be evaluated")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ABI-Bench Claim Preflight — validate result completeness and consistency"
    )
    parser.add_argument("--results", required=True, type=Path, help="Results directory")
    parser.add_argument(
        "--experiment-set",
        default="main",
        choices=["dev", "main", "ablation", "full", "paper"],
        help="Experiment set to validate (default: main)",
    )
    parser.add_argument(
        "--fixture-set",
        default="public",
        choices=["public", "hidden"],
        help="Fixture set to validate (default: public)",
    )
    parser.add_argument(
        "--min-replicates",
        type=int,
        default=3,
        help="Minimum required replicates per group/task (default: 3)",
    )
    parser.add_argument(
        "--groups",
        type=str,
        help="Comma-separated list of required groups (overrides experiment_set default)",
    )
    parser.add_argument(
        "--tasks",
        type=str,
        help="Comma-separated list of required tasks (overrides experiment_set default)",
    )
    parser.add_argument(
        "--suite",
        help="Use task and group requirements from bench/evaluation_suites.yaml",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write preflight report JSON to this path",
    )
    args = parser.parse_args()

    required_groups = None
    if args.groups:
        required_groups = [g.strip() for g in args.groups.split(",") if g.strip()]

    required_tasks = None
    if args.tasks:
        required_tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]

    if args.suite:
        suite = load_suites().get(args.suite)
        if suite is None:
            parser.error(f"Unknown evaluation suite: {args.suite}")
        if required_groups is None:
            required_groups = list(suite.get("groups", []))
        if required_tasks is None:
            required_tasks = list(suite.get("tasks", []))

    report = run_preflight(
        results_dir=args.results,
        experiment_set=args.experiment_set,
        fixture_set=args.fixture_set,
        min_replicates=args.min_replicates,
        required_groups=required_groups,
        required_tasks=required_tasks,
        output_json=args.output,
    )

    return 0 if report.all_passed() else 1


if __name__ == "__main__":
    sys.exit(main())
