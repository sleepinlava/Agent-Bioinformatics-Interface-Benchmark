# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ABI-Bench v0.9** (Agent-Bioinformatics Interface Benchmark) evaluates whether a structured ABI control layer improves LLM agent operation of bioinformatics workflows — focusing on the **scaffolding effect** (weaker models benefit more from ABI), **cross-plugin portability** (same ABI lifecycle works across 7 plugins), **evidence-based artifact scoring** (JSON, workspace files, config changes, traces — not keyword matching), **hidden robustness** (cross-plugin diagnosis with public/hidden fixture pairs), and **7-suite evaluation architecture** with distinct claim roles.

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

- **Python ≥ 3.10**
- Install dependencies: `pip install pyyaml openai scipy`
- **openai Python SDK** — required for `--agent-mode direct`
- **scipy** — required for statistical analysis (`compute_statistics.py`)
- Dev tools: `pip install pytest ruff` (optional, for linting)

## Configuration

Copy `bench/.env.example` to `bench/.env` and set your provider credentials. The harness supports these providers via `ABI_BENCH_PROVIDER`: `anthropic`, `openai`, `deepseek`, `qwen`, `glm`, `kimi`, `mimo`, `google`, `openai-compatible`.

### Local / Self-hosted Models

Set `ABI_BENCH_PROVIDER=openai-compatible` and point `ABI_BENCH_API_BASE` to any OpenAI-compatible endpoint (Ollama, vLLM, LocalAI, llama.cpp server, etc.). The endpoint must support the chat completions API with tool/function calling. Example:

```bash
ABI_BENCH_PROVIDER=openai-compatible
ABI_BENCH_API_BASE=http://localhost:11434/v1
ABI_BENCH_MODEL=llama3.1:8b
```

### Agent Tuning

- `ABI_BENCH_TEMPERATURE=0.0` — Sampling temperature (0.0–2.0). Some local models degrade at 0 — try 0.3–0.7.
- `ABI_BENCH_MAX_TOKENS=8000` — Max completion tokens per API call. Use 2048–4096 for small local models.
- `ABI_BENCH_MAX_RETRIES=3` — Retries on transient API errors (connection, timeout, rate limit, 5xx)
- `ABI_BENCH_RETRY_BASE_DELAY=2.0` — Initial retry delay in seconds (exponential backoff)
- `ABI_BENCH_RETRY_MAX_DELAY=60.0` — Retry delay cap in seconds

### Reasoning Model Support

Optional env vars for models with extended thinking (tracked in metadata but not yet actively injected into API calls):
- `ABI_BENCH_REASONING=true` — enable thinking/reasoning token tracking
- `ABI_BENCH_THINKING_BUDGET=16000` — Anthropic/Google/Qwen thinking budget in tokens (1024–128000)
- `ABI_BENCH_REASONING_EFFORT=medium` — OpenAI/Qwen/GLM/Kimi/MiMo reasoning effort (`low`, `medium`, `high`)

All config is loaded from `bench/.env` and overridable via environment variables.

## Common Commands

### Benchmark Harness (Python)

```bash
# Single task (simulated mode — no LLM needed)
python bench/harness/run_task.py --group G3 --task T01 --replicate 1 --experiment-set dev --fixture-set public

# Single task (direct Python agent — recommended)
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_task.py --group G3 --task T01 --replicate 1 --agent-mode direct --experiment-set main --fixture-set public

# Run a full group (direct mode, 5 replicates, suite-based)
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py --group G3 --tasks causal_core_v0_8 --replicates 5 --agent-mode direct --parallel --workers 4 --experiment-set main --fixture-set public

# Run with a specific model
ABI_BENCH_MODEL=gpt-4o ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py --group G3 --tasks causal_core_v0_8 --replicates 5 --agent-mode direct --parallel --workers 4 --experiment-set paper --fixture-set public

# Sequential randomized-block (v0.3 recommended for paper runs)
python bench/harness/run_sequential.py --groups G1,G2,G3,G4 --tasks causal_core_v0_8 --replicates 15 --agent-mode direct --experiment-set paper --fixture-set public --workers 4 --seed 42

# Multi-model experiment (v0.3 — scaffolding analysis)
python bench/harness/run_multi_model.py --tier all --groups G1,G2,G3,G4 --tasks causal_core_v0_8 --replicates 5 --experiment-set paper --fixture-set public --workers 4 --seed 42

# Scoring only (skip agent run)
python bench/harness/run_task.py --group G3 --task T01 --dry-run-scoring-only --outdir bench/results/G3/T01/replicate_01

# Score a single run
python bench/scoring/score_run.py --task bench/tasks/T01_list_types.yaml --run-dir bench/results/G3/T01/replicate_01 --trace-dir bench/traces/G3/T01/replicate_01

# Aggregate all results (suite-based)
python bench/scoring/aggregate_scores.py --results bench/results --experiment-set main --fixture-set public --suite causal_core_v0_8 --output bench/results/leaderboard.tsv --summary bench/results/summary.json

# Claim preflight check
python bench/scoring/claim_preflight.py --results bench/results --experiment-set main --fixture-set hidden --suite causal_core_v0_8 --min-replicates 5

# Statistical analysis (bootstrap CIs, effect sizes, scaffolding analysis)
python bench/scoring/compute_statistics.py --results bench/results --experiment-set main --fixture-set public --suite causal_core_v0_8 --output bench/results/statistics.json

# Static design audit (run before any experiment)
python bench/validation/audit_benchmark.py --strict
```

**Task specs**: `mvp` (8 tasks), `full` (18 tasks), `full_v0_3` (19), `extended_v0_3` (24), `full_v0_4` (29), `extended_v0_4` (30), `full_v0_5` (34), `extended_v0_5` (35), `full_v0_6` (47), `extended_v0_6` (52), `full_v0_7` (58), `extended_v0_7` (63), `full_v0_9` (61), `causal_core_v0_8` (24), `hidden_robustness_v0_9` (3), `ablation` (6 tasks), or comma-separated IDs.

**Linting**: `ruff check bench/` (config in `pyproject.toml`; excludes `workspaces/`, `traces/`, `results/`)

**Tests**: `python -m pytest tests/ -v` (33 tests covering config, retry logic, model tiers)

**Important**: `run_task.py`/`run_group.py` default `--experiment-set` to `dev`, but `claim_preflight.py`/`compute_statistics.py` default to `main`. Always pass `--experiment-set` explicitly to avoid mismatches.

## Architecture

### Benchmark Pipeline

The harness executes a 5-step pipeline per task run:

1. **Workspace reset** (`reset_workspace.py`): Copies fixture → isolated `workspaces/{group}/{task}/replicate_{n}/`
2. **Agent context export** (`export_agent_context.py`): Writes `agent_context.json` with tool permissions based on group profile
3. **Agent launch**: Either simulated (writes expected artifacts directly, no LLM) or direct (Python agent loop calling LLM API)
4. **Trace collection** (`collect_trace.py`): Saves `agent_trace.jsonl`, `tool_calls.jsonl`, `commands.log`
5. **Scoring** (`score_run.py`): Runs checks from `rubric.yaml` against artifacts and traces, writes `score.json`

### Group Architecture (v0.9)

Each group controls what tools and information the agent receives:

- **G1** (README + Shell): bash, read, write, edit — no ABI lifecycle. Unstructured baseline.
- **G2** (Plain Tool Calling): bash, read, write, edit, task — generic tools, no ABI lifecycle.
- **G3** (ABI Control Layer): Full ABI CLI + lifecycle operations — the primary treatment group.
- **G4** (Information-Matched Docs): Same documentation volume as G3's ABI lifecycle, but as static docs WITHOUT the lifecycle API. Controls for "is it just more docs?"
- **A1** (no provenance): G3 minus provenance artifacts — Appendix only
- **A3** (no diagnostic hints): G3 minus structured error codes — Appendix only
- **A4** (no permission model): G3 minus confirmation gating — Appendix only

These are configured in `bench/agent_profiles/*.yaml` and mapped to tool sets in `direct_agent.py:SYSTEM_PROMPTS`.

### Evaluation Suites (v0.9)

v0.9 organizes 61 tasks into 7 suites with distinct claim roles. Only `causal_core_v0_8` and `hidden_robustness_v0_9` may estimate the causal effect of ABI — their prompts are interface-neutral and every group is scored against the same outcome. Defined in `bench/evaluation_suites.yaml`:

| Suite | Claim Role | Tasks | Groups |
|-------|-----------|-------|--------|
| `causal_core_v0_8` | primary_causal | 24 | G1, G2, G3, G4 |
| `hidden_robustness_v0_9` | causal_robustness | 3 (T59-T61) | G1, G2, G3, G4 |
| `mechanism_probes_v0_8` | mechanism_descriptive | 32 | G3, A1, A3, A4 |
| `real_execution_case_studies_v0_8` | case_study | 5 (T31-T35) | G3 |
| `heldout_plugin_v0_8` | external_validity | 3 (T48-T50) | G1, G2, G3, G4 |
| `ablation_v0_8` | component_ablation | 6 (T03-T08) | G3, A1, A3, A4 |
| `full_descriptive_v0_8` | descriptive_only | 61 (T01-T61) | All |

### Agent Harness

Two agent execution modes are available:

**`direct` (recommended)** — `bench/harness/direct_agent.py`:
A ~900-line Python agent loop that calls the LLM API directly via the `openai` SDK. Handles tool calls (bash, read_file, write_file, list_files) in a loop until the model produces a final answer or max_steps is reached. Supports any OpenAI-compatible endpoint (DeepSeek, Qwen, GLM, Kimi, Ollama, vLLM, etc.). Anthropic and Google models require an OpenAI-compatible proxy — native SDK support is not yet implemented. Configure via `bench/.env` or `ABI_BENCH_*` env vars. Includes exponential backoff retry on transient API errors (connection, timeout, rate limit, 5xx).

**`simulated`** — Python function in `run_task.py`:
Produces expected artifacts directly without calling an LLM. Used for infrastructure validation and CI.

### ABI CLI (`abi_cli.py`)

Callable lifecycle CLI for G3/ablation agents. Commands: `list-types`, `plan`, `dry-run`, `inspect`, `diagnose`, `report`, `run`. Produces `execution_plan.json`, provenance artifacts, standard tables, and reports. All execution is dry-run by default (no real bioinformatics tools run).

### Configuration (`config.py`) and Model Tiers (`model_tiers.yaml`)

**`bench/harness/config.py`** — Centralized configuration module (new in v0.5). Single `BenchConfig` dataclass holds all `ABI_BENCH_*` settings with precedence: `os.environ > .env > defaults`. Provides `load_bench_config()`, `validate_config()` (pre-flight warnings), and `load_dotenv()` (canonical dotenv loader). Configurable fields include `temperature`, `max_retries`, `retry_base_delay_seconds`, `retry_max_delay_seconds`, `reasoning`, `thinking_budget`, and `reasoning_effort`.

**`bench/model_tiers.yaml`** — Editable model tier definitions. Add custom/local models here to include them in scaffolding analysis without editing source code. Loaded by `run_multi_model.py` and `compute_statistics.py` with built-in fallbacks.

### PathGuard Security (`path_guard.py`)

Filesystem access control layer that routes ALL file reads, writes, list_files, and bash commands through deny-list checks before execution. Blocks access to benchmark-internal directories: `expected_answers/`, `bench/scoring/`, `bench/tasks/`, `bench/agent_profiles/`, `fixtures_hidden/`, `bench/.env`, `bench/results/`. Also scans bash commands for indirect access patterns (cat/grep/find targeting sensitive paths).

### Bash Execution Security (5-layer defense in `direct_agent.py`)

1. **PathGuard command scan** — blocks commands targeting sensitive paths
2. **Injection/bowtie prefix block** — blocks `env`, `exec`, `xargs`, `python -c`, backticks, `$()`, `./`
3. **ABI CLI gating** — non-ABI groups (G1/G2/G4) blocked from calling `abi_cli.py` or ABI lifecycle subcommands
4. **Bio tool execution block** — blocks real bioinformatics tool invocations (prodigal, hmmscan, blastn, star, etc.); allows `which`, `--version`, `--help`, shell wrappers (cat, grep, ls, etc.)
5. **Shell injection hardening** — uses `shell=False` with `shlex.split()` when possible, falls back to `shell=True` only for commands with pipes/redirects

### Scoring System

Scoring is artifact-based and deterministic. Key scoring dimensions:
- **Plan correctness**: `execution_plan.json` schema, analysis_type, step order
- **Dry-run completeness**: `commands.tsv`, `resolved_inputs.tsv`, `run_summary.json`
- **Diagnosis accuracy**: `final_answer.json` structured fields (cause, path, resource, tool_id, fix)
- **Safety compliance**: No real execution (T01-T30), no confirm bypass
- **Real execution correctness** (T31-T35, v0.5): Actual bioinformatics tool output validation
- **Interpretation quality**: References standard tables, avoids overclaim
- **Cross-plugin portability**: All 5 plugins plan/dry-run/report successfully
- **Contract validation**: Lint, export, and violation detection (T27-T29)
- **Report quality**: Completeness and structure validation (T30)
- **Figure validation** (T36-T38, v0.6): Sciplot figure verification, diagnosis, data consistency
- **Progressive repair** (T39-T41, v0.6): Single-fault and multi-fault recovery, resource self-configuration
- **Cross-platform equivalence** (T42-T44, v0.6): Local/Nextflow/Docker output consistency, provenance audit
- **Multi-agent collaboration** (T45-T47, v0.6): Planner-reviewer, cross-model verification (v0.9: compares two independent review artifacts), zero-shot transfer
- **Evidence-based scoring** (T36-T47, v0.9): Cross-validates JSON fields, workspace files, config changes, and traces — eliminates keyword matching
- **Hidden robustness** (T59-T61, v0.9): Cross-plugin diagnosis with public/hidden fixture pairs (RNA-seq, WGS, easymetagenome)
- **Static audit** (v0.9): `audit_benchmark.py --strict` detects unknown scoring functions, fixture multi-fault mixing, per-plugin score field mismatches, and rubric indirect keyword scoring

The `rubric.yaml` (765 lines) defines all scoring checks centrally. Each task YAML references checks by key. `checks.py` (1389 lines) implements the check functions.

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
| **Strong** | GPT-4o, Claude Sonnet 4.6, DeepSeek v4-pro, Qwen3-30B-A3B-Instruct (MoE), Qwen2.5-Coder-32B-Instruct | Establish ABI benefit ceiling |
| **Medium** | GPT-4o-mini, Qwen2.5-72B, Qwen3-14B, Mistral-Small-3.2-24B-Instruct | Verify mid-tier gains |
| **Weak** | Qwen2.5-7B, Llama 3.1-8B, Qwen3-4B, Llama-3.1-8B-Instruct, DeepSeek-R1-Distill-Qwen-7B | Measure scaffolding effect |

> **Quantization note**: For local model benchmarking on RTX 4090 (24GB VRAM),
> Medium and Strong tier models require 4-bit quantization. Prefer GGUF Q4_K_M
> or GPTQ/AWQ over bitsandbytes — structured tool-calling benchmarks are
> especially sensitive to quantization degradation. Weak-tier models run
> natively without quantization. See `bench/model_tiers.yaml` for canonical tier definitions.

### Task Architecture (v0.9)

Tasks are organized into lifecycle modules:

| Module | Tasks | Type |
|--------|-------|------|
| **Discovery** | T01 | List analysis types |
| **Planning** | T02, T09, T13, T15, T17, T48, T50 | Cross-plugin plans (7 plugins) |
| **Dry-run** | T03, T10, T14, T16, T18, T49 | Cross-plugin dry-runs |
| **Inspection** | T04, T11, T25, T26 | Provenance inspection across plugins |
| **Diagnosis** | T05, T06, T07, T22, T23 | Single and multi-error diagnosis |
| **Hidden Diagnosis** | T59, T60, T61 | Cross-plugin hidden robustness (v0.9) |
| **Safety** | T08, T24 | Permission boundary and stress test |
| **Interpretation** | T12, T19 | Table interpretation and overclaim guard |
| **Job Control** | T20 | Submit/status/cancel/artifacts |
| **Cross-plugin** | T21 | Zero-shot new plugin operation |
| **Contract** | T27, T28, T29 | Contract lint, Nextflow export, violation detection |
| **Report Quality** | T30 | Report completeness and structure |
| **Real Execution** | T31, T32, T33, T34, T35 | Real bioinformatics execution (plasmid, rnaseq, amplicon, wgs, metatranscriptomics) |
| **Figure Validation** | T36, T37, T38 | Figure verification, diagnosis, data consistency (v0.9: evidence scoring) |
| **Progressive Repair** | T39, T40, T41 | Single-fault, multi-fault recovery, resource self-config (v0.9: evidence scoring) |
| **Cross-Platform** | T42, T43, T44 | Local/Nextflow/Docker comparison, provenance audit (v0.9: evidence scoring) |
| **Multi-Agent** | T45, T46, T47 | Planner-reviewer, cross-model verify (independent reviews), zero-shot transfer (v0.9: evidence scoring) |
| **ABI Query** | T51, T52 | Metadata discovery, cross-plugin (v0.7) |
| **Resource Mgmt** | T53, T54 | Check-resources, setup-resources (v0.7) |
| **Doctor Agent** | T55 | Operating guide interpretation (v0.7) |
| **Sciplot CLI** | T56, T57 | Figure validate, render (v0.7) |
| **Internal Handlers** | T58 | Internal vs external step awareness (v0.7) |

### v0.7/v0.8/v0.9 New Tasks

**v0.7** added T48-T58 (11 tasks: easymetagenome, viral_viwrap, ABI query, resource mgmt, doctor agent, sciplot CLI, internal handlers).
**v0.8** restructured evaluation into 7 suites with distinct claim roles — preventing mechanism tasks from contaminating the primary causal estimate of ABI's effect. Introduced `causal_core_v0_8`, `mechanism_probes_v0_8`, and suite-aware scoring with `--suite` flag.
**v0.9** converted T36-T47 to evidence-based artifact scoring (JSON, workspace files, config changes, traces — no keyword matching). Redesigned T46 to compare two independent review artifacts. Added T59-T61 (cross-plugin hidden robustness: RNA-seq, WGS, easymetagenome with public/hidden fixture pairs). Added static audit (`audit_benchmark.py --strict`). Fixed safety checks to fail on missing trace (no longer default-pass).

### Claim Criteria (v0.9)

The v0.9 claim criteria build on v0.8's suite architecture:

**Main Claim** (causal_core_v0_8): G3 > G1/G2 with CI-based significance on interface-neutral tasks
**Scaffolding Claim**: 
- Scaffolding Gain = (G3−G1)_weak − (G3−G1)_strong > 0
- At least 5/6 models show G3 > G1
- Weak-tier average G3−G1 ≥ 15 points
- Group × ModelTier interaction p < 0.05
- At least 1 weak model + ABI reaches ≥ 80% of strong model without ABI

**G4 Claim**: G3 > G4 by ≥ 3 points (lifecycle API beats equivalent documentation)

**Cross-Plugin Claim**: 6+ plugins (metagenomic_plasmid, metatranscriptomics, amplicon_16s, rnaseq_expression, wgs_bacteria, easymetagenome) have successful dry-run by G3; viral_viwrap has successful planning

**Hidden Robustness Claim** (hidden_robustness_v0_9): G3 > G1/G2/G4 on held-out cross-plugin diagnosis tasks, reported independently

**Evidence Scoring Claim**: T36-T47 scores from artifact cross-validation have lower false-positive rate than keyword matching (validated via static audit)

Ablation groups (A1/A3/A4) are reported in Appendix only.

### Fixture System

- `bench/fixtures/` — public fixtures: plasmid_valid, plasmid_missing_input, plasmid_missing_resource, plasmid_tool_missing, transcriptomics_valid, rnaseq_valid, amplicon_valid, wgs_valid, easymeta_single_missing_resource, wgs_single_missing_resource, figure_validation_clean, figure_diagnosis, figure_data_consistency
- `bench/fixtures_hidden/` — hidden fixtures for diagnosis tasks (prevent answer leakage): plasmid_hidden_missing_input, plasmid_hidden_missing_resource, plasmid_hidden_tool_missing, rnaseq_hidden_missing_resource, wgs_hidden_single_missing_resource, easymeta_hidden_single_missing_resource
- `--fixture-set public|hidden` selects which set; hidden is only meaningful for T05/T06/T07/T22/T23 (falls back to public for others)

## Local Model Benchmarking

### vLLM Server

```bash
# Start vLLM server with bitsandbytes 4-bit quantization
vllm serve /root/autodl-tmp/local_llms/models/Qwen3-14B \
  --served-model-name Qwen3-14B \
  --host 0.0.0.0 --port 8000 \
  --quantization bitsandbytes --load-format bitsandbytes \
  --max-model-len 8192 --gpu-memory-utilization 0.90 \
  --dtype bfloat16
```

### Model Inventory

See `/root/autodl-tmp/local_llms/llm.md` for model sizes, VRAM requirements, and tier assignments.

### Known Issues

- **4-bit bitsandbytes degrades structured instruction-following**: Qwen3-14B 4-bit G3−G2 = +1.8% vs Qwen3-4B native G3−G2 = +30.6%. Prefer GGUF or GPTQ for 4-bit quantization.
- **Qwen3-30B-A3B-Instruct OOM on RTX 4090 24GB**: Even 4-bit quantization fails. MoE architecture has high KV cache overhead. May need tensor parallelism across multiple GPUs or CPU offloading.
- **G1/G4 not yet run for Qwen3-14B**: Baseline groups missing — cannot compute full scaffolding effect for medium tier.

## Key Design Constraints

- **Suite-based evaluation (v0.8)**: Only `causal_core_v0_8` and `hidden_robustness_v0_9` may estimate the causal effect of ABI; mechanism probes and case studies are reported separately
- **Evidence-based scoring (v0.9)**: T36-T47 scores cross-validate JSON artifacts, workspace files, config changes, and traces — not keyword matching or self-reported claims
- **Dry-run primary (T01-T30)**: v0.1-v0.4 evaluate via dry-run only; real bioinformatics execution is prohibited in scoring for these tasks
- **Real execution (T31-T35, v0.5)**: Real bioinformatics tool execution is permitted for these tasks only, gated behind explicit confirmation
- **Hidden robustness (T59-T61, v0.9)**: Cross-plugin diagnosis with public/hidden fixture pairs, reported independently
- **Static audit required (v0.9)**: `audit_benchmark.py --strict` must pass before any experimental run — catches unknown scoring functions, fixture multi-fault mixing, and rubric indirect keyword scoring
- **Network off**: All fixtures are self-contained; no external network access required
- **Isolated workspaces**: Each task/group/replicate gets an independent workspace directory
- **Fixed commit**: All benchmark runs use a fixed git commit; the entire benchmark is pinned
- **Agent cannot modify**: `bench/fixtures/`, `bench/scoring/`, `bench/tasks/`, `bench/agent_profiles/`
- **No large files in context**: FASTQ/FASTA/BAM/database files pass only path, size, hash, line count, and small preview — never the full content
- **Sequential randomized-block for paper runs**: Groups are run sequentially (not parallel) to eliminate temporal confounding; group order is randomized per replicate
- **PathGuard filesystem security**: All file reads, writes, and bash commands route through `path_guard.py` which blocks access to benchmark-internal directories (`expected_answers/`, `bench/scoring/`, `bench/tasks/`, `bench/agent_profiles/`, `fixtures_hidden/`, `bench/.env`, `bench/results/`)
