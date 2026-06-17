# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ABI-Bench v0.1** (Agent-Bioinformatics Interface Benchmark) evaluates whether a structured ABI control layer improves LLM agent operation of bioinformatics workflows. It fixes all variables (model, agent harness, repository, fixtures) and varies only the interface layer — comparing G1 (README + Shell), G2 (Plain Tool Calling), and G3 (ABI Control Layer), plus ablation groups (A1, A3, A4).

The repo has a single top-level component:
- **`bench/`** — Python benchmark framework: harness, scoring, tasks, fixtures, agent profiles

Note: `opencode/` directory (vendored OpenCode source) was **removed from the benchmark in v0.1.1**. The benchmark now uses a native Python agent loop (`direct_agent.py`) that calls LLM APIs directly via the `openai` SDK. See `docs/development/opencode_removal.md` for the rationale and migration notes.

## Prerequisites

- **Python ≥ 3.10** + PyYAML (`pip install pyyaml`)
- **openai Python SDK** (`pip install openai`) — required for `--agent-mode direct`

## Common Commands

### Benchmark Harness (Python)

```bash
# Single task (simulated mode — no LLM needed)
python bench/harness/run_task.py --group G3 --task T03 --replicate 1 --experiment-set dev --fixture-set public

# Single task (direct Python agent — recommended)
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_task.py --group G3 --task T03 --replicate 1 --agent-mode direct --experiment-set main --fixture-set public

# Run a full group (direct mode, 3 replicates, parallel)
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py --group G3 --tasks mvp --replicates 3 --agent-mode direct --parallel --workers 4 --experiment-set main --fixture-set public

# Paper-level run (15 replicates, all tasks, all groups — for claim validation)
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py --group G3 --tasks full --replicates 15 --agent-mode direct --parallel --workers 4 --experiment-set paper --fixture-set public

# Run a group in parallel
python bench/harness/run_group.py --group G3 --tasks mvp --replicates 3 --parallel --workers 4

# Scoring only (skip agent run)
python bench/harness/run_task.py --group G3 --task T03 --dry-run-scoring-only --outdir bench/results/G3/T03/replicate_01

# Score a single run
python bench/scoring/score_run.py --task bench/tasks/T03_dryrun_plasmid.yaml --run-dir bench/results/G3/T03/replicate_01 --trace-dir bench/traces/G3/T03/replicate_01

# Aggregate all results
python bench/scoring/aggregate_scores.py --results bench/results --experiment-set main --fixture-set hidden --output bench/results/leaderboard.tsv --summary bench/results/summary.json

# Claim preflight check
python bench/scoring/claim_preflight.py --results bench/results --experiment-set main --fixture-set hidden --min-replicates 3

# Statistical analysis (bootstrap CIs, effect sizes)
python bench/scoring/compute_statistics.py --results bench/results --experiment-set main --fixture-set hidden --output bench/results/statistics.json
```

**Task specs**: `mvp` (8 tasks: T01,T02,T03,T05,T06,T08,T09,T10), `full` (12 tasks), `ablation` (6 tasks: T03-T08), or comma-separated IDs.

**Important**: `run_task.py`/`run_group.py` default `--experiment-set` to `dev`, but `claim_preflight.py`/`compute_statistics.py` default to `main`. Always pass `--experiment-set` explicitly to avoid mismatches.

## Architecture

### Benchmark Pipeline

The harness executes a 5-step pipeline per task run:

1. **Workspace reset** (`reset_workspace.py`): Copies fixture → isolated `workspaces/{group}/{task}/replicate_{n}/`
2. **Agent context export** (`export_agent_context.py`): Writes `agent_context.json` with tool permissions based on group profile
3. **Agent launch**: Either simulated (writes expected artifacts directly, no LLM) or direct (Python agent loop calling LLM API)
4. **Trace collection** (`collect_trace.py`): Saves `agent_trace.jsonl`, `tool_calls.jsonl`, `commands.log`
5. **Scoring** (`score_run.py`): Runs checks from `rubric.yaml` against artifacts and traces, writes `score.json`

### Group Architecture

Each group controls what tools and information the agent receives:

- **G1** (README + Shell): bash, read, write, edit — no ABI lifecycle
- **G2** (Plain Tool Calling): bash, read, write, edit, task — generic tools, no ABI
- **G3** (ABI Control Layer): Full ABI CLI + lifecycle operations — preferred group
- **A1** (no provenance): G3 minus provenance artifacts
- **A3** (no diagnostic hints): G3 minus structured error codes
- **A4** (no permission model): G3 minus confirmation gating

These are configured in `bench/agent_profiles/*.yaml` and mapped to tool sets in `direct_agent.py:SYSTEM_PROMPTS`.

### Agent Harness

Two agent execution modes are available:

**`direct` (recommended)** — `bench/harness/direct_agent.py`:
A ~250-line Python agent loop that calls the LLM API directly via the `openai` SDK. No external dependencies beyond `pip install openai`. Handles tool calls (bash, read_file, write_file, list_files) in a simple loop until the model produces a final answer or max_steps is reached. Supports all OpenAI-compatible providers (DeepSeek, Qwen, GLM, Kimi, etc.) plus Anthropic and Google. Configure via `bench/.env` or `ABI_BENCH_*` env vars.

**`simulated`** — Python function in `run_task.py`:
Produces expected artifacts directly without calling an LLM. Used for infrastructure validation and CI.

### ABI CLI (`abi_cli.py`)

Callable lifecycle CLI for G3/ablation agents. Commands: `list-types`, `plan`, `dry-run`, `inspect`, `diagnose`, `report`, `run`. Produces `execution_plan.json`, provenance artifacts, standard tables, and reports. All execution is dry-run by default (no real bioinformatics tools run).

### Scoring System

Scoring is artifact-based and deterministic. Each task YAML references check names from `rubric.yaml`. Checks are implemented in `checks.py` as simple functions (`check_file_exists`, `check_tsv_nonempty`, `check_json_field`, `check_no_real_execution`, etc.). Diagnosis tasks (T05/T06/T07) require a `final_answer.json` sidecar with structured fields — keyword-only markdown answers cannot earn full marks.

Fixture-local expected answers live in `bench/expected_answers/` and are passed to the scorer via `--expected-answer` for structured diagnosis checks.

### Claim Criteria (v0.2.0)

Thresholds are defined in `bench/BENCHMARK_SPEC.yaml` under `success_criteria`. The system uses three complementary approaches:

**Stratified thresholds** (by task set):
- Full (12 tasks, T01–T12): G3−G1 ≥ 5, G3−G2 ≥ 5
- MVP (8 tasks): G3−G1 ≥ 15, G3−G2 ≥ 10
- Ablation (6 tasks, T03–T08): G3−G1 ≥ 8, G3−G2 ≥ 6

**CI-based significance** (when n ≥ 7): 95% CI lower bound must exclude 0 for all deltas.

**ABI Advantage Index** (composite, ≥ 0.50): Weighted combination of discovery effect (T01), safety effect (T08), cross-plugin effect (T09+T10), efficiency gain, and step reduction.

See `docs/development/threshold_recalibration.md` for the full rationale and power analysis.

### Fixture System

- `bench/fixtures/` — public fixtures (5 sets: plasmid_valid, plasmid_missing_input, plasmid_missing_resource, plasmid_tool_missing, transcriptomics_valid)
- `bench/fixtures_hidden/` — hidden fixtures for diagnosis tasks (prevent answer leakage)
- `--fixture-set public|hidden` selects which set; hidden is only meaningful for T05/T06/T07 (falls back to public for others)

## Key Design Constraints

- **Dry-run primary**: v0.1 evaluates via dry-run only; real bioinformatics execution is prohibited in scoring
- **Network off**: v0.1 operates offline; all fixtures are self-contained
- **Isolated workspaces**: Each task/group/replicate gets an independent workspace directory
- **Fixed commit**: All benchmark runs use a fixed git commit; the entire benchmark is pinned
- **Agent cannot modify**: `bench/fixtures/`, `bench/scoring/`, `bench/tasks/`, `bench/agent_profiles/`
- **No large files in context**: FASTQ/FASTA/BAM/database files pass only path, size, hash, line count, and small preview — never the full content
