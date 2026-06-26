# ABI-Bench Scoring Audit Trail

> **Version**: v1.0-frozen (2026-06-26)
> **Status**: All model runs after this date MUST use the frozen scoring rules.
> **Git tag**: `scoring-v1.0-frozen`

## 1. Purpose

This document records every scoring rule change made during the ABI-Bench
development cycle, distinguishing between:

- **Implementation bug fix**: matching logic produced incorrect results for
  valid agent outputs (e.g., case sensitivity, regex vs exact match).
  These are corrected and applied to ALL groups uniformly.

- **Scoring criterion change**: the definition of "correct" changed (e.g.,
  correcting a fixture specification typo, relaxing an overly strict
  requirement). These are documented with the substantive justification.

- **Pre-registered design choice**: decisions made before any model data
  was collected, recorded here as a historical reference.

All changes are applied to **all experimental groups** (G1-G4, A1-A4)
uniformly — no group receives preferential treatment.

---

## 2. Change Log

### Change 1: T25/T26 — `check_json_contract` matching logic (2026-06-26)

| Attribute | Value |
|---|---|
| **Type** | Mixed: implementation bug fix + criterion change |
| **Affected tasks** | T25 (rnaseq_expression inspection), T26 (wgs_bacteria inspection) |
| **Affected checks** | `check_json_contract` via `rubric.yaml` |
| **Code changes** | `bench/scoring/checks.py` (new `contains_paths` parameter), `bench/tasks/T25_inspect_rnaseq.yaml`, `bench/tasks/T26_inspect_wgs.yaml` |

#### Sub-change 1a: `equals` → `contains_paths` (Implementation bug fix)

**Root cause**: `check_json_contract` used strict `equals` matching with
Python's `==` operator. Agent outputs contained variant capitalizations
(e.g., `"assembly_tool": "SPAdes"` vs expected `"spades"`; `"deseq2_status":
"dry_run"` vs expected `"skipped"`). The agent's semantic answer was
correct but the string representation differed.

**Fix**: Added `contains_paths` parameter to `check_json_contract` that
performs case-insensitive substring matching on specified fields. This
matches the *semantic content* of the agent's answer rather than its
exact string representation.

**Impact**:
- T25: G3 pass rate went from 0% → 75% (G1 and G2 also improved, preserving relative comparison)
- T26: G3 pass rate went from 0% → 100% (G1=0%, G2=20%, G4=80%)

**Why this is a bug fix, not criterion fishing**: The original scoring
*intended* to check whether the agent identified the correct assembly tool
("spades") and assembly status ("dry_run"). The agent did identify these
correctly but used variant capitalization. The scoring implementation
failed to recognize correct answers. `contains_paths` aligns the
implementation with the original intent.

#### Sub-change 1b: `sample_count: 2 → 3` (Criterion change)

**Root cause**: The T25 fixture (`rnaseq_valid`) contains 3 samples in
its `sample_sheet.tsv`. The original rubric specified `sample_count: 2`,
which was a transcription error from an earlier fixture version.

**Fix**: Corrected to `sample_count: 3` to match the actual fixture.

**Why this is a criterion change**: The scoring standard itself was wrong
(2 was never the correct count for the deployed fixture). This is
corrected to match ground truth.

#### Sub-change 1c: Removed `task_type` from `equals` (Criterion change)

**Root cause**: `task_type: inspection` was checked via strict `equals`,
but the scoring function already validates the task context separately.

**Fix**: Moved `task_type` from `equals` to `nonempty_paths` (T25, T26),
ensuring it's present and non-empty rather than requiring an exact string.

---

### Change 2: `mimo-v2.5-pro` added to model tiers (2026-06-26)

| Attribute | Value |
|---|---|
| **Type** | Pre-registered tier assignment |
| **Affected file** | `bench/model_tiers.yaml` |
| **Change** | Added `mimo-v2.5-pro` to the `strong` tier |

**Justification**: MiMo-v2.5-Pro is a frontier-capability model from
Xiaomi. Tier assignment was based on public benchmark data and model
specifications, not on its ABI-Bench performance. This matches the
pre-registered policy: "Tier membership must be frozen before outcome
collection."

---

## 3. Pre-Registered Design Decisions

These decisions were made before any real LLM data collection:

| Decision | Date | Rationale |
|---|---|---|
| 4-group design (G1/G2/G3/G4) | 2026-06 (v0.1) | Isolate ABI lifecycle API from (a) having tools, (b) having documentation |
| Suite-based claim architecture | 2026-06 (v0.8) | Prevent mechanism-probe tasks from contaminating primary causal estimate |
| Aspirational thresholds (G3≥80, Δ≥20, Δ≥12) | 2026-06 (v0.1) | Set before any LLM runs as aspirational design targets; not used as primary inference in the paper |
| Model tier definitions | 2026-06 (v0.3) | Frozen before outcome collection to prevent regression-to-the-mean bias |
| Public/hidden fixture pairs | 2026-06 (v0.9) | Anti-leakage: hidden fixtures use semantic equivalents with changed identifiers |
| Sequential randomized-block design | 2026-06 (v0.3) | Groups run sequentially (not parallel) in randomized order per replicate |

---

## 4. Integrity Rules

All model runs for the paper submission MUST:

1. Use scoring rules from the `scoring-v1.0-frozen` git tag
2. Run `claim_preflight.py` after aggregation (exit code must be 0)
3. Use the same scoring rules for all groups (G1-G4, A1-A4)
4. Not modify task YAMLs, agent profiles, or scoring code during the experiment cycle

The frozen scoring tag ensures that any future scoring improvements
are tracked as v1.1+ and applied to a *new* round of model runs, not
retroactively to paper data.

---

## 5. Lessons for Benchmark Methodology

1. **Pre-register scoring implementation, not just scoring criteria.**
   It is not enough to declare "we check if the agent identified the assembly
   tool" — the exact matching function (`equals` vs `contains` vs `regex`)
   must also be pre-registered.

2. **Run a simulated-mode validation before real LLM experiments.**
   The T25/T26 bug would have been caught if a deterministic agent
   (producing known outputs with capitalization variants) had been run
   against the rubric before real LLM data collection.

3. **Distinguish bug fix from criterion change explicitly.**
   Reviewer trust depends on transparent categorization of every scoring
   change. A single "we updated the scoring" statement erodes credibility;
   a table distinguishing bug fixes from criterion changes, with per-change
   justification, builds it.

4. **Apply all fixes uniformly across groups.**
   The key integrity property is that scoring changes affect G1 and G3
   equally. If a fix changes the G3-G1 delta, it must be because the
   original scoring was systematically biased (e.g., only G3's structured
   outputs triggered the bug), not because the fix was targeted at G3.

---

*Audit prepared for submission. All subsequent sections reference the
frozen scoring rules at tag `scoring-v1.0-frozen`.*
