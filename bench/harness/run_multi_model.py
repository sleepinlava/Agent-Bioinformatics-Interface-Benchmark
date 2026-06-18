#!/usr/bin/env python3
"""
ABI-Bench v0.3 — Multi-Model Sequential Randomized-Block Runner

Runs the benchmark across multiple LLMs organized into capability tiers
(Strong, Medium, Weak) to measure the scaffolding effect: does ABI help
weaker models more than stronger ones?

Design:
  for model in models:
      for block in randomized_blocks:
          run G1/G2/G3/G4 in randomized order
          record latency/refusal/tool-call count

This eliminates temporal confounding while enabling Group × ModelTier
interaction analysis.

Usage:
    python bench/harness/run_multi_model.py \
      --tier strong \
      --models gpt-4o,claude-sonnet-4-6 \
      --groups G1,G2,G3,G4 \
      --tasks full_v0_3 \
      --replicates 3 \
      --experiment-set paper \
      --fixture-set public \
      --workers 4 \
      --seed 42
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Model Tier Definitions ────────────────────────────────────────────────

# Built-in fallback tiers (used when bench/model_tiers.yaml is missing).
_BUILTIN_TIERS = {
    "strong": {
        "description": "Frontier models with strong reasoning capabilities",
        "models": ["gpt-4o", "claude-sonnet-4-6", "deepseek-v4-pro"],
    },
    "medium": {
        "description": "Mid-tier models with adequate reasoning",
        "models": ["gpt-4o-mini", "qwen2.5-72b"],
    },
    "weak": {
        "description": "Smaller models where scaffolding effect is most pronounced",
        "models": ["qwen2.5-7b", "llama-3.1-8b"],
    },
}


def _load_model_tiers(yaml_path: Path | None = None) -> dict:
    """Load model tiers from a YAML file, returning a dict with an ``"all"`` key.

    Falls back to *_BUILTIN_TIERS* if the file is missing or unreadable.
    """
    if yaml_path is None:
        yaml_path = PROJECT_ROOT / "bench" / "model_tiers.yaml"
    try:
        if yaml_path.is_file():
            import yaml
            with open(yaml_path) as f:
                data = yaml.safe_load(f) or {}
            tiers = {}
            all_models = []
            for tname, tinfo in data.get("tiers", {}).items():
                models = list(tinfo.get("models", []))
                tiers[tname] = {"description": tinfo.get("description", ""), "models": models}
                all_models.extend(models)
            if tiers:
                tiers["all"] = {"description": "All models across all tiers", "models": all_models}
                return tiers
    except Exception:
        pass
    # Fallback
    all_models = []
    for tinfo in _BUILTIN_TIERS.values():
        all_models.extend(tinfo["models"])
    result = dict(_BUILTIN_TIERS)
    result["all"] = {"description": "All models across all tiers", "models": all_models}
    return result


MODEL_TIERS = _load_model_tiers()


def resolve_models(tier: str | None, models_arg: str | None) -> list[dict]:
    """Resolve model list from tier and/or explicit model list.

    Returns a list of {"model_id": str, "tier": str} dicts.
    """
    if models_arg:
        model_ids = [m.strip() for m in models_arg.split(",") if m.strip()]
        # Resolve tiers
        result = []
        for mid in model_ids:
            found_tier = "unknown"
            for tname, tinfo in MODEL_TIERS.items():
                if tname == "all":
                    continue
                if mid in tinfo["models"]:
                    found_tier = tname
                    break
            result.append({"model_id": mid, "tier": found_tier})
        return result

    if tier and tier in MODEL_TIERS:
        tinfo = MODEL_TIERS[tier]
        return [{"model_id": m, "tier": tier} for m in tinfo["models"]]

    # Default: all models
    tinfo = MODEL_TIERS["all"]
    result = []
    for mid in tinfo["models"]:
        found_tier = "unknown"
        for tname, tinfo2 in MODEL_TIERS.items():
            if tname == "all":
                continue
            if mid in tinfo2["models"]:
                found_tier = tname
                break
        result.append({"model_id": mid, "tier": found_tier})
    return result


def run_model_group(
    model_id: str,
    model_tier: str,
    group_id: str,
    tasks: str,
    replicates: int,
    agent_mode: str,
    experiment_set: str,
    fixture_set: str,
    workers: int,
    run_number: int,
    total_runs: int,
) -> dict:
    """Run a single model × group combination."""
    start = time.time()
    start_dt = datetime.now(timezone.utc)

    # Use model-specific output directory
    outdir = PROJECT_ROOT / "bench" / "results" / model_id / group_id

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "bench/harness/run_group.py"),
        "--group", group_id,
        "--tasks", tasks,
        "--replicates", str(replicates),
        "--model", model_id,
        "--agent-mode", agent_mode,
        "--experiment-set", experiment_set,
        "--fixture-set", fixture_set,
        "--parallel",
        "--workers", str(workers),
        "--outdir", str(outdir),
    ]

    env = {
        **os.environ,
        "ABI_BENCH_MAX_TOKENS": "8000",
        "ABI_BENCH_MODEL": model_id,
    }

    print(f"\n{'='*70}")
    print(f"[{run_number}/{total_runs}] MODEL={model_id} (tier={model_tier}) "
          f"GROUP={group_id} — START ({start_dt.strftime('%H:%M:%S')})")
    print(f"{'='*70}")

    try:
        result = subprocess.run(cmd, env=env, cwd=str(PROJECT_ROOT))
    except FileNotFoundError as e:
        elapsed = time.time() - start
        print(f"  MODEL={model_id} GROUP={group_id} — ERROR: {e}")
        return {
            "model_id": model_id,
            "model_tier": model_tier,
            "group_id": group_id,
            "start_time": start_dt.isoformat(),
            "end_time": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "exit_code": -1,
            "success": False,
        }
    except Exception as e:
        elapsed = time.time() - start
        print(f"  MODEL={model_id} GROUP={group_id} — ERROR: {e}")
        return {
            "model_id": model_id,
            "model_tier": model_tier,
            "group_id": group_id,
            "start_time": start_dt.isoformat(),
            "end_time": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": round(elapsed, 1),
            "exit_code": -1,
            "success": False,
        }

    elapsed = time.time() - start
    end_dt = datetime.now(timezone.utc)
    success = result.returncode == 0

    status = "OK" if success else f"FAIL (exit={result.returncode})"
    print(f"  MODEL={model_id} GROUP={group_id} — {status} — {elapsed:.0f}s")

    return {
        "model_id": model_id,
        "model_tier": model_tier,
        "group_id": group_id,
        "start_time": start_dt.isoformat(),
        "end_time": end_dt.isoformat(),
        "elapsed_seconds": round(elapsed, 1),
        "exit_code": result.returncode,
        "success": success,
    }


def main():
    parser = argparse.ArgumentParser(
        description="ABI-Bench v0.3 Multi-Model Runner"
    )
    parser.add_argument("--tier", choices=["strong", "medium", "weak", "all"],
                        help="Model tier to run")
    parser.add_argument("--models", default=None,
                        help="Comma-separated model IDs (overrides --tier)")
    parser.add_argument("--groups", default="G1,G2,G3,G4",
                        help="Comma-separated group IDs")
    parser.add_argument("--tasks", default="full_v0_3")
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--agent-mode", default="direct")
    parser.add_argument("--experiment-set", default="paper")
    parser.add_argument("--fixture-set", default="public")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for group order within each model")
    parser.add_argument("--order", default=None,
                        help="Explicit group order (overrides seed)")
    args = parser.parse_args()

    models = resolve_models(args.tier, args.models)
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]

    if not models:
        print("ERROR: No models resolved. Use --tier or --models.")
        sys.exit(1)

    print(f"{'='*70}")
    print(f"ABI-Bench v0.3 — Multi-Model Experiment")
    print(f"  Models: {[m['model_id'] for m in models]}")
    print(f"  Tiers: {sorted(set(m['tier'] for m in models))}")
    print(f"  Groups: {groups}")
    print(f"  Tasks: {args.tasks}")
    print(f"  Replicates: {args.replicates}")
    print(f"  Experiment set: {args.experiment_set}")
    print(f"  Fixture set: {args.fixture_set}")
    print(f"{'='*70}")

    # ── Sequential randomized-block: for each model, randomize group order ──
    total_runs = len(models) * len(groups)
    overall_start = time.time()
    all_results = []
    failures = []

    rng = random.Random(args.seed)
    run_number = 0

    for model_info in models:
        model_id = model_info["model_id"]
        model_tier = model_info["tier"]

        # Set model env var
        os.environ["ABI_BENCH_MODEL"] = model_id

        # Randomized group order per model (sequential randomized-block)
        if args.order:
            model_groups = [g.strip() for g in args.order.split(",") if g.strip()]
        else:
            model_groups = list(groups)
            rng.shuffle(model_groups)

        print(f"\n  Model {model_id} (tier={model_tier}): "
              f"group order = {' → '.join(model_groups)}")

        for gid in model_groups:
            run_number += 1
            result = run_model_group(
                model_id=model_id,
                model_tier=model_tier,
                group_id=gid,
                tasks=args.tasks,
                replicates=args.replicates,
                agent_mode=args.agent_mode,
                experiment_set=args.experiment_set,
                fixture_set=args.fixture_set,
                workers=args.workers,
                run_number=run_number,
                total_runs=total_runs,
            )
            all_results.append(result)
            if not result["success"]:
                failures.append(result)

    overall_elapsed = time.time() - overall_start

    # ── Summary ──
    print(f"\n{'='*70}")
    print(f"MULTI-MODEL RUN COMPLETE — {overall_elapsed:.0f}s total")
    print(f"{'='*70}")
    print(f"{'Model':<22} {'Tier':<10} {'Group':<8} {'Elapsed':<10} {'Status'}")
    print(f"{'-'*22} {'-'*10} {'-'*8} {'-'*10} {'-'*8}")
    for r in all_results:
        status = "OK" if r["success"] else "FAIL"
        print(f"{r['model_id']:<22} {r['model_tier']:<10} "
              f"{r['group_id']:<8} {r['elapsed_seconds']:<10.0f} {status}")

    # Write multi-model manifest
    manifest_path = PROJECT_ROOT / "bench/results/multi_model_manifest.json"
    manifest = {
        "benchmark": "ABI-Bench",
        "version": "0.3",
        "design": "multi_model_sequential_randomized_block",
        "seed": args.seed,
        "models": [{"model_id": m["model_id"], "tier": m["tier"]} for m in models],
        "groups": groups,
        "tasks": args.tasks,
        "replicates": args.replicates,
        "experiment_set": args.experiment_set,
        "fixture_set": args.fixture_set,
        "total_elapsed_seconds": round(overall_elapsed, 1),
        "total_runs": total_runs,
        "failures": len(failures),
        "results": all_results,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nManifest: {manifest_path}")

    if failures:
        print(f"\n{len(failures)} model×group combinations failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
