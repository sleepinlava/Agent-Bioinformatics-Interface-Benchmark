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

For the paper-run claim workflow, use --fixture-set hidden instead.

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
    bootstrap_iterations: int = 10000,
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
        group_cis[gid] = bootstrap_ci(normalized, n_bootstrap=bootstrap_iterations)
        # Enrich with auxiliary metrics from raw scores
        gscores = by_group[gid]
        tokens = [s.get("metrics", {}).get("thinking_tokens", 0) for s in gscores]
        steps = [s.get("metrics", {}).get("agent_steps", 0) for s in gscores]
        group_cis[gid]["avg_thinking_tokens"] = statistics.mean(tokens) if tokens else 0
        group_cis[gid]["median_agent_steps"] = statistics.median(steps) if steps else 0

    result["bootstrap_ci"] = group_cis

    paired_delta_ci = {}
    for g_a, g_b in comparison_pairs:
        deltas = _paired_total_deltas(scores, g_a, g_b)
        paired_delta_ci[f"{g_a}_vs_{g_b}"] = bootstrap_ci(
            deltas,
            n_bootstrap=bootstrap_iterations,
        )
    result["paired_delta_ci"] = paired_delta_ci

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
    observed_tasks = sorted(set(s.get("task_id", "") for s in scores))
    result["claim_statistics"] = _build_claim_statistics(
        group_cis, effect_sizes, paired_delta_ci, observed_tasks
    )

    # ── v0.3: Multi-model scaffolding analysis ─────────────────────────
    scaffolding_result = _compute_scaffolding_analysis(scores)
    result["scaffolding_analysis"] = scaffolding_result

    # Inject scaffolding gain into group_cis for ABI Advantage Index
    if scaffolding_result.get("available") and scaffolding_result.get("scaffolding_gain") is not None:
        for gid in group_cis:
            group_cis[gid]["_scaffolding_gain"] = scaffolding_result["scaffolding_gain"]

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


def _normalized_total_map_by_replicate(scores: list[dict]) -> dict[int, float]:
    """Return normalized total score by replicate id."""
    by_rep = defaultdict(list)
    for s in scores:
        by_rep[s.get("replicate", 1)].append(s)

    totals = {}
    for rep, rep_scores in by_rep.items():
        score_sum = sum(s.get("score", 0) for s in rep_scores)
        max_sum = sum(s.get("max_score", 0) for s in rep_scores)
        totals[rep] = (score_sum / max_sum * 100) if max_sum > 0 else 0
    return totals


def _paired_total_deltas(scores: list[dict], group_a: str, group_b: str) -> list[float]:
    """Return paired normalized total deltas group_a - group_b by replicate."""
    a_scores = [s for s in scores if s.get("group_id") == group_a]
    b_scores = [s for s in scores if s.get("group_id") == group_b]
    a_by_rep = _normalized_total_map_by_replicate(a_scores)
    b_by_rep = _normalized_total_map_by_replicate(b_scores)
    common_reps = sorted(set(a_by_rep) & set(b_by_rep))
    return [a_by_rep[rep] - b_by_rep[rep] for rep in common_reps]


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


# ═══════════════════════════════════════════════════════════════════════
# v0.5 Scaffolding Analysis
# ═══════════════════════════════════════════════════════════════════════

# Built-in fallback (used when bench/model_tiers.yaml is missing).
_BUILTIN_MODEL_TIER_MAP = {
    "gpt-4o": "strong",
    "claude-sonnet-4-6": "strong",
    "deepseek-v4-pro": "strong",
    "gpt-4o-mini": "medium",
    "qwen2.5-72b": "medium",
    "qwen2.5-7b": "weak",
    "llama-3.1-8b": "weak",
}


def _load_model_tier_map(yaml_path: Path | None = None) -> dict:
    """Load model → tier mapping from ``bench/model_tiers.yaml``.

    Falls back to *_BUILTIN_MODEL_TIER_MAP* when the YAML file is absent.
    """
    if yaml_path is None:
        yaml_path = Path(__file__).resolve().parent.parent / "model_tiers.yaml"
    try:
        if yaml_path.is_file():
            import yaml
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}
            tier_map = {}
            for tname, tinfo in data.get("tiers", {}).items():
                for model in tinfo.get("models", []):
                    tier_map[model] = tname
            if tier_map:
                return tier_map
    except Exception:
        pass
    return dict(_BUILTIN_MODEL_TIER_MAP)


MODEL_TIER_MAP = _load_model_tier_map()


def _compute_scaffolding_analysis(scores: list[dict]) -> dict:
    """Compute scaffolding effect: does ABI help weak models more?

    Returns:
        scaffolding_gain: (G3−G1)_weak − (G3−G1)_strong
        by_tier: per-tier G3/G2/G1 normalized scores
        by_model: per-model G3/G2/G1 normalized scores
        interaction: tier × group interaction evidence
        weak_abi_vs_strong_no_abi: ratio comparison
    """
    # ── Detect if multi-model data is present ──
    model_ids = set(s.get("model_id", "") for s in scores if s.get("model_id"))
    if len(model_ids) <= 1:
        return {"available": False, "reason": "Single model data — scaffolding analysis requires multiple models"}

    # ── Resolve model tiers ──
    model_tiers = {}
    for mid in model_ids:
        tier = MODEL_TIER_MAP.get(mid, "unknown")
        model_tiers[mid] = tier

    tiers_present = set(model_tiers.values())
    if len(tiers_present) < 2:
        return {"available": False, "reason": f"All models in single tier: {tiers_present}"}

    # ── Per-model, per-group normalized scores (for tier aggregation) ──
    by_tier_group = defaultdict(lambda: defaultdict(list))
    for s in scores:
        mid = s.get("model_id", "")
        tier = model_tiers.get(mid, "unknown")
        gid = s.get("group_id", "unknown")
        normalized = s.get("score", 0) / max(s.get("max_score", 1), 1)
        by_tier_group[tier][gid].append(normalized)

    # ── Compute tier-level deltas ──
    tier_deltas = {}
    for tier in ("strong", "medium", "weak"):
        g1_vals = by_tier_group.get(tier, {}).get("G1", [])
        g3_vals = by_tier_group.get(tier, {}).get("G3", [])
        g2_vals = by_tier_group.get(tier, {}).get("G2", [])
        g4_vals = by_tier_group.get(tier, {}).get("G4", [])

        tier_deltas[tier] = {
            "n_scores": len(g1_vals) + len(g3_vals),
            "G1_mean": round(statistics.mean(g1_vals), 3) if g1_vals else None,
            "G2_mean": round(statistics.mean(g2_vals), 3) if g2_vals else None,
            "G3_mean": round(statistics.mean(g3_vals), 3) if g3_vals else None,
            "G4_mean": round(statistics.mean(g4_vals), 3) if g4_vals else None,
            "G3_minus_G1": round(statistics.mean(g3_vals) - statistics.mean(g1_vals), 3) if g3_vals and g1_vals else None,
            "G3_minus_G2": round(statistics.mean(g3_vals) - statistics.mean(g2_vals), 3) if g3_vals and g2_vals else None,
            "G3_minus_G4": round(statistics.mean(g3_vals) - statistics.mean(g4_vals), 3) if g3_vals and g4_vals else None,
        }

    # ── Scaffolding Gain ──
    weak_gain = tier_deltas.get("weak", {}).get("G3_minus_G1")
    strong_gain = tier_deltas.get("strong", {}).get("G3_minus_G1")
    if weak_gain is not None and strong_gain is not None:
        scaffolding_gain = round(weak_gain - strong_gain, 3)
    else:
        scaffolding_gain = None

    # ── Interaction evidence (simple ANOVA-style comparison) ──
    # Bootstrap test: is the weak-tier gain significantly larger than strong-tier?
    # Use pre-computed by_tier_group values to avoid redundant iteration.
    weak_g3 = by_tier_group.get("weak", {}).get("G3", [])
    strong_g3 = by_tier_group.get("strong", {}).get("G3", [])
    weak_g1 = by_tier_group.get("weak", {}).get("G1", [])
    strong_g1 = by_tier_group.get("strong", {}).get("G1", [])
    if weak_g3 and strong_g3 and weak_g1 and strong_g1:
        interaction_p = _bootstrap_interaction_test(
            [weak_g3, strong_g3],
            [weak_g1, strong_g1],
        )
    else:
        interaction_p = None

    # ── Weak+ABI vs Strong−ABI ratio ──
    weak_g3_vals = by_tier_group.get("weak", {}).get("G3", [])
    strong_g1_vals = by_tier_group.get("strong", {}).get("G1", [])
    if weak_g3_vals and strong_g1_vals:
        weak_abi_mean = statistics.mean(weak_g3_vals)
        strong_no_abi_mean = statistics.mean(strong_g1_vals)
        ratio = round(weak_abi_mean / strong_no_abi_mean, 3) if strong_no_abi_mean > 0 else None
    else:
        ratio = None

    # ── Per-model detail ──
    per_model = {}
    for mid in sorted(model_ids):
        tier = model_tiers.get(mid, "unknown")
        g1 = [s.get("score", 0) / max(s.get("max_score", 1), 1)
              for s in scores if s.get("model_id") == mid and s.get("group_id") == "G1"]
        g3 = [s.get("score", 0) / max(s.get("max_score", 1), 1)
              for s in scores if s.get("model_id") == mid and s.get("group_id") == "G3"]
        per_model[mid] = {
            "tier": tier,
            "G1_mean": round(statistics.mean(g1), 3) if g1 else None,
            "G3_mean": round(statistics.mean(g3), 3) if g3 else None,
            "G3_minus_G1": round(statistics.mean(g3) - statistics.mean(g1), 3) if g3 and g1 else None,
            "n": len(g1) + len(g3),
        }

    # ── Determine which models show G3 > G1 ──
    models_g3_beats_g1 = sum(
        1 for mid, data in per_model.items()
        if data["G3_minus_G1"] is not None and data["G3_minus_G1"] > 0
    )

    return {
        "available": True,
        "models_detected": len(model_ids),
        "tiers_detected": sorted(tiers_present),
        "model_tiers": model_tiers,
        "scaffolding_gain": scaffolding_gain,
        "scaffolding_gain_interpretation": (
            "ABI helps weak models more than strong models"
            if scaffolding_gain is not None and scaffolding_gain > 0
            else "No scaffolding effect detected"
        ),
        "interaction_p_value": interaction_p,
        "interaction_significant": interaction_p is not None and interaction_p < 0.05,
        "weak_abi_vs_strong_no_abi_ratio": ratio,
        "weak_abi_reaches_80pct_of_strong_no_abi": ratio is not None and ratio >= 0.80,
        "tier_deltas": tier_deltas,
        "per_model": per_model,
        "models_g3_beats_g1": models_g3_beats_g1,
        "total_models": len(model_ids),
    }


def _bootstrap_interaction_test(
    group_a_tiers: list[list[float]],  # e.g., [weak_G3, strong_G3]
    group_b_tiers: list[list[float]],  # e.g., [weak_G1, strong_G1]
    n_bootstrap: int = 5000,
    seed: int = 42,
) -> float | None:
    """Bootstrap test for Group × Tier interaction.

    H0: (G3−G1)_weak − (G3−G1)_strong = 0 (no interaction)
    Returns approximate p-value.
    """
    if not all(group_a_tiers) or not all(group_b_tiers):
        return None

    rng = random.Random(seed)

    # Observed interaction
    weak_diff = statistics.mean(group_a_tiers[0]) - statistics.mean(group_b_tiers[0])
    strong_diff = statistics.mean(group_a_tiers[1]) - statistics.mean(group_b_tiers[1])
    observed = weak_diff - strong_diff

    # Bootstrap null distribution (shuffle tier labels)
    all_a = group_a_tiers[0] + group_a_tiers[1]
    all_b = group_b_tiers[0] + group_b_tiers[1]
    n_weak = len(group_a_tiers[0])

    null_diffs = []
    for _ in range(n_bootstrap):
        rng.shuffle(all_a)
        rng.shuffle(all_b)
        weak_a = all_a[:n_weak]
        strong_a = all_a[n_weak:]
        weak_b = all_b[:n_weak]
        strong_b = all_b[n_weak:]
        null_weak_diff = statistics.mean(weak_a) - statistics.mean(weak_b)
        null_strong_diff = statistics.mean(strong_a) - statistics.mean(strong_b)
        null_diffs.append(null_weak_diff - null_strong_diff)

    # Two-sided p-value
    extreme = sum(1 for d in null_diffs if abs(d) >= abs(observed))
    return round(extreme / n_bootstrap, 4)


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
            hedges_g = comp.get("hedges_g")
            if comp.get("cohens_d") is not None and hedges_g is not None:
                rows2.append(
                    f"| {tid} | {es.get('task_type', '?')} | "
                    f"{g3.get('mean_normalized', '—')} | "
                    f"{g1.get('mean_normalized', '—')} | "
                    f"{hedges_g:.2f} | {comp.get('interpretation', '?')} |"
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


def _load_benchmark_spec() -> dict:
    """Load BENCHMARK_SPEC.yaml (cached)."""
    import yaml
    spec_path = Path(__file__).resolve().parent.parent / "BENCHMARK_SPEC.yaml"
    try:
        with open(spec_path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _detect_task_set_type(observed_tasks: list[str]) -> str:
    """Classify observed task set as 'mvp', 'ablation', or 'full'."""
    tasks = set(observed_tasks)
    mvp = {"T01", "T02", "T03", "T05", "T06", "T08", "T09", "T10"}
    ablation = {"T03", "T04", "T05", "T06", "T07", "T08"}
    if tasks == mvp or (tasks.issubset(mvp) and len(tasks) >= 6):
        return "mvp"
    elif tasks == ablation or (tasks.issubset(ablation) and len(tasks) >= 4):
        return "ablation"
    else:
        return "full"


def _build_claim_statistics(
    group_cis, effect_sizes, paired_delta_ci=None, observed_tasks=None
) -> dict:
    """Build claim-level summary statistics using BENCHMARK_SPEC thresholds."""
    spec = _load_benchmark_spec()
    criteria_config = spec.get("success_criteria", {})
    g1_ci = group_cis.get("G1", {})
    g2_ci = group_cis.get("G2", {})
    g3_ci = group_cis.get("G3", {})

    # ── Detect task set and resolve thresholds ──
    all_tasks = observed_tasks or sorted(effect_sizes.keys())
    task_set_type = _detect_task_set_type(all_tasks)
    stratified = criteria_config.get("stratified_deltas", {})
    task_thresholds = stratified.get(task_set_type, stratified.get("full", {}))
    g1_threshold = task_thresholds.get("G3_minus_G1_min_delta", 5)
    g2_threshold = task_thresholds.get("G3_minus_G2_min_delta", 5)

    stats = {
        "task_set_type": task_set_type,
        "delta_thresholds_used": {
            "G3_vs_G1_threshold": g1_threshold,
            "G3_vs_G2_threshold": g2_threshold,
        },
        "G3_mean": g3_ci.get("mean"),
        "G2_mean": g2_ci.get("mean"),
        "G1_mean": g1_ci.get("mean"),
        "G3_vs_G1_delta": None,
        "G3_vs_G2_delta": None,
        # Point-estimate checks
        "G3_beats_G1_point": None,
        "G3_beats_G2_point": None,
    }

    if g3_ci.get("mean") is not None and g1_ci.get("mean") is not None:
        delta = round(g3_ci["mean"] - g1_ci["mean"], 2)
        stats["G3_vs_G1_delta"] = delta
        stats["G3_beats_G1_point"] = delta >= g1_threshold

    if g3_ci.get("mean") is not None and g2_ci.get("mean") is not None:
        delta = round(g3_ci["mean"] - g2_ci["mean"], 2)
        stats["G3_vs_G2_delta"] = delta
        stats["G3_beats_G2_point"] = delta >= g2_threshold

    paired_delta_ci = paired_delta_ci or {}
    if "G3_vs_G1" in paired_delta_ci:
        ci = paired_delta_ci["G3_vs_G1"]
        stats["G3_vs_G1_paired_delta_ci"] = {
            "mean": ci.get("mean"),
            "lower": ci.get("lower"),
            "upper": ci.get("upper"),
            "n": ci.get("n_samples"),
        }
        # CI-based check: does lower bound exceed threshold?
        if ci.get("lower") is not None:
            stats["G3_beats_G1_ci"] = ci["lower"] > g1_threshold
            stats["G3_beats_G1_ci_above_zero"] = ci["lower"] > 0

    if "G3_vs_G2" in paired_delta_ci:
        ci = paired_delta_ci["G3_vs_G2"]
        stats["G3_vs_G2_paired_delta_ci"] = {
            "mean": ci.get("mean"),
            "lower": ci.get("lower"),
            "upper": ci.get("upper"),
            "n": ci.get("n_samples"),
        }
        if ci.get("lower") is not None:
            stats["G3_beats_G2_ci"] = ci["lower"] > g2_threshold
            stats["G3_beats_G2_ci_above_zero"] = ci["lower"] > 0

    # ── CI-based significance summary ──
    ci_config = criteria_config.get("ci_significance", {})
    n_reps = g3_ci.get("n_samples", 0)
    ci_applicable = ci_config.get("enabled", False) and n_reps >= ci_config.get("min_replicates", 5)
    stats["ci_significance_applicable"] = ci_applicable
    stats["n_replicates"] = n_reps
    if ci_applicable:
        stats["claim_by_ci"] = (
            stats.get("G3_beats_G1_ci_above_zero", False)
            and stats.get("G3_beats_G2_ci_above_zero", False)
        )

    # ── ABI Advantage Index ──
    abi_config = criteria_config.get("abi_advantage_index", {})
    if abi_config:
        stats["abi_advantage_index"] = _compute_abi_advantage_index(
            group_cis, effect_sizes, abi_config
        )

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

    # ── v0.3: Scaffolding criteria check ──
    scaffolding_criteria = criteria_config.get("scaffolding_criteria", {})
    if scaffolding_criteria:
        stats["scaffolding_criteria"] = {
            "min_models_g3_beats_g1": scaffolding_criteria.get("min_models_g3_beats_g1", 5),
            "weak_tier_min_gain": scaffolding_criteria.get("weak_tier_min_gain", 15),
            "interaction_p_threshold": scaffolding_criteria.get("interaction_p_threshold", 0.05),
            "weak_abi_vs_strong_no_abi_ratio": scaffolding_criteria.get("weak_abi_vs_strong_no_abi_ratio", 0.80),
        }

    # ── v0.3: G4 criteria check ──
    g4_criteria = criteria_config.get("g4_criteria", {})
    if g4_criteria:
        g4_ci = group_cis.get("G4", {})
        if g3_ci.get("mean") is not None and g4_ci.get("mean") is not None:
            g3_vs_g4_delta = round(g3_ci["mean"] - g4_ci["mean"], 2)
            stats["G3_vs_G4_delta"] = g3_vs_g4_delta
            stats["G3_beats_G4"] = g3_vs_g4_delta >= g4_criteria.get("G3_minus_G4_min_delta", 3)

    return stats


def _compute_abi_advantage_index(
    group_cis: dict, effect_sizes: dict, abi_config: dict
) -> dict:
    """Compute the ABI Advantage composite index from bootstrap and effect-size data.

    Returns a dict with the overall score and per-component breakdown.
    """
    g1_ci = group_cis.get("G1", {})
    g3_ci = group_cis.get("G3", {})
    weights = abi_config.get("weights", {})

    # ── Helper: extract Cohen's d for a task ──
    def _get_d(task_id: str, comp: str = "G3_vs_G1") -> float | None:
        es = effect_sizes.get(task_id, {})
        comparisons = es.get("comparisons", {})
        c = comparisons.get(comp, {})
        d = c.get("cohens_d")
        if d is not None and d != float("inf") and d == d:  # exclude inf, NaN
            return abs(d)
        return None

    # ── Component 1: Discovery effect (T01 Cohen's d) ──
    d_t01 = _get_d("T01")
    discovery = min(abs(d_t01 or 0), 3) / 3

    # ── Component 2: Safety effect (T08 Cohen's d) ──
    d_t08 = _get_d("T08")
    safety = min(abs(d_t08 or 0), 3) / 3

    # ── Component 3: Cross-plugin effect (avg T09, T10, T13, T14) ──
    d_t09 = _get_d("T09")
    d_t10 = _get_d("T10")
    d_t13 = _get_d("T13")
    d_t14 = _get_d("T14")
    cp_vals = [min(abs(d or 0), 3) / 3 for d in [d_t09, d_t10, d_t13, d_t14] if d is not None]
    cross_plugin = sum(cp_vals) / len(cp_vals) if cp_vals else 0

    # ── Component 4: Efficiency gain (thinking token reduction) ──
    g3_tokens = g3_ci.get("avg_thinking_tokens", 0) if isinstance(g3_ci, dict) else 0
    g1_tokens = g1_ci.get("avg_thinking_tokens", 0) if isinstance(g1_ci, dict) else 0
    # Fallback: use mean values if available
    if not g3_tokens:
        g3_tokens = g3_ci.get("mean", 0)
    if not g1_tokens:
        g1_tokens = g1_ci.get("mean", 0)
    efficiency = max(0, (g1_tokens - g3_tokens) / g1_tokens) if g1_tokens > 0 else 0

    # ── Component 5: Step reduction ──
    g3_steps = g3_ci.get("median_agent_steps", 0) if isinstance(g3_ci, dict) else 0
    g1_steps = g1_ci.get("median_agent_steps", 0) if isinstance(g1_ci, dict) else 0
    step_red = max(0, (g1_steps - g3_steps) / g1_steps) if g1_steps > 0 else 0

    # ── Component 6: Scaffolding effect (v0.3) ──
    scaffolding = 0.0
    scaffolding_data = group_cis.get("_scaffolding_gain")
    if scaffolding_data is not None and isinstance(scaffolding_data, (int, float)):
        scaffolding = min(max(scaffolding_data / 30.0, 0), 1.0)

    components = {
        "discovery_effect": round(discovery, 3),
        "safety_effect": round(safety, 3),
        "cross_plugin_effect": round(cross_plugin, 3),
        "efficiency_gain": round(efficiency, 3),
        "step_reduction": round(step_red, 3),
        "scaffolding_effect": round(scaffolding, 3),
    }

    score = sum(weights.get(k, 0) * v for k, v in components.items())

    return {
        "score": round(score, 3),
        "min_score_required": abi_config.get("min_score", 0.5),
        "components": components,
        "weights_used": weights,
        "met": score >= abi_config.get("min_score", 0.5),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="ABI-Bench Statistical Analysis — bootstrap CIs, effect sizes, taxonomy"
    )
    parser.add_argument("--results", required=True, type=Path, help="Results directory")
    parser.add_argument(
        "--experiment-set",
        choices=["dev", "main", "ablation", "full", "paper"],
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
        bootstrap_iterations=args.bootstrap_iterations,
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

    if stats.get("paired_delta_ci"):
        print("\nPaired Delta 95% CIs (normalized total score):")
        for name, ci in sorted(stats["paired_delta_ci"].items()):
            if ci["mean"] is not None:
                print(
                    f"  {name}: {ci['mean']:.1f} "
                    f"[{ci['lower']:.1f}, {ci['upper']:.1f}] "
                    f"(n={ci['n_samples']})"
                )
            else:
                print(f"  {name}: insufficient paired data")

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


# ═══════════════════════════════════════════════════════════════════════
# v0.6 Effect Size Matrix
# ═══════════════════════════════════════════════════════════════════════


def compute_effect_size_matrix(results: dict) -> dict:
    """Compute Cohen's d effect size for every (group_pair * task) combination.

    Returns a dict suitable for abi-sciplot heatmap rendering:
      {
        "matrix": [[task_id, group_pair, cohens_d, ci_lower, ci_upper], ...],
        "metadata": {"n_bootstrap": 10000, "confidence": 0.95}
      }
    """
    import numpy as np

    group_pairs = [("G3", "G1"), ("G3", "G2"), ("G3", "G4")]
    tasks = sorted(set(
        t for run in results.values()
        for t in run.get("tasks", {}).keys()
    ))

    matrix = []
    for task_id in tasks:
        for g1, g2 in group_pairs:
            scores_g1 = _collect_task_scores(results, g1, task_id)
            scores_g2 = _collect_task_scores(results, g2, task_id)
            if len(scores_g1) < 2 or len(scores_g2) < 2:
                continue
            d = _cohens_d(scores_g1, scores_g2)
            ci = _bootstrap_ci(scores_g1, scores_g2, n=10000)
            matrix.append({
                "task_id": task_id,
                "group_pair": f"{g1}_vs_{g2}",
                "cohens_d": round(d, 3),
                "ci_lower": round(ci[0], 3),
                "ci_upper": round(ci[1], 3),
            })

    return {
        "matrix": matrix,
        "metadata": {"n_bootstrap": 10000, "confidence": 0.95},
    }


def _collect_task_scores(results: dict, group: str, task_id: str) -> list[float]:
    """Collect all replicate scores for a given group/task."""
    scores = []
    for run_id, run_data in results.items():
        if run_data.get("group") != group:
            continue
        tasks = run_data.get("tasks", {})
        if task_id in tasks:
            score = tasks[task_id].get("score", 0)
            max_score = tasks[task_id].get("max_score", 1)
            scores.append(score / max(max_score, 1) * 100)
    return scores


def _cohens_d(a: list[float], b: list[float]) -> float:
    """Cohen's d effect size: (mean(a) - mean(b)) / pooled_std."""
    import numpy as np
    na, nb = len(a), len(b)
    ma, mb = np.mean(a), np.mean(b)
    va, vb = np.var(a, ddof=1), np.var(b, ddof=1)
    pooled_std = np.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    if pooled_std == 0:
        return 0.0
    return (ma - mb) / pooled_std


def _bootstrap_ci(a: list[float], b: list[float], n: int = 10000) -> tuple[float, float]:
    """Bootstrap 95% CI for Cohen's d between two groups."""
    import numpy as np
    diffs = []
    rng = np.random.RandomState(42)
    for _ in range(n):
        sa = rng.choice(a, size=len(a), replace=True)
        sb = rng.choice(b, size=len(b), replace=True)
        diffs.append(_cohens_d(sa, sb))
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
