#!/bin/bash
# ABI-Bench Paper — Component Ablation Experiments
# =============================================================================
# Runs A1/A3/A4 ablation groups to measure the contribution of individual
# ABI components (provenance, diagnostic hints, permission model).
#
# The ablation is most informative on weak models where chain-of-thought
# compensation is less likely to mask the component effect.
#
# Usage:
#   bash run_ablation.sh <model_short_name>
#
# Example:
#   bash run_ablation.sh qwen3-4b      # Weak model — primary ablation target
#   bash run_ablation.sh mimo-v2.5-pro # Strong model — CoT compensation check
#
# Ablation groups:
#   A1: G3 minus provenance artifacts (no commands.tsv, versions, etc.)
#   A3: G3 minus diagnostic hints (no structured error codes in JSON envelope)
#   A4: G3 minus permission model (no confirmation gate for execution)
#   G3: Full ABI control layer (reference)
#
# If weak model ablation shows significant component contributions, this
# provides mechanistic evidence for the main claim. If not, the results
# demonstrate that strong models compensate through chain-of-thought,
# which is itself an informative null result.
# =============================================================================

set -euo pipefail

MODEL="${1:?Usage: $0 <model_short_name>}"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BENCH_DIR="$PROJECT_ROOT/bench"

EXPERIMENT_SET="paper_v1_ablation"
FIXTURE_SET="public"
AGENT_MODE="direct"
REPLICATES=5
WORKERS=3
TASKS="mvp"  # MVP tasks for ablation (T01-T10 minus non-ablation tasks)

# Use the same model config from run_paper_models.sh
# Set env vars before running:
#   export ABI_BENCH_PROVIDER="..."
#   export ABI_BENCH_API_KEY="sk-..."
#   export ABI_BENCH_API_BASE="..."
#   export ABI_BENCH_MODEL="$MODEL"

OUTDIR="$PROJECT_ROOT/bench/results/$MODEL"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ABI-Bench Paper — Component Ablation                     ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Model:  $MODEL"
echo "║  Groups: G3 A1 A3 A4"
echo "║  Tasks:  $TASKS"
echo "║  Reps:   $REPLICATES"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

export ABI_BENCH_MAX_TOKENS=8000
export ABI_BENCH_TEMPERATURE=0.0

ABLATION_GROUPS=("G3" "A1" "A3" "A4")

for GROUP in "${ABLATION_GROUPS[@]}"; do
    echo ""
    echo "─── $GROUP ───"

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
done

# ── Aggregate ────────────────────────────────────────────────────────────

python bench/scoring/aggregate_scores.py \
    --results "$OUTDIR" \
    --experiment-set "$EXPERIMENT_SET" --fixture-set "$FIXTURE_SET" \
    --output "$OUTDIR/ablation_leaderboard.tsv" \
    --summary "$OUTDIR/ablation_summary.json"

python bench/scoring/compute_statistics.py \
    --results "$OUTDIR" \
    --experiment-set "$EXPERIMENT_SET" --fixture-set "$FIXTURE_SET" \
    --suite ablation_v0_8 \
    --comparisons "G3_vs_A1,G3_vs_A3,G3_vs_A4" \
    --output "$OUTDIR/ablation_statistics.json"

echo ""
echo "✓ Ablation complete for $MODEL"
echo "  Results: $OUTDIR/"
