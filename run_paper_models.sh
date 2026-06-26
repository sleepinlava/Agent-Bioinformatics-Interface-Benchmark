#!/bin/bash
# ABI-Bench Paper — Multi-Model Data Collection Script
# =============================================================================
# Runs the benchmark across multiple LLM tiers (Strong/Medium/Weak) to support
# the scaffolding hypothesis and cross-model generalizability claims.
#
# Prerequisites:
#   1. ABI installed: pip install abi
#   2. Python deps: pip install pyyaml openai scipy
#   3. Scoring rules frozen: git checkout scoring-v1.0-frozen
#   4. Each model configured in bench/.env (see MODELS section below)
#
# Usage:
#   bash run_paper_models.sh <model_short_name>
#
# Examples:
#   bash run_paper_models.sh deepseek-v4-pro     # Full 24-task, 5 reps
#   bash run_paper_models.sh qwen3-14b           # MVP 8-task, 5 reps
#   bash run_paper_models.sh gpt-4o-mini         # MVP 8-task, 5 reps
#   bash run_paper_models.sh qwen3-4b            # MVP 8-task, 5 reps
#   bash run_paper_models.sh llama-3.1-8b        # MVP 8-task, 5 reps
#
# Task sets:
#   mvp (8 tasks) — Medium/Weak models
#     T01 (discovery), T02 (planning), T03 (dry-run plasmid),
#     T05 (diagnosis), T06 (diagnosis multi), T08 (safety),
#     T09 (planning amplicon), T10 (dry-run amplicon)
#
#   causal_core_v0_8 (24 tasks) — Strong models (full primary causal suite)
#     T01-T19, T48-T50
#
# Replicates: 5 per model/group/task (paper target: 15 after aggregation)
#   - 5 replicates × [4 groups (G1-G4) or 3 groups (MVP)] × [8 or 24 tasks]
#   - Strong full: 5 × 4 × 24 = 480 runs (est. 4-8 hrs with --workers 4)
#   - Medium MVP:  5 × 4 × 8  = 160 runs (est. 2-4 hrs with --workers 4)
#   - Weak MVP:    5 × 4 × 8  = 160 runs (est. 2-6 hrs with --workers 4)
#
# =============================================================================

set -euo pipefail

MODEL="${1:?Usage: $0 <model_short_name>}"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BENCH_DIR="$PROJECT_ROOT/bench"

# ── Model Configuration Database ──────────────────────────────────────────
# Each model maps to provider, API config, and task set.
# Edit these before running.

declare -A MODEL_PROVIDER
declare -A MODEL_API_BASE
declare -A MODEL_TIER
declare -A TASK_SET
declare -A NEEDS_REASONING

# === Strong Tier (full 24-task, 5 reps, 4 groups) ===

MODEL_PROVIDER["deepseek-v4-pro"]="deepseek"
MODEL_API_BASE["deepseek-v4-pro"]="https://api.deepseek.com"
MODEL_TIER["deepseek-v4-pro"]="strong"
TASK_SET["deepseek-v4-pro"]="causal_core_v0_8"
NEEDS_REASONING["deepseek-v4-pro"]="false"

MODEL_PROVIDER["gpt-4o"]="openai"
MODEL_API_BASE["gpt-4o"]="https://api.openai.com/v1"
MODEL_TIER["gpt-4o"]="strong"
TASK_SET["gpt-4o"]="causal_core_v0_8"
NEEDS_REASONING["gpt-4o"]="false"

MODEL_PROVIDER["claude-sonnet-4-6"]="anthropic"
MODEL_API_BASE["claude-sonnet-4-6"]=""
MODEL_TIER["claude-sonnet-4-6"]="strong"
TASK_SET["claude-sonnet-4-6"]="causal_core_v0_8"
NEEDS_REASONING["claude-sonnet-4-6"]="true"

MODEL_PROVIDER["mimo-v2.5-pro"]="mimo"
MODEL_API_BASE["mimo-v2.5-pro"]="https://token-plan-sgp.xiaomimimo.com/v1"
MODEL_TIER["mimo-v2.5-pro"]="strong"
TASK_SET["mimo-v2.5-pro"]="causal_core_v0_8"
NEEDS_REASONING["mimo-v2.5-pro"]="true"

# === Medium Tier (MVP 8-task, 5 reps, 4 groups) ===

MODEL_PROVIDER["qwen3-14b"]="openai-compatible"
MODEL_API_BASE["qwen3-14b"]="https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_TIER["qwen3-14b"]="medium"
TASK_SET["qwen3-14b"]="mvp"
NEEDS_REASONING["qwen3-14b"]="true"

MODEL_PROVIDER["gpt-4o-mini"]="openai"
MODEL_API_BASE["gpt-4o-mini"]="https://api.openai.com/v1"
MODEL_TIER["gpt-4o-mini"]="medium"
TASK_SET["gpt-4o-mini"]="mvp"
NEEDS_REASONING["gpt-4o-mini"]="false"

MODEL_PROVIDER["mistral-small-3.2-24b"]="openai-compatible"
MODEL_API_BASE["mistral-small-3.2-24b"]="https://api.mistral.ai/v1"
MODEL_TIER["mistral-small-3.2-24b"]="medium"
TASK_SET["mistral-small-3.2-24b"]="mvp"
NEEDS_REASONING["mistral-small-3.2-24b"]="false"

# === Weak Tier (MVP 8-task, 5 reps, 4 groups) ===

MODEL_PROVIDER["qwen3-4b"]="openai-compatible"
MODEL_API_BASE["qwen3-4b"]="https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL_TIER["qwen3-4b"]="weak"
TASK_SET["qwen3-4b"]="mvp"
NEEDS_REASONING["qwen3-4b"]="false"

MODEL_PROVIDER["llama-3.1-8b"]="openai-compatible"
MODEL_API_BASE["llama-3.1-8b"]="http://localhost:11434/v1"
MODEL_TIER["llama-3.1-8b"]="weak"
TASK_SET["llama-3.1-8b"]="mvp"
NEEDS_REASONING["llama-3.1-8b"]="false"

MODEL_PROVIDER["qwen2.5-7b"]="openai-compatible"
MODEL_API_BASE["qwen2.5-7b"]="http://localhost:11434/v1"
MODEL_TIER["qwen2.5-7b"]="weak"
TASK_SET["qwen2.5-7b"]="mvp"
NEEDS_REASONING["qwen2.5-7b"]="false"

# ── Validate model ───────────────────────────────────────────────────────

if [ -z "${MODEL_PROVIDER[$MODEL]:-}" ]; then
    echo "ERROR: Unknown model '$MODEL'"
    echo "Available models:"
    printf "  %s\n" "${!MODEL_PROVIDER[@]}" | sort
    exit 1
fi

PROVIDER="${MODEL_PROVIDER[$MODEL]}"
API_BASE="${MODEL_API_BASE[$MODEL]}"
TIER="${MODEL_TIER[$MODEL]}"
TASKS="${TASK_SET[$MODEL]}"
REASONING="${NEEDS_REASONING[$MODEL]}"

# ═════════════════════════════════════════════════════════════════════════
# Configuration
# ═════════════════════════════════════════════════════════════════════════

EXPERIMENT_SET="paper_v1"
FIXTURE_SET="public"
AGENT_MODE="direct"
REPLICATES=5
WORKERS=4
SEED=42

OUTDIR="$PROJECT_ROOT/bench/results/$MODEL"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ABI-Bench Paper — Multi-Model Collection                  ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Model:      $MODEL"
echo "║  Provider:   $PROVIDER"
echo "║  Tier:       $TIER"
echo "║  Task set:   $TASKS"
echo "║  Replicates: $REPLICATES"
echo "║  Groups:     G1 G2 G3 G4"
echo "║  Workers:    $WORKERS"
echo "║  Outdir:     $OUTDIR"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ── Export environment ───────────────────────────────────────────────────

export ABI_BENCH_PROVIDER="$PROVIDER"
export ABI_BENCH_MODEL="$MODEL"
export ABI_BENCH_API_BASE="$API_BASE"
export ABI_BENCH_MAX_TOKENS=8000
export ABI_BENCH_TEMPERATURE=0.0
export ABI_BENCH_MAX_RETRIES=5
export ABI_BENCH_RETRY_BASE_DELAY=10.0
export ABI_BENCH_RETRY_MAX_DELAY=120.0

if [ "$REASONING" = "true" ]; then
    export ABI_BENCH_REASONING=true
    export ABI_BENCH_THINKING_BUDGET=5000
    export ABI_BENCH_REASONING_EFFORT=high
fi

# NOTE: Set your API key before running:
#   export ABI_BENCH_API_KEY="sk-..."

# ── Preflight check ──────────────────────────────────────────────────────

echo "🔍 Preflight: validating scoring rules..."
cd "$PROJECT_ROOT"
python bench/harness/run_task.py \
    --group G3 --task T03 --replicate 1 \
    --agent-mode simulated \
    --experiment-set "$EXPERIMENT_SET" --fixture-set "$FIXTURE_SET" \
    --outdir "$OUTDIR/_preflight/G3/T03/replicate_01" 2>&1 | tail -1

echo ""

# ── Run groups sequentially (randomized-block design) ────────────────────

# Generate randomized group order
GROUP_ORDER="G1 G2 G3 G4"
GROUPS_ARR=($GROUP_ORDER)
# Fisher-Yates shuffle with fixed seed for reproducibility
for ((i=${#GROUPS_ARR[@]}-1; i>0; i--)); do
    j=$(( RANDOM % (i+1) ))
    tmp="${GROUPS_ARR[$i]}"
    GROUPS_ARR[$i]="${GROUPS_ARR[$j]}"
    GROUPS_ARR[$j]="$tmp"
done

echo "📋 Group order (randomized, seed=$SEED): ${GROUPS_ARR[@]}"
echo ""

TOTAL_GROUPS=${#GROUPS_ARR[@]}
RUN_NUMBER=0

for GROUP in "${GROUPS_ARR[@]}"; do
    RUN_NUMBER=$((RUN_NUMBER + 1))
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "[$RUN_NUMBER/$TOTAL_GROUPS] MODEL=$MODEL GROUP=$GROUP START"
    echo "═══════════════════════════════════════════════════════════════"

    python bench/harness/run_group.py \
        --group "$GROUP" \
        --tasks "$TASKS" \
        --replicates "$REPLICATES" \
        --model "$MODEL" \
        --agent-mode "$AGENT_MODE" \
        --experiment-set "$EXPERIMENT_SET" \
        --fixture-set "$FIXTURE_SET" \
        --parallel \
        --workers "$WORKERS" \
        --outdir "$OUTDIR/$GROUP"

    echo ""
    echo "✓ GROUP=$GROUP finished ($(date +%H:%M:%S))"
done

# ── Aggregate & Score ────────────────────────────────────────────────────

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "Aggregating scores for $MODEL..."
echo "═══════════════════════════════════════════════════════════════"

python bench/scoring/aggregate_scores.py \
    --results "$OUTDIR" \
    --experiment-set "$EXPERIMENT_SET" --fixture-set "$FIXTURE_SET" \
    --output "$OUTDIR/leaderboard.tsv" \
    --summary "$OUTDIR/summary.json" \
    --per-task "$OUTDIR/per_task_scores.tsv"

python bench/scoring/claim_preflight.py \
    --results "$OUTDIR" \
    --experiment-set "$EXPERIMENT_SET" --fixture-set "$FIXTURE_SET" \
    --min-replicates 3 \
    --output "$OUTDIR/preflight.json"

python bench/scoring/compute_statistics.py \
    --results "$OUTDIR" \
    --experiment-set "$EXPERIMENT_SET" --fixture-set "$FIXTURE_SET" \
    --suite causal_core_v0_8 \
    --output "$OUTDIR/statistics.json"

# ── Print summary ────────────────────────────────────────────────────────

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Results: $MODEL ($TIER)                                  ║"
echo "╚══════════════════════════════════════════════════════════════╝"

python -c "
import json, sys
try:
    with open('$OUTDIR/summary.json') as f:
        s = json.load(f)
    for g in ['G1','G2','G3','G4']:
        gd = s.get('groups', {}).get(g, {})
        print(f'  {g}: score={gd.get(\"total_score_mean\",\"N/A\")} success={gd.get(\"task_success_rate\",\"N/A\")}')
    cs = s.get('claim_statistics', {})
    print(f'  G3-G1 delta: {cs.get(\"G3_vs_G1_delta\", \"N/A\")}')
    print(f'  Claim supported: {cs.get(\"primary_claim_all\", \"N/A\")}')
except Exception as e:
    print(f'  (summary not yet available: {e})')
"

echo ""
echo "✓ $MODEL collection complete."
echo "  Results: $OUTDIR/"
echo ""
