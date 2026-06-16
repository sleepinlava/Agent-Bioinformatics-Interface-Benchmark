# OpenCode Removal — Development Record

**Date**: 2026-06-17  
**Version**: v0.1.1  
**Decision**: Remove OpenCode middleware entirely from the ABI-Bench benchmark harness.

## Background

ABI-Bench v0.1 was originally designed with OpenCode as the agent runtime.
OpenCode is a TypeScript monorepo (~20 packages) providing an HTTP server,
session management, and tool-calling infrastructure for LLM agents. The
benchmark harness (`bench/harness/run_agent.ts`) started an OpenCode server,
created sessions via the `@opencode-ai/sdk` client, sent task prompts, and
polled for completion.

## Problems with OpenCode

Three fundamental issues made OpenCode unsuitable as a benchmark agent harness:

### 1. Message Parser Incompatibility with DeepSeek

OpenCode's message parser could not handle DeepSeek v4-pro's `reasoning_content`
field. DeepSeek v4-pro always produces thinking tokens even without explicit
reasoning requests. OpenCode's parser treated these as empty responses
(`message_count=0`), causing the agent to produce zero output. This was an
architectural incompatibility — not a config issue.

### 2. Authentication Architecture Mismatch

OpenCode auto-detected DeepSeek by base URL and switched to a "native" provider
type that embedded the API key in the request body. DeepSeek's API rejects this
format, requiring `Authorization: Bearer` header auth. A workaround proxy
(`deepseek_proxy.py`) was created but added failure points.

### 3. Unnecessary Infrastructure Overhead

Each benchmark run incurred 5–15 seconds of fixed overhead from:
- OpenCode HTTP server startup
- Session creation via SDK
- 3-second polling loop for agent completion

For 72 runs, this accumulated to 6–18 minutes of infrastructure overhead alone.
A benchmark harness should have zero overhead beyond the LLM API call latency.

## Solution: `direct_agent.py`

A 525-line Python agent loop (`bench/harness/direct_agent.py`) that:

1. Calls the LLM API directly via the `openai` SDK — no intermediate server
2. Executes tool calls (bash, read_file, write_file, list_files) in-process
3. Runs in non-streaming mode, avoiding all reasoning_content issues
4. Produces identical trace formats (agent_trace.jsonl, tool_calls.jsonl,
   commands.log, final_answer.md, metadata.json)
5. Supports all 6 groups (G1/G2/G3/A1/A3/A4) with group-specific system prompts
6. Injects structured JSON output instructions for diagnosis tasks

## What Was Removed

### Files Deleted
- `bench/harness/run_agent.ts` — OpenCode TypeScript harness (1203 lines)
- `bench/harness/deepseek_proxy.py` — Auth proxy workaround
- `bench/harness/opencode` — CLI wrapper script

### Code Changes
- `bench/harness/run_task.py`: Removed OpenCode branch from `_launch_agent_opencode`
  (renamed to `_run_agent`), removed `_is_reasoning_model()` and
  `_get_reasoning_timeout_extra_seconds()` (only used by OpenCode path),
  updated CLI choices
- `bench/harness/run_group.py`: Removed `"opencode"` from `--agent-mode` choices
- `bench/harness/collect_trace.py`: Updated default `agent_harness` to `"direct"`
- `bench/scoring/score_run.py`: Updated default `agent_harness` to `"direct"`
- `bench/harness/direct_agent.py`: Updated comments referencing `run_agent.ts`

### Config Changes
- `bench/BENCHMARK_SPEC.yaml`: `agent_harness: opencode` → `agent_harness: direct`

### Documentation Updated
- `CLAUDE.md` — Removed OpenCode section, updated architecture
- `README.md` — Removed OpenCode references, installation, and examples
- `README.zh.md` — Same (Chinese)
- `bench/README.md` — Removed OpenCode from mode table, directory structure
- `bench/docs/methods.md` — Rewrote agent execution modes section
- `bench/docs/feasibility_check_report.md` — Added update note
- `docs/experiments/ABI_Bench_v0_1_Results_Report.md` — Updated reference
- `docs/experiments/ABI_Bench_v0_1_Results_Report_zh.md` — Updated reference

## Impact

| Metric | Before (OpenCode) | After (Direct) |
|--------|-------------------|----------------|
| Agent harness code | 1203 lines TS + ~20 packages | 525 lines Python |
| External dependencies | Bun, Node.js, OpenCode, SDK | `pip install openai` |
| First run | Timed out (0% success) | 100% success |
| Per-run overhead | 5–15 s | 0 s |
| 72-run benchmark | N/A (failed) | ~90 min, 0 infrastructure failures |
| Debuggability | Server logs, SDK traces | stdout tool calls + token stats |

## Compatibility

The `opencode/` directory remains in the repository for historical reference
but is in `.gitignore` and no longer required for any benchmark operation.
The `--agent-mode opencode` CLI option has been removed. Users who attempt
it will get an argument error pointing them to `--agent-mode direct`.

## Future Considerations

If a future version needs a more sophisticated agent runtime:
1. The `direct_agent.py` loop can be extended with additional tools
2. Provider support follows the `openai` SDK's compatibility — any
   OpenAI-compatible endpoint works out of the box
3. For Anthropic/Google, `direct_agent.py` already detects provider
   and configures the SDK accordingly

---

## Post-Removal Fix: G1/G2 Tool Leakage (2026-06-17)

After OpenCode removal, an audit identified three leakage vectors where
G1/G2 agents could access ABI CLI tooling:

1. **`allowed_actions` not enforced**: The old `run_agent.ts:getAgentConfig()`
   had logic to remove bash for non-ABI groups when `run_shell: false`. This
   was lost in the direct agent, which used a static TOOLS list for all groups.

2. **Bash tool description leaked ABI CLI**: The static bash description
   mentioned ABI CLI commands (`list-types`, `plan`, `dry-run`, etc.) and was
   sent to ALL groups, effectively advertising the ABI CLI to G1/G2.

3. **No command-level filtering**: G1/G2 agents with bash access could discover
   and call `abi_cli.py` via the filesystem.

### Fix: Three-Layer Defense

| Layer | Mechanism | Implementation |
|-------|-----------|---------------|
| 1 | Group-aware tool descriptions | `_build_tools()` generates bash description without ABI CLI references for G1/G2 |
| 2 | `allowed_actions` enforcement | Non-ABI groups with `run_shell: false` lose bash entirely; ABI groups always keep it |
| 3 | Command-level regex guard | `_ABI_CLI_RE` blocks bash commands referencing `abi_cli.py` or lifecycle subcommands with word-boundary anchors |

### Additional Improvements (Code Review Fixes)

- **ABI_GROUPS constant**: All group membership checks now reference the single
  `ABI_GROUPS` set instead of hardcoded tuples, preventing silent divergence.
- **Regex instead of substring matching**: Eliminated false positives on
  filenames (`T01_list_types.yaml`) and parameters (`--mode abi_run_simulation`).
- **Fail-closed on invalid config**: Malformed `--allowed-actions` JSON now
  exits with error instead of silently disabling all tool restrictions.
- **Eliminated redundant YAML load**: Task fields extracted once in `run_task()`
  and passed to `_run_agent()`, removing the second `yaml.safe_load()` call.
- **Module-level constants**: `_ABI_CLI_RE` and `_ABI_LIFECYCLE_COMMANDS` are
  module-level, avoiding re-allocation in hot paths and serving as single source
  of truth for the bash tool description.
