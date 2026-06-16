# ABI-Bench v0.1 Feasibility Check Report

Date: 2026-06-13 | **Updated: 2026-06-17** (OpenCode removed — replaced by `direct_agent.py`)

## Update (2026-06-17): OpenCode Removed

The OpenCode middleware has been completely removed from the benchmark in v0.1.1.
The `direct_agent.py` Python agent loop (calling the LLM API via the `openai` SDK)
is now the sole real-agent execution mode. All "remaining problems" referencing
OpenCode below are therefore resolved or moot. See `docs/development/opencode_removal.md`
for the full rationale.

## Original Report

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

13. Experiment runs now carry an explicit `experiment_set` label (`dev`,
    `main`, `ablation`, or `full`) through context, trace metadata, and
    `score.json`.

14. `aggregate_scores.py` now supports `--experiment-set` filtering and writes
    a `completeness` report showing expected groups, observed groups, missing
    groups, expected tasks, missing tasks, missing replicates, and unknown
    groups.

15. Dry-run tasks now generate and score `artifact_manifest.json`. The
    manifest records task metadata, experiment set, generated artifacts,
    provenance files, tables, reports, and trace-sidecar availability.

16. `artifact_manifest.schema.json` now documents `experiment_set` and
    `final_answer_json`, and scoring validates manifest content against actual
    run-dir artifacts.

17. Diagnosis tasks T05/T06/T07 now require `final_answer.json` sidecars with
    structured fields. Keyword-only markdown can no longer receive full
    credit.

18. The simulated harness writes diagnosis sidecars, `collect_trace.py`
    collects them, and `score_run.py` checks `final_answer.json` in trace
    output.

19. Real-agent prompts now ask for diagnosis JSON sidecars, and `run_agent.ts`
    copies workspace-level `final_answer.json` produced by ABI diagnose into
    `.agent_log` for trace collection.

20. ABI CLI commands exposed in `agent_context.json` now include task and
    experiment metadata so generated manifests do not fall back to placeholder
    task IDs.

21. Diagnosis tasks now support public and hidden fixture selection. T05/T06/T07
    define `public_fixture` and `hidden_fixture`, and `run_task.py` /
    `run_group.py` accept `--fixture-set public|hidden`.

22. Structured diagnosis scoring can now read fixture-specific expected answer
    JSON from `bench/expected_answers/` instead of hard-coding all public
    fixture answers in scoring functions.

23. Hidden diagnosis fixtures were added under `bench/fixtures_hidden/` for
    missing input, missing resource, and tool-not-found cases. Expected answers
    are stored outside the fixture directories so `reset_workspace.py` does not
    copy them into the agent-visible workspace.

24. Score metadata now records `fixture_set`, and trace metadata records both
    `fixture_set` and `fixture_name` when runs are launched via `run_task.py`.

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
python bench/harness/run_task.py --group G3 --task T03 --replicate 1 --experiment-set main --agent-mode simulated --outdir /tmp/abi_p2_main_results/G3/T03/replicate_01
python bench/scoring/aggregate_scores.py --results /tmp/abi_p2_main_results --experiment-set main --output /tmp/abi_p2_main_results/leaderboard.tsv --summary /tmp/abi_p2_main_results/summary.json
python bench/harness/run_task.py --group A1 --task T03 --replicate 1 --experiment-set ablation --agent-mode simulated --outdir /tmp/abi_p2_ablation_results/A1/T03/replicate_01
python bench/scoring/aggregate_scores.py --results /tmp/abi_p2_ablation_results --experiment-set ablation --output /tmp/abi_p2_ablation_results/leaderboard.tsv --summary /tmp/abi_p2_ablation_results/summary.json
python bench/harness/abi_cli.py dry-run --workspace /tmp/abi_p3_cli_T03 --group G3 --analysis-type metagenomic_plasmid --task-id T03 --experiment-set dev --replicate 1
python bench/scoring/score_run.py --task bench/tasks/T03_dryrun_plasmid.yaml --run-dir /tmp/abi_p3_cli_T03 --trace-dir /tmp/abi_p3_cli_T03 --output /tmp/abi_p3_cli_T03/score.json --experiment-set dev
python bench/harness/abi_cli.py dry-run --workspace /tmp/abi_p3_cli_T10 --group G3 --analysis-type metatranscriptomics --task-id T10 --experiment-set dev --replicate 1
python bench/scoring/score_run.py --task bench/tasks/T10_dryrun_metatranscriptomics.yaml --run-dir /tmp/abi_p3_cli_T10 --trace-dir /tmp/abi_p3_cli_T10 --output /tmp/abi_p3_cli_T10/score.json --experiment-set dev
python bench/scoring/score_run.py --task bench/tasks/T05_missing_input.yaml --run-dir /tmp/abi_p3_bad_T05_nojson --trace-dir /tmp/abi_p3_bad_T05_nojson --output /tmp/abi_p3_bad_T05_nojson/score.json --experiment-set dev
python bench/harness/run_task.py --group G3 --task T03 --replicate 1 --experiment-set dev --agent-mode simulated --outdir /tmp/abi_p3_run_task_G3_T03
python bench/harness/run_task.py --group G3 --task T05 --replicate 1 --experiment-set dev --agent-mode simulated --outdir /tmp/abi_p3_run_task_G3_T05
python bench/harness/run_task.py --group A3 --task T05 --replicate 1 --experiment-set ablation --agent-mode simulated --outdir /tmp/abi_p3_run_task_A3_T05
python bench/harness/run_task.py --group G3 --task T05 --replicate 1 --experiment-set dev --fixture-set public --agent-mode simulated --outdir /tmp/abi_p4_run_task_G3_T05_public
python bench/harness/run_task.py --group G3 --task T05 --replicate 1 --experiment-set dev --fixture-set hidden --agent-mode simulated --outdir /tmp/abi_p4_run_task_G3_T05_hidden
python bench/harness/run_task.py --group G3 --task T06 --replicate 1 --experiment-set dev --fixture-set hidden --agent-mode simulated --outdir /tmp/abi_p4_run_task_G3_T06_hidden
python bench/harness/run_task.py --group G3 --task T07 --replicate 1 --experiment-set dev --fixture-set hidden --agent-mode simulated --outdir /tmp/abi_p4_run_task_G3_T07_hidden
python bench/harness/run_task.py --group A3 --task T05 --replicate 1 --experiment-set ablation --fixture-set hidden --agent-mode simulated --outdir /tmp/abi_p4_run_task_A3_T05_hidden
```

Additional P3 validation results:

- T03 ABI CLI dry-run scored 12/12.
- T10 ABI CLI dry-run scored 10/10.
- T05/T06/T07 ABI CLI diagnosis scored 10/10, 10/10, and 8/8 with structured
  JSON sidecars.
- A markdown-only T05 negative control without `final_answer.json` scored 4/10.
- Simulated end-to-end G3 T03 and G3 T05 scored 12/12 and 10/10.
- Simulated end-to-end A3 T05 scored 2/10, confirming that missing structured
  diagnosis fields prevent full credit.
- Public G3 T05 after the expected-answer refactor scored 10/10.
- Hidden G3 T05/T06/T07 scored 10/10, 10/10, and 8/8.
- Hidden A3 T05 scored 2/10.
- Hidden expected-answer files were confirmed absent from the agent workspace
  after reset.

Current `bench/results/summary.json` reports `primary_claim_supported: false`
because G1/G2 real comparison results are not present.

## Remaining Problems

1. Real `opencode` mode now has a callable local ABI CLI, but it is still not a
   native MCP/OpenCode tool server with enforced allowlists. G1/G2 could still
   bypass isolation if they discover and invoke the CLI path. A stricter tool
   isolation layer is needed before paper-grade real-agent runs.

2. The current committed/working `bench/results` set contains simulated G3 and
   ablation runs, but no G1/G2 main experiment results. Main-claim reporting is
   therefore intentionally blocked; use `--experiment-set main` once real main
   runs are generated.

3. Existing fixture `data/` directories contain placeholders only. This is
   acceptable for dry-run and path-diagnosis tasks, but the benchmark should not
   describe v0.1 fixtures as real biological data.

4. Some non-diagnosis answer checks remain keyword-based. T05/T06/T07 now have
   structured sidecar requirements, but discovery, inspection, and
   interpretation tasks still need stronger answer schemas or hidden fixtures
   for paper-grade robustness.

5. Hidden fixtures now reduce direct answer leakage for T05/T06/T07, but the
   hidden bundle is still committed locally. Paper-grade runs should use an
   external hidden bundle or private release artifact.

6. Statistical analysis still lacks bootstrap confidence intervals despite the
   methods document describing them. Add CI computation before paper use.

7. Temporary result folders such as `G3_abl` and `G3_full` are ambiguous for
   aggregation. Keep official runs under a clean results root or add an
   explicit experiment-set dimension to score metadata.
