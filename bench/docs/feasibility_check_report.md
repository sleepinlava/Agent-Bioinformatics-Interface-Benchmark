# ABI-Bench v0.1 Feasibility Check Report

Date: 2026-06-13

## Conclusion

The benchmark is feasible as a local infrastructure and scoring validation
suite. The simulated mode can reset workspaces, generate traces, score tasks,
aggregate results, and regenerate paper tables.

The current repository is not yet sufficient to support the paper-level claim
that G3 outperforms G1/G2. That claim still requires real `opencode` runs for
G1, G2, and G3 under the same model, with complete traces and statistical
analysis.

## Fixed Issues

1. `run_group.py` now accepts and forwards `--agent-mode` to `run_task.py`.
   Previously documented real-agent commands silently ran the default simulated
   mode.

2. Real-agent trace collection now reads from `bench/traces/.../.agent_log`.
   Previously `run_agent.ts` wrote real-agent traces there, while `run_task.py`
   collected only from the workspace `.agent_log`.

3. `opencode` mode now fails closed when `bun`, task YAML, or agent launch is
   unavailable. It writes a failure trace instead of silently falling back to
   simulated output.

4. `agent_context.json` is now injected into the OpenCode prompt context.
   Previously the group profile was exported to disk but not reliably shown to
   the real agent.

5. Tool registry scoring is stricter. `tool_ids_valid` now checks tool IDs
   against `config.yaml` tool keys and executable names instead of passing when
   no registry was provided.

6. Plan schema checks are stricter. Empty or missing `steps` no longer pass
   `step_ids_unique`.

7. Safety scoring now scans tool calls and command logs for obvious real
   bioinformatics commands, not only idealized `is_real_execution` markers.

8. Scoring metadata now records `task_type`, `agent_mode`, and real trace
   metadata when available. `final_answer.md` artifacts are checked in trace
   output instead of only in result directories.

9. Aggregation now normalizes total score by summed points per replicate and
   computes dry-run success only over dry-run tasks. Claim support now includes
   all documented criteria and reports `primary_claim_supported`.

10. Paper table generation no longer emits empty G1/G2 rows as if they were
    valid results. Existing tables were regenerated from current score files.

11. A minimal local ABI lifecycle CLI now exists at `bench/harness/abi_cli.py`.
    It supports `list-types`, `plan`, `dry-run`, `inspect`, `diagnose`,
    `report`, and permission-gated `run` without executing real bioinformatics
    tools.

12. G3 and ABI ablation groups now receive ABI CLI command hints in
    `agent_context.json`; G1/G2 contexts explicitly mark the ABI interface as
    unavailable.

## Current Verified Commands

```bash
PYTHONDONTWRITEBYTECODE=1 python -c "from pathlib import Path; files=list(Path('bench/harness').glob('*.py'))+list(Path('bench/scoring').glob('*.py')); [compile(p.read_text(), str(p), 'exec') for p in files]; print('syntax ok', len(files))"
python bench/harness/run_group.py --group G3 --tasks mvp --replicates 1 --agent-mode simulated --outdir bench/results/G3
python bench/harness/run_group.py --group A1 --tasks ablation --replicates 1 --agent-mode simulated --outdir bench/results/A1
python bench/harness/run_group.py --group A3 --tasks ablation --replicates 1 --agent-mode simulated --outdir bench/results/A3
python bench/harness/run_group.py --group A4 --tasks ablation --replicates 1 --agent-mode simulated --outdir bench/results/A4
python bench/scoring/aggregate_scores.py --results bench/results --output bench/results/leaderboard.tsv --summary bench/results/summary.json --per-task bench/results/per_task_scores.tsv
python bench/scoring/make_tables.py --results bench/results --outdir docs/experiments/abi_bench_v0_1
python bench/harness/abi_cli.py dry-run --workspace /tmp/abi_cli_plasmid --group G3 --analysis-type metagenomic_plasmid
python bench/harness/abi_cli.py dry-run --workspace /tmp/abi_cli_transcriptomics --group G3 --analysis-type metatranscriptomics
```

Current `bench/results/summary.json` reports `primary_claim_supported: false`
because G1/G2 real comparison results are not present.

## Remaining Problems

1. Real `opencode` mode now has a callable local ABI CLI, but it is still not a
   native MCP/OpenCode tool server with enforced allowlists. G1/G2 could still
   bypass isolation if they discover and invoke the CLI path. A stricter tool
   isolation layer is needed before paper-grade real-agent runs.

2. The current committed/working `bench/results` set contains simulated G3 and
   ablation runs, but no G1/G2 main experiment results. Main-claim reporting is
   therefore intentionally blocked.

3. Existing fixture `data/` directories contain placeholders only. This is
   acceptable for dry-run and path-diagnosis tasks, but the benchmark should not
   describe v0.1 fixtures as real biological data.

4. Several answer checks remain keyword-based. They are deterministic but can
   be gamed by mentioning required terms without performing the intended
   reasoning. Stronger structured answer schemas or hidden fixtures are needed
   for paper-grade robustness.

5. Prompt text currently reveals many expected diagnosis details. This is fine
   for infrastructure smoke tests but weakens measurement of independent
   diagnostic ability.

6. Statistical analysis still lacks bootstrap confidence intervals despite the
   methods document describing them. Add CI computation before paper use.

7. Temporary result folders such as `G3_abl` and `G3_full` are ambiguous for
   aggregation. Keep official runs under a clean results root or add an
   explicit experiment-set dimension to score metadata.
