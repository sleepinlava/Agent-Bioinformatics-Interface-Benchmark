#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Paper Table Generator

Reads aggregated results and produces publication-ready TSV tables.

Usage:
    python bench/scoring/make_tables.py \
      --results bench/results \
      --outdir docs/experiments/abi_bench_v0_1
"""

import argparse
import json
import sys
from pathlib import Path

# Reuse the aggregation logic
sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate_scores import collect_scores, compute_group_stats, build_summary, filter_scores


def make_table1_main_results(summary: dict, outdir: Path):
    """Table 1: Main experimental results (G1/G2/G3)."""
    rows = []
    for gid in ["G1", "G2", "G3"]:
        gs = summary["groups"].get(gid, {})
        if gs.get("score_count", 0) == 0:
            continue
        rows.append({
            "Group": gid,
            "Description": {
                "G1": "README + Shell",
                "G2": "Plain Tool Calling",
                "G3": "ABI Control Layer",
            }.get(gid, ""),
            "Total_Score_Mean": gs.get("total_score_mean", "NA"),
            "Total_Score_SD": gs.get("total_score_std", "NA"),
            "Task_Success_Rate": gs.get("task_success_rate", "NA"),
            "Dry_Run_Success_Rate": gs.get("successful_dryrun_rate", "NA"),
            "Diagnostic_Accuracy": gs.get("diagnostic_accuracy", "NA"),
            "Unsafe_Exec_Rate": gs.get("unsafe_execution_rate", "NA"),
            "Artifact_Completeness": gs.get("artifact_completeness_mean", "NA"),
            "Median_Steps": gs.get("median_agent_steps", "NA"),
            "N": gs.get("score_count", 0),
        })

    _write_tsv(outdir / "table1_main_results.tsv", rows)


def make_table2_per_task(scores: list[dict], outdir: Path):
    """Table 2: Per-task score breakdown."""
    from aggregate_scores import group_by
    by_task = group_by(scores, "task_id")
    by_group = group_by(scores, "group_id")

    rows = []
    for task_id in sorted(by_task.keys()):
        for gid in ["G1", "G2", "G3"]:
            task_group_scores = [
                s for s in by_group.get(gid, [])
                if s["task_id"] == task_id
            ]
            if not task_group_scores:
                continue
            score_vals = [s["score"] for s in task_group_scores]
            import statistics
            rows.append({
                "Task": task_id,
                "Group": gid,
                "Mean_Score": round(statistics.mean(score_vals), 2),
                "SD": round(statistics.stdev(score_vals), 2) if len(score_vals) >= 2 else 0.0,
                "Max": max(score_vals),
                "Min": min(score_vals),
                "Success_Rate": round(sum(s["passed"] for s in task_group_scores) / len(task_group_scores), 3),
                "N": len(task_group_scores),
            })

    _write_tsv(outdir / "table2_per_task.tsv", rows)


def make_table3_ablation(summary: dict, outdir: Path):
    """Table 3: Ablation study results."""
    rows = []
    for gid in ["G3", "A1", "A3", "A4"]:
        gs = summary["groups"].get(gid, {})
        if gs.get("score_count", 0) == 0:
            continue
        rows.append({
            "Group": gid,
            "Description": {
                "G3": "ABI-full",
                "A1": "ABI-no-provenance",
                "A3": "ABI-no-diagnostic-hints",
                "A4": "ABI-no-permission-model",
            }.get(gid, ""),
            "Total_Score_Mean": gs.get("total_score_mean", "NA"),
            "Diagnostic_Accuracy": gs.get("diagnostic_accuracy", "NA"),
            "Unsafe_Exec_Rate": gs.get("unsafe_execution_rate", "NA"),
            "Delta_vs_G3": _delta_vs_g3(summary, gid),
        })

    _write_tsv(outdir / "table3_ablation.tsv", rows)


def make_table4_failure_taxonomy(scores: list[dict], outdir: Path):
    """Table 4: Failure code frequency by group."""
    from collections import Counter
    from aggregate_scores import group_by

    by_group = group_by(scores, "group_id")
    rows = []
    all_codes = set()
    group_code_counts = {}
    for gid in by_group:
        codes = []
        for s in by_group[gid]:
            codes.extend(s.get("failure_codes", []))
        group_code_counts[gid] = Counter(codes)
        all_codes.update(codes)

    for code in sorted(all_codes):
        row = {"Failure_Code": code}
        for gid in ["G1", "G2", "G3", "A1", "A3", "A4"]:
            row[f"{gid}_count"] = group_code_counts.get(gid, Counter()).get(code, 0)
        rows.append(row)

    _write_tsv(outdir / "table4_failure_taxonomy.tsv", rows)


def _delta_vs_g3(summary: dict, gid: str) -> str:
    """Calculate delta from G3."""
    g3 = summary["groups"].get("G3", {})
    gs = summary["groups"].get(gid, {})
    g3_mean = g3.get("total_score_mean")
    gs_mean = gs.get("total_score_mean")
    if g3_mean is None or gs_mean is None:
        return "NA"
    delta = gs_mean - g3_mean
    return f"{delta:+.2f}"


def _write_tsv(output_path: Path, rows: list[dict]):
    """Write a list of dicts as a TSV file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        with open(output_path, "w") as f:
            f.write("# No data\n")
        print(f"  (empty) {output_path}")
        return
    headers = list(rows[0].keys())
    with open(output_path, "w") as f:
        f.write("\t".join(headers) + "\n")
        for row in rows:
            f.write("\t".join(str(row.get(h, "")) for h in headers) + "\n")
    print(f"  Wrote {len(rows)} rows to {output_path}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate paper tables from ABI-Bench results")
    parser.add_argument("--results", required=True, type=Path, help="Results directory with score.json files")
    parser.add_argument("--outdir", required=True, type=Path, help="Output directory for TSV tables")
    parser.add_argument(
        "--experiment-set",
        choices=["dev", "main", "ablation", "full", "paper"],
        help="Filter by experiment set before generating tables",
    )
    parser.add_argument(
        "--fixture-set",
        choices=["public", "hidden"],
        help="Filter by fixture set before generating tables",
    )
    args = parser.parse_args()

    scores = filter_scores(
        collect_scores(args.results),
        experiment_set=args.experiment_set,
        fixture_set=args.fixture_set,
    )
    if not scores:
        print(
            "No scores found in",
            args.results,
            f"(experiment_set={args.experiment_set or 'all'}, fixture_set={args.fixture_set or 'all'})",
        )
        return 1

    summary = build_summary(scores, experiment_set=args.experiment_set, fixture_set=args.fixture_set)
    args.outdir.mkdir(parents=True, exist_ok=True)

    print("Generating paper tables...")
    make_table1_main_results(summary, args.outdir)
    make_table2_per_task(scores, args.outdir)
    make_table3_ablation(summary, args.outdir)
    make_table4_failure_taxonomy(scores, args.outdir)
    print(f"\nDone. Tables written to {args.outdir}/")

    return 0


if __name__ == "__main__":
    sys.exit(main())
