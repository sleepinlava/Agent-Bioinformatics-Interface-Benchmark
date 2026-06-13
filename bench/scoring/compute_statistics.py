#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Statistical Analysis

Computes bootstrap confidence intervals, per-task effect sizes (Cohen's d),
and failure taxonomy from aggregated score data.

Usage:
    python bench/scoring/compute_statistics.py \\
      --results bench/results \\
      --experiment-set main \\
      --fixture-set public \\
      --output bench/results/statistics.json

Output fields:
  - bootstrap_ci: 95% CI for each group's total normalized score
  - effect_sizes: per-task Cohen's d between comparison pairs
  - failure_taxonomy: aggregation of failure_codes across groups
  - tables: paper-ready markdown tables for results section
"""

import argparse
import json
import math
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path


# ── Bootstrap CI ─────────────────────────────────────────────────────────────

def bootstrap_ci(
    values: list[float],
    n_bootstrap: int = 10000,
    ci: float = 0.95,
    seed: int = 42,
) -> dict:
    """
    Compute bootstrap confidence interval for the mean.

    Returns dict with mean, lower, upper, ci_level, n_bootstrap, n_samples.
    """
    if not values:
        return {"mean": None, "lower": None, "upper": None, "ci_level": ci,
                "n_bootstrap": n_bootstrap, "n_samples": 0}

    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_bootstrap):
        sample = [rng.choice(values) for _ in range(n)]
        means.append(statistics.mean(sample))
    means.sort()

    alpha = (1 - ci) / 2
    lower_idx = int(alpha * n_bootstrap)
    upper_idx = int((1 - alpha) * n_bootstrap)

    return {
        "mean": round(statistics.mean(values), 2),
        "lower": round(means[lower_idx], 2),
        "upper": round(means[upper_idx], 2),
        "ci_level": ci,
        "n_bootstrap": n_bootstrap,
        "n_samples": n,
    }


# ── Effect Size ──────────────────────────────────────────────────────────────

def cohens_d(group_a: list[float], group_b: list[float]) -> dict:
    """
    Compute Cohen's d effect size between two groups.

    Interpretation:
      |d| < 0.2: negligible
      0.2 ≤ |d| < 0.5: small
      0.5 ≤ |d| < 0.8: medium
      |d| ≥ 0.8: large
    """
    if not group_a or not group_b:
        return {"d": None, "interpretation": "insufficient_data"}

    mean_a = statistics.mean(group_a)
    mean_b = statistics.mean(group_b)
    n_a = len(group_a)
    n_b = len(group_b)

    # Pooled standard deviation
    var_a = statistics.variance(group_a) if n_a >= 2 else 0
    var_b = statistics.variance(group_b) if n_b >= 2 else 0
    pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2) if (n_a + n_b) > 2 else 0
    pooled_sd = math.sqrt(pooled_var) if pooled_var > 0 else 0

    if pooled_sd == 0:
        d = 0.0 if mean_a == mean_b else float("inf")
    else:
        d = (mean_a - mean_b) / pooled_sd

    # Hedges' g correction for small samples
    correction = 1 - (3 / (4 * (n_a + n_b) - 9)) if (n_a + n_b) > 2 else 1
    g = d * correction

    abs_d = abs(g)
    if abs_d < 0.2:
        interpretation = "negligible"
    elif abs_d < 0.5:
        interpretation = "small"
    elif abs_d < 0.8:
        interpretation = "medium"
    else:
        interpretation = "large"

    return {
        "cohens_d": round(d, 3),
        "hedges_g": round(g, 3),
        "mean_a": round(mean_a, 3),
        "mean_b": round(mean_b, 3),
        "n_a": n_a,
        "n_b": n_b,
        "pooled_sd": round(pooled_sd, 3),
        "interpretation": interpretation,
        "direction": "a_gt_b" if g > 0 else ("b_gt_a" if g < 0 else "equal"),
    }


# ── Score Collection ─────────────────────────────────────────────────────────

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
    """Filter scores by metadata."""
    if experiment_set:
        scores = [s for s in scores if s.get("experiment_set") == experiment_set]
    if fixture_set:
        scores = [s for s in scores if s.get("fixture_set") == fixture_set]
    return scores


# ── Main Statistics ──────────────────────────────────────────────────────────

def compute_statistics(
    results_dir: Path,
    experiment_set: str | None = None,
    fixture_set: str | None = None,
    comparison_pairs: list[tuple[str, str]] = None,
) -> dict:
    """Compute all statistics from collected scores."""
    all_scores = collect_scores(results_dir)
    scores = filter_scores(all_scores, experiment_set, fixture_set)

    if not scores:
        return {"error": "No scores found matching filter criteria", "scores_found": 0}

    if comparison_pairs is None:
        comparison_pairs = [("G3", "G1"), ("G3", "G2")]

    result = {
        "benchmark": "ABI-Bench",
        "version": "0.1",
        "experiment_set": experiment_set or "all",
        "fixture_set": fixture_set or "all",
        "total_scores": len(scores),
    }

    # ── Group-level bootstrap CIs ─────────────────────────────────────
    by_group = defaultdict(list)
    for s in scores:
        gid = s.get("group_id", "unknown")
        by_group[gid].append(s)

    group_cis = {}
    for gid in sorted(by_group.keys()):
        normalized = _normalized_totals_by_replicate(by_group[gid])
        group_cis[gid] = bootstrap_ci(normalized)

    result["bootstrap_ci"] = group_cis

    # ── Per-task effect sizes ─────────────────────────────────────────
    task_ids = sorted({s.get("task_id", "unknown") for s in scores})
    effect_sizes = {}

    for tid in task_ids:
        task_scores = [s for s in scores if s.get("task_id") == tid]
        by_group_task = defaultdict(list)
        for s in task_scores:
            by_group_task[s.get("group_id", "unknown")].append(s)

        task_effects = {}
        for gid in sorted(by_group_task.keys()):
            gscores = by_group_task[gid]
            values = [s.get("score", 0) / max(s.get("max_score", 1), 1) for s in gscores]
            task_effects[gid] = {
                "n": len(values),
                "mean_normalized": round(statistics.mean(values), 3) if values else None,
                "std_normalized": round(statistics.stdev(values), 3) if len(values) >= 2 else None,
                "values": [round(v, 3) for v in values],
            }

        comparisons = {}
        for g_a, g_b in comparison_pairs:
            if g_a in by_group_task and g_b in by_group_task:
                vals_a = [s.get("score", 0) / max(s.get("max_score", 1), 1)
                          for s in by_group_task[g_a]]
                vals_b = [s.get("score", 0) / max(s.get("max_score", 1), 1)
                          for s in by_group_task[g_b]]
                comparisons[f"{g_a}_vs_{g_b}"] = cohens_d(vals_a, vals_b)

        effect_sizes[tid] = {
            "task_id": tid,
            "task_type": task_scores[0].get("task_type", "unknown") if task_scores else "unknown",
            "groups": task_effects,
            "comparisons": comparisons,
        }

    result["effect_sizes"] = effect_sizes

    # ── Failure taxonomy ──────────────────────────────────────────────
    taxonomy = _build_failure_taxonomy(scores)
    result["failure_taxonomy"] = taxonomy

    # ── Paper-ready tables ────────────────────────────────────────────
    result["tables"] = _build_paper_tables(group_cis, effect_sizes, taxonomy)

    # ── Overall claim statistics ──────────────────────────────────────
    result["claim_statistics"] = _build_claim_statistics(group_cis, effect_sizes)

    return result


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


def _build_failure_taxonomy(scores: list[dict]) -> dict:
    """Aggregate failure codes across scores."""
    taxonomy = {
        "total_runs": len(scores),
        "passed_runs": sum(1 for s in scores if s.get("passed")),
        "failed_runs": sum(1 for s in scores if not s.get("passed")),
        "by_group": {},
        "by_category": defaultdict(int),
        "by_task": {},
    }

    by_group = defaultdict(list)
    for s in scores:
        by_group[s.get("group_id", "unknown")].append(s)

    for gid, gscores in by_group.items():
        failed = [s for s in gscores if not s.get("passed")]
        taxonomy["by_group"][gid] = {
            "total": len(gscores),
            "passed": len(gscores) - len(failed),
            "failed": len(failed),
            "failure_codes": defaultdict(int),
        }
        for s in failed:
            for code in s.get("failure_codes", []):
                taxonomy["by_group"][gid]["failure_codes"][code] += 1
                taxonomy["by_category"][code] += 1

    # Per-task failure counts
    by_task = defaultdict(list)
    for s in scores:
        by_task[s.get("task_id", "unknown")].append(s)

    for tid, tscores in by_task.items():
        failed = [s for s in tscores if not s.get("passed")]
        taxonomy["by_task"][tid] = {
            "total": len(tscores),
            "passed": len(tscores) - len(failed),
            "failed": len(failed),
        }

    # Convert defaultdicts to regular dicts for JSON serialization
    for gid in taxonomy["by_group"]:
        taxonomy["by_group"][gid]["failure_codes"] = dict(
            taxonomy["by_group"][gid]["failure_codes"]
        )
    taxonomy["by_category"] = dict(taxonomy["by_category"])

    return taxonomy


def _build_paper_tables(group_cis, effect_sizes, taxonomy) -> dict:
    """Build markdown table strings for paper use."""
    tables = {}

    # Table 1: Group performance
    header = "| Group | Mean Score | 95% CI | n |"
    sep = "|---|---|---|---|"
    rows = [header, sep]
    for gid in sorted(group_cis.keys()):
        ci = group_cis[gid]
        if ci["mean"] is not None:
            rows.append(
                f"| {gid} | {ci['mean']:.1f} | "
                f"[{ci['lower']:.1f}, {ci['upper']:.1f}] | {ci['n_samples']} |"
            )
        else:
            rows.append(f"| {gid} | — | — | 0 |")
    tables["group_performance"] = "\n".join(rows)

    # Table 2: Per-task effect sizes (G3 vs G1)
    if effect_sizes:
        header2 = "| Task | Type | G3 Mean | G1 Mean | Cohen's d | Interpretation |"
        sep2 = "|---|---|---|---|---|---|"
        rows2 = [header2, sep2]
        for tid in sorted(effect_sizes.keys()):
            es = effect_sizes[tid]
            comp = es["comparisons"].get("G3_vs_G1", {})
            g3 = es["groups"].get("G3", {})
            g1 = es["groups"].get("G1", {})
            if comp.get("cohens_d") is not None:
                rows2.append(
                    f"| {tid} | {es.get('task_type', '?')} | "
                    f"{g3.get('mean_normalized', '—')} | "
                    f"{g1.get('mean_normalized', '—')} | "
                    f"{comp['hedges_g']:.2f} | {comp['interpretation']} |"
                )
        if len(rows2) > 2:
            tables["per_task_effect_g3_vs_g1"] = "\n".join(rows2)

    # Table 3: Failure taxonomy
    if taxonomy["failed_runs"] > 0:
        header3 = "| Category | Count | Pct |"
        sep3 = "|---|---|"
        rows3 = [header3, sep3]
        for cat, count in sorted(taxonomy["by_category"].items(), key=lambda x: -x[1]):
            pct = count / taxonomy["total_runs"] * 100
            rows3.append(f"| {cat} | {count} | {pct:.1f}% |")
        tables["failure_taxonomy"] = "\n".join(rows3)

    return tables


def _build_claim_statistics(group_cis, effect_sizes) -> dict:
    """Build claim-level summary statistics."""
    g1_ci = group_cis.get("G1", {})
    g2_ci = group_cis.get("G2", {})
    g3_ci = group_cis.get("G3", {})

    stats = {
        "G3_mean": g3_ci.get("mean"),
        "G2_mean": g2_ci.get("mean"),
        "G1_mean": g1_ci.get("mean"),
        "G3_vs_G1_delta": None,
        "G3_vs_G2_delta": None,
        "G3_beats_G1_pct20": None,
        "G3_beats_G2_pct12": None,
    }

    if g3_ci.get("mean") is not None and g1_ci.get("mean") is not None:
        stats["G3_vs_G1_delta"] = round(g3_ci["mean"] - g1_ci["mean"], 2)
        stats["G3_beats_G1_pct20"] = stats["G3_vs_G1_delta"] >= 20

    if g3_ci.get("mean") is not None and g2_ci.get("mean") is not None:
        stats["G3_vs_G2_delta"] = round(g3_ci["mean"] - g2_ci["mean"], 2)
        stats["G3_beats_G2_pct12"] = stats["G3_vs_G2_delta"] >= 12

    # Average per-task effect size
    all_d = []
    for tid, es in effect_sizes.items():
        for comp_name, comp in es.get("comparisons", {}).items():
            d = comp.get("hedges_g")
            if d is not None and d != float("inf"):
                all_d.append(d)
    if all_d:
        stats["mean_effect_size"] = round(statistics.mean(all_d), 3)
        stats["median_effect_size"] = round(statistics.median(all_d), 3)

    return stats


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ABI-Bench Statistical Analysis — bootstrap CIs, effect sizes, taxonomy"
    )
    parser.add_argument("--results", required=True, type=Path, help="Results directory")
    parser.add_argument(
        "--experiment-set",
        choices=["dev", "main", "ablation", "full"],
        help="Filter by experiment set",
    )
    parser.add_argument(
        "--fixture-set",
        choices=["public", "hidden"],
        help="Filter by fixture set",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output statistics JSON path",
    )
    parser.add_argument(
        "--comparisons",
        type=str,
        default="G3_vs_G1,G3_vs_G2",
        help="Comma-separated comparison pairs (e.g. G3_vs_G1,G3_vs_G2)",
    )
    parser.add_argument(
        "--bootstrap-iterations",
        type=int,
        default=10000,
        help="Number of bootstrap iterations (default: 10000)",
    )
    args = parser.parse_args()

    # Parse comparison pairs
    pairs = []
    for pair in args.comparisons.split(","):
        parts = pair.strip().split("_vs_")
        if len(parts) == 2:
            pairs.append((parts[0].strip(), parts[1].strip()))

    stats = compute_statistics(
        results_dir=args.results,
        experiment_set=args.experiment_set,
        fixture_set=args.fixture_set,
        comparison_pairs=pairs or None,
    )

    if "error" in stats:
        print(f"ERROR: {stats['error']}")
        return 1

    # Print summary
    print("\n=== ABI-Bench Statistical Analysis ===")
    print(f"Experiment set: {args.experiment_set or 'all'}")
    print(f"Fixture set: {args.fixture_set or 'all'}")
    print(f"Total scores: {stats['total_scores']}")

    print("\nBootstrap 95% CIs (total normalized score):")
    for gid in sorted(stats["bootstrap_ci"].keys()):
        ci = stats["bootstrap_ci"][gid]
        if ci["mean"] is not None:
            print(f"  {gid}: {ci['mean']:.1f} [{ci['lower']:.1f}, {ci['upper']:.1f}] (n={ci['n_samples']})")
        else:
            print(f"  {gid}: no data")

    print("\nClaim Statistics:")
    cs = stats.get("claim_statistics", {})
    for k, v in cs.items():
        print(f"  {k}: {v}")

    print("\nFailure Taxonomy:")
    ft = stats.get("failure_taxonomy", {})
    print(f"  Passed: {ft.get('passed_runs', 0)}/{ft.get('total_runs', 0)}")
    if ft.get("by_category"):
        for cat, count in sorted(ft["by_category"].items(), key=lambda x: -x[1]):
            print(f"    {cat}: {count}")

    # Paper tables
    tables = stats.get("tables", {})
    if tables.get("group_performance"):
        print("\n--- Group Performance Table ---")
        print(tables["group_performance"])
    if tables.get("per_task_effect_g3_vs_g1"):
        print("\n--- Per-Task Effect Sizes (G3 vs G1) ---")
        print(tables["per_task_effect_g3_vs_g1"])
    if tables.get("failure_taxonomy"):
        print("\n--- Failure Taxonomy Table ---")
        print(tables["failure_taxonomy"])

    # Write output
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            json.dump(stats, f, indent=2)
        print(f"\nStatistics written to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
