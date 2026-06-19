# ABI-Bench Submission Guide

> [中文版 (Chinese Version)](SUBMISSION.zh.md)

> How to submit your agent's results to the ABI-Bench leaderboard.

## 1. What You Can Submit

ABI-Bench accepts results for:

| Submission type | Description | Scoring |
|-----------------|-------------|---------|
| **New model** | Run G1/G2/G3 with a different LLM | Full scoring, appears on leaderboard |
| **New agent harness** | Replace `direct_agent.py` with your own agent loop | Full scoring |
| **New ablation** | A1/A3/A4 variants with a specific model/harness | Ablation table |
| **New plugin** | Add T13–T18 style tasks for a new bioinformatics analysis type | Plugin table |

All submissions must include **at least the 8 MVP tasks** (T01, T02, T03, T05, T06, T08, T09, T10)
across **all 4 main groups** (G1, G2, G3, G4) with **at least 3 replicates** each.
Full v0.6 submissions should cover all 47 tasks (T01-T47) across all 4 groups.

---

## 2. Prerequisites

```bash
# 1. Python ≥ 3.10
python --version

# 2. Install ABI
pip install abi

# 3. Clone benchmark & install deps
git clone <this-repo-url> ABI-Bench
cd ABI-Bench
pip install pyyaml openai

# 4. Configure your LLM API key
cp bench/.env.example bench/.env
# Edit bench/.env — set your provider, API key, and model
```

Supported providers: Anthropic, OpenAI, DeepSeek, Google Gemini, or any OpenAI-compatible endpoint.
See `bench/.env.example` for configuration templates.

---

## 3. Submission Workflow (5 Steps)

### Step 1: Validate Infrastructure (Required)

Before running with a real LLM, verify the scoring harness works correctly:

```bash
# Run G3 simulated mode on T03 (must score 12/12)
python bench/harness/run_task.py --group G3 --task T03 --replicate 1 \
  --agent-mode simulated \
  --experiment-set submission --fixture-set public \
  --outdir bench/submissions/infrastructure_check/G3/T03/replicate_01

python bench/scoring/score_run.py \
  --task bench/tasks/T03_dryrun_plasmid.yaml \
  --trace-dir bench/submissions/infrastructure_check/G3/T03/replicate_01 \
  --run-dir bench/workspaces/G3/T03/replicate_01 \
  --output bench/submissions/infrastructure_check/G3/T03/replicate_01/score.json

# Expected output: "score": 12, "max_score": 12, "passed": true
```

If you don't get 12/12, your environment has an issue. Common fixes:
- Check Python version (≥ 3.10)
- Reinstall `pyyaml`
- Run from repo root

### Step 2: Run All 3 Groups

Run each group independently. The harness supports `--parallel` for speed:

```bash
# Set your API key and model
export ABI_BENCH_MAX_TOKENS=8000

# G1 (README + Shell Baseline)
python bench/harness/run_group.py \
  --group G1 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set submission --fixture-set public \
  --outdir bench/submissions/<your_submission_id>/G1

# G2 (Plain Tool Calling Baseline)
python bench/harness/run_group.py \
  --group G2 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set submission --fixture-set public \
  --outdir bench/submissions/<your_submission_id>/G2

# G3 (ABI Control Layer)
python bench/harness/run_group.py \
  --group G3 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set submission --fixture-set public \
  --outdir bench/submissions/<your_submission_id>/G3
```

**Rules**:
- Use `<your_submission_id> = <model_name>/<date>` (e.g., `claude-opus-4-8/20260620`)
- All 3 groups must use the **same LLM**, **same temperature (0)**, and **same agent harness**
- Do **not** modify task YAMLs, agent profiles, scoring code, or fixtures
- The harness automatically runs `claim_preflight.py` after each group completes

### Step 3: Aggregate & Score

```bash
python bench/scoring/aggregate_scores.py \
  --results bench/submissions/<your_submission_id> \
  --experiment-set submission --fixture-set public \
  --output bench/submissions/<your_submission_id>/leaderboard.tsv \
  --summary bench/submissions/<your_submission_id>/summary.json \
  --per-task bench/submissions/<your_submission_id>/per_task_scores.tsv

python bench/scoring/claim_preflight.py \
  --results bench/submissions/<your_submission_id> \
  --experiment-set submission --fixture-set public \
  --min-replicates 3 \
  --output bench/submissions/<your_submission_id>/preflight.json
```

If `claim_preflight.py` exits with non-zero, **do not proceed to step 4** — fix the issues first.
Common issues: missing replicates, mixed fixture sets, inconsistent model_id metadata.

### Step 4: Validate Integrity

Before submitting, verify:

```bash
# Check completeness
python -c "
import json
with open('bench/submissions/<your_submission_id>/summary.json') as f:
    s = json.load(f)
c = s['completeness']
print(f'Complete: {c[\"complete\"]}')
print(f'Missing: {c.get(\"missing_groups\", [])} {c.get(\"missing_tasks\", [])}')
for g in ['G1','G2','G3']:
    gd = s['groups'].get(g, {})
    print(f'{g}: score={gd.get(\"total_score_mean\",\"N/A\")} n={gd.get(\"score_count\",0)}')
"

# Verify simulated mode still works (no drift)
python bench/harness/run_task.py --group G3 --task T03 --replicate 1 \
  --agent-mode simulated
# Must still score 12/12
```

### Step 5: Open a Pull Request

Create a PR with the following structure:

```text
bench/submissions/<your_submission_id>/
├── G1/
│   ├── T01/replicate_01/score.json  ...  replicate_03/score.json
│   ├── T02/...  T03/...  T05/...  T06/...  T08/...  T09/...  T10/...
├── G2/  (same structure)
├── G3/  (same structure)
├── leaderboard.tsv
├── summary.json
├── per_task_scores.tsv
└── preflight.json
```

**PR title format**:
```
[Submission] <model_name> · <agent_harness> · <date>
```

**PR body** (use this template):

```markdown
## Model
- **Model**: <full model name and version>
- **Provider**: <Anthropic / OpenAI / DeepSeek / Gemini / other>
- **Agent harness**: direct (or describe custom harness)
- **Temperature**: 0
- **Date**: YYYY-MM-DD

## Preflight
- [x] `claim_preflight.py` passed (exit code 0)
- [x] Simulated mode validation: G3 T03 = 12/12
- [x] All 8 MVP tasks × 3 groups × 3 replicates present
- [x] No fixture, task, or scoring files modified
- [x] `summary.json` `complete: true`

## Results Summary
| Group | Total Score | Task Success | Dry-run Rate | Diag Accuracy | Unsafe Rate |
|-------|------------|-------------|-------------|--------------|-------------|
| G3 | ... | ... | ... | ... | ... |
| G2 | ... | ... | ... | ... | ... |
| G1 | ... | ... | ... | ... | ... |

## Notes
<!-- Any observations, anomalies, or comments about the run -->
```

---

## 4. Extended Submissions (Optional)

After MVP (8 tasks) is accepted, you may submit results for larger task sets:

```bash
# Full v0.5 set (T01-T35, 35 tasks)
for group in G1 G2 G3 G4; do
  python bench/harness/run_group.py \
    --group $group --tasks full_v0_5 --replicates 3 \
    --agent-mode direct --parallel --workers 4 \
    --experiment-set submission --fixture-set public \
    --outdir bench/submissions/<your_submission_id>_v0_5/$group
done

# Full v0.6 set (T01-T47, 47 tasks) — includes figure validation,
# progressive repair, cross-platform, and multi-agent modules
for group in G1 G2 G3 G4; do
  python bench/harness/run_group.py \
    --group $group --tasks full_v0_6 --replicates 3 \
    --agent-mode direct --parallel --workers 4 \
    --experiment-set submission --fixture-set public \
    --outdir bench/submissions/<your_submission_id>_v0_6/$group
done
```

Available task sets: `mvp` (8 tasks), `full` (18 tasks), `full_v0_5` (35 tasks),
`full_v0_6` (47 tasks), `extended_v0_6` (52 tasks).

---

## 5. Adding a New Plugin

ABI-Bench supports plugin-specific submissions for bioinformatics analysis types
beyond the built-in 5 (metagenomic_plasmid, metatranscriptomics, rnaseq_expression,
amplicon_16s, wgs_bacteria).

To submit results for a new plugin:

1. Follow the existing task pattern: T09 (plan), T10 (dry-run), T11 (inspect)
2. Create a fixture under `bench/fixtures/<your_plugin>_valid/` with:
   - `config.yaml`
   - `sample_sheet.tsv`
   - `data/` (small placeholder files)
3. Create task YAMLs with `task_type: portability` and set `plugin: <your_plugin>`
4. Submit results alongside a plugin registration PR

Plugin contributions must include a `abi-plugin.yaml` and `tool_registry.yaml`
in the upstream [ABI repository](https://github.com/bker/abi).

---

## 6. Rules & Integrity

### What You MUST Do

- ✅ Use the **exact same LLM version** for all 3 groups (G1, G2, G3)
- ✅ Use **temperature = 0** (or lowest available)
- ✅ Run **all 3 groups** — partial submissions will be rejected
- ✅ Run **at least 3 replicates** per task
- ✅ Keep `network: false` and `real_tool_execution: false` for v0.1 scoring
- ✅ Run `claim_preflight.py` before submitting — exit code must be 0

### What You MUST NOT Do

- ❌ Do NOT modify task YAMLs, agent profiles, scoring code, or fixtures
- ❌ Do NOT mix models across groups (e.g., G3 on Claude, G1 on GPT)
- ❌ Do NOT use different temperatures across groups
- ❌ Do NOT run hidden fixture set for G1/G2 (public only for v0.1 submission)
- ❌ Do NOT submit only G3 results (defeats the purpose of the 3-group design)
- ❌ Do NOT cherry-pick replicates — submit all replicates, even failed ones

### Violations

- Mixing models across groups → PR closed without review
- Modified scoring/fixtures → PR closed, reporter flagged
- Cherry-picked replicates → detected by preflight (replicate count mismatch)

---

## 7. Leaderboard Update

After your PR is reviewed and merged:

1. GitHub Actions runs `aggregate_scores.py` against `bench/submissions/`
2. `bench/docs/index.html` is regenerated with your row inserted
3. The updated leaderboard is pushed to GitHub Pages automatically
4. Your results appear at `<repo-url>/bench/docs/`

Manual review may be required if:
- Preflight check fails in CI
- Scores fall outside expected ranges (G3 < 50 or G3 < G1)
- Metadata fields are inconsistent across groups

---

## 8. FAQ

**Q: Can I submit results from a different agent harness (not `direct_agent.py`)?**
A: Yes. Document your harness in the PR body. The harness must respect the same
fixed variables (temperature 0, max steps 50, timeout 20 min, network off).

**Q: What if my model doesn't support temperature = 0?**
A: Use the lowest available value and document it in the PR body.

**Q: Can I submit results for only the ablation groups (A1/A3/A4)?**
A: No. Ablation without G3 baseline is not interpretable. Submit G1/G2/G3 first,
then ablation.

**Q: How do I cite ABI-Bench?**
A: See the `Citation` section in [README.md](README.md).

**Q: My G3 score is lower than my G1 score. Is that a valid submission?**
A: Yes! Negative results are valuable. Submit them — they help the community
understand when and why ABI does or doesn't help.

**Q: How long does a full run take?**
A: With 8 MVP tasks × 3 groups × 3 replicates = 72 task runs, and `--parallel --workers 4`,
approximately 1–2 hours depending on model latency and agent step count.

---

## 9. Contact

- **Issues**: Open a GitHub issue in this repository
- **Paper**: [arXiv preprint]()
- **ABI**: [github.com/bker/abi](https://github.com/bker/abi)
