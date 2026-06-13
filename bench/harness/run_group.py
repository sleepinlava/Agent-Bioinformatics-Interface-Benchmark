#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Group Runner

Orchestrates running all tasks for a given group and replicate count.

Usage:
    python bench/harness/run_group.py \
      --group G3 \
      --tasks mvp \
      --replicates 3 \
      --model LLM4 \
      --agent opencode \
      --outdir bench/results/G3
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

MVP_TASKS = ["T01", "T02", "T03", "T05", "T06", "T08", "T09", "T10"]
FULL_TASKS = ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12"]
ABLATION_TASKS = ["T03", "T04", "T05", "T06", "T07", "T08"]


def resolve_tasks(task_spec: str) -> list[str]:
    """Resolve task specification to list of task IDs."""
    if task_spec == "mvp":
        return MVP_TASKS
    elif task_spec == "full":
        return FULL_TASKS
    elif task_spec == "ablation":
        return ABLATION_TASKS
    else:
        return [t.strip() for t in task_spec.split(",") if t.strip()]


def run_group(
    group_id: str,
    tasks: list[str],
    replicates: int = 3,
    model_id: str = "LLM4",
    agent_harness: str = "opencode",
    agent_mode: str = "simulated",
    outdir: Path = None,
):
    """Run all tasks for a group."""
    if outdir is None:
        outdir = PROJECT_ROOT / "bench" / "results" / group_id

    task_count = len(tasks)
    total_runs = task_count * replicates
    run_number = 0
    failures = []

    print(f"{'='*70}")
    print(f"ABI-Bench v0.1 — Run Group '{group_id}'")
    print(f"  Tasks: {tasks}")
    print(f"  Replicates: {replicates}")
    print(f"  Agent mode: {agent_mode}")
    print(f"  Total runs: {total_runs}")
    print(f"  Outdir: {outdir}")
    print(f"{'='*70}")

    for rep in range(1, replicates + 1):
        for task_id in tasks:
            run_number += 1
            run_outdir = outdir / task_id / f"replicate_{rep:02d}"

            print(f"\n{'─'*70}")
            print(f"[{run_number}/{total_runs}] Group={group_id} Task={task_id} Replicate={rep}/{replicates}")
            print(f"{'─'*70}")

            start = time.time()
            result = subprocess.run([
                sys.executable,
                str(PROJECT_ROOT / "bench" / "harness" / "run_task.py"),
                "--group", group_id,
                "--task", task_id,
                "--replicate", str(rep),
                "--model", model_id,
                "--agent", agent_harness,
                "--agent-mode", agent_mode,
                "--outdir", str(run_outdir),
            ])

            elapsed = time.time() - start

            if result.returncode != 0:
                print(f"  FAILED after {elapsed:.1f}s (exit code {result.returncode})")
                failures.append({
                    "group": group_id,
                    "task": task_id,
                    "replicate": rep,
                    "exit_code": result.returncode,
                })
            else:
                print(f"  OK ({elapsed:.1f}s)")

    # Summary
    print(f"\n{'='*70}")
    print(f"Group '{group_id}' complete.")
    print(f"  Runs: {total_runs}")
    print(f"  Failures: {len(failures)}")
    if failures:
        print("  Failed runs:")
        for f in failures:
            print(f"    {f['group']}/{f['task']}/rep_{f['replicate']} (exit={f['exit_code']})")
    print(f"{'='*70}")

    return len(failures)


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run a group of ABI-Bench tasks")
    parser.add_argument("--group", required=True, type=str, help="Group ID (G1/G2/G3/A1/A3/A4)")
    parser.add_argument("--tasks", default="mvp", type=str,
                        help="Task spec: 'mvp', 'full', 'ablation', or comma-separated list")
    parser.add_argument("--replicates", type=int, default=3, help="Number of replicates per task")
    parser.add_argument("--model", type=str, default="LLM4", help="Model ID")
    parser.add_argument("--agent", type=str, default="opencode", help="Agent harness name")
    parser.add_argument(
        "--agent-mode",
        type=str,
        choices=["simulated", "opencode"],
        default="simulated",
        help="Agent execution mode: simulated (default) or opencode (real LLM)",
    )
    parser.add_argument("--outdir", type=Path, help="Output directory for results")
    args = parser.parse_args()

    tasks = resolve_tasks(args.tasks)
    failures = run_group(
        group_id=args.group,
        tasks=tasks,
        replicates=args.replicates,
        model_id=args.model,
        agent_harness=args.agent,
        agent_mode=args.agent_mode,
        outdir=args.outdir,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
