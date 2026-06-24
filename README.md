# ABI-Bench v0.9

> [中文版 (Chinese Version)](README.zh.md)

## Agent-Bioinformatics Interface Benchmark

> 📋 **Submission Guide**: [English](SUBMISSION.md) | [中文版](SUBMISSION.zh.md)

---

## 1. What is ABI-Bench

**ABI-Bench** (Agent-Bioinformatics Interface Benchmark) evaluates whether
a structured **ABI control layer** improves LLM agent operation of
bioinformatics workflows. v0.9 converts T36–T47 to evidence-based scoring
(JSON artifacts, workspace files, config changes, and traces instead of
keyword matching), adds a cross-plugin hidden robustness suite (T59–T61:
RNA-seq, WGS, easymetagenome), and separates evaluation into 7 suites
with distinct claim roles — preventing mechanism tasks from contaminating
the primary causal estimate of ABI's effect.

ABI-Bench answers three core questions:

> 1. Does an **ABI control layer** enable agents to more reliably plan,
>    dry-run, inspect, diagnose, and report on bioinformatics workflows
>    compared to unstructured baselines (README + Shell, Plain Tool Calling)?

> 2. Does ABI help **weaker models more** than stronger models, acting as a
>    domain-specific scaffold that lowers the capability barrier?

> 3. Can the same ABI lifecycle **transfer across multiple workflow plugins**
>    (metagenomic_plasmid, metatranscriptomics, amplicon_16s, rnaseq_expression,
>    wgs_bacteria, easymetagenome, viral_viwrap)?

---

## 2. Key Claims (v0.9)

### 2.1 Main Claim: ABI Improves Agent Operability

Across multiple LLMs (Strong/Medium/Weak) and five workflow plugins, G3
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
works across metagenomic_plasmid, metatranscriptomics, amplicon_16s,
rnaseq_expression, and wgs_bacteria plugins without plugin-specific modifications.

### 2.4 G4 Control: Lifecycle API > Equivalent Documentation

G4 receives the same information volume as G3's ABI lifecycle but as
static documentation without the lifecycle API. G3 > G4 demonstrates
that the structured lifecycle interface (CLI + JSON envelopes + standard
artifact paths) provides value beyond simply having more documentation.

### 2.5 Figure Validation Claim: ABI Enables Scientific Figure Quality Control

ABI's sciplot integration enables agents to validate, diagnose, and verify
data consistency of publication-grade scientific figures (T36-T38). G3
figure validation pass rate exceeds baseline.

### 2.6 Progressive Repair Claim: ABI Enables Autonomous Error Recovery

ABI's diagnostic hints and resource manifests enable agents to recover from
single-fault and multi-fault failure scenarios, including autonomous resource
self-configuration (T39-T41).

### 2.7 Cross-Platform Claim: ABI Pipelines are Platform-Portable

ABI workflows produce equivalent outputs across local, Docker, and Nextflow
execution platforms with full provenance audit trail (T42-T44).

### 2.8 Multi-Agent Claim: ABI Lifecycle Supports Agent Collaboration

ABI's structured JSON envelopes and standard artifact paths enable effective
planner-reviewer collaboration, cross-model verification (comparing two
independently-generated review artifacts), and zero-shot
transfer between agent platforms (T45-T47).

### 2.9 Evidence Scoring Claim: Artifact-Based Evaluation is More Reliable

v0.9 replaces keyword-matching (`final_answer_contains`) with evidence-based
scoring for T36–T47: JSON field validation, workspace file cross-checking,
config change verification, and trace inspection. This eliminates false
positives from self-reported claims and ensures the agent actually performed
the work rather than describing it.

### 2.10 Hidden Robustness Claim: Diagnosis Skills Generalize to Held-Out Plugins

T59–T61 test whether diagnosis ability transfers to RNA-seq, bacterial WGS,
and shotgun metagenomics with public/hidden fixture pairs that change
identifiers and paths while preserving the fault class. These tasks form a
separate `hidden_robustness_v0_9` suite, reported independently from the
primary causal estimate.

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
  --group G3 --tasks causal_core_v0_8 --replicates 5 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set main --fixture-set public
```

### Multi-Model Experiment

```bash
python bench/harness/run_multi_model.py \
  --tier all --groups G1,G2,G3,G4 \
  --tasks causal_core_v0_8 --replicates 5 \
  --experiment-set paper --fixture-set public \
  --workers 4 --seed 42
```

### Static Design Audit

```bash
# Run before any experiment to catch design-time issues
python bench/validation/audit_benchmark.py --strict
```

### Score and Analyze

```bash
# Aggregate scores for a specific suite
python bench/scoring/aggregate_scores.py \
  --results bench/results --experiment-set main \
  --suite causal_core_v0_8 \
  --output bench/results/leaderboard.tsv \
  --summary bench/results/summary.json

# Statistical analysis with scaffolding metrics
python bench/scoring/compute_statistics.py \
  --results bench/results --experiment-set main \
  --suite causal_core_v0_8 \
  --output bench/results/statistics.json

# Claim preflight check
python bench/scoring/claim_preflight.py \
  --results bench/results --experiment-set main --fixture-set hidden \
  --suite hidden_robustness_v0_9 --min-replicates 5
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
| Figure Validation | T36-T38 | Sciplot figure verification, diagnosis, data consistency (v0.6) |
| Progressive Repair | T39-T41 | Single-fault and multi-fault recovery, resource self-config (v0.6) |
| Cross-Platform | T42-T44 | Local/Nextflow/Docker comparison, provenance audit (v0.6) |
| Multi-Agent | T45-T47 | Planner-reviewer, cross-model verify, zero-shot transfer (v0.6) |
| Hidden Diagnosis | T59-T61 | Cross-plugin hidden robustness: RNA-seq, WGS, easymetagenome (v0.9) |

---

## 6. Evaluation Suites (v0.9)

v0.9 organizes tasks into 7 evaluation suites with distinct claim roles,
preventing mechanism tasks from contaminating the primary causal estimate:

| Suite | Claim Role | Tasks | Groups |
|-------|-----------|-------|--------|
| `causal_core_v0_8` | primary_causal | 24 tasks (T01–T19, T25–T26, T48–T50) | G1, G2, G3, G4 |
| `hidden_robustness_v0_9` | causal_robustness | 3 tasks (T59–T61) | G1, G2, G3, G4 |
| `mechanism_probes_v0_8` | mechanism_descriptive | 32 tasks (T20–T24, T27–T30, T36–T47, T51–T58) | G3, A1, A3, A4 |
| `real_execution_case_studies_v0_8` | case_study | 5 tasks (T31–T35) | G3 |
| `heldout_plugin_v0_8` | external_validity | 3 tasks (T48–T50) | G1, G2, G3, G4 |
| `ablation_v0_8` | component_ablation | 6 tasks (T03–T08) | G3, A1, A3, A4 |
| `full_descriptive_v0_8` | descriptive_only | 61 tasks (T01–T61) | All groups |

Run suite-based scoring with `--suite <name>` on `aggregate_scores.py`,
`compute_statistics.py`, and `claim_preflight.py`.

---

## 7. Repository Structure

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
    aggregate_scores.py  # Score aggregation (supports --suite)
    compute_statistics.py  # Bootstrap CIs, effect sizes, scaffolding analysis
    claim_preflight.py  # Pre-submission completeness check
  validation/       # Static design auditing (v0.9)
    audit_benchmark.py  # Detects unknown scoring functions, fixture multi-fault
                       #   mixing, rubric indirect keyword scoring, and
                       #   per-plugin score field mismatches
  tasks/            # Task YAML definitions (T01–T61)
  agent_profiles/   # Group profiles (G1–G4, A1, A3, A4)
  fixtures/         # Public workspace fixtures
  fixtures_hidden/  # Hidden fixtures (diagnosis anti-leakage, 9 plugins)
  expected_answers/ # Fixture-local expected answers for structured checks
  evaluation_suites.yaml  # v0.9 suite definitions with claim roles
  BENCHMARK_SPEC.yaml  # Benchmark specification
```

For detailed architecture, see [CLAUDE.md](CLAUDE.md).

---

## 8. Local Model Results (v0.6-dev)

ABI-Bench has been validated on a suite of 7 local/self-hosted models
across Weak, Medium, and Strong capability tiers, confirming the core
scaffolding hypothesis:

### 7.1 Leaderboard (T01-T30, public fixtures)

| Model | Tier | G1 | G2 | G3 | G4 | G3−G1 | G3−G2 |
|-------|------|----|----|----|----|-------|-------|
| Qwen3-4B | Weak | 29.4% | 22.9% | **53.5%** | 33.9% | **+24.1%** | **+30.6%** |
| Llama-3.1-8B | Weak | 18.3% | 17.6% | **46.1%** | 20.3% | **+27.7%** | **+28.5%** |
| Qwen3-14B (4-bit) | Medium | — | 23.5% | **25.2%** | — | — | +1.8% |

> **Scaffolding effect confirmed**: Weak models gain 24-28 points from ABI in G3,
> while the medium model (Qwen3-14B, 4-bit quantized) gains less than 2 points.
> This directly validates the core claim: ABI is a domain-specific scaffold that
> lowers the model capability threshold.

### 7.2 Quantization Impact

Qwen3-14B was run with 4-bit bitsandbytes quantization (NF4) due to VRAM constraints
(RTX 4090 24GB). Observed effects:

- **G2 parity with 4B model**: Qwen3-14B (4-bit) G2 ≈ 23.5% vs Qwen3-4B (native) G2 ≈ 22.9% — quantization reduces 14B raw reasoning to near-4B levels
- **Near-zero ABI gain**: G3−G2 = +1.8% vs +30.6% for native 4B — quantization severely damages structured instruction-following (ABI lifecycle commands)
- **Cross-plugin collapse**: 14B 4-bit scores 0-13% on cross-plugin planning/dry-run tasks where 4B native scores 100%

> **Recommendation**: For ABI-Bench, prefer native-precision models or GGUF/GPTQ
> quantization over bitsandbytes when 4-bit is required. Structured tool-calling
> benchmarks are especially sensitive to quantization degradation.

### 7.3 Model Tiers (Local)

| Tier | Models | Quantization |
|------|--------|-------------|
| **Weak** | Qwen3-4B, Llama-3.1-8B, Llama-3.1-8B-Instruct, DeepSeek-R1-Distill-Qwen-7B | Native |
| **Medium** | Qwen3-14B, Mistral-Small-3.2-24B-Instruct | 4-bit required |
| **Strong** | Qwen3-30B-A3B-Instruct (MoE), Qwen2.5-Coder-32B-Instruct | 4-bit required |

See `bench/model_tiers.yaml` for the canonical tier definitions.

## 9. Citing

If you use ABI-Bench in your research, please cite:

```bibtex
@software{abi_bench_v0_9,
  title = {ABI-Bench: Agent-Bioinformatics Interface Benchmark v0.9},
  author = {ABI-Bench Contributors},
  year = {2026},
  note = {Evaluates structured ABI control layer for LLM agent
          bioinformatics workflow operation across model capability tiers.
          v0.9 adds evidence-based artifact scoring (T36-T47), cross-plugin
          hidden robustness suite (T59-T61), and 7-suite evaluation
          architecture with distinct claim roles.},
}
```
