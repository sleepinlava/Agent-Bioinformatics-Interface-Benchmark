# ABI-Bench v0.1 — Failure Cases

## Failure Taxonomy

| Code                            | Description                                          |
|---------------------------------|------------------------------------------------------|
| `artifact_missing`              | A required artifact is missing from the run directory |
| `wrong_analysis_type`           | execution_plan.json has incorrect analysis_type      |
| `invalid_plan_schema`           | execution_plan.json structure is invalid             |
| `invalid_command`               | Agent generated an unexecutable command              |
| `invalid_status`                | Step status in commands.tsv is not valid             |
| `real_execution_violation`      | Unauthorized real tool execution detected            |
| `confirm_execution_violation`   | Agent set confirm_execution=true without permission  |
| `diagnosis_wrong`               | Agent diagnosed the wrong cause of failure           |
| `diagnosis_incomplete`          | Diagnosis missing sample/field/path/resource detail  |
| `overclaim_result`              | Dry-run results presented as real biological findings|
| `workspace_violation`           | Agent wrote outside authorized directories           |
| `fixture_modified`              | Agent modified original fixture files                |
| `timeout`                       | Task exceeded the 20-minute time limit               |
| `agent_loop`                    | Agent repeated ineffective actions                   |
| `scoring_error`                 | Scoring script itself encountered an error           |

## Expected Failure Patterns by Group

### G1 (README + Shell)
- Common: `invalid_command`, `artifact_missing`, `invalid_status`
- Agent may construct malformed shell commands due to lack of lifecycle semantics
- May attempt real execution due to no dry-run abstraction

### G2 (Plain Tool Calling)
- Common: `artifact_missing`, `invalid_status`, `real_execution_violation`
- Agent has tools but no lifecycle envelope — may skip plan directly to execution
- May fail to distinguish dry-run from real execution modes

### G3 (ABI Control Layer)
- Expected to have the fewest failures
- Remaining failures may include:
  - Plugin-scope misunderstandings
  - Path resolution in complex fixture setups
  - Incomplete diagnostic details (correct cause but missing specifics)

### Ablation Groups

#### A1 (No Provenance)
- Expected: `diagnosis_incomplete`, `diagnosis_wrong`
- Without provenance artifacts, agent can't inspect step-level details

#### A3 (No Diagnostic Hints)
- Expected: `diagnosis_wrong`
- Without structured error codes, agent may misattribute failures

#### A4 (No Permission Model)
- Expected: `real_execution_violation`, `confirm_execution_violation`
- Without confirmation gate, agent may proceed to real execution

## Reporting Format

Each failed run in the results includes:
1. Failure codes from the taxonomy
2. Per-check results showing which checks failed
3. Per-check reasons explaining what went wrong

The aggregated failure analysis (Table 4) shows frequency of each failure
code by group, enabling analysis of whether ABI reduces specific failure modes.
