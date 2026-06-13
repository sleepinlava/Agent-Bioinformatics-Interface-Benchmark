# ABI-Bench v0.1 — Methods

## Benchmark Design

ABI-Bench v0.1 evaluates whether an Agent-Bioinformatics Interface (ABI)
control layer improves LLM agent operation of bioinformatics workflows.
The benchmark compares three conditions under the same model and agent
harness:

| Group | Name                    | Description                                               |
|-------|-------------------------|-----------------------------------------------------------|
| G1    | README + Shell          | Agent uses documentation and shell; no structured ABI     |
| G2    | Plain Tool Calling      | Agent has general tool execution but no lifecycle control |
| G3    | ABI Control Layer       | Full ABI lifecycle: plan, dry_run, inspect, report        |

## Ablation Conditions

| Group | Name                    | Removed Feature          | Primary Impact             |
|-------|-------------------------|--------------------------|----------------------------|
| A1    | ABI-no-provenance       | Provenance artifacts     | Inspection, diagnosis      |
| A3    | ABI-no-diagnostic-hints | Structured error codes   | Fault localization         |
| A4    | ABI-no-permission-model | Confirmation gate        | Execution safety           |

## Agent Execution Modes

ABI-Bench supports two agent execution modes:

### 1. Simulated Mode (default)

The simulated agent produces expected artifacts directly without calling
an LLM. In this mode, all groups (G1/G2/G3) score identically because
the agent does not read or respect group profiles. The simulated mode
is used for **infrastructure validation** and **CI regression testing**.

For ablation experiments (A1/A3/A4), the simulated agent is **group-aware**:
it reads the group profile and deliberately omits or degrades artifacts
to match the expected behavior of each ablation condition:

- **A1 (no-provenance)**: Skips provenance artifact generation entirely;
  generates incomplete diagnostic answers that fail to identify specific
  samples, fields, paths, or resource names.
- **A3 (no-diagnostic-hints)**: Generates vague diagnostic answers lacking
  specific error codes, tool IDs, and field-level detail.
- **A4 (no-permission-model)**: Adds `confirm_execution=true` to tool calls
  and creates a `real_execution_marker` to simulate safety boundary violation.

### 2. OpenCode Mode (`--agent-mode opencode`)

Uses the OpenCode agent harness with a real LLM backend. Requires an
LLM provider API key. See [Provider Configuration](#provider-configuration).

## Provider Configuration

OpenCode mode requires an LLM provider. Configure one of:

```bash
# Option 1: Environment variables (auto-detected by provider SDKs)
ANTHROPIC_API_KEY=sk-ant-...          # Anthropic Claude
OPENAI_API_KEY=sk-...                 # OpenAI
GOOGLE_GENERATIVE_AI_API_KEY=...      # Google Gemini

# Option 2: bench/.env file
cp bench/.env.example bench/.env
# Edit bench/.env with your credentials

# Option 3: ABI_BENCH_* variables (for openai-compatible endpoints)
ABI_BENCH_PROVIDER=deepseek
ABI_BENCH_API_KEY=sk-...
ABI_BENCH_API_BASE=https://api.deepseek.com
```

All API keys are passed as environment variables to the OpenCode server
process and are never written to disk or tracked by git.

```bash
# Run with real LLM agent
ANTHROPIC_API_KEY=sk-ant-... python bench/harness/run_task.py \
  --group G3 --task T03 --agent-mode opencode
```

## Task Suite (v0.1)

Twelve tasks cover the ABI lifecycle across two bioinformatics plugins:

| Task | Type            | Plugin              | Description                       | Score |
|------|-----------------|---------------------|-----------------------------------|-------|
| T01  | Discovery       | both                | List available analysis types     | 5     |
| T02  | Planning        | metagenomic_plasmid | Plan plasmid analysis             | 10    |
| T03  | Dry-run         | metagenomic_plasmid | Dry-run plasmid analysis          | 12    |
| T04  | Inspection      | metagenomic_plasmid | Inspect plasmid dry-run results   | 8     |
| T05  | Diagnosis       | metagenomic_plasmid | Diagnose missing input            | 10    |
| T06  | Diagnosis       | metagenomic_plasmid | Diagnose missing resource         | 10    |
| T07  | Diagnosis       | metagenomic_plasmid | Diagnose tool-not-found           | 8     |
| T08  | Safety          | metagenomic_plasmid | Permission-gated execution        | 10    |
| T09  | Planning        | metatranscriptomics | Plan transcriptomics analysis     | 8     |
| T10  | Dry-run         | metatranscriptomics | Dry-run transcriptomics analysis  | 10    |
| T11  | Inspection      | metatranscriptomics | Inspect transcriptomics dry-run   | 5     |
| T12  | Interpretation  | both                | Interpret standard tables         | 4     |

**Total: 100 points**

### Task Sets

| Set       | Tasks                                    | Use case                           |
|-----------|------------------------------------------|------------------------------------|
| `mvp`     | T01–T03, T05–T06, T08–T10               | Main experiment (G1/G2/G3)         |
| `ablation`| T03–T08                                  | Ablation experiments (A1/A3/A4)    |
| `full`    | T01–T12                                  | Complete v0.1 benchmark            |

## Metrics

### Primary Metrics

- **Total Score**: Sum of per-task scores, normalized to 100
- **Task Success Rate**: Proportion of tasks with score ≥ 70% of max
- **Successful Dry-run Rate**: Proportion of dry-run tasks that complete
- **Diagnostic Accuracy**: Proportion of diagnostic checks passed
- **Unsafe Execution Rate**: Proportion of runs with unauthorized real execution
- **Artifact Completeness**: Proportion of expected artifacts produced
- **Human Intervention Count**: Number of manual interventions per run
- **Median Agent Steps**: Median number of agent actions per task

### Scoring

Each task has a `max_score` and a set of binary checks defined in
`scoring/rubric.yaml`. A task is considered "passed" if it achieves
≥ 70% of its max score. All checks are artifact-based (file existence,
field value, content pattern matching) — no subjective human evaluation.

## Verified Ablation Results

The group-aware simulated agent produces these expected patterns
(validated 2026-06-13). These are infrastructure-validation results, not
evidence for the main G3-vs-G1/G2 benchmark claim.

| Group | Total Score | Task Success | Diag Accuracy | Unsafe Rate | Key Finding |
|-------|------------|-------------|--------------|-------------|-------------|
| G3    | 100.0      | 1.000       | 1.000        | 0.000       | Full ABI capability |
| A1    | 51.72      | 0.167       | 0.400        | 0.000       | Provenance removal → diagnosis collapse |
| A3    | 75.86      | 0.667       | 0.533        | 0.000       | Missing hints → fault localization drop |
| A4    | 89.66      | 0.833       | 1.000        | **0.167**   | Permission model removed → safety violation |

These results validate that the benchmark scoring infrastructure correctly
detects the expected degradations from each ablation condition.

## Statistical Analysis

For each metric, we report:
1. Mean
2. Standard deviation
3. Median
4. 95% bootstrap confidence interval
5. Per-task breakdown

Group comparisons use mean difference with bootstrap confidence intervals.
The primary comparison is G3 vs G1 (ABI vs README+Shell), with secondary
comparisons G3 vs G2 and ablation groups vs G3.

## Claim Support Criteria

ABI-Bench v0.1 supports the main claim that ABI improves agent-operability when:
1. G3 total score ≥ 80
2. G3 - G1 total score ≥ 20 points
3. G3 - G2 total score ≥ 12 points
4. G3 diagnostic accuracy ≥ 0.75
5. G3 unsafe execution rate = 0
6. G3 completes successful dry-runs on both plugins

## Fixed Variables

- Agent harness: OpenCode
- LLM: same version for all groups
- Temperature: 0 (or lowest available)
- Max agent steps: 50
- Timeout: 20 minutes per task
- Network: off (v0.1)
- Real execution: off (v0.1, except safety violation tests)
- Workspace: isolated per task/group/replicate

## Reproducibility

All benchmark runs are:
1. Isolated to workspace directories (`bench/workspaces/{group}/{task}/replicate_{n}/`)
2. Reset from fixed fixtures before each task
3. Scored automatically by artifact-based checks (no human judgment)
4. Traced with `agent_trace.jsonl`, `tool_calls.jsonl`, `commands.log`, `final_answer.md`
5. Versioned with a fixed benchmark commit
6. Provider-agnostic: any LLM can be swapped via env vars

## Quick Start

```bash
# Infrastructure test (simulated, no API key needed)
python bench/harness/run_group.py --group G3 --tasks mvp --replicates 1

# Ablation experiment (simulated, group-aware)
python bench/harness/run_group.py --group A1 --tasks ablation --replicates 1

# Real LLM agent (requires API key)
ANTHROPIC_API_KEY=sk-ant-... python bench/harness/run_group.py \
  --group G3 --tasks mvp --replicates 3 --agent-mode opencode

# Aggregate results
python bench/scoring/aggregate_scores.py \
  --results bench/results \
  --output bench/results/leaderboard.tsv \
  --summary bench/results/summary.json

# Generate paper tables
python bench/scoring/make_tables.py \
  --results bench/results \
  --outdir docs/experiments/abi_bench_v0_1
```
