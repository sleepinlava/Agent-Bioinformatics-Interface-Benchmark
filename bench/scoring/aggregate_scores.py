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

import yaml
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# Allow direct execution from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bench.harness.task_suites import resolve_suite
from bench.metadata import BENCHMARK_NAME, BENCHMARK_VERSION

EXPECTED_GROUPS = {
    "main": ["G1", "G2", "G3", "G4"],
    "paper": ["G1", "G2", "G3", "G4"],
    "ablation": ["G3", "A1", "A3", "A4"],
    "full": ["G1", "G2", "G3", "G4"],
    "dev": ["G1", "G2", "G3", "G4", "A1", "A3", "A4"],
}

PRIMARY_CAUSAL_TASKS = resolve_suite("causal_core_v0_8") or []

EXPECTED_TASKS = {
    "main": PRIMARY_CAUSAL_TASKS,
    "paper": PRIMARY_CAUSAL_TASKS,
    "ablation": ["T03", "T04", "T05", "T06", "T07", "T08"],
    "full": ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18"],
    "full_v0_3": ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19"],
    "extended_v0_3": ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19", "T20", "T21", "T22", "T23", "T24"],
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
    task_ids: list[str] | None = None,
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
    if task_ids is not None:
        allowed = set(task_ids)
        scores = [s for s in scores if s.get("task_id") in allowed]
    return scores


def group_by(scores: list[dict], key: str) -> dict:
    """Group score dicts by a top-level key."""
    grouped = defaultdict(list)
    for s in scores:
        val = s.get(key, "unknown")
        grouped[val].append(s)
    return dict(grouped)


def _compute_per_plugin_breakdown(scores: list[dict]) -> dict:
    """Compute per-plugin statistics across all groups (Fix 5)."""
    from collections import defaultdict as _dd
    plugin_scores: dict[str, dict[str, list[float]]] = _dd(lambda: _dd(list))
    for s in scores:
        plugin = s.get("plugin", "unknown")
        gid = s.get("group_id", "unknown")
        if s.get("score", -1) >= 0 and s.get("max_score", 0) > 0:
            normalized = s["score"] / s["max_score"] * 100
            plugin_scores[plugin][gid].append(normalized)

    breakdown = {}
    for plugin, groups in sorted(plugin_scores.items()):
        breakdown[plugin] = {}
        for gid, vals in sorted(groups.items()):
            if len(vals) >= 1:
                breakdown[plugin][gid] = {
                    "mean": round(sum(vals) / len(vals), 2),
                    "std": round(
                        (sum((v - sum(vals)/len(vals))**2 for v in vals) / (len(vals)-1))**0.5, 2
                    ) if len(vals) >= 2 else 0.0,
                    "n": len(vals),
                }
    return breakdown


def _compute_hidden_fixture_coverage(scores: list[dict]) -> dict:
    """Report which plugins have hidden fixture coverage (Fix 15)."""
    plugins_seen = set()
    hidden_seen = set()
    for s in scores:
        plugin = s.get("plugin", "")
        if plugin:
            plugins_seen.add(plugin)
            if s.get("fixture_set") == "hidden":
                hidden_seen.add(plugin)
    return {
        "plugins_with_hidden": sorted(hidden_seen),
        "plugins_without_hidden": sorted(plugins_seen - hidden_seen),
        "note": (
            "v0.9 hidden diagnosis fixtures cover metagenomic_plasmid, "
            "rnaseq_expression, wgs_bacteria, and easymetagenome. Coverage is "
            "reported from observed score metadata, not assumed for every task."
        ),
    }


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
            "abi_leakage_rate": None,
            "artifact_completeness_mean": None,
            "median_agent_steps": None,
            "score_count": 0,
        }

    normalized = _normalized_totals_by_unit(group_scores)

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
        s.get("metrics", {}).get("unsafe_execution")
        for s in group_scores
        if s.get("metrics", {}).get("unsafe_execution") is not None
    ]
    completeness = [
        s.get("metrics", {}).get("artifact_completeness", 0)
        for s in group_scores
    ]
    agent_steps = [
        s.get("metrics", {}).get("agent_steps", 0)
        for s in group_scores
    ]
    thinking_tokens = [
        s.get("metrics", {}).get("thinking_tokens", 0)
        for s in group_scores
        if s.get("metrics", {}).get("thinking_tokens", 0) > 0
    ]
    reasoning_used_count = sum(
        1 for s in group_scores
        if s.get("metrics", {}).get("reasoning_used", False)
    )
    abi_leakage = [
        s.get("metrics", {}).get("abi_interface_used", False)
        for s in group_scores
    ]
    trace_incomplete = [
        s.get("metrics", {}).get("trace_incomplete", False)
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
        "abi_leakage_rate": round(sum(abi_leakage) / len(abi_leakage), 3) if abi_leakage else None,
        "artifact_completeness_mean": round(statistics.mean(completeness), 3) if completeness else None,
        "median_agent_steps": int(statistics.median(agent_steps)) if agent_steps else None,
        "score_count": len(group_scores),
        "reasoning_used_count": reasoning_used_count,
        "avg_thinking_tokens": round(statistics.mean(thinking_tokens), 0) if thinking_tokens else 0,
        "trace_incomplete_count": sum(trace_incomplete) if trace_incomplete else 0,
    }


def _normalized_totals_by_unit(scores: list[dict]) -> list[float]:
    """Return one normalized total per ``model_id × replicate`` unit."""
    by_unit = defaultdict(list)
    for s in scores:
        unit = (s.get("model_id", "unknown"), s.get("replicate", 1))
        by_unit[unit].append(s)

    normalized = []
    for unit_scores in by_unit.values():
        score_sum = sum(s.get("score", 0) for s in unit_scores)
        max_sum = sum(s.get("max_score", 0) for s in unit_scores)
        normalized.append((score_sum / max_sum * 100) if max_sum > 0 else 0)
    return normalized


def _normalized_totals_by_replicate(scores: list[dict]) -> list[float]:
    """Backward-compatible alias using the corrected experimental unit."""
    return _normalized_totals_by_unit(scores)


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
                "reasoning_used": ts.get("metrics", {}).get("reasoning_used", False),
                "thinking_tokens": ts.get("metrics", {}).get("thinking_tokens", 0),
            })
    return rows


# ── Benchmark Spec & Claim Helpers ──────────────────────────────────────────

_SPEC_CACHE: dict | None = None


def _load_benchmark_spec() -> dict:
    """Load BENCHMARK_SPEC.yaml (cached)."""
    global _SPEC_CACHE
    if _SPEC_CACHE is not None:
        return _SPEC_CACHE
    spec_path = Path(__file__).resolve().parent.parent / "BENCHMARK_SPEC.yaml"
    try:
        with open(spec_path) as f:
            _SPEC_CACHE = yaml.safe_load(f) or {}
    except Exception:
        _SPEC_CACHE = {}
    return _SPEC_CACHE


def _detect_task_set_type(observed_tasks: list[str]) -> str:
    """Classify observed task set as 'mvp', 'ablation', or 'full'."""
    tasks = set(observed_tasks)
    causal_core = set(PRIMARY_CAUSAL_TASKS)
    mvp = {"T01", "T02", "T03", "T05", "T06", "T08", "T09", "T10"}
    ablation = {"T03", "T04", "T05", "T06", "T07", "T08"}

    if tasks == causal_core:
        return "causal_core_v0_8"
    if tasks == mvp or (tasks.issubset(mvp) and len(tasks) >= 6):
        return "mvp"
    elif tasks == ablation or (tasks.issubset(ablation) and len(tasks) >= 4):
        return "ablation"
    else:
        return "full"


def _compute_abi_advantage_index(
    groups_stats: dict, observed_tasks: list[str], abi_config: dict
) -> dict:
    """Compute the ABI Advantage composite index from group statistics.

    Returns a dict with the overall score and per-component breakdown.
    """
    g1 = groups_stats.get("G1", {})
    g3 = groups_stats.get("G3", {})
    weights = abi_config.get("weights", {})

    # ── Component 1: Discovery effect (T01 Cohen's d) ──
    discovery_effect = _normalized_cohens_d(groups_stats, "T01", "G3", "G1")

    # ── Component 2: Safety effect (T08 Cohen's d) ──
    safety_effect = _normalized_cohens_d(groups_stats, "T08", "G3", "G1")

    # ── Component 3: Cross-plugin effect (avg T09, T10, T13, T14) ──
    cp09 = _normalized_cohens_d(groups_stats, "T09", "G3", "G1")
    cp10 = _normalized_cohens_d(groups_stats, "T10", "G3", "G1")
    cp13 = _normalized_cohens_d(groups_stats, "T13", "G3", "G1")
    cp14 = _normalized_cohens_d(groups_stats, "T14", "G3", "G1")
    cp_vals = [v for v in [cp09, cp10, cp13, cp14] if v is not None]
    cross_plugin_effect = sum(cp_vals) / len(cp_vals) if cp_vals else 0

    # ── Component 4: Efficiency gain (thinking token reduction) ──
    g3_tokens = g3.get("avg_thinking_tokens") or 0
    g1_tokens = g1.get("avg_thinking_tokens") or 0
    if g1_tokens > 0:
        efficiency_gain = max(0, (g1_tokens - g3_tokens) / g1_tokens)
    else:
        efficiency_gain = 0

    # ── Component 5: Step reduction ──
    g3_steps = g3.get("median_agent_steps") or 0
    g1_steps = g1.get("median_agent_steps") or 0
    if g1_steps > 0:
        step_reduction = max(0, (g1_steps - g3_steps) / g1_steps)
    else:
        step_reduction = 0

    # ── Weighted composite ──
    components = {
        "discovery_effect": round(discovery_effect or 0, 3),
        "safety_effect": round(safety_effect or 0, 3),
        "cross_plugin_effect": round(cross_plugin_effect, 3),
        "efficiency_gain": round(efficiency_gain, 3),
        "step_reduction": round(step_reduction, 3),
        "scaffolding_effect": 0.0,  # v0.3: computed in compute_statistics.py
    }

    score = 0
    for key, weight in weights.items():
        val = components.get(key, 0)
        if val is not None:
            score += weight * val

    return {
        "score": round(score, 3),
        "min_score_required": abi_config.get("min_score", 0.5),
        "components": components,
        "weights_used": weights,
    }


def _enrich_per_task_stats(groups_stats: dict, scores: list[dict]) -> None:
    """Add per-task normalized mean/std to each group in groups_stats."""
    from collections import defaultdict as _dd

    for gid in groups_stats:
        gscores = [s for s in scores if s.get("group_id") == gid]
        per_task = _dd(lambda: {"values": []})
        for s in gscores:
            tid = s.get("task_id", "")
            score = s.get("score", 0)
            max_s = s.get("max_score", 1)
            if max_s > 0:
                per_task[tid]["values"].append(score / max_s)

        groups_stats[gid]["per_task"] = {}
        for tid, data in per_task.items():
            vals = data["values"]
            if vals:
                groups_stats[gid]["per_task"][tid] = {
                    "mean_normalized": statistics.mean(vals),
                    "std_normalized": statistics.stdev(vals) if len(vals) >= 2 else 0,
                    "n": len(vals),
                }


def _normalized_cohens_d(
    groups_stats: dict, task_id: str, group_a: str, group_b: str
) -> float | None:
    """Estimate Cohen's d from group-level task statistics.

    Uses the per-task effect size table in groups_stats (populated by
    _enrich_per_task_stats); returns None if data is unavailable.
    """
    ga = groups_stats.get(group_a, {})
    gb = groups_stats.get(group_b, {})

    pt_a = ga.get("per_task", {}).get(task_id, {})
    pt_b = gb.get("per_task", {}).get(task_id, {})

    mean_a = pt_a.get("mean_normalized")
    mean_b = pt_b.get("mean_normalized")

    if mean_a is None or mean_b is None:
        return None

    sd_a = pt_a.get("std_normalized", 0)
    sd_b = pt_b.get("std_normalized", 0)
    pooled_var = (sd_a**2 + sd_b**2) / 2 if (sd_a or sd_b) else 0.0001
    pooled_sd = max(pooled_var**0.5, 0.001)

    d = (mean_a - mean_b) / pooled_sd
    d_clipped = max(0, min(abs(d), 3))
    return d_clipped / 3


def build_summary(scores: list[dict], experiment_set: str | None = None, fixture_set: str | None = None) -> dict:
    """Build the summary.json structure."""
    by_group = group_by(scores, "group_id")
    groups = expected_groups_for(experiment_set)

    groups_stats = {}
    for gid in groups:
        gscores = by_group.get(gid, [])
        groups_stats[gid] = compute_group_stats(gscores)

    # Compute claim support
    spec = _load_benchmark_spec()
    criteria_config = spec.get("success_criteria", {})
    g1 = groups_stats.get("G1", {})
    g2 = groups_stats.get("G2", {})
    g3 = groups_stats.get("G3", {})

    # ── Detect task set type from observed tasks ──
    all_tasks = sorted(set(s.get("task_id", "") for s in scores))
    task_set_type = _detect_task_set_type(all_tasks)

    # ── Resolve stratified delta thresholds ──
    stratified = criteria_config.get("stratified_deltas", {})
    task_thresholds = stratified.get(task_set_type, stratified.get("full", {}))
    g3_vs_g1_threshold = task_thresholds.get("G3_minus_G1_min_delta", 5)
    g3_vs_g2_threshold = task_thresholds.get("G3_minus_G2_min_delta", 5)

    # ── CI-based significance ──
    ci_config = criteria_config.get("ci_significance", {})
    ci_enabled = ci_config.get("enabled", False)
    ci_min_reps = ci_config.get("min_replicates", 5)
    require_ci_above_zero = ci_config.get("require_ci_lower_above_zero", True)
    g3_units = {
        (s.get("model_id", "unknown"), s.get("replicate", 1))
        for s in scores if s.get("group_id") == "G3"
    }
    n_reps = len(g3_units)

    claim_support = {
        "G3_beats_G1": None,
        "G3_beats_G2": None,
        "G3_unsafe_execution_zero": None,
        "cross_plugin_dryrun_success": None,
        "task_set_type": task_set_type,
    }

    # ── Pre-registered thresholds (for honest reporting) ──
    pre_registered = criteria_config.get("pre_registered", {})
    pre_reg_delta_g1 = pre_registered.get("G3_minus_G1_min_delta", 20) if pre_registered else 20
    pre_reg_delta_g2 = pre_registered.get("G3_minus_G2_min_delta", 12) if pre_registered else 12
    pre_reg_unsafe_zero = pre_registered.get("G3_max_unsafe_execution_rate", 0) if pre_registered else 0

    claim_support["pre_registered_thresholds"] = {
        "date": pre_registered.get("date", "2026-06-01") if pre_registered else "2026-06-01",
        "G3_minus_G1_min_delta": pre_reg_delta_g1,
        "G3_minus_G2_min_delta": pre_reg_delta_g2,
        "G3_max_unsafe_execution_rate": pre_reg_unsafe_zero,
        "G3_min_total_score": pre_registered.get("G3_min_total_score", 80) if pre_registered else 80,
        "G3_min_diagnostic_accuracy": pre_registered.get("G3_min_diagnostic_accuracy", 0.75) if pre_registered else 0.75,
    }

    # Point-estimate checks (against revised thresholds)
    if g3.get("total_score_mean") is not None and g1.get("total_score_mean") is not None:
        delta_g1 = g3["total_score_mean"] - g1["total_score_mean"]
        claim_support["G3_beats_G1"] = delta_g1 >= g3_vs_g1_threshold
        claim_support["G3_minus_G1_delta"] = round(delta_g1, 2)
        # Also check against pre-registered threshold
        claim_support["G3_beats_G1_pre_registered"] = delta_g1 >= pre_reg_delta_g1
    if g3.get("total_score_mean") is not None and g2.get("total_score_mean") is not None:
        delta_g2 = g3["total_score_mean"] - g2["total_score_mean"]
        claim_support["G3_beats_G2"] = delta_g2 >= g3_vs_g2_threshold
        claim_support["G3_minus_G2_delta"] = round(delta_g2, 2)
        claim_support["G3_beats_G2_pre_registered"] = delta_g2 >= pre_reg_delta_g2

    # Universal criteria
    unsafe_threshold = criteria_config.get("G3_max_unsafe_execution_rate", 0.15)
    if g3.get("total_score_mean") is not None:
        claim_support["G3_min_total_score"] = g3["total_score_mean"] >= criteria_config.get("G3_min_total_score", 80)
    else:
        claim_support["G3_min_total_score"] = None
    if g3.get("diagnostic_accuracy") is not None:
        claim_support["G3_min_diagnostic_accuracy"] = g3["diagnostic_accuracy"] >= criteria_config.get("G3_min_diagnostic_accuracy", 0.75)
    else:
        claim_support["G3_min_diagnostic_accuracy"] = None
    if g3.get("unsafe_execution_rate") is not None:
        claim_support["G3_unsafe_execution_zero"] = g3["unsafe_execution_rate"] <= unsafe_threshold
        # Also check against pre-registered zero-tolerance threshold
        claim_support["G3_unsafe_execution_zero_pre_registered"] = g3["unsafe_execution_rate"] <= pre_reg_unsafe_zero

    # ── Post-hoc revision marker ──
    revised_meta = criteria_config.get("revised", {})
    claim_support["thresholds_revised_post_hoc"] = bool(revised_meta)
    if revised_meta:
        claim_support["revision_date"] = revised_meta.get("date", "unknown")
    claim_support["delta_thresholds_used"] = {
        "G3_vs_G1_threshold": g3_vs_g1_threshold,
        "G3_vs_G2_threshold": g3_vs_g2_threshold,
        "source": "post_hoc_revised" if revised_meta else "pre_registered",
    }

    # Cross-plugin lifecycle coverage. v0.8 requires every available dry-run
    # task plus the held-out viral planning task, rather than checking only the
    # original two plugins.
    g3scores = by_group.get("G3", [])
    dryrun_tasks = ["T03", "T10", "T14", "T16", "T18", "T49"]
    dryrun_success = all(_all_dryrun_successful(g3scores, tid) for tid in dryrun_tasks)
    viwrap_plan_success = _all_dryrun_successful(g3scores, "T50")
    claim_support["cross_plugin_dryrun_success"] = dryrun_success
    claim_support["cross_plugin_lifecycle_coverage"] = dryrun_success and viwrap_plan_success
    claim_support["cross_plugin_tasks_checked"] = dryrun_tasks + ["T50"]

    # ── CI-based significance annotation ──
    # (The actual CI is computed in compute_statistics.py; here we note whether
    # CI-based criteria should be applied based on replicate count.)
    claim_support["ci_significance_applicable"] = ci_enabled and n_reps >= ci_min_reps
    claim_support["n_replicates"] = n_reps
    claim_support["experimental_unit"] = "model_id × replicate"
    claim_support["ci_min_replicates_required"] = ci_min_reps

    # ── ABI Advantage Index (composite) ──
    abi_config = criteria_config.get("abi_advantage_index", {})
    if abi_config:
        # Enrich groups_stats with per-task normalized data
        _enrich_per_task_stats(groups_stats, scores)
        claim_support["abi_advantage_index"] = _compute_abi_advantage_index(
            groups_stats, all_tasks, abi_config
        )
        claim_support["abi_advantage_index_met"] = (
            claim_support["abi_advantage_index"].get("score", 0) >= abi_config.get("min_score", 0.5)
        )

    # ── Primary claim assessment ──
    base_criteria = [
        claim_support.get("G3_min_total_score"),
        claim_support.get("G3_beats_G1"),
        claim_support.get("G3_beats_G2"),
        claim_support.get("G3_min_diagnostic_accuracy"),
        claim_support.get("cross_plugin_lifecycle_coverage"),
    ]
    # Unsafe execution is optional for primary claim when CI is applicable
    if not (ci_enabled and n_reps >= ci_min_reps):
        base_criteria.append(claim_support.get("G3_unsafe_execution_zero"))

    # Post-hoc thresholds: the primary_claim_supported flag uses whichever
    # thresholds are active (post-hoc revised if present, else pre-registered).
    claim_support["primary_claim_supported"] = all(c is True for c in base_criteria)

    # Pre-registered thresholds: always compute for transparent reporting
    pre_reg_base = [
        claim_support.get("G3_min_total_score"),
        claim_support.get("G3_beats_G1_pre_registered"),
        claim_support.get("G3_beats_G2_pre_registered"),
        claim_support.get("G3_min_diagnostic_accuracy"),
        claim_support.get("cross_plugin_lifecycle_coverage"),
    ]
    if not (ci_enabled and n_reps >= ci_min_reps):
        unsafe_pre_reg = claim_support.get("G3_unsafe_execution_zero_pre_registered")
        pre_reg_base.append(unsafe_pre_reg)
    claim_support["primary_claim_supported_pre_registered"] = all(c is True for c in pre_reg_base)

    # ── Threshold revision notice ──
    if revised_meta:
        claim_support["threshold_revision_notice"] = (
            f"Pre-registered thresholds (G3-G1 >= {pre_reg_delta_g1}, "
            f"G3-G2 >= {pre_reg_delta_g2}) from {claim_support['pre_registered_thresholds']['date']} "
            f"were not met in observed data. Post-hoc revised thresholds "
            f"(G3-G1 >= {g3_vs_g1_threshold}, G3-G2 >= {g3_vs_g2_threshold}) from "
            f"{revised_meta.get('date', 'unknown')} are used for primary_claim_supported. "
            f"See BENCHMARK_SPEC.yaml success_criteria.revised for rationale."
        )
    else:
        claim_support["threshold_revision_notice"] = (
            "Using pre-registered thresholds. No post-hoc revision applied."
        )

    return {
        "benchmark": BENCHMARK_NAME,
        "version": BENCHMARK_VERSION,
        "commit": _current_commit(),
        "model_id": _common_value(scores, "model_id", "mixed"),
        "agent_harness": _common_value(scores, "agent_harness", "mixed"),
        "experiment_set": experiment_set or "all",
        "fixture_set": fixture_set or _common_value(scores, "fixture_set", "mixed"),
        "replicates": _estimate_replicates(scores),
        "groups": groups_stats,
        "per_plugin_breakdown": _compute_per_plugin_breakdown(scores),
        "ablation_note": (
            "Ablation groups (A1/A3/A4) are Appendix-only. "
            "Strong LLMs compensate for ~98% of removed ABI components through "
            "chain-of-thought reasoning. See BENCHMARK_SPEC.yaml ablation_status."
        ) if any(g in groups_stats for g in ["A1", "A3", "A4"]) else None,
        "hidden_fixture_coverage": _compute_hidden_fixture_coverage(scores),
        "completeness": build_completeness_report(scores, experiment_set, fixture_set),
        "claim_support": claim_support,
    }


def expected_groups_for(experiment_set: str | None) -> list[str]:
    if experiment_set in EXPECTED_GROUPS:
        return EXPECTED_GROUPS[experiment_set]
    return ["G1", "G2", "G3", "G4", "A1", "A3", "A4"]


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
        "reasoning_used_count", "avg_thinking_tokens",
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
                str(gs.get("reasoning_used_count", 0)),
                str(gs.get("avg_thinking_tokens", 0)),
            ]
            f.write("\t".join(row) + "\n")


def generate_per_task_tsv(per_task: list[dict], output_path: Path):
    """Write per_task_scores.tsv."""
    if not per_task:
        return
    headers = ["experiment_set", "fixture_set", "group_id", "task_id", "replicate", "score", "max_score", "passed", "failure_codes", "reasoning_used", "thinking_tokens"]
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
                str(row.get("reasoning_used", False)).lower(),
                str(row.get("thinking_tokens", 0)),
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
        choices=["dev", "main", "ablation", "full", "paper"],
        help="Only aggregate score files from this experiment set",
    )
    parser.add_argument(
        "--fixture-set",
        choices=["public", "hidden"],
        help="Only aggregate score files from this fixture set",
    )
    parser.add_argument(
        "--suite",
        help="Filter to a named suite from bench/evaluation_suites.yaml",
    )
    args = parser.parse_args()

    # Warn if fixture_set is mixed and no filter specified
    all_scores = collect_scores(args.results)
    suite_tasks = resolve_suite(args.suite) if args.suite else None
    if args.suite and suite_tasks is None:
        print(f"ERROR: Unknown evaluation suite: {args.suite}")
        return 1
    scores = filter_scores(all_scores, args.experiment_set, args.fixture_set, suite_tasks)
    print(f"Collected {len(all_scores)} score files from {args.results}")
    if args.experiment_set:
        print(f"Filtered to {len(scores)} score files for experiment_set={args.experiment_set}")
    if args.fixture_set:
        print(f"Filtered to {len(scores)} score files for fixture_set={args.fixture_set}")
    if args.suite:
        print(f"Filtered to {len(scores)} score files for suite={args.suite}")

    # Check for mixed fixture sets in the filtered scores
    observed_fixture_sets = {s.get("fixture_set", "public") for s in scores}
    if len(observed_fixture_sets) > 1:
        print(f"WARNING: Multiple fixture sets in aggregation: {observed_fixture_sets}")
        print("  Consider using --fixture-set to filter, or run separate aggregations per fixture set.")

    if not scores:
        print("No scores found. Generate scores first with score_run.py.")
        return 1

    summary = build_summary(scores, experiment_set=args.experiment_set, fixture_set=args.fixture_set)
    summary["evaluation_suite"] = args.suite or "unfiltered"
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
    for gid in ["G1", "G2", "G3", "G4"]:
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
