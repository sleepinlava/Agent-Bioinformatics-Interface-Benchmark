#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Group Runner

Orchestrates running all tasks for a given group and replicate count.

Usage:
    python bench/harness/run_group.py \\
      --group G3 \\
      --tasks mvp \\
      --replicates 3 \\
      --model LLM4 \\
      --agent direct \\
      --outdir bench/results/G3

Parallel execution (runs tasks concurrently within each replicate batch):
    python bench/harness/run_group.py \\
      --group G3 --tasks mvp --replicates 3 --parallel --workers 4
"""

import argparse
import concurrent.futures
import subprocess
import sys
import threading
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

MVP_TASKS = ["T01", "T02", "T03", "T05", "T06", "T08", "T09", "T10"]
FULL_TASKS = ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12"]
ABLATION_TASKS = ["T03", "T04", "T05", "T06", "T07", "T08"]

_print_lock = threading.Lock()


def _ts_print(*args, **kwargs):
    """Thread-safe print."""
    with _print_lock:
        print(*args, **kwargs)


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


def _run_single_task(
    group_id: str,
    task_id: str,
    replicate: int,
    model_id: str,
    agent_harness: str,
    agent_mode: str,
    experiment_set: str,
    fixture_set: str,
    outdir: Path,
    run_number: int,
    total_runs: int,
) -> dict:
    """Run a single task and return its result.  This is the worker function
    called by both sequential and parallel paths."""
    run_outdir = outdir / task_id / f"replicate_{replicate:02d}"

    _ts_print(f"\n{'─'*70}")
    _ts_print(f"[{run_number}/{total_runs}] Group={group_id} Task={task_id} "
              f"Replicate={replicate} (started)")
    _ts_print(f"{'─'*70}")

    start = time.time()
    result = subprocess.run([
        sys.executable,
        str(PROJECT_ROOT / "bench" / "harness" / "run_task.py"),
        "--group", group_id,
        "--task", task_id,
        "--replicate", str(replicate),
        "--model", model_id,
        "--agent", agent_harness,
        "--experiment-set", experiment_set,
        "--fixture-set", fixture_set,
        "--agent-mode", agent_mode,
        "--outdir", str(run_outdir),
    ], capture_output=True, text=True)

    elapsed = time.time() - start

    outcome = {
        "group": group_id,
        "task": task_id,
        "replicate": replicate,
        "exit_code": result.returncode,
        "elapsed": elapsed,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }

    if result.returncode != 0:
        _ts_print(f"  FAILED [{group_id}/{task_id}/rep_{replicate}] "
                  f"after {elapsed:.1f}s (exit={result.returncode})")
        # Print agent-relevant stderr lines
        for line in result.stderr.strip().split("\n"):
            if "error" in line.lower() or "fail" in line.lower():
                _ts_print(f"  [stderr] {line}")
    else:
        _ts_print(f"  OK [{group_id}/{task_id}/rep_{replicate}] ({elapsed:.1f}s)")

    return outcome


def run_group(
    group_id: str,
    tasks: list[str],
    replicates: int = 3,
    model_id: str = "LLM4",
    agent_harness: str = "direct",
    agent_mode: str = "simulated",
    experiment_set: str = "dev",
    fixture_set: str = "public",
    outdir: Path = None,
    parallel: bool = False,
    workers: int = 4,
):
    """Run all tasks for a group.

    When ``parallel`` is True, tasks within the same replicate batch are
    executed concurrently using a thread pool (each task calls a separate
    subprocess, so the GIL is not a bottleneck).  Replicate batches are
    still run sequentially to ensure clean state and reproducible ordering.
    """
    if outdir is None:
        outdir = PROJECT_ROOT / "bench" / "results" / group_id

    task_count = len(tasks)
    total_runs = task_count * replicates
    failures = []

    print(f"{'='*70}")
    print(f"ABI-Bench v0.1 — Run Group '{group_id}'")
    print(f"  Tasks: {tasks}")
    print(f"  Replicates: {replicates}")
    print(f"  Experiment set: {experiment_set}")
    print(f"  Fixture set: {fixture_set}")
    print(f"  Agent mode: {agent_mode}")
    print(f"  Total runs: {total_runs}")
    print(f"  Parallel: {parallel}" + (f" (workers={workers})" if parallel else ""))
    print(f"  Outdir: {outdir}")
    print(f"{'='*70}")

    run_number = 0  # shared counter for display ordering

    if not parallel:
        # ── Sequential mode (original behaviour) ──────────────────────────
        for rep in range(1, replicates + 1):
            for task_id in tasks:
                run_number += 1
                outcome = _run_single_task(
                    group_id=group_id, task_id=task_id, replicate=rep,
                    model_id=model_id, agent_harness=agent_harness,
                    agent_mode=agent_mode, experiment_set=experiment_set,
                    fixture_set=fixture_set, outdir=outdir,
                    run_number=run_number, total_runs=total_runs,
                )
                if outcome["exit_code"] != 0:
                    failures.append(outcome)
    else:
        # ── Parallel mode ─────────────────────────────────────────────────
        actual_workers = min(workers, task_count)
        with concurrent.futures.ThreadPoolExecutor(max_workers=actual_workers) as pool:
            for rep in range(1, replicates + 1):
                # Build a future for every task in this replicate batch
                future_map: dict[concurrent.futures.Future, tuple] = {}
                for task_id in tasks:
                    run_number += 1
                    future = pool.submit(
                        _run_single_task,
                        group_id=group_id, task_id=task_id, replicate=rep,
                        model_id=model_id, agent_harness=agent_harness,
                        agent_mode=agent_mode, experiment_set=experiment_set,
                        fixture_set=fixture_set, outdir=outdir,
                        run_number=run_number, total_runs=total_runs,
                    )
                    future_map[future] = (group_id, task_id, rep)

                # Wait for the whole batch to finish before starting next replicate
                for future in concurrent.futures.as_completed(future_map):
                    outcome = future.result()
                    if outcome["exit_code"] != 0:
                        failures.append(outcome)

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"Group '{group_id}' complete.")
    print(f"  Runs: {total_runs}")
    print(f"  Failures: {len(failures)}")
    if failures:
        print("  Failed runs:")
        for f in failures:
            print(f"    {f['group']}/{f['task']}/rep_{f['replicate']} "
                  f"(exit={f['exit_code']}, {f['elapsed']:.1f}s)")
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
    parser.add_argument("--agent", type=str, default="direct", help="Agent harness name")
    parser.add_argument(
        "--experiment-set",
        type=str,
        choices=["dev", "main", "ablation", "full", "paper"],
        default="dev",
        help="Experiment set label written into all run metadata and scores",
    )
    parser.add_argument(
        "--agent-mode",
        type=str,
        choices=["simulated", "direct"],
        default="simulated",
        help="Agent execution mode: simulated (default) or direct (Python + LLM API)",
    )
    parser.add_argument(
        "--fixture-set",
        type=str,
        choices=["public", "hidden"],
        default="public",
        help="Fixture set to use for tasks that define hidden fixtures",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Run tasks within a replicate batch concurrently (thread pool)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Max concurrent workers when --parallel is set (default: 4)",
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
        experiment_set=args.experiment_set,
        fixture_set=args.fixture_set,
        outdir=args.outdir,
        parallel=args.parallel,
        workers=args.workers,
    )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
