#!/usr/bin/env python3
"""
ABI-Bench v0.6 — G4 Information-Matched Documentation Generator

Generates the 9 static markdown guide files for the G4 (Information-Matched
Documentation Baseline) group.  Each guide provides the same information that
G3 agents receive through the ABI lifecycle CLI, but delivered as static
documentation without any executable API.

The guides are derived from the ABI CLI's actual behavior and the benchmark's
output format documentation in export_agent_context.py, ensuring information
parity between G3 (CLI) and G4 (docs only).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# ── Guide content generators ──────────────────────────────────────────────────

def _abi_cli_path() -> str:
    return str(PROJECT_ROOT / "bench" / "harness" / "abi_cli.py")


def _run_abi(subcommand: str, workspace: str | None = None) -> dict | str:
    """Run an ABI CLI subcommand and return parsed output."""
    cmd = [sys.executable, _abi_cli_path(), subcommand]
    if workspace:
        cmd.append(f"--workspace={workspace}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        # Try JSON first, fall back to raw text
        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return result.stdout
    except Exception:
        return {}


def generate_analysis_types_guide() -> str:
    """Generate analysis_types.md — equivalent to `abi list-types`."""
    output = _run_abi("list-types")
    types_list = output.get("analysis_types", []) if isinstance(output, dict) else []
    type_descriptions = {
        "metagenomic_plasmid": "Plasmid detection and annotation in metagenomic assemblies. "
                               "Typical tools: Prodigal (gene prediction), HMMER (protein domain search), "
                               "geNomad (plasmid classification).",
        "metatranscriptomics": "Gene expression quantification from metatranscriptomic reads. "
                               "Typical tools: fastp (read QC), STAR (alignment), samtools (BAM processing), "
                               "featureCounts (quantification).",
        "rnaseq_expression": "RNA-seq differential expression analysis. "
                             "Typical tools: fastp (read QC), STAR (alignment), featureCounts (quantification).",
        "amplicon_16s": "16S rRNA amplicon sequencing analysis for microbial community profiling.",
        "wgs_bacteria": "Whole-genome sequencing analysis for bacterial isolate characterization.",
    }

    lines = [
        "# Analysis Types",
        "",
        "This document describes the bioinformatics analysis types available in the",
        "ABI-Bench environment. Use this reference when selecting an analysis type",
        "for a workflow.",
        "",
    ]
    for t in types_list:
        desc = type_descriptions.get(t, "Bioinformatics analysis workflow.")
        lines.append(f"## {t}")
        lines.append(f"{desc}")
        lines.append("")

    if not types_list:
        lines.append("## metagenomic_plasmid")
        lines.append(type_descriptions["metagenomic_plasmid"])
        lines.append("")
        lines.append("## metatranscriptomics")
        lines.append(type_descriptions["metatranscriptomics"])
        lines.append("")

    lines.extend([
        "## Lifecycle Phases",
        "",
        "Each analysis follows these phases:",
        "",
        "1. **Planning** — Define the execution plan: steps, tools, inputs, outputs",
        "2. **Dry-run** — Validate the plan without executing real bioinformatics tools",
        "3. **Inspection** — Examine provenance artifacts to verify correctness",
        "4. **Diagnosis** — Identify and fix failures when a run does not complete",
        "5. **Reporting** — Generate structured reports summarizing the analysis",
        "",
        "## Important",
        "",
        "- Real bioinformatics tool execution is disabled by default.",
        "- Use `which <tool>` and `<tool> --version` to check tool availability.",
        "- All workflows operate on workspace-local data — no network access.",
    ])
    return "\n".join(lines)


def generate_execution_plan_guide() -> str:
    """Generate execution_plan_guide.md — equivalent to `abi plan` schema."""
    return """# Execution Plan Guide

## Overview

An execution plan describes a bioinformatics workflow as a JSON document with
a standardized schema. The plan defines what steps to run, in what order, using
which tools, with what inputs and outputs.

## Schema

The execution plan file is named `execution_plan.json` and uses schema version
`abi-bench.plan.v1`.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Must be `"abi-bench.plan.v1"` |
| `analysis_type` | string | e.g. `"metagenomic_plasmid"`, `"metatranscriptomics"` |
| `steps` | array | Ordered list of step objects |

### Step Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `step_id` | string | Unique identifier (e.g. `"step_01_qc"`) |
| `tool_id` | string | Tool identifier from the tool registry in `config.yaml` |
| `executable` | string | Name of the executable or script |
| `command_template` | string | Shell command with `{placeholders}` for inputs/outputs |
| `status` | string | One of: `planned`, `dry_run`, `skipped`, `failed` |
| `inputs` | array | List of input file paths |
| `outputs` | array | List of output file paths |

### Example

```json
{
  "schema_version": "abi-bench.plan.v1",
  "analysis_type": "metagenomic_plasmid",
  "steps": [
    {
      "step_id": "step_01_gene_prediction",
      "tool_id": "prodigal",
      "executable": "prodigal",
      "command_template": "prodigal -i {assembly} -a {proteins} -p meta",
      "status": "planned",
      "inputs": ["data/assembly.fasta"],
      "outputs": ["results/proteins.faa"]
    }
  ]
}
```

## Building a Plan

1. Read `config.yaml` to identify the analysis type, tools, resources, and
   sample sheet path.
2. Read `sample_sheet.tsv` to identify samples and input files.
3. Define steps in the correct order based on the analysis type's standard
   workflow.
4. Assign unique `step_id` values to each step.
5. Reference tool IDs from the tool registry in `config.yaml`.
"""


def generate_dry_run_guide() -> str:
    """Generate dry_run_guide.md — equivalent to `abi dry-run` behavior."""
    return """# Dry-Run Guide

## Overview

A dry-run validates a workflow plan without executing real bioinformatics tools.
It produces provenance artifacts that record what *would* have been executed,
enabling verification and debugging without consuming compute resources or
modifying data.

## Dry-Run Artifacts

After a dry-run, the following directories and files are produced:

### `execution_plan.json`
The validated execution plan with step statuses updated to `dry_run`.

### `provenance/` Directory

| File | Format | Description |
|------|--------|-------------|
| `commands.tsv` | TSV | Columns: step_id, tool_id, executable, command, status |
| `resolved_inputs.tsv` | TSV | Columns: step_id, input_path, resolved_path, exists |
| `tool_versions.tsv` | TSV | Columns: tool_id, executable, version, source |
| `resources.json` | JSON | Resource name → resolved path mapping |
| `run_summary.json` | JSON | execution_mode, total_steps, status_counts |
| `progress.jsonl` | JSONL | One object per step: {step_id, status, timestamp} |

### `tables/` Directory

Plugin-specific standard-format TSV output tables:
- `metagenomic_plasmid`: `plasmid_annotations.tsv`
- `metatranscriptomics`: `gene_expression.tsv`

### `report/` Directory

- `report.md` — Markdown analysis report
- `report.html` — HTML version of the report

### `artifact_manifest.json`

Machine-readable inventory of all produced artifacts with paths, types, sizes,
and existence flags.

## Running a Dry-Run

1. Ensure `execution_plan.json` exists (create one first if needed).
2. Validate that all referenced tools exist: `which <tool>`
3. Check that input files referenced in the plan are present.
4. Write provenance files documenting what would execute.
5. Generate standard table headers and a report.
6. Do NOT execute real bioinformatics tools on data.
"""


def generate_inspection_guide() -> str:
    """Generate inspection_guide.md — equivalent to `abi inspect` output."""
    return """# Inspection Guide

## Overview

Inspection examines the provenance artifacts produced by a dry-run (or a
failed run) to understand what happened, what succeeded, what failed, and
what the next safe steps are.

## Key Files to Inspect

### `provenance/run_summary.json`

Shows the big picture:
```json
{
  "execution_mode": "dry_run",
  "total_steps": 3,
  "status_counts": {"completed": 2, "failed": 1}
}
```

### `provenance/commands.tsv`

Lists every command that was (or would be) executed, with its status.
Look for rows with `status: failed` to identify problematic steps.

### `provenance/resolved_inputs.tsv`

Shows whether each input file could be found (`exists: true/false`).
Missing inputs (`exists: false`) are a common cause of pipeline failure.

### `provenance/resources.json`

Maps resource names (e.g., `genomad_db`) to their resolved file paths.
A missing resource will show a path under `missing/` or a path that does
not exist on disk.

## Inspection Process

1. Start with `run_summary.json` to get the overall status.
2. If failures exist, check `commands.tsv` for the specific failed step.
3. Check `resolved_inputs.tsv` to see if inputs for that step exist.
4. Check `resources.json` to verify all required databases are present.
5. Use the tool registry in `config.yaml` to verify tool availability.
"""


def generate_reporting_guide() -> str:
    """Generate reporting_guide.md — equivalent to `abi report` format."""
    return """# Reporting Guide

## Overview

A report summarizes the analysis results in human-readable form. Reports
should be written in Markdown and an HTML version should also be provided.

## Report Structure

### Required Sections

1. **Title and Summary** — What analysis was performed and high-level results.
2. **Methods** — Description of the workflow, tools used, and parameters.
3. **Results** — Key findings, referencing standard tables where applicable.
4. **Limitations** — Known limitations of the analysis.
5. **Dry-Run Disclosure** — Clearly state this was a dry-run (no real execution).

### Report Files

- `report/report.md` — Markdown report (minimum 200 words)
- `report/report.html` — HTML version

### Quality Guidelines

- Reference standard table files (e.g., `tables/plasmid_annotations.tsv`)
  when discussing results.
- Do not overclaim biological findings from dry-run results.
- Include at least 3 relevant citations or tool references.
- Acknowledge that dry-run results are simulated.
"""


def generate_provenance_guide() -> str:
    """Generate provenance_guide.md — explains provenance artifact structure."""
    return """# Provenance Guide

## Overview

Provenance artifacts record the execution trace of a workflow — what was run,
with what inputs, producing what outputs, and with what status. They enable
debugging, reproducibility, and audit.

## Provenance Directory Structure

```
provenance/
  commands.tsv         — All executed/planned commands
  resolved_inputs.tsv  — Input path resolution results
  tool_versions.tsv    — Tool version information
  resources.json       — Resource path mapping
  run_summary.json     — Execution summary
  progress.jsonl       — Per-step progress log
```

## File Schemas

### commands.tsv
| Column | Description |
|--------|-------------|
| step_id | Step identifier from execution_plan.json |
| tool_id | Tool identifier from config.yaml |
| executable | Executable name or path |
| command | Full command string |
| status | `completed`, `failed`, `skipped`, `dry_run` |

### resolved_inputs.tsv
| Column | Description |
|--------|-------------|
| step_id | Step identifier |
| input_path | Path as declared in the plan |
| resolved_path | Actual resolved filesystem path |
| exists | `true` or `false` |

### resources.json
Maps resource names to their resolved filesystem paths:
```json
{
  "genomad_db": "/path/to/genomad_db",
  "pfam_db": "/path/to/Pfam-A.hmm"
}
```

### run_summary.json
```json
{
  "execution_mode": "dry_run",
  "total_steps": 5,
  "status_counts": {"completed": 4, "failed": 1, "skipped": 0}
}
```

## Using Provenance for Diagnosis

1. Check `run_summary.json` for overall status.
2. For failures, find the failed step_id in `commands.tsv`.
3. Check `resolved_inputs.tsv` for that step — are inputs present?
4. Check `resources.json` — are required databases available?
5. Check `config.yaml` tool registry — is the tool installed?
"""


def generate_standard_tables_guide() -> str:
    """Generate standard_tables_guide.md — table formats per plugin."""
    return """# Standard Tables Guide

## Overview

Each analysis plugin produces standard-format TSV output tables. These tables
follow consistent schemas that enable downstream interpretation.

## Plugin Table Schemas

### metagenomic_plasmid
- **File**: `tables/plasmid_annotations.tsv`
- **Columns**: contig_id, contig_length, plasmid_score, fdr, annotation

### metatranscriptomics
- **File**: `tables/gene_expression.tsv`
- **Columns**: gene_id, gene_name, log2fc, pvalue, padj, expression_level

### rnaseq_expression
- **File**: `tables/expression.tsv`
- **Columns**: gene_id, base_mean, log2fc, pvalue, padj

### amplicon_16s
- **File**: `tables/otu_table.tsv`
- **Columns**: otu_id, taxonomy, abundance

### wgs_bacteria
- **File**: `tables/variants.tsv`
- **Columns**: position, ref, alt, quality, gene, effect

## Reading Standard Tables

- All tables are TSV (tab-separated values) with a header row.
- Use standard command-line tools to inspect: `head`, `cut`, `awk`.
- Tables produced by dry-run contain headers only (no data rows).
"""


def generate_diagnostic_guide() -> str:
    """Generate diagnostic_guide.md — common failure modes and fixes."""
    return """# Diagnostic Guide

## Overview

This guide describes common failure modes in bioinformatics workflows and
how to diagnose them from workspace files and provenance artifacts.

## Common Failure Modes

### 1. Missing Input File

**Symptoms**: A step fails because an input file cannot be found.
**Detection**: Check `provenance/resolved_inputs.tsv` — look for `exists: false`.
Also check `sample_sheet.tsv` for paths that reference nonexistent files.
**Fix**: Verify that all files referenced in `sample_sheet.tsv` exist in the
`data/` directory. Correct any incorrect paths.

### 2. Missing Resource / Database

**Symptoms**: A tool cannot run because a required reference database is missing.
**Detection**: Check `provenance/resources.json` — look for paths under
`missing/` directories. Check `config.yaml` resources section.
**Fix**: Ensure the resource path in `config.yaml` points to an existing
directory or file. Update the path if the resource has been relocated.

### 3. Tool Not Found / Not Installed

**Symptoms**: A step references a tool that is not available in the environment.
**Detection**: Run `which <tool>` — if it returns empty, the tool is not on PATH.
Check `config.yaml` tools section for environment requirements (conda/pip).
**Fix**: Install the tool, activate the correct conda environment, or update
the tool registry in `config.yaml`.

### 4. Contract Violation

**Symptoms**: A checksum or integrity check fails, indicating file corruption
or tampering.
**Detection**: Compare computed file hashes against expected hashes in
`config.yaml` contract section.
**Fix**: Re-obtain the original file from a trusted source and verify its hash.

## Diagnosis Process

1. Read `config.yaml` to understand the expected pipeline configuration.
2. Read `sample_sheet.tsv` to identify samples and their inputs.
3. Check `provenance/run_summary.json` for overall status.
4. For any failed step, trace backward through provenance files to find the
   root cause.
5. Categorize the failure: missing_input, missing_resource, or tool_not_found.
6. Report the specific affected sample, field, path, resource, or tool.
7. Suggest a concrete fix.
"""


# ── Main generator ────────────────────────────────────────────────────────────

def generate_g4_docs(workspace: Path) -> list[Path]:
    """Generate all G4 documentation files in the workspace docs/ directory.

    Returns a list of paths to the generated files.
    """
    docs_dir = workspace / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    guides = {
        "analysis_types.md": generate_analysis_types_guide,
        "execution_plan_guide.md": generate_execution_plan_guide,
        "dry_run_guide.md": generate_dry_run_guide,
        "inspection_guide.md": generate_inspection_guide,
        "reporting_guide.md": generate_reporting_guide,
        "provenance_guide.md": generate_provenance_guide,
        "standard_tables_guide.md": generate_standard_tables_guide,
        "diagnostic_guide.md": generate_diagnostic_guide,
    }

    written = []
    for filename, generator in guides.items():
        filepath = docs_dir / filename
        filepath.write_text(generator())
        written.append(filepath)

    return written


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate G4 documentation")
    parser.add_argument("--workspace", type=Path, required=True,
                        help="Workspace directory to write docs into")
    args = parser.parse_args()
    paths = generate_g4_docs(args.workspace)
    print(f"Generated {len(paths)} G4 documentation files in {args.workspace / 'docs'}")
