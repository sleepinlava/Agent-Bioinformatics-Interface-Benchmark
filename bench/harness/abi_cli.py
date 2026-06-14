#!/usr/bin/env python3
"""
ABI-Bench local ABI lifecycle CLI.

This is the minimal callable control layer for G3-style agents. It produces
plans, dry-run artifacts, inspection summaries, and diagnoses without running
real bioinformatics tools.
"""

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Allow direct execution from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from bench.harness.diagnosis import diagnose_workspace_structured, format_diagnosis_markdown


ANALYSIS_TYPES = ["metagenomic_plasmid", "metatranscriptomics"]


def load_config(workspace: Path) -> dict:
    config_path = workspace / "config.yaml"
    if not config_path.is_file():
        raise SystemExit(f"config.yaml not found in workspace: {workspace}")
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        raise SystemExit(f"Failed to parse config.yaml: {e}") from e
    if not isinstance(data, dict):
        raise SystemExit(f"config.yaml must contain a mapping, got {type(data).__name__}")
    return data


def infer_analysis_type(workspace: Path, requested: str | None = None) -> str:
    if requested:
        return requested
    config = load_config(workspace)
    return config.get("analysis", {}).get("type", "metagenomic_plasmid")


def command_list_types(args) -> int:
    payload = {
        "analysis_types": ANALYSIS_TYPES,
        "lifecycle": ["list-types", "plan", "dry-run", "inspect", "diagnose", "report", "run"],
        "real_execution_default": False,
    }
    print(json.dumps(payload, indent=2))
    return 0


def command_plan(args) -> int:
    workspace = args.workspace.resolve()
    analysis_type = infer_analysis_type(workspace, args.analysis_type)
    plan = build_plan(workspace, analysis_type)
    outpath = workspace / "execution_plan.json"
    outpath.write_text(json.dumps(plan, indent=2) + "\n")
    print(f"Wrote {outpath}")
    return 0


def build_plan(workspace: Path, analysis_type: str) -> dict:
    config = load_config(workspace)
    tools = config.get("tools", {})
    workflow_steps = config.get("workflow", {}).get("steps", [])
    steps = []

    if not workflow_steps:
        workflow_steps = default_workflow(analysis_type)

    for idx, step in enumerate(workflow_steps, start=1):
        tool_key = str(step.get("tool", "unknown"))
        tool_meta = tools.get(tool_key, {})
        executable = str(tool_meta.get("executable", tool_key))
        tool_id = normalized_tool_id(tool_key, executable)
        step_id = str(step.get("id", f"step_{idx:02d}"))
        steps.append({
            "step_id": step_id,
            "tool_id": tool_id,
            "executable": executable,
            "status": "planned",
            "input": step.get("input"),
            "output": step.get("output"),
            "command": dryrun_command(analysis_type, tool_key, executable, step),
        })

    return {
        "schema_version": "abi-bench.plan.v1",
        "analysis_type": analysis_type,
        "generated_by": "abi_cli",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
    }


def default_workflow(analysis_type: str) -> list[dict]:
    if analysis_type == "metatranscriptomics":
        return [
            {"id": "trim_reads", "tool": "fastp", "input": "read1,read2", "output": "trimmed_reads"},
            {"id": "align_reads", "tool": "star", "input": "trimmed_reads", "output": "aligned.bam"},
            {"id": "sort_bam", "tool": "samtools", "input": "aligned.bam", "output": "sorted.bam"},
            {"id": "quantify_genes", "tool": "featureCounts", "input": "sorted.bam", "output": "gene_expression.tsv"},
        ]
    return [
        {"id": "predict_genes", "tool": "prodigal", "input": "assembly", "output": "genes.faa"},
        {"id": "annotate_domains", "tool": "hmmer", "input": "genes.faa", "output": "domain_annotations.tsv"},
        {"id": "classify_plasmids", "tool": "genomad", "input": "assembly", "output": "plasmid_classification.tsv"},
    ]


def normalized_tool_id(tool_key: str, executable: str) -> str:
    executable_map = {
        "star": "STAR",
        "hisat2": "HISAT2",
    }
    return executable_map.get(tool_key.lower(), tool_key if tool_key != "featurecounts" else "featureCounts")


def dryrun_command(analysis_type: str, tool_key: str, executable: str, step: dict) -> str:
    if analysis_type == "metatranscriptomics":
        templates = {
            "fastp": "fastp -i {read1} -I {read2} -o trimmed_R1.fastq.gz -O trimmed_R2.fastq.gz",
            "star": "STAR --genomeDir {genome_index} --readFilesIn trimmed_R1.fastq.gz trimmed_R2.fastq.gz",
            "hisat2": "hisat2 -x {genome_index} -1 trimmed_R1.fastq.gz -2 trimmed_R2.fastq.gz",
            "samtools": "samtools sort aligned.bam -o sorted.bam",
            "featureCounts": "featureCounts -a {annotation_gtf} -o gene_expression.tsv sorted.bam",
        }
    else:
        templates = {
            "prodigal": "prodigal -i {assembly} -a genes.faa",
            "hmmer": "hmmscan --domtblout domain_annotations.tsv {pfam_hmm} genes.faa",
            "genomad": "genomad run {assembly} genomad_output {genomad_db}",
            "blast": "blastn -query plasmid_sequences.fasta -db {plasmid_db} -out blast_results.tsv",
            "plasflow": "PlasFlow.py --input {assembly} --output plasmid_predictions.tsv",
        }
    return templates.get(tool_key, f"{executable} # dry-run placeholder for {step.get('id', tool_key)}")


def command_dry_run(args) -> int:
    workspace = args.workspace.resolve()
    analysis_type = infer_analysis_type(workspace, args.analysis_type)
    plan = build_plan(workspace, analysis_type)
    (workspace / "execution_plan.json").write_text(json.dumps(plan, indent=2) + "\n")

    if args.group != "A1":
        write_provenance(workspace, analysis_type, plan)
    else:
        (workspace / "provenance").mkdir(exist_ok=True)

    write_tables(workspace, analysis_type)
    write_report(workspace, analysis_type, plan)
    write_artifact_manifest(
        workspace,
        task_id=args.task_id,
        group_id=args.group,
        replicate=args.replicate,
        experiment_set=args.experiment_set,
        fixture_set=getattr(args, 'fixture_set', 'public'),
    )
    print(json.dumps({
        "status": "dry_run_complete",
        "analysis_type": analysis_type,
        "workspace": str(workspace),
        "real_execution": False,
    }, indent=2))
    return 0


def write_provenance(workspace: Path, analysis_type: str, plan: dict):
    provenance = workspace / "provenance"
    provenance.mkdir(exist_ok=True)

    with open(provenance / "commands.tsv", "w") as f:
        writer = csv.DictWriter(f, fieldnames=["step_id", "command", "status", "exit_code"], delimiter="\t")
        writer.writeheader()
        for step in plan["steps"]:
            writer.writerow({
                "step_id": step["step_id"],
                "command": step["command"],
                "status": "dry_run",
                "exit_code": "",
            })

    write_resolved_inputs(workspace, provenance)
    write_tool_versions(workspace, provenance)
    write_resources(workspace, provenance)

    (provenance / "run_summary.json").write_text(json.dumps({
        "execution_mode": "dry_run",
        "analysis_type": analysis_type,
        "total_steps": len(plan["steps"]),
        "completed_steps": len(plan["steps"]),
        "failed_steps": 0,
        "real_execution": False,
    }, indent=2) + "\n")

    with open(provenance / "progress.jsonl", "w") as f:
        for step in plan["steps"]:
            f.write(json.dumps({
                "step_id": step["step_id"],
                "status": "dry_run",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }) + "\n")


def write_resolved_inputs(workspace: Path, provenance: Path):
    sample_sheet = workspace / "sample_sheet.tsv"
    target = provenance / "resolved_inputs.tsv"
    if sample_sheet.is_file():
        target.write_text(sample_sheet.read_text())
    else:
        target.write_text("sample_id\n")


def write_tool_versions(workspace: Path, provenance: Path):
    config = load_config(workspace)
    with open(provenance / "tool_versions.tsv", "w") as f:
        writer = csv.DictWriter(f, fieldnames=["tool_id", "executable", "version", "env"], delimiter="\t")
        writer.writeheader()
        for tool_id, meta in sorted(config.get("tools", {}).items()):
            writer.writerow({
                "tool_id": tool_id,
                "executable": meta.get("executable", tool_id) if isinstance(meta, dict) else tool_id,
                "version": meta.get("version", "unknown") if isinstance(meta, dict) else "unknown",
                "env": meta.get("env", "") if isinstance(meta, dict) else "",
            })


def write_resources(workspace: Path, provenance: Path):
    config = load_config(workspace)
    (provenance / "resources.json").write_text(json.dumps(config.get("resources", {}), indent=2) + "\n")


def write_tables(workspace: Path, analysis_type: str):
    tables = workspace / "tables"
    tables.mkdir(exist_ok=True)
    if analysis_type == "metatranscriptomics":
        (tables / "gene_expression.tsv").write_text(
            "gene_id\tgene_name\tcount_control\tcount_treatment\tlog2fc\tpvalue\n"
        )
        (tables / "quality_metrics.tsv").write_text("sample_id\treads_total\treads_retained\n")
    else:
        (tables / "plasmid_annotations.tsv").write_text(
            "contig_id\tplasmid_score\tlength\tpredicted_type\n"
        )
        (tables / "plasmid_sequences.fasta").write_text(">dry_run_placeholder\nNNNN\n")


def write_report(workspace: Path, analysis_type: str, plan: dict):
    report = workspace / "report"
    report.mkdir(exist_ok=True)
    markdown = [
        "# ABI Dry-Run Report",
        "",
        f"Analysis type: `{analysis_type}`",
        f"Steps: {len(plan['steps'])}",
        "",
        "No real bioinformatics tools were executed.",
    ]
    (report / "report.md").write_text("\n".join(markdown) + "\n")
    (report / "report.html").write_text(
        f"<html><body><h1>ABI Dry-Run Report</h1><p>{analysis_type}</p></body></html>\n"
    )


def write_artifact_manifest(
    workspace: Path,
    task_id: str = "T00",
    group_id: str = "G3",
    replicate: int = 1,
    experiment_set: str = "dev",
    fixture_set: str = "public",
) -> dict:
    """Write a deterministic manifest describing generated run artifacts."""
    tables_dir = workspace / "tables"
    table_names = sorted(p.name for p in tables_dir.glob("*.tsv")) if tables_dir.is_dir() else []
    manifest = {
        "benchmark": "ABI-Bench",
        "version": "0.1",
        "task_id": task_id or "T00",
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
                "commands_tsv": (workspace / "provenance" / "commands.tsv").is_file(),
                "resolved_inputs_tsv": (workspace / "provenance" / "resolved_inputs.tsv").is_file(),
                "tool_versions_tsv": (workspace / "provenance" / "tool_versions.tsv").is_file(),
                "resources_json": (workspace / "provenance" / "resources.json").is_file(),
                "run_summary_json": (workspace / "provenance" / "run_summary.json").is_file(),
                "progress_jsonl": (workspace / "provenance" / "progress.jsonl").is_file(),
            },
            "tables": {
                "directory": "tables/",
                "has_headers": _tables_have_headers(tables_dir),
                "table_names": table_names,
            },
            "report": {
                "markdown": (workspace / "report" / "report.md").is_file(),
                "html": (workspace / "report" / "report.html").is_file(),
            },
        },
        "trace": {
            "agent_trace_jsonl": (workspace / ".agent_log" / "agent_trace.jsonl").is_file(),
            "tool_calls_jsonl": (workspace / ".agent_log" / "tool_calls.jsonl").is_file(),
            "commands_log": (workspace / ".agent_log" / "commands.log").is_file(),
            "final_answer_md": (workspace / ".agent_log" / "final_answer.md").is_file(),
            "final_answer_json": (workspace / ".agent_log" / "final_answer.json").is_file()
            or (workspace / "final_answer.json").is_file(),
            "metadata_json": False,
        },
    }
    (workspace / "artifact_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


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


def command_inspect(args) -> int:
    workspace = args.workspace.resolve()
    summary_path = workspace / "provenance" / "run_summary.json"
    commands_path = workspace / "provenance" / "commands.tsv"
    lines = ["# ABI Inspection", ""]
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text())
        lines.append(f"Execution mode: {summary.get('execution_mode', 'unknown')}")
        lines.append(f"Total steps: {summary.get('total_steps', 'unknown')}")
    if commands_path.is_file():
        rows = list(csv.DictReader(open(commands_path), delimiter="\t"))
        status_counts = {}
        for row in rows:
            status_counts[row.get("status", "")] = status_counts.get(row.get("status", ""), 0) + 1
        lines.append(f"Status counts: {status_counts}")
    else:
        lines.append("Provenance commands.tsv is missing.")
    lines.append("Next safe step: verify resources and keep using dry-run until confirmation is granted.")
    print("\n".join(lines))
    return 0


def command_diagnose(args) -> int:
    workspace = args.workspace.resolve()
    group = args.group
    if group == "A1":
        structured = {
            "schema_version": "abi-bench.final_answer.v1",
            "task_type": "diagnosis",
            "cause": "unknown",
            "fix": "Regenerate provenance and inspect the workspace again.",
        }
        diagnosis = "# ABI Diagnosis\n\nInput/resource/tool failure suspected, but provenance is unavailable."
    elif group == "A3":
        structured = {
            "schema_version": "abi-bench.final_answer.v1",
            "task_type": "diagnosis",
            "cause": "unstructured_failure",
            "fix": "Inspect config.yaml and sample_sheet.tsv manually.",
        }
        diagnosis = "# ABI Diagnosis\n\nA failure was detected, but structured diagnostic hints are unavailable."
    else:
        structured = diagnose_workspace_structured(workspace)
        diagnosis = format_diagnosis_markdown(structured)
    (workspace / "final_answer.json").write_text(json.dumps(structured, indent=2) + "\n")
    print(diagnosis)
    return 0


def diagnose_workspace(workspace: Path) -> str:
    """Thin wrapper retained for backward compatibility."""
    return format_diagnosis_markdown(diagnose_workspace_structured(workspace))


def command_report(args) -> int:
    workspace = args.workspace.resolve()
    analysis_type = infer_analysis_type(workspace, args.analysis_type)
    plan_path = workspace / "execution_plan.json"
    plan = json.loads(plan_path.read_text()) if plan_path.is_file() else build_plan(workspace, analysis_type)
    write_report(workspace, analysis_type, plan)
    print(f"Wrote report for {analysis_type}")
    return 0


def command_run(args) -> int:
    payload = {
        "status": "confirmation_required",
        "confirmation_required": True,
        "confirm_execution": False,
        "real_execution": False,
        "message": "Real execution is disabled unless explicit external confirmation is granted.",
    }
    print(json.dumps(payload, indent=2))
    return 2


def add_common(parser: argparse.ArgumentParser):
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace directory")
    parser.add_argument("--group", default="G3", help="Benchmark group id")
    parser.add_argument("--analysis-type", choices=ANALYSIS_TYPES, help="Analysis type override")
    parser.add_argument("--task-id", default="T00", help="Benchmark task id for generated metadata")
    parser.add_argument("--replicate", type=int, default=1, help="Benchmark replicate for generated metadata")
    parser.add_argument(
        "--experiment-set",
        choices=["dev", "main", "ablation", "full"],
        default="dev",
        help="Experiment set label for generated metadata",
    )
    parser.add_argument(
        "--fixture-set",
        choices=["public", "hidden"],
        default="public",
        help="Fixture set label for generated metadata",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ABI-Bench local ABI lifecycle CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list-types")
    p.set_defaults(func=command_list_types)

    for name, func in [
        ("plan", command_plan),
        ("dry-run", command_dry_run),
        ("inspect", command_inspect),
        ("diagnose", command_diagnose),
        ("report", command_report),
        ("run", command_run),
    ]:
        sp = sub.add_parser(name)
        add_common(sp)
        sp.set_defaults(func=func)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
