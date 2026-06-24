#!/usr/bin/env python3
"""
ABI-Bench v0.2 — Sequential Randomized-Block Group Runner

Runs groups sequentially (one at a time) with randomized order per replicate
to eliminate temporal confounding from parallel API execution.

Usage:
    python bench/harness/run_sequential.py \
      --groups G1,G2,G3,A1,A3,A4 \
      --tasks full \
      --replicates 15 \
      --agent-mode direct \
      --experiment-set paper \
      --fixture-set public \
      --workers 4 \
      --seed 42

Design:
  - Groups are run SEQUENTIALLY (one at a time), eliminating temporal confounding
  - Each group's 180 tasks use internal --parallel for speed
  - Execution order and API latency are recorded for covariate analysis
"""

import argparse
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def _resolve_tasks_for_count(task_spec: str) -> list[str]:
    """Resolve task spec to a task list for counting only (avoids importing run_group)."""
    spec = task_spec.strip()
    from bench.harness.task_suites import resolve_suite

    suite_tasks = resolve_suite(spec)
    if suite_tasks is not None:
        return suite_tasks
    if spec == "mvp":
        return ["T01", "T02", "T03", "T05", "T06", "T08", "T09", "T10"]
    elif spec == "full":
        return ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12"]
    elif spec == "full_v0_3":
        return ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19"]
    elif spec == "extended_v0_3":
        return ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19", "T20", "T21", "T22", "T23", "T24"]
    elif spec == "full_v0_4":
        return ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19", "T25", "T26", "T27", "T28", "T29", "T30"]
    elif spec == "extended_v0_4":
        return ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19", "T20", "T21", "T22", "T23", "T24", "T25", "T26", "T27", "T28", "T29", "T30"]
    elif spec == "full_v0_5":
        return ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19", "T25", "T26", "T27", "T28", "T29", "T30", "T31", "T32", "T33", "T34", "T35"]
    elif spec == "extended_v0_5":
        return ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19", "T20", "T21", "T22", "T23", "T24", "T25", "T26", "T27", "T28", "T29", "T30", "T31", "T32", "T33", "T34", "T35"]
    elif spec == "full_v0_6":
        return ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19", "T25", "T26", "T27", "T28", "T29", "T30", "T31", "T32", "T33", "T34", "T35", "T36", "T37", "T38", "T39", "T40", "T41", "T42", "T43", "T44", "T45", "T46", "T47"]
    elif spec == "extended_v0_6":
        return ["T01", "T02", "T03", "T04", "T05", "T06", "T07", "T08", "T09", "T10", "T11", "T12", "T13", "T14", "T15", "T16", "T17", "T18", "T19", "T20", "T21", "T22", "T23", "T24", "T25", "T26", "T27", "T28", "T29", "T30", "T31", "T32", "T33", "T34", "T35", "T36", "T37", "T38", "T39", "T40", "T41", "T42", "T43", "T44", "T45", "T46", "T47"]
    elif spec == "ablation":
        return ["T03", "T04", "T05", "T06", "T07", "T08"]
    else:
        return [t.strip() for t in spec.split(",") if t.strip()]


def run_group(
    group_id: str,
    tasks: str,
    replicates: int,
    agent_mode: str,
    experiment_set: str,
    fixture_set: str,
    workers: int,
    randomize_tasks: bool = False,
    seed: int = 42,
) -> dict:
    """Run a single group. Returns timing and result info."""
    start = time.time()
    start_dt = datetime.now(timezone.utc)

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "bench/harness/run_group.py"),
        "--group", group_id,
        "--tasks", tasks,
        "--replicates", str(replicates),
        "--agent-mode", agent_mode,
        "--experiment-set", experiment_set,
        "--fixture-set", fixture_set,
        "--parallel",
        "--workers", str(workers),
    ]
    if randomize_tasks:
        cmd.extend(["--randomize-tasks", "--seed", str(seed)])

    from bench.harness.config import load_bench_config
    _cfg = load_bench_config()
    env = {**__import__("os").environ, "ABI_BENCH_MAX_TOKENS": str(_cfg.max_tokens)}

    print(f"\n{'='*70}")
    print(f"GROUP {group_id} — START ({start_dt.strftime('%H:%M:%S')})")
    print(f"{'='*70}")

    result = subprocess.run(cmd, env=env, cwd=str(PROJECT_ROOT))

    elapsed = time.time() - start
    end_dt = datetime.now(timezone.utc)
    success = result.returncode == 0

    status = "✅ OK" if success else f"❌ FAIL (exit={result.returncode})"
    print(f"\nGROUP {group_id} — {status} — {elapsed:.0f}s "
          f"({start_dt.strftime('%H:%M:%S')} → {end_dt.strftime('%H:%M:%S')})")

    return {
        "group_id": group_id,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "exit_code": result.returncode,
        "success": success,
    }


def main():
    parser = argparse.ArgumentParser(
        description="ABI-Bench Sequential Randomized-Block Group Runner"
    )
    parser.add_argument("--groups", default="G1,G2,G3,A1,A3,A4",
                        help="Comma-separated group IDs")
    parser.add_argument("--tasks", default="full_v0_3")
    parser.add_argument("--replicates", type=int, default=15)
    parser.add_argument("--agent-mode", default="direct")
    parser.add_argument("--experiment-set", default="paper")
    parser.add_argument("--fixture-set", default="public")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for group order and task order (use 0 for fixed order)")
    parser.add_argument("--order", default=None,
                        help="Explicit group order, comma-separated (overrides seed)")
    parser.add_argument("--randomize-tasks", action="store_true",
                        help="Randomize task order per replicate to eliminate fixed-order confound")
    args = parser.parse_args()

    groups = [g.strip() for g in args.groups.split(",") if g.strip()]

    # ── Determine execution order ──
    if args.order:
        ordered = [g.strip() for g in args.order.split(",") if g.strip()]
        # Validate
        if set(ordered) != set(groups):
            print(f"ERROR: --order {ordered} doesn't match --groups {groups}")
            sys.exit(1)
        print(f"Execution order (explicit): {' → '.join(ordered)}")
    elif args.seed == 0:
        ordered = list(groups)
        print(f"Execution order (fixed): {' → '.join(ordered)}")
    else:
        rng = random.Random(args.seed)
        ordered = list(groups)
        rng.shuffle(ordered)
        print(f"Execution order (random seed={args.seed}): {' → '.join(ordered)}")

    # ── Metadata header ──
    task_list = _resolve_tasks_for_count(args.tasks)
    total_tasks = len(args.groups.split(",")) * args.replicates * len(task_list)
    print(f"\nSequential run: {len(ordered)} groups × {len(task_list)} tasks × "
          f"{args.replicates} reps ≈ {total_tasks} total runs")
    print(f"Estimated wall time: {len(ordered)} × ~15min ≈ "
          f"{len(ordered) * 15} minutes\n")

    # ── Run groups sequentially ──
    overall_start = time.time()
    results = []

    for i, gid in enumerate(ordered):
        print(f"\n[{i+1}/{len(ordered)}] Running {gid}...")
        result = run_group(
            group_id=gid,
            tasks=args.tasks,
            replicates=args.replicates,
            agent_mode=args.agent_mode,
            experiment_set=args.experiment_set,
            fixture_set=args.fixture_set,
            workers=args.workers,
            randomize_tasks=args.randomize_tasks,
            seed=args.seed,
        )
        results.append(result)

    overall_elapsed = time.time() - overall_start

    # ── Summary ──
    print(f"\n{'='*70}")
    print(f"SEQUENTIAL RUN COMPLETE — {overall_elapsed:.0f}s total")
    print(f"{'='*70}")
    print(f"{'Group':<8} {'Elapsed':<12} {'Start':<12} {'End':<12} {'Status'}")
    print(f"{'-'*8} {'-'*12} {'-'*12} {'-'*12} {'-'*8}")
    for r in results:
        start_ts = r["start_time"][11:19] if "T" in r["start_time"] else r["start_time"]
        end_ts = r["end_time"][11:19] if "T" in r["end_time"] else r["end_time"]
        status = "✅" if r["success"] else "❌"
        print(f"{r['group_id']:<8} {r['elapsed_seconds']:<12.0f} "
              f"{start_ts:<12} {end_ts:<12} {status}")

    # Write execution manifest
    manifest_path = PROJECT_ROOT / "bench/results/sequential_manifest.json"
    import json
    manifest = {
        "design": "sequential_randomized_block",
        "seed": args.seed,
        "execution_order": ordered,
        "groups": args.groups,
        "tasks": args.tasks,
        "replicates": args.replicates,
        "experiment_set": args.experiment_set,
        "fixture_set": args.fixture_set,
        "total_elapsed_seconds": round(overall_elapsed, 1),
        "group_results": results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest: {manifest_path}")

    # Return non-zero if any group failed
    failed = [r for r in results if not r["success"]]
    if failed:
        print(f"\n{failed} groups failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
