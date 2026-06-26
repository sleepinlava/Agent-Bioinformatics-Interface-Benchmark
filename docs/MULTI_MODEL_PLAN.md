# Multi-Model Data Collection Plan

> Paper target: 2 Strong + 2 Medium + 2 Weak = 6 models
> Minimum viable: 1 Strong + 1 Medium + 1 Weak = 3 models

## Status

| Model | Tier | Status | Task Set | Replicates | Est. Cost |
|---|---|---|---|---|---|
| mimo-v2.5-pro | Strong | ✅ Done | causal_core_v0_8 (24) | 5 | — |
| deepseek-v4-pro | Strong | ⬜ To run | causal_core_v0_8 (24) | 5 | ~$30-50 |
| gpt-4o-mini | Medium | ⬜ To run | mvp (8) | 5 | ~$10-15 |
| qwen3-14b | Medium | ⬜ To run | mvp (8) | 5 | ~$5-10 |
| qwen3-4b | Weak | ⬜ To run | mvp (8) | 5 | ~$2-5 |
| llama-3.1-8b | Weak | ⬜ To run (local) | mvp (8) | 5 | $0 |

## Quick Start

### Step 1: Configure API keys

Edit `bench/.env` with the appropriate provider before each model run:

```bash
# For DeepSeek:
export ABI_BENCH_PROVIDER=deepseek
export ABI_BENCH_API_KEY=sk-...
export ABI_BENCH_API_BASE=https://api.deepseek.com
export ABI_BENCH_MODEL=deepseek-v4-pro

# For Qwen (DashScope):
export ABI_BENCH_PROVIDER=openai-compatible
export ABI_BENCH_API_KEY=sk-...
export ABI_BENCH_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
export ABI_BENCH_MODEL=qwen3-14b

# For local Ollama models:
export ABI_BENCH_PROVIDER=openai-compatible
export ABI_BENCH_API_KEY=ollama
export ABI_BENCH_API_BASE=http://localhost:11434/v1
export ABI_BENCH_MODEL=qwen3:4b
```

### Step 2: Run

```bash
# Strong model (full 24 tasks, ~4-8 hrs):
bash run_paper_models.sh deepseek-v4-pro

# Medium model (MVP 8 tasks, ~2-4 hrs):
bash run_paper_models.sh qwen3-14b

# Weak model (MVP 8 tasks, ~2-6 hrs):
bash run_paper_models.sh qwen3-4b
```

### Step 3: Aggregate across models

```bash
python bench/scoring/aggregate_scores.py \
  --results bench/results/ \
  --experiment-set paper_v1 --fixture-set public \
  --output bench/results/paper_all_models_leaderboard.tsv \
  --summary bench/results/paper_all_models_summary.json

python bench/scoring/compute_statistics.py \
  --results bench/results/ \
  --experiment-set paper_v1 --fixture-set public \
  --suite causal_core_v0_8 \
  --output bench/results/paper_all_models_statistics.json
```

### Step 4: Ablation on weak model

```bash
bash run_ablation.sh qwen3-4b
```

## Statistical Power

Based on MiMo-v2.5-Pro pilot data (δ=12.84, SD=8.2):

| n replicates | Power (δ≥5) | CI half-width |
|---|---|---|
| 5 (current MiMo) | 57% | ±7.2 pts |
| 15 (paper target, across models) | 96% | ±4.1 pts |

For the paper, n=15 across 3 models (5 reps each) provides 96% power.
If only 5 reps per model, report achieved power honestly (57%).

## MVP Task Set (8 tasks)

These tasks cover the modules where ABI shows the strongest effect:

| Task | Module | Plugin | Description |
|---|---|---|---|
| T01 | Discovery | cross-plugin | List available analysis types |
| T02 | Planning | metagenomic_plasmid | Build execution plan |
| T03 | Dry-run | metagenomic_plasmid | Validate plan without execution |
| T05 | Diagnosis | metagenomic_plasmid | Diagnose missing input |
| T06 | Diagnosis | metagenomic_plasmid | Diagnose multiple faults |
| T08 | Safety | metagenomic_plasmid | Respect execution boundary |
| T09 | Planning | amplicon_16s | Plan cross-plugin |
| T10 | Dry-run | amplicon_16s | Dry-run cross-plugin |

## Contingency Plans

- If API budget is exhausted: reduce to 3 reps per model (still reportable)
- If weak model fails completely on G1/G2: document as evidence for ABI necessity
- If ablation is inconclusive on weak model: downgrade to Appendix with "CoT compensation" interpretation
