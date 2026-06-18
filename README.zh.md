# ABI-Bench v0.5

> [English Version (英文版)](README.md)

## Agent-Bioinformatics Interface Benchmark · 智能体-生物信息学接口基准测试

---

## 1. 什么是 ABI-Bench

**ABI-Bench**（Agent-Bioinformatics Interface Benchmark）用于评估：
在相同 LLM、相同 agent harness、相同仓库、相同任务、相同 fixture 条件下，
一个结构化的 **ABI control layer**（智能体-生物信息学接口中间层）是否能比
**README + Shell** 或 **Plain Tool Calling** 让 agent 更稳定地完成
生物信息学 workflow 的规划、dry-run、检查、诊断、恢复和报告生成。

ABI-Bench **不是**一个评测"哪个 LLM 最强"的 benchmark，**不是**一个评测
"哪个生信流程生物学结果更好"的 benchmark，也**不是**一个评测"哪个 agent 
框架最好"的 benchmark。

---

## 2. 设计动机

### 2.1 为什么需要 ABI

LLM agent 在操作生物信息学 workflow 时面临五类特有困难：

1. **生命周期缺失**：生信分析有"发现→规划→预演→检查→诊断→报告"的明确
   生命周期，但普通 shell 或 tool-calling 接口不提供这一语义层。

2. **溯源信息缺失**：生信分析的可复现性依赖完整的 provenance——输入文件路径、
   工具版本、资源数据库、命令序列、执行状态。没有结构化的 provenance artifact，
   agent 无法有效检查结果或诊断故障。

3. **结果解读困难**：生信 pipeline 输出大量表格（基因丰度表、表达矩阵等），
   agent 需要理解标准表结构才能正确解读，而非把空表或中间产物当成最终生物学发现。

4. **安全边界模糊**：生信工具涉及大量计算和数据库下载。agent 需要明确的
   "plan→dry-run→确认→执行"权限边界，避免未经授权启动大规模真实计算。

5. **跨领域复用性**：生物信息学包含众多分析类型（宏基因组质粒分析、宏转录组、
   扩增子测序等），同一 control layer 应能跨类型复用。

ABI-Bench 通过**固定所有其他变量**（模型、harness、仓库、fixture），只改变
agent 可用的接口层，来**严格测量 ABI control layer 本身的贡献**。

### 2.2 外部方法论吸收

ABI-Bench 吸收了七个领域 benchmark 的方法论精华：

| 外部 Benchmark | 核心理念 | ABI-Bench 对应做法 |
|---|---|---|
| **GAIA** | 任务接近真实需求，要求工具使用与多步推理 | 真实仓库、真实 CLI、真实 fixture，产出真实 artifact |
| **SWE-bench** | 绑定固定 repository state，自动测试判定 | 固定 commit、独立 workspace、脚本判定 score.json |
| **AgentBench** | 评估多轮交互中的推理、决策、工具调用和失败类型 | 保存 trace、记录 step 数、failure_code、分析失败类型 |
| **StableToolBench** | 避免外部 API/工具状态漂移导致不可复现 | 以 dry-run 为主，不依赖大型数据库下载，不依赖联网 API |
| **BioCoder** | 生物信息任务应有领域特异性 | 包含 sample sheet、FASTQ path、assembly、database、tool registry |
| **LAB-Bench** | 面向 practical biology research capabilities | 测 workflow planning、数据库配置、结果表解释、避免过度生物学解释 |
| **BixBench** | 覆盖真实数据分析场景、多步轨迹和结果解释 | 要求中间 artifact，评估 agent 是否知道下一步 |

---

## 3. 实验假设体系

### 3.1 主假设

**H1：ABI control layer 能显著提高 LLM agent 对生物信息学 workflow 的 agent-operability。**

### 3.2 次级假设

| 假设 | 内容 | 验证方式 |
|---|---|---|
| **H2** | ABI 的优势不是来自"多给了工具"，而是来自 lifecycle-level control | G3 vs G2 |
| **H3** | provenance artifacts 能显著提高错误诊断与恢复能力 | A1 消融实验 |
| **H4** | standard tables 能显著提高结果结构理解能力 | A2 消融实验 (v0.2) |
| **H5** | permission model 能降低未授权真实执行风险 | A4 消融实验 |
| **H6** | 同一 ABI control layer 能跨分析类型复用 | T09/T10 跨插件任务 |

---

## 4. 实验组设计

### 4.1 三组主实验

| 组别 | 名称 | Agent 可用信息 | 核心目的 |
|---|---|---|---|
| **G1** | README + Shell Baseline | README、docs、CLI help、shell、文件读写 | 测试非结构化文档 + shell 的 agent 能力 |
| **G2** | Plain Tool Calling Baseline | 普通工具函数、CLI wrapper、文件读写 | 测试只暴露工具接口是否足够（无 lifecycle 语义） |
| **G3** | ABI Control Layer | ABI lifecycle、JSON envelope、provenance、standard tables、permission model | **ABI 中间层的完整贡献** |

**核心设计原则**：三组使用**完全相同的 LLM**、**相同的 agent harness**、
**相同的仓库 commit**、**相同的 task fixture**。唯一变量是 agent 可用的接口层。
ABI-Bench 支持两种 agent 执行模式：`direct`（Python 直连，推荐）、
`simulated`（无 LLM，CI/测试用）。

### 4.2 ABI 内部消融组

| 组别 | 名称 | 移除内容 | 主要影响 |
|---|---|---|---|
| **A0** | ABI-full | 无（完整 ABI） | 完整能力 |
| **A1** | ABI-no-provenance | `commands.tsv`、`resolved_inputs.tsv`、`run_summary.json` | inspect、diagnosis、recovery |
| **A3** | ABI-no-diagnostic-hints | 结构化 `error_code` / `diagnostic_hints` | fault localization |
| **A4** | ABI-no-permission-model | `confirmation_required` gating | execution safety |

消融实验回答的核心问题："ABI 的优势到底是 lifecycle 设计整体起作用，还是某个
具体组件（provenance、diagnostic hints、permission model）分别贡献了多少？"

### 4.3 固定变量

| 变量 | 固定值 |
|---|---|
| Agent harness | Python 直连 agent（`direct_agent.py`） |
| LLM | 同一版本，所有组相同 |
| Temperature | 0（或最低可用值） |
| Max agent steps | 50 |
| Timeout | 每任务 20 分钟 |
| Workspace | 每个 task/group/replicate 独立 |
| Git commit | 固定 benchmark commit |
| Network | v0.1 默认关闭 |
| 真实生信执行 | v0.1 主评分禁止 |
| 主运行模式 | dry-run / inspect / report |

---

## 5. 八维能力评估模型

ABI-Bench 通过 12 个具体任务评估 agent 的 8 个核心能力维度：

| 能力维度 | 评估内容 | 对应任务 |
|---|---|---|
| **可发现性** (Discoverability) | agent 是否能发现可用的 analysis types | T01 |
| **可规划性** (Plannability) | agent 是否能构建合法的 execution plan | T02, T09 |
| **可预演性** (Dry-runnability) | agent 是否能完成 dry-run 并生成完整 artifact | T03, T10 |
| **可诊断性** (Diagnosability) | agent 是否能定位 missing input / resource / tool | T05, T06, T07 |
| **可检查性** (Inspectability) | agent 是否能正确读取 provenance 并给出下一步 | T04, T11 |
| **安全性** (Safety) | agent 是否遵守执行确认边界 | T08 |
| **可解释性** (Interpretability) | agent 是否能理解标准表结构但不做过度生物学解读 | T12 |
| **可移植性** (Portability) | 同一 ABI 是否能驱动两类 bioinformatics 分析 | T09, T10, T11 |

---

## 6. 任务设计

### 6.1 任务总览

| 任务 | 名称 | 插件 | 类型 | 分值 |
|---|---|---|---|---|
| T01 | 列出分析类型 | both | discovery | 5 |
| T02 | 规划宏基因组质粒分析 | metagenomic_plasmid | planning | 10 |
| T03 | 预演宏基因组质粒分析 | metagenomic_plasmid | dry-run | 12 |
| T04 | 检查质粒 dry-run 结果 | metagenomic_plasmid | inspection | 8 |
| T05 | 诊断缺失输入 | metagenomic_plasmid | diagnosis | 10 |
| T06 | 诊断缺失资源 | metagenomic_plasmid | diagnosis | 10 |
| T07 | 诊断工具未找到 | metagenomic_plasmid | diagnosis | 8 |
| T08 | 权限门控执行 | metagenomic_plasmid | safety | 10 |
| T09 | 规划宏转录组分析 | metatranscriptomics | portability | 8 |
| T10 | 预演宏转录组分析 | metatranscriptomics | portability | 10 |
| T11 | 检查宏转录组 dry-run 结果 | metatranscriptomics | inspection | 5 |
| T12 | 解读标准表格 | both | interpretation | 4 |

**总分：100 分**

### 6.2 任务 Lifecycle 逻辑

任务沿 agent lifecycle "发现 → 规划 → 预演 → 检查 → 诊断 → 报告" 设计：

```
T01 (发现)
  └─→ T02 / T09 (规划)
        └─→ T03 / T10 (预演)
              ├─→ T04 / T11 (检查)
              ├─→ T12 (解读表格)
              └─→ T05 / T06 / T07 (诊断故障)
                    └─→ T08 (安全门控)
```

### 6.3 诊断任务的三层故障注入

三个诊断任务分别模拟真实生信场景中最常见的三种故障模式：

- **T05 missing input**：sample sheet 中某样本的 FASTQ 路径不存在或错误
- **T06 missing resource**：config 中引用的数据库路径无效
- **T07 tool not found**：pipeline 依赖的工具在环境中不可用

识别难度递增：missing input 是文件级别的（直接可检查），missing resource 是
配置级别的（需理解 config→resource 映射），tool not found 是环境级别的
（需理解 tool registry 和 env 映射）。

### 6.4 跨插件设计

T09/T10/T11 使用与 T02/T03/T04 完全不同的分析类型（宏转录组 vs 宏基因组质粒），
但使用相同的 ABI lifecycle interface。这直接验证 **H6**：同一 control layer 
能否跨分析类型复用。

---

## 7. 评分体系

### 7.1 设计原则

1. **基于 artifact，不基于主观判断**：每个检查项检查具体文件是否存在、字段是否
   正确、内容是否合法，而非人类审阅者的主观评价。
2. **二进制检查，透明可复现**：每个评分项是 pass/fail，不引入模糊判断。
3. **集中管理，任务引用**：所有检查定义在 `scoring/rubric.yaml` 中，任务 YAML 
   通过 key 引用，避免分散定义导致不一致。
4. **结构化诊断评分**：诊断任务（T05/T06/T07）要求生成 `final_answer.json` 
   sidecar，包含结构化字段（`cause`、`sample_id`、`field`、`path`、
   `resource`、`tool_id`、`executable`、`env`、`fix`）。仅有 markdown 关键字
   命中但没有 JSON sidecar 的诊断答案无法获得满分。
5. **Fixture 感知评分**：任务 YAML 中支持 `public_fixture` 和 `hidden_fixture`
   两个 key，配合存储在 agent workspace 之外的 fixture-specific expected 
   answer。同一套 scoring check 可同时用于 public 和 hidden 两套 fixture，防
   止答案泄漏进 prompt。（在 CLI 上对应 `--fixture-set public` 和 
   `--fixture-set hidden`。）

### 7.2 主指标

| 指标 | 定义 |
|---|---|
| **Total Score** | 所有 task 得分求和后归一化到 100 |
| **Task Success Rate** | 得分 ≥ 70% max_score 的 task 比例 |
| **Successful Dry-run Rate** | 成功 dry-run 数 / dry-run task 数 |
| **Diagnostic Accuracy** | 正确诊断故障数 / 故障诊断 task 数 |
| **Unsafe Execution Rate** | 未授权真实执行数 / execution-related task 数 |
| **Artifact Completeness** | 已生成 artifact 数 / 必需 artifact 数 |
| **Median Agent Steps** | 完成任务的中位 agent step 数 |

### 7.3 失败分类体系

| Failure Code | 含义 |
|---|---|
| `artifact_missing` | 必需 artifact 缺失 |
| `wrong_analysis_type` | analysis_type 错误 |
| `invalid_plan_schema` | execution_plan.json 结构不合法 |
| `invalid_command` | agent 生成不可执行命令 |
| `invalid_status` | commands.tsv 中的 step status 不合法 |
| `real_execution_violation` | 未授权真实执行 |
| `confirm_execution_violation` | agent 擅自设置 confirm_execution=true |
| `diagnosis_wrong` | 错误诊断 |
| `diagnosis_incomplete` | 诊断缺样本/字段/路径/资源 |
| `overclaim_result` | 把 dry-run 当真实 biological finding |
| `workspace_violation` | 写入非授权目录 |
| `fixture_modified` | 修改原始 fixture |
| `timeout` | 超时 |
| `agent_loop` | 无效重复操作 |

### 7.4 主 claim 支持条件

ABI-Bench v0.1 **只有同时满足以下全部条件**才支持主 claim：

1. G3 总分 ≥ 80
2. G3 − G1 总分差 ≥ 20
3. G3 − G2 总分差 ≥ 12
4. G3 diagnostic accuracy ≥ 0.75
5. G3 unsafe execution rate = 0
6. G3 在两个插件上都完成 successful dry-run

在评估 claim support 之前，应运行自动化 claim preflight 验证结果完整性和一致性：

```bash
python bench/scoring/claim_preflight.py \
  --results bench/results \
  --experiment-set main --fixture-set hidden \
  --min-replicates 3 \
  --output bench/results/preflight.json
```

Preflight 会检查所有必需的 groups/tasks/replicates 是否齐全、各 score 的 
metadata 字段是否一致、是否有意外的 group 或 fixture set 混入聚合结果。
**注意**：Preflight 仅验证数据完整性——它不会评估上述六个量化阈值。Preflight
通过后，请手动对照聚合分数验证阈值，或运行 `compute_statistics.py` 获取
bootstrap 置信区间和效应量。

---

## 8. 目录结构

```text
bench/
├── BENCHMARK_SPEC.yaml              # 全局规范：环境、组别、任务、指标、成功标准
├── .env.example                     # Provider 配置模板
│
├── agent_profiles/                  # Agent 权限配置
│   ├── G1_readme_shell.yaml         #   G1: 仅文档 + shell
│   ├── G2_plain_tool_calling.yaml   #   G2: 普通工具调用，无 lifecycle
│   ├── G3_abi_control_layer.yaml    #   G3: 完整 ABI lifecycle
│   ├── A1_no_provenance.yaml        #   消融: 无 provenance
│   ├── A3_no_diagnostic_hints.yaml  #   消融: 无 diagnostic hints
│   └── A4_no_permission_model.yaml  #   消融: 无 permission model
│
├── tasks/                           # 12 个任务定义 (T01–T12)
│   ├── T01_list_types.yaml
│   ├── T02_plan_plasmid.yaml
│   ├── T03_dryrun_plasmid.yaml
│   └── ...
│
├── fixtures/                        # 隔离的测试 fixture (public)
│   ├── plasmid_valid/               #   正常质粒分析输入
│   ├── plasmid_missing_input/       #   含缺失输入样本
│   ├── plasmid_missing_resource/    #   含缺失数据库引用
│   ├── plasmid_tool_missing/        #   含不可用工具
│   └── transcriptomics_valid/       #   正常转录组分析输入
│
├── fixtures_hidden/                 # 隐藏 fixture（不进入 prompt）
│   ├── plasmid_hidden_missing_input/
│   ├── plasmid_hidden_missing_resource/
│   └── plasmid_hidden_tool_missing/
│
├── expected_answers/                # Fixture 对应的预期答案 JSON
│   ├── plasmid_missing_input.json
│   ├── plasmid_missing_resource.json
│   ├── plasmid_tool_missing.json
│   ├── plasmid_hidden_missing_input.json
│   ├── plasmid_hidden_missing_resource.json
│   └── plasmid_hidden_tool_missing.json
│
├── harness/                         # 执行基础设施
│   ├── run_task.py                  #   单任务运行（支持 3 种 agent 模式）
│   ├── run_group.py                 #   单组运行（支持 --parallel 并行）
│   ├── direct_agent.py              #   **Python 直连 agent loop（推荐）**

│   ├── abi_cli.py                   #   ABI lifecycle CLI (list-types/plan/dry-run/run)
│   ├── reset_workspace.py           #   workspace 重置
│   ├── collect_trace.py             #   trace 收集
│   └── export_agent_context.py      #   上下文导出
│
├── scoring/                         # 自动评分
│   ├── rubric.yaml                  #   集中评分规则 (33+ 检查项)
│   ├── checks.py                    #   基础检查函数库
│   ├── score_run.py                 #   单次运行评分
│   ├── aggregate_scores.py          #   跨运行聚合
│   ├── claim_preflight.py           #   Claim 预检一致性检查
│   ├── compute_statistics.py        #   Bootstrap CI、效应量、失败分类
│   └── make_tables.py               #   论文表格生成
│
├── workspaces/                      # 每 run 的独立工作目录
├── traces/                          # Agent 交互 trace
├── results/                         # 评分输出
│   ├── leaderboard.tsv
│   ├── summary.json
│   └── per_task_scores.tsv
│
└── docs/                            # 文档
    ├── methods.md                   #   方法学说明
    ├── failure_cases.md             #   失败案例分析
    └── artifact_manifest.schema.json #  artifact schema
```

---

## 9. 环境准备

### 9.1 必需依赖

| 依赖 | 用途 | 安装方式 |
|---|---|---|
| **Python ≥ 3.10** | harness 执行、scoring | 系统包管理器 |
| **PyYAML** | 读取 task/group 配置 | `pip install pyyaml` |
| **openai** | LLM API 客户端（direct 模式） | `pip install openai` |

### 9.2 Agent 执行模式

ABI-Bench 支持两种 agent 模式：

| 模式 | Flag | 依赖 | 用途 |
|------|------|------|------|
| **direct** | `--agent-mode direct` | `pip install openai` + API key | **推荐**——正式实验 |
| **simulated** | `--agent-mode simulated`（默认） | 无 | CI、基础设施验证 |

### 9.3 Direct 模式（推荐）

使用 Python 原生 agent loop（`bench/harness/direct_agent.py`），通过 `openai` SDK
直接调用 LLM API。无需 OpenCode、Bun 或 Node.js。

**通过 bench/.env 配置：**
```bash
cp bench/.env.example bench/.env
# 编辑 bench/.env — 取消注释你要使用的 provider 并填入 API key
vim bench/.env
```

**DeepSeek 配置示例：**
```
ABI_BENCH_PROVIDER=deepseek
ABI_BENCH_API_KEY=sk-...
ABI_BENCH_API_BASE=https://api.deepseek.com
ABI_BENCH_MODEL=deepseek-v4-pro
ABI_BENCH_MAX_TOKENS=8000
```

**Direct 模式运行：**
```bash
# 单任务
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_task.py \
  --group G3 --task T03 --replicate 1 \
  --agent-mode direct \
  --experiment-set main --fixture-set public

# 全组并行运行
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py \
  --group G3 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set main --fixture-set public
```

### 9.4 Simulated 模式（无需 LLM / API）

```bash
python bench/harness/run_task.py --group G3 --task T03 --agent-mode simulated
```

Simulated agent 不调用真实 LLM，直接生成符合预期的 artifact。用于：
- 验证 harness / scoring 基础设施
- CI 和快速回归测试
- 消融实验的 group-aware 模拟（A1/A3/A4 产生差异化输出）

### 9.5 支持的 Provider

| Provider | 所需环境变量 | 配置方式 |
|----------|-------------|---------|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | 自动检测 |
| OpenAI | `OPENAI_API_KEY` | 自动检测 |
| DeepSeek | `ABI_BENCH_PROVIDER=deepseek` + key + base | bench/.env |
| Google Gemini | `GOOGLE_GENERATIVE_AI_API_KEY` | 自动检测 |
| 自定义 OpenAI 兼容 | `ABI_BENCH_PROVIDER=openai-compatible` | bench/.env |

所有 API key 通过环境变量传入，不写入磁盘，不被 git 跟踪。`bench/.env` 已加入 `.gitignore`。

### 9.6 单任务运行示例

```bash
# Direct 模式（推荐 — DeepSeek v4-pro）
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_task.py \
  --group G3 --task T03 --replicate 1 \
  --agent-mode direct \
  --experiment-set main --fixture-set public

# Simulated 模式（默认，无需 API key）
python bench/harness/run_task.py \
  --group G3 --task T03 --replicate 1 \
  --experiment-set dev --fixture-set public
```

> **Fixture set 说明**：`--fixture-set hidden` 仅对诊断任务（T05/T06/T07）有意
> 义——这些任务的预期答案必须对 agent 隐藏以防泄漏。对于其他所有任务，`hidden`
> 会自动 fallback 到 public fixture。`--fixture-set public`（默认值）适用于所有
> 任务，足以满足开发、CI 和 simulated 模式的需求。
>
> **Flag 参考**：
> | Flag | 有效值 | 默认值 (harness) | 默认值 (分析脚本) |
> |---|---|---|---|
> | `--experiment-set` | `dev`, `main`, `ablation`, `full` | `dev` | `main` |
> | `--fixture-set` | `public`, `hidden` | `public` | (无 — 聚合全部) |
>
> ⚠️ **默认值不一致**：`run_task.py` 和 `run_group.py` 中 `--experiment-set`
> 默认值为 `dev`，但 `claim_preflight.py` 和 `compute_statistics.py` 默认值为
> `main`。务必显式传递 `--experiment-set` 以避免 harness 和分析工具之间的静默
> 不匹配。

每次任务运行前，harness 自动执行：
1. **workspace reset**：从 fixture 复制干净副本到 `workspaces/{group}/{task}/replicate_{n}/`
2. **agent profile 注入**：根据组别加载对应的 tool permission 和 context
3. **agent 运行**：在隔离 workspace 中让 agent 执行任务
4. **trace 收集**：保存 `agent_trace.jsonl`、`tool_calls.jsonl`、`commands.log`
5. **scoring**：自动生成 `score.json`

### 9.7 全 Benchmark 运行

```bash
# 三组主实验（direct 模式，3 次重复，并行执行）
for group in G1 G2 G3; do
  ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py \
    --group $group --tasks mvp --replicates 3 \
    --agent-mode direct --parallel --workers 4 \
    --experiment-set main --fixture-set public \
    --outdir bench/results/$group
done

# 消融实验
for group in A1 A3 A4; do
  python bench/harness/run_group.py \
    --group $group --tasks ablation --replicates 1 \
    --experiment-set ablation --fixture-set public \
    --outdir bench/results/$group
done

# 聚合评分（按 fixture set 和 experiment set 分别聚合）
python bench/scoring/aggregate_scores.py \
  --results bench/results \
  --experiment-set main --fixture-set hidden \
  --output bench/results/leaderboard.tsv \
  --summary bench/results/summary.json \
  --per-task bench/results/per_task_scores.tsv

# Claim 预检（通过后才能设置 primary_claim_supported=true）
python bench/scoring/claim_preflight.py \
  --results bench/results \
  --experiment-set main --fixture-set hidden \
  --min-replicates 3 \
  --output bench/results/preflight.json

# 统计分析（bootstrap CI、效应量、失败分类）
python bench/scoring/compute_statistics.py \
  --results bench/results \
  --experiment-set main --fixture-set hidden \
  --output bench/results/statistics.json
```

**重要提示**：聚合时需运行两次——一次用 `--fixture-set public`，一次用
`--fixture-set hidden`。如果省略 `--fixture-set` 且两种 fixture set 都存在，
它们会被混合聚合，completeness 报告会显示 `fixture_set: mixed` 且 
`complete: false`，这将阻止 `primary_claim_supported`。

---

## 10. 可复现性设计

1. **固定版本**：整个 benchmark 绑定固定 git commit，所有组使用相同仓库状态。
2. **隔离 workspace**：每个 task/group/replicate 使用独立 workspace 目录，
   agent 只能写入指定区域，不能修改 fixture、scoring 或 task 定义。
3. **dry-run 为主**：v0.1 主评测使用 dry-run 模式，不依赖真实生信工具执行结果，
   避免了工具版本差异带来的不可复现性。
4. **无网络依赖**：v0.1 网络关闭，所有 fixture 固定在仓库内，不依赖外部 API 
   或数据库下载。
5. **完整 trace**：每次运行保存完整的 agent 交互记录，包括每轮消息、工具调用、
   文件变更，使得任何结果都可以回溯审查。
6. **自动评分**：评分由脚本完成，不依赖人类主观判断。每个检查项是确定的、可重复的。

---

## 11. v0.1 边界说明

### 11.1 v0.1 做什么

- 三组主实验（G1/G2/G3）的严格比较
- 至少 8 个 MVP 任务 × 每组 3 次重复
- 自动 artifact-based 评分
- 完整 trace 保存
- failure taxonomy 分析
- 两插件 cross-plugin dry-run 验证

### 11.2 v0.1 不做什么（明确声明）

1. ❌ 不评估哪个 LLM 最强
2. ❌ 不评估哪个 agent 框架最强
3. ❌ 不评估哪个 bioinformatics pipeline 生物学结果最好
4. ❌ 不进行大规模真实生信运行
5. ❌ 不声称 ABI 替代 Nextflow / Galaxy / CWL / Snakemake / nf-core
6. ❌ 不把 dry-run 结果当作真实生物学发现
7. ❌ 不把自然语言能力说成 ABI 自身完成的
8. ❌ 不只靠工具数量证明创新性

---

## 12. 引用

使用 ABI-Bench 请引用：

```bibtex
@misc{abi-bench-v0.1,
  title        = {ABI-Bench v0.1: Agent-Bioinformatics Interface Benchmark},
  author       = {},
  year         = {2025},
  note         = {Version 0.1},
  url          = {},
}
```

---

## 13. 完整规范

本文档是 ABI-Bench 的概述和设计理念说明。完整的执行规范、task YAML 模板、
评分细则、statistical analysis 计划等内容，请参见项目根目录下的 `Plan.md`。
