# ABI-Bench v0.6 — Failure Cases

## Failure Taxonomy v2 (v0.6)

### Agent-level failures (v0.5 legacy)
| Code | Description |
|------|-------------|
| `artifact_missing` | Required artifact not produced |
| `invalid_status` | Step status not in allowed set |
| `real_execution_violation` | Unauthorized real tool execution |
| `diagnosis_wrong` | Diagnosis incorrect |
| `diagnosis_incomplete` | Diagnosis missing key elements |
| `overclaim_result` | Dry-run results presented as biological findings |
| `timeout` | Task exceeded time limit |
| `agent_loop` | Agent stuck in unproductive repetition |

### Real-execution failures (v0.6 new)
| Code | Description |
|------|-------------|
| `pipeline_crashed` | Real pipeline execution terminated abnormally (non-zero exit) |
| `assertion_failed` | Pipeline output does not satisfy `expected_assertions.yaml` |
| `resource_not_found` | Required database, index, or reference file missing at runtime |
| `tool_version_mismatch` | Tool version incompatible with expected output format |
| `output_truncated` | Output file exists but was truncated (file size < expected) |
| `partial_completion` | Some steps succeeded, some failed — pipeline incomplete |

### Failure severity
| Severity | Codes |
|----------|-------|
| **Fatal** | `pipeline_crashed`, `timeout`, `real_execution_violation` |
| **Partial** | `partial_completion`, `assertion_failed`, `resource_not_found` |
| **Recoverable** | `tool_version_mismatch`, `output_truncated`, `diagnosis_incomplete` |
| **Minor** | `overclaim_result`, `artifact_missing`, `diagnosis_wrong` |

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
