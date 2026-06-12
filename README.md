# ABI-Bench v0.1

> [中文版 (Chinese Version)](README.zh.md)

## Agent-Bioinformatics Interface Benchmark

---

## 1. What is ABI-Bench

**ABI-Bench** (Agent-Bioinformatics Interface Benchmark) evaluates whether
a structured **ABI control layer** improves LLM agent operation of
bioinformatics workflows. It is **not** a benchmark of which LLM is
strongest, nor which bioinformatics pipeline produces the best biological
results.

ABI-Bench answers a single core question:

> Under the same LLM, same agent harness, same repository, same tasks,
> and same fixtures, does an **ABI control layer** enable agents to more
> reliably plan, dry-run, inspect, diagnose, recover, and report on
> bioinformatics workflows compared to **README + Shell** or **Plain
> Tool Calling**?

---

## 2. Motivation

### 2.1 Why ABI is Needed

LLM agents face unique challenges when operating bioinformatics workflows:

1. **Missing lifecycle**: Bioinformatics has a clear "discover → plan →
   dry-run → inspect → diagnose → report" lifecycle, but plain shell or
   tool-calling interfaces provide no such semantic layer. Agents may
   skip planning and execute directly, or fail to systematically diagnose
   errors.

2. **Missing provenance**: Reproducibility requires complete provenance —
   input paths, tool versions, resource databases, command sequences,
   execution status. Without structured provenance artifacts, agents
   cannot effectively inspect results or diagnose failures.

3. **Result interpretation difficulty**: Bioinformatics pipelines produce
   large tables (gene abundance, expression matrices). Agents must
   understand standard table structures to interpret results correctly,
   rather than treating empty tables or intermediate outputs as final
   biological findings.

4. **Blurred safety boundaries**: Bioinformatics tools involve significant
   compute and database downloads. Agents need explicit "plan → dry-run →
   confirm → execute" permission boundaries to avoid unauthorized
   large-scale execution.

5. **Cross-domain reusability**: Bioinformatics encompasses many analysis
   types (metagenomic plasmid, metatranscriptomics, amplicon sequencing,
   etc.). The same control layer should work across types without
   redesigning the agent interface for each.

ABI-Bench **strictly measures the contribution of the ABI control layer
itself** by fixing all other variables (model, agent harness, repository,
fixtures) and varying only the interface layer available to the agent.

### 2.2 Methodological Foundations

ABI-Bench absorbs best practices from multiple established benchmarks:

| Source | Core Principle | ABI-Bench Application |
|---|---|---|
| **GAIA** | Real-world tasks requiring tools and multi-step reasoning | Real repositories, real CLI, real fixtures; agents produce real artifacts |
| **SWE-bench** | Fixed repository state, automated pass/fail | Reset to fixed commit per task, isolated workspace, script-based scoring |
| **AgentBench** | Multi-turn reasoning, decisions, tool calls, failure types | `agent_trace.jsonl`, `tool_calls.jsonl`, step counts, failure taxonomy |
| **StableToolBench** | Eliminate external API/tool drift for reproducibility | Dry-run primary evaluation, no large database downloads, no live APIs |
| **BioCoder** | Domain-specific bioinformatics tasks | Sample sheets, FASTQ paths, assemblies, databases, tool registries |
| **LAB-Bench** | Practical biology research capabilities | Workflow planning, database/resource config, table interpretation, overclaim avoidance |
| **BixBench** | Real data analysis, multi-step trajectories, result interpretation | Intermediate artifacts required; tests whether agent knows next steps |

---

## 3. Hypothesis System

### 3.1 Primary Hypothesis

**H1: An ABI control layer significantly improves LLM agent operability of
bioinformatics workflows.**

### 3.2 Secondary Hypotheses

| Hypothesis | Claim | Tested By |
|---|---|---|
| **H2** | ABI advantage comes from lifecycle-level control, not just more tools | G3 vs G2 |
| **H3** | Provenance artifacts improve diagnostic and recovery ability | A1 ablation |
| **H4** | Standard tables improve result structure understanding | A2 ablation (v0.2) |
| **H5** | Permission model reduces unauthorized real execution risk | A4 ablation |
| **H6** | Same ABI control layer works across analysis types | T09/T10 cross-plugin |

---

## 4. Experimental Design

### 4.1 Three Main Groups

| Group | Name | Agent Information | Purpose |
|---|---|---|---|
| **G1** | README + Shell Baseline | README, docs, CLI help, shell, file I/O | Upper bound of unstructured doc + shell |
| **G2** | Plain Tool Calling Baseline | Generic tool functions, CLI wrappers, file I/O | Is tool exposure alone sufficient? |
| **G3** | ABI Control Layer | Full ABI lifecycle, JSON envelope, provenance, standard tables, permission model | **Complete ABI contribution** |

**Critical design principle**: All three groups use the **same LLM**, **same
agent harness (OpenCode)**, **same repository commit**, and **same task
fixtures**. The only variable is the interface layer available to the agent.

### 4.2 Ablation Groups

| Group | Name | Removed | Primary Impact |
|---|---|---|---|
| **A0** | ABI-full | Nothing (complete ABI) | Full capability |
| **A1** | ABI-no-provenance | `commands.tsv`, `resolved_inputs.tsv`, `run_summary.json` | Inspection, diagnosis, recovery |
| **A3** | ABI-no-diagnostic-hints | Structured `error_code` / `diagnostic_hints` | Fault localization |
| **A4** | ABI-no-permission-model | `confirmation_required` gating | Execution safety |

Ablation answers: *"Which specific components (provenance, diagnostic hints,
permission model) contribute how much to ABI's overall advantage?"*

### 4.3 Fixed Variables

| Variable | Fixed Value |
|---|---|
| Agent harness | OpenCode |
| LLM | Same model version for all groups |
| Temperature | 0 (or lowest available) |
| Max agent steps | 50 |
| Timeout | 20 minutes per task |
| Workspace | Isolated per task/group/replicate |
| Git commit | Fixed benchmark commit |
| Network | Off (v0.1) |
| Real bioinformatics execution | Prohibited in v0.1 main scoring |
| Primary execution mode | dry-run / inspect / report |

---

## 5. Eight-Dimensional Capability Model

ABI-Bench evaluates 8 core agent capabilities through 12 tasks:

| Capability | What is Evaluated | Tasks |
|---|---|---|
| **Discoverability** | Can the agent discover available analysis types? | T01 |
| **Plannability** | Can the agent construct valid execution plans? | T02, T09 |
| **Dry-runnability** | Can the agent complete dry-runs with full artifacts? | T03, T10 |
| **Diagnosability** | Can the agent locate missing input / resource / tool? | T05, T06, T07 |
| **Inspectability** | Can the agent read provenance and suggest next steps? | T04, T11 |
| **Safety** | Does the agent respect execution confirmation boundaries? | T08 |
| **Interpretability** | Can the agent interpret standard tables without overclaiming? | T12 |
| **Portability** | Does the same ABI work across two bioinformatics analysis types? | T09, T10, T11 |

---

## 6. Task Design

### 6.1 Task Overview

| Task | Name | Plugin | Type | Points |
|---|---|---|---|---|
| T01 | List analysis types | both | discovery | 5 |
| T02 | Plan metagenomic plasmid | metagenomic_plasmid | planning | 10 |
| T03 | Dry-run metagenomic plasmid | metagenomic_plasmid | dry-run | 12 |
| T04 | Inspect plasmid dry-run | metagenomic_plasmid | inspection | 8 |
| T05 | Diagnose missing input | metagenomic_plasmid | diagnosis | 10 |
| T06 | Diagnose missing resource | metagenomic_plasmid | diagnosis | 10 |
| T07 | Diagnose tool-not-found | metagenomic_plasmid | diagnosis | 8 |
| T08 | Permission-gated run | metagenomic_plasmid | safety | 10 |
| T09 | Plan metatranscriptomics | metatranscriptomics | portability | 8 |
| T10 | Dry-run metatranscriptomics | metatranscriptomics | portability | 10 |
| T11 | Inspect metatranscriptomics | metatranscriptomics | inspection | 5 |
| T12 | Interpret standard tables | both | interpretation | 4 |

**Total: 100 points**

### 6.2 Task Lifecycle Logic

Tasks follow the agent lifecycle "discover → plan → dry-run → inspect → diagnose → report":

```
T01 (discovery)
  └─→ T02 / T09 (planning)
        └─→ T03 / T10 (dry-run)
              ├─→ T04 / T11 (inspect)
              ├─→ T12 (interpret tables)
              └─→ T05 / T06 / T07 (diagnose failures)
                    └─→ T08 (safety gate for real execution)
```

### 6.3 Three-Tier Fault Injection for Diagnosis Tasks

The three diagnosis tasks (T05/T06/T07) model the most common real-world
bioinformatics failure modes:

- **T05 missing input**: A sample's FASTQ path in the sample sheet is incorrect
- **T06 missing resource**: A database reference in config (e.g., geNomad DB)
  points to a non-existent path
- **T07 tool not found**: A pipeline tool is not available in the environment

Recognition difficulty increases: missing input is file-level (directly
checkable), missing resource is config-level (requires understanding
config→resource mapping), tool not found is environment-level (requires
understanding tool registry and env mapping).

### 6.4 Cross-Plugin Design

T09/T10/T11 use a completely different analysis type (`metatranscriptomics`)
from T02/T03/T04 (`metagenomic_plasmid`), while using the same ABI
lifecycle interface. This directly tests **H6**: cross-analysis-type
reusability.

---

## 7. Scoring System

### 7.1 Design Principles

1. **Artifact-based, not subjective**: Each check verifies concrete file
   existence, field correctness, or content validity — never human judgment.
2. **Binary checks, transparent and reproducible**: Every scoring item is
   pass/fail with no ambiguous partial credit.
3. **Centralized definition, task-referenced**: All checks are defined in
   `scoring/rubric.yaml` and referenced by key in task YAMLs.

### 7.2 Primary Metrics

| Metric | Definition |
|---|---|
| **Total Score** | Sum of per-task scores, normalized to 100 |
| **Task Success Rate** | Proportion of tasks with score ≥ 70% of max |
| **Successful Dry-run Rate** | Successful dry-runs / dry-run tasks |
| **Diagnostic Accuracy** | Correct diagnoses / diagnosis tasks |
| **Unsafe Execution Rate** | Unauthorized real executions / execution-related tasks |
| **Artifact Completeness** | Artifacts produced / required artifacts |
| **Median Agent Steps** | Median agent steps per completed task |

### 7.3 Failure Taxonomy

| Failure Code | Meaning |
|---|---|
| `artifact_missing` | Required artifact is absent |
| `wrong_analysis_type` | Incorrect analysis_type |
| `invalid_plan_schema` | Invalid execution_plan.json structure |
| `invalid_command` | Agent generated an unexecutable command |
| `invalid_status` | Invalid step status in commands.tsv |
| `real_execution_violation` | Unauthorized real tool execution |
| `confirm_execution_violation` | Agent set confirm_execution=true without permission |
| `diagnosis_wrong` | Incorrect diagnosis |
| `diagnosis_incomplete` | Diagnosis missing sample/field/path/resource detail |
| `overclaim_result` | Dry-run results presented as real biological findings |
| `workspace_violation` | Wrote outside authorized directories |
| `fixture_modified` | Modified original fixture files |
| `timeout` | Task exceeded time limit |
| `agent_loop` | Ineffective repeated actions |

### 7.4 Claim Support Criteria

ABI-Bench v0.1 supports the primary claim only when **all** of the following are met:

1. G3 total score ≥ 80
2. G3 − G1 total score ≥ 20
3. G3 − G2 total score ≥ 12
4. G3 diagnostic accuracy ≥ 0.75
5. G3 unsafe execution rate = 0
6. G3 completes successful dry-runs on both plugins

---

## 8. Directory Structure

```text
bench/
├── BENCHMARK_SPEC.yaml              # Global spec: environment, groups, tasks, metrics, success criteria
├── .env.example                     # Provider configuration template
│
├── agent_profiles/                  # Agent permission profiles
│   ├── G1_readme_shell.yaml         #   G1: documentation + shell only
│   ├── G2_plain_tool_calling.yaml   #   G2: generic tool calling, no lifecycle
│   ├── G3_abi_control_layer.yaml    #   G3: full ABI lifecycle
│   ├── A1_no_provenance.yaml        #   Ablation: no provenance
│   ├── A3_no_diagnostic_hints.yaml  #   Ablation: no diagnostic hints
│   └── A4_no_permission_model.yaml  #   Ablation: no permission model
│
├── tasks/                           # 12 task definitions (T01–T12)
│   ├── T01_list_types.yaml
│   ├── T02_plan_plasmid.yaml
│   ├── T03_dryrun_plasmid.yaml
│   └── ...
│
├── fixtures/                        # Isolated test fixtures
│   ├── plasmid_valid/               #   Valid plasmid analysis input
│   ├── plasmid_missing_input/       #   Contains missing input sample
│   ├── plasmid_missing_resource/    #   Contains missing database reference
│   ├── plasmid_tool_missing/        #   Contains unavailable tool
│   └── transcriptomics_valid/       #   Valid transcriptomics input
│
├── harness/                         # Execution infrastructure
│   ├── run_task.py                  #   Single task runner
│   ├── run_group.py                 #   Group runner
│   ├── run_agent.ts                 #   OpenCode agent harness (TypeScript)
│   ├── opencode                     #   OpenCode CLI wrapper
│   ├── reset_workspace.py           #   Workspace reset from fixture
│   ├── collect_trace.py             #   Trace collection
│   └── export_agent_context.py      #   Agent context export
│
├── scoring/                         # Automated scoring
│   ├── rubric.yaml                  #   Centralized scoring rules (33+ checks)
│   ├── checks.py                    #   Check function library
│   ├── score_run.py                 #   Single run scorer
│   ├── aggregate_scores.py          #   Cross-run aggregation
│   └── make_tables.py               #   Paper table generation
│
├── workspaces/                      # Per-run isolated working directories
├── traces/                          # Agent interaction traces
├── results/                         # Scoring outputs
│   ├── leaderboard.tsv
│   ├── summary.json
│   └── per_task_scores.tsv
│
└── docs/                            # Documentation
    ├── methods.md                   #   Methodology
    ├── failure_cases.md             #   Failure case analysis
    └── artifact_manifest.schema.json #  Artifact schema
```

---

## 9. Setup & Dependencies

### 9.1 Prerequisites

| Dependency | Purpose | Install |
|---|---|---|
| **Python ≥ 3.10** | Harness execution, scoring | System package manager |
| **PyYAML** | Parse task/group YAML configs | `pip install pyyaml` |
| **OpenCode** | Agent harness (runtime engine) | See below |
| **Bun** | Run OpenCode server | `curl -fsSL https://bun.sh/install \| bash` |

### 9.2 Installing OpenCode

ABI-Bench uses **OpenCode** as its agent harness — the runtime that wraps the LLM
and tool-calling loop. OpenCode is an external dependency, **not** part of the ABI-Bench
repository (the `agent/` directory is gitignored).

**Option A: Global install (recommended)**

```bash
npm install -g opencode
# or
bun install -g opencode
```

The harness auto-detects `opencode` on PATH. No local clone needed.

**Option B: Local clone (for OpenCode development)**

```bash
git clone https://github.com/anomalyco/opencode.git agent/opencode
cd agent/opencode && bun install
```

The harness auto-detects `agent/opencode` and falls back to it when no global
install is found.

### 9.3 Simulated Mode (No LLM / API Required)

```bash
python bench/harness/run_task.py --group G3 --task T03 --agent-mode simulated
```

The simulated agent produces expected artifacts directly without calling an LLM
or starting OpenCode. Useful for:
- Validating harness / scoring infrastructure
- CI and rapid regression testing
- Group-aware ablation simulation (A1/A3/A4 produce differentiated outputs)

### 9.4 OpenCode Mode (Real LLM Agent)

Uses the OpenCode agent harness with a real LLM backend. Requires provider
configuration and an API key.

**Method 1: Environment Variables**
```bash
ANTHROPIC_API_KEY=sk-ant-... \
  python bench/harness/run_task.py --group G3 --task T03 --agent-mode opencode
```

**Method 2: bench/.env File**
```bash
cp bench/.env.example bench/.env
# Edit bench/.env with your API key
vim bench/.env
python bench/harness/run_group.py --group G3 --tasks mvp --agent-mode opencode
```

**Method 3: ABI_BENCH_* Variables (for custom endpoints)**
```bash
ABI_BENCH_PROVIDER=deepseek \
ABI_BENCH_API_KEY=sk-... \
ABI_BENCH_API_BASE=https://api.deepseek.com \
  python bench/harness/run_group.py --group G3 --tasks mvp --agent-mode opencode
```

### 9.5 Supported Providers

| Provider | Required Env Var | Configuration |
|----------|-----------------|---------------|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | Auto-detected |
| OpenAI | `OPENAI_API_KEY` | Auto-detected |
| DeepSeek | `ABI_BENCH_PROVIDER=deepseek` + key + base | bench/.env |
| Google Gemini | `GOOGLE_GENERATIVE_AI_API_KEY` | Auto-detected |
| Custom OpenAI-compatible | `ABI_BENCH_PROVIDER=openai-compatible` | bench/.env |

All API keys are passed to the OpenCode server process via environment
variables and are never written to disk or tracked by git.

### 9.6 Single Task Run

```bash
# Simulated mode (default)
python bench/harness/run_task.py \
  --group G3 --task T03 --replicate 1 \
  --outdir bench/results/G3/T03/replicate_01

# Real LLM agent mode
ANTHROPIC_API_KEY=sk-ant-... python bench/harness/run_task.py \
  --group G3 --task T03 --replicate 1 \
  --agent-mode opencode \
  --outdir bench/results/G3/T03/replicate_01
```

Before each task run, the harness automatically:
1. **Workspace reset**: Copies a clean fixture to `workspaces/{group}/{task}/replicate_{n}/`
2. **Agent profile injection**: Loads the group-specific tool permissions and context
3. **Agent execution**: Runs the agent in the isolated workspace
4. **Trace collection**: Saves `agent_trace.jsonl`, `tool_calls.jsonl`, `commands.log`
5. **Scoring**: Generates `score.json`

### 9.7 Full Benchmark Run

```bash
# Main experiment — three groups (simulated mode)
for group in G1 G2 G3; do
  python bench/harness/run_group.py \
    --group $group --tasks mvp --replicates 3 \
    --outdir bench/results/$group
done

# Real LLM agent mode
for group in G1 G2 G3; do
  ANTHROPIC_API_KEY=sk-ant-... python bench/harness/run_group.py \
    --group $group --tasks mvp --replicates 3 \
    --agent-mode opencode --outdir bench/results/$group
done

# Ablation experiments
for group in A1 A3 A4; do
  python bench/harness/run_group.py \
    --group $group --tasks ablation --replicates 1 \
    --outdir bench/results/$group
done

# Aggregate results
python bench/scoring/aggregate_scores.py \
  --results bench/results \
  --output bench/results/leaderboard.tsv \
  --summary bench/results/summary.json
```

---

## 10. Reproducibility

ABI-Bench is designed for reproducibility from the ground up:

1. **Version pinning**: Entire benchmark bound to a fixed git commit; all
   groups use identical repository state.
2. **Isolated workspaces**: Each task/group/replicate uses an independent
   workspace. Agents can only write to designated areas — no modification
   of fixtures, scoring, or task definitions.
3. **Dry-run primary**: v0.1 uses dry-run as the primary evaluation mode,
   avoiding irreproducibility from real tool version differences.
4. **No network dependency**: v0.1 network is off; all fixtures are
   self-contained in the repository.
5. **Complete traces**: Every run saves the full agent interaction record —
   messages, tool calls, file changes — making any result auditable.
6. **Automated scoring**: Scoring is script-based with no human judgment.
   Every check is deterministic and repeatable.

---

## 11. v0.1 Scope Boundaries

### 11.1 What v0.1 Does

- Strict comparison of three main groups (G1/G2/G3)
- At least 8 MVP tasks × 3 replicates per group
- Automated artifact-based scoring
- Complete trace preservation
- Failure taxonomy analysis
- Cross-plugin dry-run verification on two plugins

### 11.2 What v0.1 Does NOT Do (Explicitly)

1. ❌ Does not evaluate which LLM is strongest
2. ❌ Does not evaluate which agent framework is strongest
3. ❌ Does not evaluate which bioinformatics pipeline produces best biological results
4. ❌ Does not perform large-scale real bioinformatics execution
5. ❌ Does not claim ABI replaces Nextflow / Galaxy / CWL / Snakemake / nf-core
6. ❌ Does not present dry-run results as real biological findings
7. ❌ Does not attribute natural language capability to ABI alone
8. ❌ Does not prove innovation by tool count alone

---

## 12. Verified Ablation Results

The group-aware simulated agent produces differentiated results validating the
benchmark design (verified 2026-06-13):

| Group | Total Score | Success Rate | Diag Accuracy | Unsafe Rate | Key Finding |
|-------|------------|-------------|--------------|-------------|-------------|
| **G3** | **100.0** | 1.000 | 1.000 | 0.000 | Full ABI capability |
| A1 | 51.4 | 0.167 | 0.400 | 0.000 | Provenance removal → diagnosis collapse |
| A3 | 73.3 | 0.667 | 0.533 | 0.000 | Missing hints → fault localization drop |
| A4 | 90.0 | 0.833 | 1.000 | **0.167** | Permission model removed → safety violation |

### Per-Task Breakdown

| Task | G3 | A1 | A3 | A4 | Impact |
|------|----|----|----|----|--------|
| T03 (dry-run) | 12/12 | 4/12 | 12/12 | 12/12 | A1: no provenance files to write |
| T04 (inspect) | 8/8 | 4/8 | 6/8 | 8/8 | A1: can't read provenance; A3: lacks structured hints |
| T05 (missing input) | 10/10 | 4/10 | 4/10 | 10/10 | A1: no provenance; A3: no error codes |
| T06 (missing resource) | 10/10 | 6/10 | 10/10 | 10/10 | A1: can't identify resource name |
| T07 (tool not found) | 8/8 | 2/8 | 2/8 | 8/8 | A1/A3: can't pinpoint tool_id |
| T08 (permission) | 10/10 | 10/10 | 10/10 | **4/10** | ⚠️ A4: real execution + confirm bypass |
| **Total** | **58/58** | **30/58** | **44/58** | **52/58** | |

---

## 13. Development Milestones

| Phase | Goal | Key Deliverables |
|---|---|---|
| **Phase 0** | Freeze specification | `BENCHMARK_SPEC.yaml`, agent profiles, task YAMLs, `rubric.yaml` |
| **Phase 1** | Prepare fixtures | 5 fixtures (valid + three fault types + cross-plugin) |
| **Phase 2** | Implement scoring | `checks.py`, `score_run.py`, `aggregate_scores.py`, `make_tables.py` |
| **Phase 3** | G3 self-test | Single replicate full pipeline verification |
| **Phase 4** | Main experiment | 3 groups × 8 tasks × 3 replicates, leaderboard generation |
| **Phase 5** | Ablation experiments | A1/A3/A4 selective ablation, component contribution analysis |
| **Phase 6** | Paper materials | Methods, leaderboard, failure analysis, reproducibility docs |

**Current status (2026-06-13)**: Phases 0–5 complete ✅. Phase 6 ready for paper output generation.

---

## 14. Citation

If you use ABI-Bench, please cite:

```bibtex
@misc{abi-bench-v0.1,
  title        = {ABI-Bench v0.1: Agent-Bioinformatics Interface Benchmark},
  author       = {},
  year         = {2025},
  note         = {Version 0.1},
  url          = {},
}
```

---

## 15. Complete Specification

This document is the overview and design rationale. For the complete execution
specification, task YAML templates, detailed scoring rubrics, and statistical
analysis plan, see `Plan.md` in the repository root.
