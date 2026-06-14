#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Trace Collector

Collects agent interaction traces from a run and writes them
into structured trace files in the traces directory.

Usage:
    python bench/harness/collect_trace.py \
      --source bench/workspaces/G3/T03/replicate_01/.agent_log \
      --output bench/traces/G3/T03/replicate_01
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def collect_trace(source_dir: Path, output_dir: Path, task_id: str = None,
                  group_id: str = None, replicate: int = 1,
                  experiment_set: str = "dev"):
    """Collect trace files from agent log directory into structured trace output."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Copy key log files if present
    trace_files = [
        "agent_trace.jsonl",
        "tool_calls.jsonl",
        "commands.log",
        "file_changes.json",
        "final_answer.md",
        "final_answer.json",
    ]

    collected = []
    for fname in trace_files:
        src = source_dir / fname
        if src.is_file():
            dst = output_dir / fname
            shutil.copy2(src, dst)
            collected.append(fname)
        else:
            print(f"  (not found: {fname})")

    # Generate metadata.json
    metadata = {
        "benchmark": "ABI-Bench",
        "version": "0.1",
        "task_id": task_id or _infer_from_path(output_dir, "T"),
        "group_id": group_id or _infer_from_path(output_dir, "G"),
        "experiment_set": experiment_set,
        "replicate": replicate,
        "model_id": "LLM4",
        "agent_harness": "opencode",
        "commit": _current_commit(),
        "start_time": datetime.now(timezone.utc).isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "workspace_dir": str(_sibling_dir(output_dir, "traces", "workspaces")),
        "result_dir": str(_sibling_dir(output_dir, "traces", "results")),
        "collected_files": collected,
    }
    with open(output_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Trace collected to {output_dir}: {len(collected)} files")
    return collected


def _sibling_dir(trace_dir: Path, from_dir: str, to_dir: str) -> Path:
    """Derive workspace/result dir from trace dir by swapping the top-level directory name.

    E.g. bench/traces/G3/T03/replicate_01 → bench/workspaces/G3/T03/replicate_01

    Uses the relative path from PROJECT_ROOT to find and replace only the
    first relevant component, avoiding the fragile ``str.replace()`` that
    corrupts paths when the search string appears multiple times.
    """
    try:
        rel = trace_dir.resolve().relative_to(PROJECT_ROOT)
    except ValueError:
        # trace_dir is not under PROJECT_ROOT — fall back to the old heuristic
        return Path(str(trace_dir).replace(from_dir, to_dir, 1))
    parts = rel.parts
    if parts and parts[0] == from_dir:
        return PROJECT_ROOT / to_dir / Path(*parts[1:])
    # Walk parts to find the right component to replace
    for i, part in enumerate(parts):
        if part == from_dir:
            new_parts = list(parts)
            new_parts[i] = to_dir
            return PROJECT_ROOT / Path(*new_parts)
    # If 'traces' not found, fall back to the first occurrence
    return Path(str(trace_dir).replace(from_dir, to_dir, 1))


def _infer_from_path(path: Path, prefix: str) -> str:
    """Infer task_id or group_id from directory path.

    Matches known group IDs (G1-G3, A1/A3/A4) or task IDs (T01-T12).
    """
    known_groups = {"G1", "G2", "G3", "A1", "A3", "A4"}
    for p in path.parts:
        if prefix == "G" or prefix == "A":
            if p in known_groups:
                return p
        elif prefix == "T":
            if len(p) == 3 and p.startswith("T") and p[1:].isdigit():
                return p
    return "unknown"


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


def main():
    parser = argparse.ArgumentParser(description="Collect ABI-Bench agent traces")
    parser.add_argument("--source", required=True, type=Path, help="Agent log source directory")
    parser.add_argument("--output", required=True, type=Path, help="Trace output directory")
    parser.add_argument("--task-id", type=str, help="Task ID override")
    parser.add_argument("--group-id", type=str, help="Group ID override")
    parser.add_argument("--replicate", type=int, default=1, help="Replicate number")
    parser.add_argument(
        "--experiment-set",
        choices=["dev", "main", "ablation", "full", "paper"],
        default="dev",
        help="Experiment set label for trace metadata",
    )
    args = parser.parse_args()

    collected = collect_trace(
        args.source, args.output,
        task_id=args.task_id,
        group_id=args.group_id,
        replicate=args.replicate,
        experiment_set=args.experiment_set,
    )
    return 0 if collected else 1


if __name__ == "__main__":
    sys.exit(main())
