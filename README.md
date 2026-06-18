# ABI-Bench v0.5

> [中文版 (Chinese Version)](README.zh.md)

## Agent-Bioinformatics Interface Benchmark

> 📋 **Submission Guide**: [English](SUBMISSION.md) | [中文版](SUBMISSION.zh.md)

---

## 1. What is ABI-Bench

**ABI-Bench** (Agent-Bioinformatics Interface Benchmark) evaluates whether
a structured **ABI control layer** improves LLM agent operation of
bioinformatics workflows. v0.5 focuses on the **scaffolding effect**:
does ABI lower the model capability threshold required for reliable
bioinformatics workflow operation, and extends evaluation to real
bioinformatics tool execution (T31-T35).

ABI-Bench answers three core questions:

> 1. Does an **ABI control layer** enable agents to more reliably plan,
>    dry-run, inspect, diagnose, and report on bioinformatics workflows
>    compared to unstructured baselines (README + Shell, Plain Tool Calling)?

> 2. Does ABI help **weaker models more** than stronger models, acting as a
>    domain-specific scaffold that lowers the capability barrier?

> 3. Can the same ABI lifecycle **transfer across multiple workflow plugins**
>    (metagenomic_plasmid, metatranscriptomics, amplicon_16s)?

---

## 2. Key Claims (v0.3)

### 2.1 Main Claim: ABI Improves Agent Operability

Across multiple LLMs (Strong/Medium/Weak) and three workflow plugins, G3
(ABI Control Layer) consistently outperforms G1 (README + Shell) and G2
(Plain Tool Calling). The effect is validated via sequential
randomized-block experiments with bootstrap confidence intervals.

### 2.2 Scaffolding Claim: ABI Helps Weak Models More

The **Scaffolding Gain** — defined as (G3−G1)_weak − (G3−G1)_strong —
quantifies how much more weak models benefit from ABI compared to strong
models. A positive Scaffolding Gain indicates that ABI's primary value is
as a domain scaffold that reduces the model reasoning burden, rather than
as a capability multiplier for already-strong models.

### 2.3 Cross-Plugin Claim: ABI Lifecycle is Portable

The same ABI lifecycle (list-types → plan → dry-run → inspect → report)
works across metagenomic_plasmid, metatranscriptomics, and amplicon_16s
plugins without plugin-specific modifications.

### 2.4 G4 Control: Lifecycle API > Equivalent Documentation

G4 receives the same information volume as G3's ABI lifecycle but as
static documentation without the lifecycle API. G3 > G4 demonstrates
that the structured lifecycle interface (CLI + JSON envelopes + standard
artifact paths) provides value beyond simply having more documentation.

---

## 3. Group Architecture

| Group | Name | Key Difference |
|-------|------|---------------|
| **G1** | README + Shell | Documentation + bash only |
| **G2** | Plain Tool Calling | Generic tools, no lifecycle |
| **G3** | ABI Control Layer | Full ABI CLI + lifecycle API |
| **G4** | Info-Matched Docs | Same docs as G3, no lifecycle API |
| **A1** | No Provenance | G3 minus provenance (Appendix) |
| **A3** | No Diagnostic Hints | G3 minus error codes (Appendix) |
| **A4** | No Permission Model | G3 minus confirmation gate (Appendix) |

---

## 4. Quick Start

### Prerequisites

- Python ≥ 3.10
- `pip install pyyaml openai scipy`
- Dev tools (optional): `pip install pytest ruff`

### Configuration

Copy `bench/.env.example` to `bench/.env` and set your provider credentials.
The harness supports any OpenAI-compatible endpoint, including self-hosted
models (Ollama, vLLM, llama.cpp):

```bash
# Local model example (Ollama)
ABI_BENCH_API_BASE=http://localhost:11434/v1
ABI_BENCH_MODEL=qwen2.5:7b
ABI_BENCH_TEMPERATURE=0.3
ABI_BENCH_MAX_TOKENS=4096
```

See `bench/.env.example` for all configuration options including retry
settings, reasoning model support, and provider-specific notes.

### Run a Single Task

```bash
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_task.py \
  --group G3 --task T01 --replicate 1 \
  --agent-mode direct --experiment-set dev --fixture-set public
```

### Run a Full Group

```bash
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py \
  --group G3 --tasks full_v0_5 --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set main --fixture-set public
```

### Multi-Model Experiment

```bash
python bench/harness/run_multi_model.py \
  --tier all --groups G1,G2,G3,G4 \
  --tasks full_v0_5 --replicates 3 \
  --experiment-set paper --fixture-set public \
  --workers 4 --seed 42
```

### Score and Analyze

```bash
# Aggregate all scores
python bench/scoring/aggregate_scores.py \
  --results bench/results --experiment-set main \
  --output bench/results/leaderboard.tsv \
  --summary bench/results/summary.json

# Statistical analysis with scaffolding metrics
python bench/scoring/compute_statistics.py \
  --results bench/results --experiment-set main \
  --output bench/results/statistics.json
```

---

## 5. Task Modules

| Module | Tasks | Description |
|--------|-------|-------------|
| Discovery | T01 | List available analysis types |
| Planning | T02, T09, T13, T15, T17 | Create execution plans across plugins |
| Dry-run | T03, T10, T14, T16, T18 | Validate plans without real execution |
| Inspection | T04, T11, T25, T26 | Read provenance, identify placeholders |
| Diagnosis | T05, T06, T07 | Single-fault diagnosis |
| Complex Diagnosis | T22, T23 | Multi-fault and distractor diagnosis |
| Safety | T08, T24 | Permission boundary and stress test |
| Interpretation | T12, T19 | Table interpretation, overclaim guard |
| Job Control | T20 | Submit, monitor, cancel, retrieve |
| Cross-plugin | T21 | Zero-shot new plugin operation |
| Contract | T27, T28, T29 | Contract lint, Nextflow export, violation detection |
| Report Quality | T30 | Report completeness and structure |
| Real Execution | T31-T35 | Real bioinformatics tool execution (v0.5) |

---

## 6. Repository Structure

```
bench/
  harness/          # Agent loop, ABI CLI, workspace reset, trace collection
    direct_agent.py   # LLM API agent loop (OpenAI SDK)
    abi_cli.py        # ABI lifecycle CLI
    run_task.py       # Single task runner
    run_group.py      # Group runner (parallel)
    run_sequential.py # Sequential randomized-block runner
    run_multi_model.py  # v0.3: Multi-model experiment runner
    path_guard.py     # Filesystem access control
  scoring/          # Scoring framework
    score_run.py      # Single run scorer
    checks.py         # Check function implementations
    rubric.yaml       # Centralized check definitions
    aggregate_scores.py  # Score aggregation
    compute_statistics.py  # Bootstrap CIs, effect sizes, scaffolding analysis
    claim_preflight.py  # Pre-submission completeness check
  tasks/            # Task YAML definitions (T01–T24)
  agent_profiles/   # Group profiles (G1–G4, A1, A3, A4)
  fixtures/         # Public workspace fixtures
  fixtures_hidden/  # Hidden fixtures (diagnosis anti-leakage)
  expected_answers/ # Fixture-local expected answers for structured checks
  BENCHMARK_SPEC.yaml  # v0.3 benchmark specification
```

For detailed architecture, see [CLAUDE.md](CLAUDE.md).

---

## 7. Citing

If you use ABI-Bench in your research, please cite:

```bibtex
@software{abi_bench_v0_5,
  title = {ABI-Bench: Agent-Bioinformatics Interface Benchmark v0.3},
  author = {ABI-Bench Contributors},
  year = {2026},
  note = {Evaluates structured ABI control layer for LLM agent
          bioinformatics workflow operation across model capability tiers},
}
```
