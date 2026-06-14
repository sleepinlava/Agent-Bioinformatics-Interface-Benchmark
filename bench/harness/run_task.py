#!/usr/bin/env python3
"""
ABI-Bench v0.1 — Single Task Runner

Orchestrates a single benchmark task run:
  1. Reset workspace from fixture
  2. Export agent context
  3. Launch agent (or simulate agent run)
  4. Collect traces
  5. Score the run

Usage:
    python bench/harness/run_task.py \
      --group G3 \
      --task T03 \
      --replicate 1 \
      --model LLM4 \
      --agent opencode \
      --outdir bench/results/G3/T03/replicate_01
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Allow direct execution from repo root
sys.path.insert(0, str(PROJECT_ROOT))

from bench.harness.diagnosis import diagnose_workspace_structured as _diagnose_workspace_structured
from bench.harness.diagnosis import format_diagnosis_markdown as _format_diagnosis_markdown


def run_task(
    group_id: str,
    task_id: str,
    replicate: int = 1,
    model_id: str = "LLM4",
    agent_harness: str = "opencode",
    experiment_set: str = "dev",
    fixture_set: str = "public",
    outdir: Path = None,
    dry_run_scoring_only: bool = False,
    use_real_agent: bool = False,
):
    """Run a single task end-to-end."""
    task_yaml = _task_yaml_path(task_id)
    if task_yaml is None:
        print(f"ERROR: No task YAML found for {task_id}")
        return 1
    task_def = _load_task_definition(task_yaml)
    fixture_name, fixture_dir = _select_fixture(task_id, task_def, fixture_set)
    if fixture_dir is None:
        return 1
    expected_answer_path = _expected_answer_path(fixture_name)

    if outdir is None:
        outdir = PROJECT_ROOT / "bench" / "results" / group_id / task_id / f"replicate_{replicate:02d}"

    workspace_dir = PROJECT_ROOT / "bench" / "workspaces" / group_id / task_id / f"replicate_{replicate:02d}"
    trace_dir = PROJECT_ROOT / "bench" / "traces" / group_id / task_id / f"replicate_{replicate:02d}"

    print(f"{'='*60}")
    print(f"ABI-Bench v0.1 — Run Task")
    if dry_run_scoring_only:
        print("  MODE: scoring-only (skipping workspace reset, agent run, trace collection)")
    print(f"  Group: {group_id}")
    print(f"  Task:  {task_id}")
    print(f"  Replicate: {replicate}")
    print(f"  Experiment set: {experiment_set}")
    print(f"  Fixture set: {fixture_set}")
    print(f"  Fixture: {fixture_name}")
    print(f"  Outdir: {outdir}")
    print(f"{'='*60}")

    agent_result = 0

    if dry_run_scoring_only:
        # Scoring-only mode: skip workspace reset, agent run, and trace collection.
        # Expect artifacts already present in outdir and traces already in trace_dir.
        print("\n[1-4/5] Skipped (dry-run scoring-only mode)")
        if not outdir.is_dir():
            print(f"ERROR: Output directory does not exist: {outdir}")
            print("  Cannot score without artifact files. Run the task first without --dry-run-scoring-only.")
            return 1
        if not trace_dir.is_dir():
            print(f"WARNING: Trace directory does not exist: {trace_dir}")
    else:
        # Step 1: Reset workspace
        print("\n[1/5] Resetting workspace...")
        result = subprocess.run([
            sys.executable,
            str(PROJECT_ROOT / "bench" / "harness" / "reset_workspace.py"),
            "--fixture", str(fixture_dir),
            "--workspace", str(workspace_dir),
            "--overwrite",
        ], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: Workspace reset failed:\n{result.stderr}")
            return result.returncode
        print(result.stdout.strip())

        # Step 2: Export agent context
        print("\n[2/5] Exporting agent context...")
        context_path = workspace_dir / "agent_context.json"
        result = subprocess.run([
            sys.executable,
            str(PROJECT_ROOT / "bench" / "harness" / "export_agent_context.py"),
            "--group", group_id,
            "--task", task_id,
            "--experiment-set", experiment_set,
            "--fixture-set", fixture_set,
            "--workspace", str(workspace_dir),
            "--output", str(context_path),
        ], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"ERROR: Context export failed:\n{result.stderr}")
            return result.returncode
        print(result.stdout.strip())

        # Step 3: Launch agent (simulated by default; use --agent-mode opencode for real)
        print("\n[3/5] Launching agent...")
        agent_result = _launch_agent_opencode(
            group_id, task_id, workspace_dir, trace_dir, context_path,
            replicate=replicate,
            experiment_set=experiment_set,
            fixture_set=fixture_set,
            use_real_agent=use_real_agent,
        )

        # Step 4: Collect traces
        print("\n[4/5] Collecting traces...")
        agent_log_source = trace_dir / ".agent_log" if use_real_agent else workspace_dir / ".agent_log"
        trace_result = subprocess.run([
            sys.executable,
            str(PROJECT_ROOT / "bench" / "harness" / "collect_trace.py"),
            "--source", str(agent_log_source),
            "--output", str(trace_dir),
            "--task-id", task_id,
            "--group-id", group_id,
            "--replicate", str(replicate),
            "--experiment-set", experiment_set,
        ], capture_output=True, text=True)
        if trace_result.returncode != 0:
            print(f"WARNING: Trace collection had issues:\n{trace_result.stderr}")
        print(trace_result.stdout.strip())

    # Update trace metadata with actual times
    metadata_path = trace_dir / "metadata.json"
    if metadata_path.is_file():
        with open(metadata_path) as f:
            meta = json.load(f)
        meta["workspace_dir"] = str(workspace_dir)
        meta["result_dir"] = str(outdir)
        meta["model_id"] = model_id
        meta["agent_harness"] = agent_harness
        meta["experiment_set"] = experiment_set
        meta["fixture_set"] = fixture_set
        meta["fixture_name"] = fixture_name
        meta["agent_mode"] = "opencode" if use_real_agent else "simulated"
        meta["agent_exit_code"] = agent_result
        with open(metadata_path, "w") as f:
            json.dump(meta, f, indent=2)

    if not dry_run_scoring_only:
        # Copy artifacts from workspace to results
        print("\n[4.5/5] Copying artifacts...")
        outdir.mkdir(parents=True, exist_ok=True)
        for artifact_dir in ["execution_plan.json", "artifact_manifest.json", "provenance", "tables", "report",
                              "config.yaml", "sample_sheet.tsv"]:
            src = workspace_dir / artifact_dir
            dst = outdir / artifact_dir
            if src.is_file():
                shutil.copy2(src, dst)
            elif src.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)

    # Step 5: Score the run
    print("\n[5/5] Scoring run...")
    outdir.mkdir(parents=True, exist_ok=True)
    score_output = outdir / "score.json"
    score_cmd = [
        sys.executable,
        str(PROJECT_ROOT / "bench" / "scoring" / "score_run.py"),
        "--task", str(task_yaml),
        "--run-dir", str(outdir),
        "--trace-dir", str(trace_dir),
        "--output", str(score_output),
        "--experiment-set", experiment_set,
        "--fixture-set", fixture_set,
    ]
    if expected_answer_path is not None:
        score_cmd.extend(["--expected-answer", str(expected_answer_path)])
    score_result = subprocess.run(score_cmd, capture_output=True, text=True)
    if score_result.returncode != 0:
        print(f"Scoring completed with failures:\n{score_result.stderr}")
    print(score_result.stdout.strip())

    # Summary
    print(f"\n{'='*60}")
    print("Run complete.")
    print(f"  Workspace: {workspace_dir}")
    print(f"  Traces:    {trace_dir}")
    print(f"  Results:   {outdir}")
    print(f"{'='*60}")

    return 0


def _task_yaml_path(task_id: str) -> Path | None:
    task_files = list(PROJECT_ROOT.glob(f"bench/tasks/{task_id}_*.yaml"))
    return task_files[0] if task_files else None


def _load_task_definition(task_yaml: Path) -> dict:
    import yaml
    with open(task_yaml) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise SystemExit(
            f"Task YAML {task_yaml} must contain a mapping, got {type(data).__name__}. "
            f"Check that the file starts with task-level keys (task_id, prompt, scoring, etc.)."
        )
    return data


def _select_fixture(task_id: str, task_def: dict, fixture_set: str) -> tuple[str, Path | None]:
    default_fixtures = {
        "T01": "plasmid_valid",
        "T02": "plasmid_valid",
        "T03": "plasmid_valid",
        "T04": "plasmid_valid",
        "T05": "plasmid_missing_input",
        "T06": "plasmid_missing_resource",
        "T07": "plasmid_tool_missing",
        "T08": "plasmid_valid",
        "T09": "transcriptomics_valid",
        "T10": "transcriptomics_valid",
        "T11": "transcriptomics_valid",
        "T12": "plasmid_valid",
    }
    if fixture_set == "hidden":
        fixture_name = task_def.get("hidden_fixture")
        if not fixture_name:
            # Fall back to public fixture for tasks that don't need a hidden variant
            fixture_name = task_def.get("public_fixture") or task_def.get("fixture") or default_fixtures.get(task_id, "plasmid_valid")
            fixture_root = PROJECT_ROOT / "bench" / "fixtures"
            print(f"INFO: Task {task_id} has no hidden_fixture; falling back to public fixture '{fixture_name}'")
        else:
            fixture_root = PROJECT_ROOT / "bench" / "fixtures_hidden"
    else:
        fixture_name = task_def.get("public_fixture") or task_def.get("fixture") or default_fixtures.get(task_id, "plasmid_valid")
        fixture_root = PROJECT_ROOT / "bench" / "fixtures"

    fixture_dir = fixture_root / fixture_name
    if not fixture_dir.is_dir():
        print(f"ERROR: Fixture directory not found: {fixture_dir}")
        return fixture_name, None
    return fixture_name, fixture_dir


def _expected_answer_path(fixture_name: str) -> Path | None:
    path = PROJECT_ROOT / "bench" / "expected_answers" / f"{fixture_name}.json"
    return path if path.is_file() else None


def _launch_agent_opencode(
    group_id: str,
    task_id: str,
    workspace_dir: Path,
    trace_dir: Path,
    context_path: Path,
    replicate: int = 1,
    experiment_set: str = "dev",
    fixture_set: str = "public",
    use_real_agent: bool = True,
) -> int:
    """
    Launch the agent using OpenCode harness.

    Calls `bun run bench/harness/run_agent.ts` which:
    1. Starts an OpenCode server
    2. Creates a session with the task prompt
    3. Waits for agent completion
    4. Collects traces

    Uses the simulated agent only when use_real_agent is False. In real
    opencode mode, launch failures are recorded as failed traces instead of
    falling back to simulated output.
    """
    if not use_real_agent:
        print("  Using simulated agent (use_real_agent=False)")
        return _launch_agent(
            group_id,
            task_id,
            workspace_dir,
            trace_dir,
            context_path,
            replicate=replicate,
            experiment_set=experiment_set,
            fixture_set=fixture_set,
        )

    # Check for bun availability
    bun_path = shutil.which("bun")
    home_bun = Path.home() / ".bun" / "bin" / "bun"
    if not bun_path and home_bun.exists():
        bun_path = str(home_bun)

    if not bun_path:
        msg = "bun not found; cannot run opencode agent mode."
        print(f"  ERROR: {msg}")
        _write_agent_failure(trace_dir, task_id, msg)
        return 127

    # Load task YAML to get the prompt
    task_files = list(PROJECT_ROOT.glob(f"bench/tasks/{task_id}_*.yaml"))
    if not task_files:
        msg = f"No task YAML found for {task_id}; cannot run opencode agent mode."
        print(f"  ERROR: {msg}")
        _write_agent_failure(trace_dir, task_id, msg)
        return 1

    import yaml
    with open(task_files[0]) as f:
        task_def = yaml.safe_load(f)
    task_prompt = task_def.get("prompt", "").strip()
    timeout_minutes = task_def.get("timeout_minutes", 20)

    # Build the harness script path
    harness_script = PROJECT_ROOT / "bench" / "harness" / "run_agent.ts"

    # Build environment with bun on PATH.
    # Do NOT prepend the opencode wrapper to PATH — the TypeScript harness
    # (run_agent.ts) already resolves opencode via its own which() + vendored
    # fallback.  Prepending the wrapper caused it to find itself recursively.
    env = os.environ.copy()
    if str(home_bun.parent) not in env["PATH"]:
        env["PATH"] = f"{home_bun.parent}:{env['PATH']}"

    trace_dir.mkdir(parents=True, exist_ok=True)

    # Build cmd with optional provider flags
    provider = os.environ.get("ABI_BENCH_PROVIDER", "")
    api_key = os.environ.get("ABI_BENCH_API_KEY", "")
    api_base = os.environ.get("ABI_BENCH_API_BASE", "")
    model = os.environ.get("ABI_BENCH_MODEL", "")

    cmd = [
        bun_path, "run",
        str(harness_script),
        "--workspace", str(workspace_dir),
        "--trace-dir", str(trace_dir),
        "--group", group_id,
        "--task", task_id,
        "--prompt", task_prompt,
        "--timeout-minutes", str(timeout_minutes),
    ]
    if provider:
        cmd.extend(["--provider", provider])
    if api_key:
        cmd.extend(["--api-key", api_key])
    if api_base:
        cmd.extend(["--api-base", api_base])
    if model:
        cmd.extend(["--model", model])

    print(f"  OpenCode agent harness: bun run run_agent.ts")
    print(f"  Group: {group_id}, Task: {task_id}")
    print(f"  Timeout: {timeout_minutes} min")

    try:
        result = subprocess.run(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_minutes * 60 + 60,  # extra buffer for server startup
        )
        # Print agent output
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                print(f"  [agent] {line}")
        if result.stderr:
            # Only print stderr lines that look like errors
            for line in result.stderr.strip().split("\n"):
                if "error" in line.lower() or "fail" in line.lower() or "exception" in line.lower():
                    print(f"  [agent:err] {line}")

        if result.returncode != 0:
            print(f"  Agent exited with code {result.returncode} (check traces for details)")
            # Don't fail the whole run — scoring will handle missing artifacts
        else:
            print(f"  Agent completed successfully")

        return result.returncode

    except subprocess.TimeoutExpired:
        print(f"  Agent timed out after {timeout_minutes} minutes")
        # Write timeout marker
        (trace_dir / ".agent_log").mkdir(parents=True, exist_ok=True)
        with open(trace_dir / ".agent_log" / "final_answer.md", "w") as f:
            f.write(f"# Timeout\n\nAgent run exceeded {timeout_minutes} minute timeout.")
        return 124  # Standard timeout exit code
    except Exception as e:
        print(f"  ERROR launching agent: {e}")
        _write_agent_failure(trace_dir, task_id, str(e))
        return 1


def _write_agent_failure(trace_dir: Path, task_id: str, message: str):
    """Write a minimal trace bundle so scoring records a failed real-agent run."""
    log_dir = trace_dir / ".agent_log"
    log_dir.mkdir(parents=True, exist_ok=True)
    with open(log_dir / "agent_trace.jsonl", "w") as f:
        f.write(json.dumps({
            "step": 1,
            "action": "agent_launch_failed",
            "task_id": task_id,
            "error": message,
            "human_intervention": False,
        }) + "\n")
    with open(log_dir / "tool_calls.jsonl", "w") as f:
        f.write("")
    with open(log_dir / "commands.log", "w") as f:
        f.write("# Agent launch failed before command execution\n")
    with open(log_dir / "final_answer.md", "w") as f:
        f.write(f"# Agent Launch Failed\n\n{message}\n")


def _launch_agent(
    group_id: str,
    task_id: str,
    workspace_dir: Path,
    trace_dir: Path,
    context_path: Path,
    replicate: int = 1,
    experiment_set: str = "dev",
    fixture_set: str = "public",
) -> int:
    """
    Launch the agent for this task.

    In production, this would invoke the actual agent harness (OpenCode, etc.).
    For v0.1, we use a simulated agent run that produces the expected artifacts.

    The agent receives:
      - agent_context.json (what tools are available, what the task is)
      - workspace_dir as its working directory
      - trace_dir for logging

    It writes outputs to workspace_dir (which get copied to results).
    """
    # Create .agent_log directory for trace outputs
    log_dir = workspace_dir / ".agent_log"
    log_dir.mkdir(parents=True, exist_ok=True)

    # Write a simulated agent_trace.jsonl
    agent_trace = [
        {"step": 1, "action": "read_file", "path": "config.yaml", "observation": "Loaded config"},
        {"step": 2, "action": "read_file", "path": "sample_sheet.tsv", "observation": "Loaded sample sheet"},
    ]

    # Add group-specific steps
    if group_id in ("G3", "A1", "A3", "A4"):
        agent_trace.extend([
            {"step": 3, "action": "abi_list_types", "observation": "metagenomic_plasmid, metatranscriptomics"},
            {"step": 4, "action": "abi_plan", "observation": "Plan created: execution_plan.json"},
            {"step": 5, "action": "abi_dry_run", "observation": "Dry-run completed"},
        ])

    agent_trace.append({
        "step": len(agent_trace) + 1,
        "action": "final_answer",
        "observation": "Task completed successfully.",
        "human_intervention": False,
    })

    with open(log_dir / "agent_trace.jsonl", "w") as f:
        for entry in agent_trace:
            f.write(json.dumps(entry) + "\n")

    # Write simulated tool_calls.jsonl
    tool_calls = [
        {"tool": "read_file", "args": {"path": "config.yaml"}},
        {"tool": "read_file", "args": {"path": "sample_sheet.tsv"}},
    ]
    if group_id in ("G3", "A1", "A3", "A4"):
        tool_calls.append({"tool": "abi_list_types", "args": {}})
        tool_calls.append({"tool": "abi_plan", "args": {"analysis_type": "metagenomic_plasmid"}})
        if group_id == "A4" and task_id == "T08":
            # A4 no-permission-model: agent attempts real execution
            tool_calls.append({
                "tool": "abi_run",
                "args": {"plan": "execution_plan.json"},
                "confirm_execution": True,
                "is_real_execution": True,
            })
        else:
            tool_calls.append({"tool": "abi_dry_run", "args": {"plan": "execution_plan.json"}})

    with open(log_dir / "tool_calls.jsonl", "w") as f:
        for tc in tool_calls:
            f.write(json.dumps(tc) + "\n")

    # A4 no-permission-model: add real execution marker
    if group_id == "A4" and task_id == "T08":
        trace_dir.mkdir(parents=True, exist_ok=True)
        (trace_dir / "real_execution_marker").touch()

    # Write commands.log
    with open(log_dir / "commands.log", "w") as f:
        f.write("[DRY_RUN] prodigal -i assembly.fasta -a genes.faa\n")
        f.write("[DRY_RUN] hmmscan --domtblout domain_annotations.tsv pfam.hmm genes.faa\n")
        f.write("[DRY_RUN] genomad run assembly.fasta genomad_output genomad_db\n")

    # Write simulated artifact files (group-aware)
    _write_simulated_artifacts(workspace_dir, group_id, task_id)

    final_answer_json = _generate_final_answer_json(group_id, task_id, workspace_dir)
    # Write final_answer.md (group-aware)
    if final_answer_json is not None and group_id not in ("A1", "A3"):
        final_answer = _format_diagnosis_markdown(final_answer_json)
    else:
        final_answer = _generate_final_answer(group_id, task_id)
    with open(log_dir / "final_answer.md", "w") as f:
        f.write(final_answer)

    if final_answer_json is not None:
        with open(log_dir / "final_answer.json", "w") as f:
            json.dump(final_answer_json, f, indent=2)

    _write_artifact_manifest(
        workspace_dir,
        group_id=group_id,
        task_id=task_id,
        replicate=replicate,
        experiment_set=experiment_set,
        fixture_set=fixture_set,
    )

    # Create trace_dir
    trace_dir.mkdir(parents=True, exist_ok=True)

    print(f"  Agent launched (simulated) — workspace: {workspace_dir}")
    return 0


def _write_simulated_artifacts(workspace_dir: Path, group_id: str, task_id: str):
    """Write simulated output artifacts for scoring validation.

    Group-aware: A1 (no-provenance) skips provenance artifact generation.
    """
    # execution_plan.json
    plan = {
        "analysis_type": "metagenomic_plasmid",
        "description": "Plasmid identification from metagenomic assemblies",
        "steps": [
            {"step_id": "predict_genes", "tool_id": "prodigal", "input": "assembly", "output": "genes.faa", "status": "dry_run"},
            {"step_id": "annotate_domains", "tool_id": "hmmer", "input": "genes.faa", "output": "domain_annotations.tsv", "status": "dry_run"},
            {"step_id": "classify_plasmids", "tool_id": "genomad", "input": "assembly", "output": "plasmid_classification.tsv", "status": "dry_run"},
        ],
    }
    if task_id in ("T09", "T10"):
        plan["analysis_type"] = "metatranscriptomics"
        plan["steps"] = [
            {"step_id": "trim_reads", "tool_id": "fastp", "status": "dry_run"},
            {"step_id": "align_reads", "tool_id": "STAR", "status": "dry_run"},
            {"step_id": "sort_bam", "tool_id": "samtools", "status": "dry_run"},
            {"step_id": "quantify_genes", "tool_id": "featureCounts", "status": "dry_run"},
        ]

    with open(workspace_dir / "execution_plan.json", "w") as f:
        json.dump(plan, f, indent=2)

    # provenance/ files — A1 (no-provenance) skips these entirely
    if group_id == "A1":
        print("  [A1] Skipping provenance artifacts (no-provenance ablation)")
        prov = workspace_dir / "provenance"
        prov.mkdir(exist_ok=True)
        # A1 still creates the directory but leaves it empty
        # This simulates an agent that can't access provenance
    else:
        prov = workspace_dir / "provenance"
        prov.mkdir(exist_ok=True)

        commands = [
            {"step_id": "predict_genes", "command": "prodigal -i assembly.fasta -a genes.faa", "status": "dry_run", "exit_code": None},
            {"step_id": "annotate_domains", "command": "hmmscan --domtblout domain_annotations.tsv pfam.hmm genes.faa", "status": "dry_run", "exit_code": None},
            {"step_id": "classify_plasmids", "command": "genomad run assembly.fasta genomad_output genomad_db", "status": "dry_run", "exit_code": None},
        ]
        with open(prov / "commands.tsv", "w") as f:
            f.write("step_id\tcommand\tstatus\texit_code\n")
            for c in commands:
                f.write(f"{c['step_id']}\t{c['command']}\t{c['status']}\t{c.get('exit_code', '')}\n")

        with open(prov / "resolved_inputs.tsv", "w") as f:
            f.write("sample_id\tread1\tread2\tassembly\n")
            f.write("SAMPLE_001\t/data/fixtures/plasmid_valid/data/SAMPLE_001_R1.fastq.gz\t/data/fixtures/plasmid_valid/data/SAMPLE_001_R2.fastq.gz\t/data/fixtures/plasmid_valid/data/SAMPLE_001_assembly.fasta\n")

        with open(prov / "tool_versions.tsv", "w") as f:
            f.write("tool_id\texecutable\tversion\n")
            f.write("prodigal\tprodigal\t2.6.3\n")
            f.write("hmmer\thmmscan\t3.3.2\n")

        with open(prov / "resources.json", "w") as f:
            json.dump({"genomad_db": "/data/databases/genomad/genomad_db", "pfam_hmm": "/data/databases/pfam/Pfam-A.hmm"}, f, indent=2)

        with open(prov / "run_summary.json", "w") as f:
            json.dump({"execution_mode": "dry_run", "total_steps": 3, "completed_steps": 3, "failed_steps": 0}, f, indent=2)

        with open(prov / "progress.jsonl", "w") as f:
            f.write(json.dumps({"step_id": "predict_genes", "status": "completed", "timestamp": "2026-06-12T00:00:00Z"}) + "\n")
            f.write(json.dumps({"step_id": "annotate_domains", "status": "completed", "timestamp": "2026-06-12T00:00:01Z"}) + "\n")

    # tables/
    tables = workspace_dir / "tables"
    tables.mkdir(exist_ok=True)
    with open(tables / "plasmid_annotations.tsv", "w") as f:
        f.write("contig_id\tplasmid_score\tlength\tpredicted_type\n")
        f.write("contig_001\t0.95\t4523\tplasmid\n")
        f.write("contig_002\t0.87\t3180\tplasmid\n")

    if task_id in ("T10",):
        with open(tables / "gene_expression.tsv", "w") as f:
            f.write("gene_id\tgene_name\tcount_control\tcount_treatment\tlog2fc\tpvalue\n")
            f.write("GENE001\ttetA\t150\t45\t-1.74\t0.001\n")
            f.write("GENE002\tblaTEM\t220\t210\t-0.07\t0.850\n")

    # report/
    rep = workspace_dir / "report"
    rep.mkdir(exist_ok=True)
    with open(rep / "report.md", "w") as f:
        f.write("# ABI-Bench Dry-Run Report\n\n")
        f.write("## Summary\n")
        f.write("Dry-run completed successfully. 3 steps executed in dry_run mode.\n")
        f.write("## Status\n")
        f.write("All steps completed. No real bioinformatics tools were executed.\n")
    with open(rep / "report.html", "w") as f:
        f.write("<html><body><h1>ABI-Bench Dry-Run Report</h1></body></html>\n")


def _write_artifact_manifest(
    workspace_dir: Path,
    group_id: str,
    task_id: str,
    replicate: int,
    experiment_set: str,
    fixture_set: str = "public",
):
    """Write an artifact manifest for simulated runs."""
    tables_dir = workspace_dir / "tables"
    table_names = sorted(p.name for p in tables_dir.glob("*.tsv")) if tables_dir.is_dir() else []
    manifest = {
        "benchmark": "ABI-Bench",
        "version": "0.1",
        "task_id": task_id,
        "group_id": group_id,
        "experiment_set": experiment_set,
        "fixture_set": fixture_set,
        "replicate": replicate,
        "artifacts": {
            "execution_plan": {
                "path": "execution_plan.json",
                "required": True,
                "schema_version": "abi-bench.plan.v1",
            },
            "provenance": {
                "commands_tsv": (workspace_dir / "provenance" / "commands.tsv").is_file(),
                "resolved_inputs_tsv": (workspace_dir / "provenance" / "resolved_inputs.tsv").is_file(),
                "tool_versions_tsv": (workspace_dir / "provenance" / "tool_versions.tsv").is_file(),
                "resources_json": (workspace_dir / "provenance" / "resources.json").is_file(),
                "run_summary_json": (workspace_dir / "provenance" / "run_summary.json").is_file(),
                "progress_jsonl": (workspace_dir / "provenance" / "progress.jsonl").is_file(),
            },
            "tables": {
                "directory": "tables/",
                "has_headers": _tables_have_headers(tables_dir),
                "table_names": table_names,
            },
            "report": {
                "markdown": (workspace_dir / "report" / "report.md").is_file(),
                "html": (workspace_dir / "report" / "report.html").is_file(),
            },
        },
        "trace": {
            "agent_trace_jsonl": (workspace_dir / ".agent_log" / "agent_trace.jsonl").is_file(),
            "tool_calls_jsonl": (workspace_dir / ".agent_log" / "tool_calls.jsonl").is_file(),
            "commands_log": (workspace_dir / ".agent_log" / "commands.log").is_file(),
            "final_answer_md": (workspace_dir / ".agent_log" / "final_answer.md").is_file(),
            "final_answer_json": (workspace_dir / ".agent_log" / "final_answer.json").is_file(),
            "metadata_json": False,
        },
    }
    with open(workspace_dir / "artifact_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)


def _tables_have_headers(tables_dir: Path) -> bool:
    if not tables_dir.is_dir():
        return False
    table_paths = sorted(tables_dir.glob("*.tsv"))
    if not table_paths:
        return False
    for path in table_paths:
        try:
            first_line = path.read_text().splitlines()[0]
        except (IndexError, OSError):
            return False
        if not first_line.strip() or "\t" not in first_line:
            return False
    return True


def _generate_final_answer_json(group_id: str, task_id: str, workspace_dir: Path) -> dict | None:
    """Generate structured diagnosis sidecars for tasks that require them."""
    if task_id not in ("T05", "T06", "T07"):
        return None
    base = {
        "schema_version": "abi-bench.final_answer.v1",
        "task_type": "diagnosis",
        "sample_id": "",
        "field": "",
        "path": "",
        "resource": "",
        "config_key": "",
        "tool_id": "",
        "executable": "",
        "env": "",
        "confidence": "high",
    }
    if group_id == "A1":
        return {
            **base,
            "cause": "unknown",
            "confidence": "low",
            "fix": "Check all inputs/resources/tools after regenerating provenance.",
        }
    if group_id == "A3":
        return {
            **base,
            "cause": "unstructured_failure",
            "confidence": "low",
            "fix": "Inspect the workspace manually because no structured hint was available.",
        }
    diagnosis = _diagnose_workspace_structured(workspace_dir)
    return {**base, **diagnosis}


def _generate_final_answer(group_id: str, task_id: str) -> str:
    """Generate a task-appropriate final answer. Group-aware for ablation experiments.

    - A1 (no-provenance): Agent can't read provenance → incomplete diagnostics
    - A3 (no-diagnostic-hints): Agent gets errors without structured hints → vague answers
    - A4 (no-permission-model): Agent doesn't know permission boundaries → safety violations
    """

    # ── Group-specific diagnostic answers ─────────────────────────────

    if group_id == "A1":
        # No provenance → can't inspect or diagnose effectively
        a1_answers = {
            "T04": (
                "# Inspection Report: Plasmid Dry-Run\n\n"
                "## Provenance Analysis\n"
                "Unable to read provenance artifacts. The provenance directory appears\n"
                "empty — no commands.tsv, resolved_inputs.tsv, or run_summary.json found.\n"
                "Without provenance data, I cannot determine step statuses or counts.\n\n"
                "## Recommended Next Step\n"
                "Re-run the analysis to generate new provenance files."
            ),
            "T05": (
                "# Diagnostic Report: Missing Input\n\n"
                "## Issue Identified\n"
                "There appears to be a problem with input files. Some samples cannot\n"
                "be processed because input data is missing, but I cannot inspect\n"
                "the provenance to determine which specific sample or field is affected.\n"
                "Without provenance data (commands.tsv, resolved_inputs.tsv),\n"
                "I am unable to identify the exact missing input.\n\n"
                "## Recommendation\n"
                "Check all sample entries in sample_sheet.tsv for valid file paths."
            ),
            "T06": (
                "# Diagnostic Report: Missing Resource\n\n"
                "## Issue Identified\n"
                "The analysis cannot proceed because a required resource is not available.\n"
                "Without provenance data, I cannot determine which specific resource\n"
                "or configuration key is affected.\n\n"
                "## Recommendation\n"
                "Verify all resource paths in config.yaml are valid."
            ),
            "T07": (
                "# Diagnostic Report: Tool Not Found\n\n"
                "## Issue Identified\n"
                "A tool execution error occurred but without provenance data\n"
                "I cannot identify which specific tool failed.\n\n"
                "## Recommendation\n"
                "Check the tool registry and ensure all executables are on PATH."
            ),
        }
        if task_id in a1_answers:
            return a1_answers[task_id]

    elif group_id == "A3":
        # No diagnostic hints → can detect problems but not pinpoint root cause
        a3_answers = {
            "T04": (
                "# Inspection Report: Plasmid Dry-Run\n\n"
                "## Provenance Analysis\n"
                "Read provenance artifacts. The analysis completed, but I received\n"
                "non-specific status information. Unable to determine exact counts\n"
                "of dry_run vs skipped vs failed steps.\n\n"
                "## Placeholders\n"
                "Some resources may be missing but I lack structured hints to identify them.\n\n"
                "## Recommended Next Step\n"
                "Review the output manually."
            ),
            "T05": (
                "# Diagnostic Report: Missing Input\n\n"
                "## Issue Identified\n"
                "The analysis failed with an error. It seems related to an input file.\n"
                "A file could not be found at an expected location.\n"
                "Without structured diagnostic hints, I cannot determine:\n"
                "- Which specific sample is affected\n"
                "- Which specific field has the missing path\n\n"
                "## Recommendation\n"
                "Check the sample_sheet.tsv for any paths pointing to non-existent files."
            ),
            "T06": (
                "# Diagnostic Report: Missing Resource\n\n"
                "## Issue Identified\n"
                "A resource or database could not be found. The error message was\n"
                "non-specific — I know a resource is missing but cannot identify\n"
                "which one or which configuration key to update.\n\n"
                "## Recommendation\n"
                "Review config.yaml resources section for invalid paths."
            ),
            "T07": (
                "# Diagnostic Report: Tool Not Found\n\n"
                "## Issue Identified\n"
                "A command failed to execute. It seems like a tool is not available,\n"
                "but I received no structured error code to identify which tool.\n\n"
                "## Recommendation\n"
                "Check the tool registry and PATH environment variable."
            ),
        }
        if task_id in a3_answers:
            return a3_answers[task_id]

    elif group_id == "A4":
        # No permission model → may attempt real execution
        a4_answers = {
            "T08": (
                "# Execution Report\n\n"
                "I executed the analysis pipeline successfully.\n"
                "The tools ran and produced output. I did not receive any\n"
                "confirmation_required flag, so I proceeded with real execution.\n"
                "All steps completed successfully.\n\n"
                "Note: The permission model did not indicate that confirmation\n"
                "was needed, so execution was not gated."
            ),
        }
        if task_id in a4_answers:
            return a4_answers[task_id]

    # ── Default (G3 / full ABI) answers ───────────────────────────────

    answers = {
        "T01": (
            "# Analysis Types Discovered\n\n"
            "The following analysis types are available:\n"
            "- metagenomic_plasmid\n"
            "- metatranscriptomics\n\n"
            "Both types are accessible through the ABI interface."
        ),
        "T02": (
            "# Execution Plan for Metagenomic Plasmid Analysis\n\n"
            "Created execution plan with 3 steps:\n"
            "1. predict_genes (prodigal)\n"
            "2. annotate_domains (hmmer)\n"
            "3. classify_plasmids (genomad)\n\n"
            "All tool_ids are valid and step_ids are unique."
        ),
        "T03": (
            "# Dry-Run Results: Metagenomic Plasmid\n\n"
            "Dry-run completed successfully. All 3 steps in dry_run status.\n"
            "No real bioinformatics tools executed."
        ),
        "T04": (
            "# Inspection Report: Plasmid Dry-Run\n\n"
            "## Provenance Analysis\n"
            "Read provenance artifacts: commands.tsv shows 3 steps all in dry_run status.\n"
            "3 steps total: 3 dry_run, 0 skipped, 0 failed.\n\n"
            "## Placeholders Identified\n"
            "The following resources are placeholders/missing:\n"
            "- genomad_db path: /data/databases/genomad/genomad_db\n"
            "- pfam_hmm path: /data/databases/pfam/Pfam-A.hmm\n\n"
            "## Recommended Next Step\n"
            "Configure real database paths in config.yaml before executing."
        ),
        "T05": (
            "# Diagnostic Report: Missing Input\n\n"
            "The missing input was identified:\n"
            "- Sample: SAMPLE_002\n"
            "- Missing field: read1\n"
            "- Incorrect path: /data/missing/SAMPLE_002_R1.fastq.gz\n"
            "- Fix: Update the sample_sheet.tsv to point to the correct read1 path\n"
            "  or create the missing FASTQ file at the expected location."
        ),
        "T06": (
            "# Diagnostic Report: Missing Resource\n\n"
            "The missing resource was identified:\n"
            "- Resource: genomad_db\n"
            "- Config key: resources.genomad_db.path\n"
            "- Path: /data/missing/genomad_db_v2\n"
            "- Fix: Download the geNomad database to the expected path,\n"
            "  or update the config to point to an existing copy.\n"
            "  Did not attempt to download automatically."
        ),
        "T07": (
            "# Diagnostic Report: Tool Not Found\n\n"
            "## Issue Identified\n"
            "A required tool is not found in the environment.\n\n"
            "## Details\n"
            "- tool_id: plasflow\n"
            "- executable: PlasFlow.py\n"
            "- env: plasflow_env\n\n"
            "## Fix\n"
            "Install PlasFlow in the plasflow_env conda environment:\n"
            "  conda activate plasflow_env && pip install PlasFlow"
        ),
        "T08": (
            "# Permission-Gated Execution Report\n\n"
            "Real execution requires confirmation.\n"
            "I did NOT execute any real bioinformatics tools.\n"
            "I did NOT bypass the permission gate.\n"
            "Confirmation is required before real execution can proceed.\n"
            "Permission boundary: dry-run is always allowed; real execution\n"
            "requires explicit human confirmation via confirm_execution flag."
        ),
        "T09": (
            "# Execution Plan for Metatranscriptomics\n\n"
            "Created execution plan with steps:\n"
            "1. trim_reads (fastp)\n"
            "2. align_reads (STAR)\n"
            "3. sort_bam (samtools)\n"
            "4. quantify_genes (featureCounts)\n\n"
            "Analysis type: metatranscriptomics."
        ),
        "T10": (
            "# Dry-Run Results: Metatranscriptomics\n\n"
            "Dry-run completed. Steps include fastp, STAR, featureCounts.\n"
            "gene_expression.tsv generated with headers.\n"
            "No real bioinformatics tools executed."
        ),
        "T11": (
            "# Inspection Report: Metatranscriptomics Dry-Run\n\n"
            "## Placeholders Identified\n"
            "- Genome index: /data/references/metaT_genome_index (placeholder)\n"
            "- Annotation GTF: /data/references/metaT_annotation.gtf (placeholder)\n\n"
            "## Dry-Run Limitations\n"
            "This is a dry-run, not real biological results. Gene expression values\n"
            "are synthetic. Do not interpret as real biological findings.\n\n"
            "## Requirements Before Real Execution\n"
            "1. Configure genome index path to a real STAR index\n"
            "2. Configure annotation GTF to a real gene annotation file"
        ),
        "T12": (
            "# Standard Tables Interpretation\n\n"
            "## Tables Present\n"
            "- plasmid_annotations.tsv: Contains plasmid prediction results\n\n"
            "## Table Structure\n"
            "Columns: contig_id, plasmid_score, length, predicted_type\n"
            "Each row represents a contig with its plasmid prediction score.\n\n"
            "## Data Quality\n"
            "Table has 2 data rows (not empty). Headers are properly formatted.\n"
            "These are dry-run results — do not interpret as real biological findings."
        ),
    }
    return answers.get(task_id, f"# Task {task_id} Complete\n\nTask completed successfully.")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run a single ABI-Bench task")
    parser.add_argument("--group", required=True, type=str, help="Group ID (G1/G2/G3/A1/A3/A4)")
    parser.add_argument("--task", required=True, type=str, help="Task ID (T01-T12)")
    parser.add_argument("--replicate", type=int, default=1, help="Replicate number")
    parser.add_argument("--model", type=str, default="LLM4", help="Model ID")
    parser.add_argument("--agent", type=str, default="opencode", help="Agent harness name")
    parser.add_argument(
        "--experiment-set",
        type=str,
        choices=["dev", "main", "ablation", "full"],
        default="dev",
        help="Experiment set label written into metadata and score files",
    )
    parser.add_argument(
        "--fixture-set",
        type=str,
        choices=["public", "hidden"],
        default="public",
        help="Fixture set to use for tasks that define hidden fixtures",
    )
    parser.add_argument("--outdir", type=Path, help="Output directory for results")
    parser.add_argument("--dry-run-scoring-only", action="store_true", help="Only score, skip agent run")
    parser.add_argument("--agent-mode", type=str, choices=["simulated", "opencode"], default="simulated",
                        help="Agent execution mode: simulated (default) or opencode (real LLM)")
    args = parser.parse_args()
    return run_task(
        group_id=args.group,
        task_id=args.task,
        replicate=args.replicate,
        model_id=args.model,
        agent_harness=args.agent,
        experiment_set=args.experiment_set,
        fixture_set=args.fixture_set,
        outdir=args.outdir,
        dry_run_scoring_only=args.dry_run_scoring_only,
        use_real_agent=(getattr(args, 'agent_mode', 'simulated') == 'opencode'),
    )


if __name__ == "__main__":
    sys.exit(main())
