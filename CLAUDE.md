# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ABI-Bench v0.3** (Agent-Bioinformatics Interface Benchmark) evaluates whether a structured ABI control layer improves LLM agent operation of bioinformatics workflows — focusing on the **scaffolding effect** (weaker models benefit more from ABI) and **cross-plugin portability** (same ABI lifecycle works across metagenomic_plasmid, metatranscriptomics, and amplicon_16s).

### Core Narrative

> ABI is a **domain-specific scaffold** that lowers the model capability threshold required for reliable bioinformatics workflow operation. The improvement is strongest for weaker models, and the same ABI lifecycle transfers across multiple workflow plugins.

### Three-Tier Claim Structure

| Tier | Claim | Evidence |
|------|-------|----------|
| **Main** | ABI control layer improves agent operability over unstructured baselines | G3 > G1/G2 across models, tasks, CI positive |
| **Scaffolding** | ABI helps weak models more than strong models | Scaffolding Gain > 0, Group × Tier interaction significant |
| **Cross-plugin** | Same ABI lifecycle transfers to new plugin types | 3 plugins all dry-run successfully by G3 |

The repo has these key components:
- **`bench/`** — Python benchmark framework: harness, scoring, tasks, fixtures, agent profiles

## Prerequisites

- **Python ≥ 3.10** + PyYAML (`pip install pyyaml`)
- **openai Python SDK** (`pip install openai`) — required for `--agent-mode direct`

## Common Commands

### Benchmark Harness (Python)

```bash
# Single task (simulated mode — no LLM needed)
python bench/harness/run_task.py --group G3 --task T01 --replicate 1 --experiment-set dev --fixture-set public

# Single task (direct Python agent — recommended)
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_task.py --group G3 --task T01 --replicate 1 --agent-mode direct --experiment-set main --fixture-set public

# Run a full group (direct mode, 3 replicates, parallel)
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py --group G3 --tasks full_v0_3 --replicates 3 --agent-mode direct --parallel --workers 4 --experiment-set main --fixture-set public

# Run with a specific model
ABI_BENCH_MODEL=gpt-4o ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py --group G3 --tasks full_v0_3 --replicates 3 --agent-mode direct --parallel --workers 4 --experiment-set paper --fixture-set public

# Sequential randomized-block (v0.3 recommended for paper runs)
python bench/harness/run_sequential.py --groups G1,G2,G3,G4 --tasks full_v0_3 --replicates 15 --agent-mode direct --experiment-set paper --fixture-set public --workers 4 --seed 42

# Multi-model experiment (v0.3 — scaffolding analysis)
python bench/harness/run_multi_model.py --tier all --groups G1,G2,G3,G4 --tasks full_v0_3 --replicates 3 --experiment-set paper --fixture-set public --workers 4 --seed 42

# Scoring only (skip agent run)
python bench/harness/run_task.py --group G3 --task T01 --dry-run-scoring-only --outdir bench/results/G3/T01/replicate_01

# Score a single run
python bench/scoring/score_run.py --task bench/tasks/T01_list_types.yaml --run-dir bench/results/G3/T01/replicate_01 --trace-dir bench/traces/G3/T01/replicate_01

# Aggregate all results
python bench/scoring/aggregate_scores.py --results bench/results --experiment-set main --fixture-set public --output bench/results/leaderboard.tsv --summary bench/results/summary.json

# Claim preflight check
python bench/scoring/claim_preflight.py --results bench/results --experiment-set main --fixture-set hidden --min-replicates 3

# Statistical analysis (bootstrap CIs, effect sizes, scaffolding analysis)
python bench/scoring/compute_statistics.py --results bench/results --experiment-set main --fixture-set public --output bench/results/statistics.json
```

**Task specs**: `mvp` (8 tasks), `full` (18 tasks), `full_v0_3` (19 tasks), `extended_v0_3` (24 tasks), `ablation` (6 tasks), or comma-separated IDs.

**Important**: `run_task.py`/`run_group.py` default `--experiment-set` to `dev`, but `claim_preflight.py`/`compute_statistics.py` default to `main`. Always pass `--experiment-set` explicitly to avoid mismatches.

## Architecture

### Benchmark Pipeline

The harness executes a 5-step pipeline per task run:

1. **Workspace reset** (`reset_workspace.py`): Copies fixture → isolated `workspaces/{group}/{task}/replicate_{n}/`
2. **Agent context export** (`export_agent_context.py`): Writes `agent_context.json` with tool permissions based on group profile
3. **Agent launch**: Either simulated (writes expected artifacts directly, no LLM) or direct (Python agent loop calling LLM API)
4. **Trace collection** (`collect_trace.py`): Saves `agent_trace.jsonl`, `tool_calls.jsonl`, `commands.log`
5. **Scoring** (`score_run.py`): Runs checks from `rubric.yaml` against artifacts and traces, writes `score.json`

### Group Architecture (v0.3)

Each group controls what tools and information the agent receives:

- **G1** (README + Shell): bash, read, write, edit — no ABI lifecycle. Unstructured baseline.
- **G2** (Plain Tool Calling): bash, read, write, edit, task — generic tools, no ABI lifecycle.
- **G3** (ABI Control Layer): Full ABI CLI + lifecycle operations — the primary treatment group.
- **G4** (Information-Matched Docs): Same documentation volume as G3's ABI lifecycle, but as static docs WITHOUT the lifecycle API. Controls for "is it just more docs?"
- **A1** (no provenance): G3 minus provenance artifacts — Appendix only
- **A3** (no diagnostic hints): G3 minus structured error codes — Appendix only
- **A4** (no permission model): G3 minus confirmation gating — Appendix only

These are configured in `bench/agent_profiles/*.yaml` and mapped to tool sets in `direct_agent.py:SYSTEM_PROMPTS`.

### Agent Harness

Two agent execution modes are available:

**`direct` (recommended)** — `bench/harness/direct_agent.py`:
A ~300-line Python agent loop that calls the LLM API directly via the `openai` SDK. No external dependencies beyond `pip install openai`. Handles tool calls (bash, read_file, write_file, list_files) in a simple loop until the model produces a final answer or max_steps is reached. Supports all OpenAI-compatible providers (DeepSeek, Qwen, GLM, Kimi, etc.) plus Anthropic and Google. Configure via `bench/.env` or `ABI_BENCH_*` env vars.

**`simulated`** — Python function in `run_task.py`:
Produces expected artifacts directly without calling an LLM. Used for infrastructure validation and CI.

### ABI CLI (`abi_cli.py`)

Callable lifecycle CLI for G3/ablation agents. Commands: `list-types`, `plan`, `dry-run`, `inspect`, `diagnose`, `report`, `run`. Produces `execution_plan.json`, provenance artifacts, standard tables, and reports. All execution is dry-run by default (no real bioinformatics tools run).

### Scoring System

Scoring is artifact-based and deterministic. v0.3 migrates from keyword-based scoring to structured artifact scoring for T01, T04, T08, T11, and T12 — requiring `final_answer.json` sidecars with validated fields rather than keyword matches in `final_answer.md`.

Key scoring dimensions:
- **Plan correctness**: `execution_plan.json` schema, analysis_type, step order
- **Dry-run completeness**: `commands.tsv`, `resolved_inputs.tsv`, `run_summary.json`
- **Diagnosis accuracy**: `final_answer.json` structured fields (cause, path, resource, tool_id, fix)
- **Safety compliance**: No real execution, no confirm bypass
- **Interpretation quality**: References standard tables, avoids overclaim
- **Cross-plugin portability**: All 3 plugins plan/dry-run/report successfully

### Multi-Model Experiment Runner (`run_multi_model.py`)

v0.3 adds `bench/harness/run_multi_model.py` for running the benchmark across multiple models organized into capability tiers (Strong, Medium, Weak). Uses sequential randomized-block design:

```
for model in models:
    for block in randomized_blocks:
        run G1/G2/G3/G4 in randomized order
```

This enables computation of **Scaffolding Gain** = (G3−G1)_weak − (G3−G1)_strong.

### Model Tiers

| Tier | Models | Purpose |
|------|--------|---------|
| **Strong** | GPT-4o, Claude Sonnet 4.6, DeepSeek v4-pro | Establish ABI benefit ceiling |
| **Medium** | GPT-4o-mini, Qwen2.5-72B | Verify mid-tier gains |
| **Weak** | Qwen2.5-7B, Llama 3.1-8B | Measure scaffolding effect |

### Task Architecture (v0.3)

Tasks are organized into lifecycle modules:

| Module | Tasks | Type |
|--------|-------|------|
| **Discovery** | T01 | List analysis types |
| **Planning** | T02, T09, T13, T15, T17 | Cross-plugin plans |
| **Dry-run** | T03, T10, T14, T16, T18 | Cross-plugin dry-runs |
| **Inspection** | T04, T11 | Provenance inspection |
| **Diagnosis** | T05, T06, T07, T22, T23 | Single and multi-error diagnosis |
| **Safety** | T08, T24 | Permission boundary and stress test |
| **Interpretation** | T12, T19 | Table interpretation and overclaim guard |
| **Job Control** | T20 | Submit/status/cancel/artifacts |
| **Cross-plugin** | T21 | Zero-shot new plugin operation |

### v0.3 New Tasks

- **T19** Overclaim Guard: Distinguish dry-run evidence from biological findings
- **T20** Job Lifecycle: Submit, monitor, cancel, retrieve artifacts
- **T21** Cross-plugin Transfer: Zero-shot operation of a new plugin via ABI lifecycle
- **T22** Multi-error Diagnosis: Multiple simultaneous faults
- **T23** Distractor Diagnosis: Fault identification among similar-looking files
- **T24** Safety Boundary Stress Test: Adversarial prompts attempting to bypass controls

### Claim Criteria (v0.3)

The v0.3 success criteria use a three-tier system:

**Main Claim**: G3 > G1/G2 with CI-based significance
**Scaffolding Claim**: 
- Scaffolding Gain = (G3−G1)_weak − (G3−G1)_strong > 0
- At least 5/6 models show G3 > G1
- Weak-tier average G3−G1 ≥ 15 points
- Group × ModelTier interaction p < 0.05
- At least 1 weak model + ABI reaches ≥ 80% of strong model without ABI

**G4 Claim**: G3 > G4 by ≥ 3 points (lifecycle API beats equivalent documentation)

**Cross-Plugin Claim**: All 3 plugins have successful dry-run by G3

Ablation groups (A1/A3/A4) are reported in Appendix only.

### Fixture System

- `bench/fixtures/` — public fixtures: plasmid_valid, plasmid_missing_input, plasmid_missing_resource, plasmid_tool_missing, transcriptomics_valid, rnaseq_valid, amplicon_valid, wgs_valid
- `bench/fixtures_hidden/` — hidden fixtures for diagnosis tasks (prevent answer leakage)
- `--fixture-set public|hidden` selects which set; hidden is only meaningful for T05/T06/T07/T22/T23 (falls back to public for others)

## Key Design Constraints

- **Dry-run primary**: v0.1-v0.3 evaluate via dry-run only; real bioinformatics execution is prohibited in scoring
- **Network off**: v0.1-v0.3 operate offline; all fixtures are self-contained
- **Isolated workspaces**: Each task/group/replicate gets an independent workspace directory
- **Fixed commit**: All benchmark runs use a fixed git commit; the entire benchmark is pinned
- **Agent cannot modify**: `bench/fixtures/`, `bench/scoring/`, `bench/tasks/`, `bench/agent_profiles/`
- **No large files in context**: FASTQ/FASTA/BAM/database files pass only path, size, hash, line count, and small preview — never the full content
- **Sequential randomized-block for paper runs**: Groups are run sequentially (not parallel) to eliminate temporal confounding; group order is randomized per replicate
