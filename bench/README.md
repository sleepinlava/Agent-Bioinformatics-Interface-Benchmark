# ABI-Bench v0.9

## Agent-Bioinformatics Interface Benchmark

---

## 目录

1. [什么是 ABI-Bench](#1-什么是-abi-bench)
2. [设计动机](#2-设计动机)
3. [实验假设体系](#3-实验假设体系)
4. [实验组设计](#4-实验组设计)
5. [八维能力评估模型](#5-八维能力评估模型)
6. [任务设计](#6-任务设计)
7. [评分体系](#7-评分体系)
8. [环境准备](#8-环境准备)
9. [快速开始](#9-快速开始)
10. [执行流程](#10-执行流程)
11. [目录结构](#11-目录结构)
12. [可复现性设计](#12-可复现性设计)
13. [v0.1 边界说明](#13-v01-边界说明)
14. [开发里程碑](#14-开发里程碑)

---

## 1. 什么是 ABI-Bench

**ABI-Bench**（Agent-Bioinformatics Interface Benchmark）是一个用于评估 **LLM Agent 操作生物信息学 workflow 能力**的基准测试。

它回答的唯一核心问题是：

> 在相同 LLM、相同 agent harness、相同仓库、相同任务、相同 fixture 条件下，一个 **ABI control layer**（Agent-Bioinformatics Interface 中间层）是否比 **README + Shell** 或 **Plain Tool Calling** 更能让 agent 稳定完成生物信息学 workflow 的规划、dry-run、检查、诊断、恢复和报告生成。

ABI-Bench 的核心设计原则是 **控制变量**：固定 LLM、agent harness、仓库、fixture，唯一的变量是 agent 可用的接口层（ABI control layer vs 普通 shell vs 普通 tool calling）。

---

## 2. 设计动机

### 2.1 为什么需要 ABI

LLM agent 操作生信 workflow 面临五大特有困难：

1. **lifecycle 缺失**：生信分析有"发现 → 规划 → 预演 → 检查 → 诊断 → 报告"的生命周期，但普通 shell 或纯工具调用接口不提供这一语义，导致 agent 跳步骤或无法系统性诊断。
2. **provenance 缺失**：生信可复现性依赖完整的溯源信息（输入路径、工具版本、数据库、命令序列），没有结构化的 provenance artifact，agent 无法有效检查或诊断。
3. **结果解读困难**：生信 pipeline 输出大量表格（丰度表、表达矩阵），agent 需要理解标准表结构才能正确解读，不能把空表当最终结果。
4. **安全边界模糊**：生信涉及大量计算和数据库下载，agent 需要明确的 plan→dry-run→确认→执行边界。
5. **跨领域复用性**：生物信息学包含多种分析类型，同一 control layer 应能跨分析类型复用。

### 2.2 外部方法论吸收

| 来源 | 核心理念 | ABI-Bench 做法 |
|---|---|---|
| **GAIA** | 真实任务、工具使用、多步推理 | 真实仓库 + 真实 fixture + 产出 artifact，不只看 final answer |
| **SWE-bench** | 固定 repo state、自动测试判定 | 固定 commit、独立 workspace、脚本评分、`score.json` |
| **AgentBench** | 多轮交互中的推理/决策/失败类型 | 保存 trace、记录 step 数、标记 failure_code |
| **StableToolBench** | 避免外部状态漂移 | dry-run 为主、无网络依赖、fixture 内嵌 |
| **BioCoder** | 生信领域特异性 | 包含 sample sheet、FASTQ path、tool registry 等领域对象 |
| **LAB-Bench** | 评测 practical biology capabilities | 测 planning、database 配置、结果解读、不过度生物学解释 |
| **BixBench** | 多步轨迹和结果解释 | 要求中间 artifact、区分 dry-run 与真实 biological finding |

---

## 3. 实验假设体系

### 3.1 主假设

**H1：ABI control layer 能显著提高 LLM agent 对生信 workflow 的 agent-operability。**

### 3.2 次级假设

| 假设 | 内容 | 验证方法 |
|---|---|---|
| **H2** | ABI 优势来自 lifecycle-level control，而非"多给了工具" | G3 vs G2 比较 |
| **H3** | provenance artifacts 能提高诊断与恢复能力 | A1 消融实验 |
| **H4** | standard tables 能提高结果理解能力 | A2 消融 (v0.2) |
| **H5** | permission model 能降低未授权执行风险 | A4 消融实验 |
| **H6** | 同一 ABI 能跨分析类型复用 | T09/T10 跨插件任务 |

---

## 4. 实验组设计

### 4.1 三组主实验

| 组别 | 名称 | Agent 可用的信息 | 目的 |
|---|---|---|---|
| **G1** | README + Shell | README、docs、CLI help、shell、文件读写 | 非结构化文档 + shell 的能力上限 |
| **G2** | Plain Tool Calling | 普通工具函数、CLI wrapper、文件读写 | 纯工具暴露（无 lifecycle）是否足够 |
| **G3** | ABI Control Layer | ABI lifecycle、JSON envelope、provenance、standard tables、permission model | **ABI 中间层的完整贡献** |

**所有三组使用相同的 LLM、agent harness、仓库 commit、task fixture。唯一变量是接口层。**

### 4.2 消融组

| 组别 | 移除内容 | 影响的维度 |
|---|---|---|
| **A1** no-provenance | `commands.tsv`、`resolved_inputs.tsv`、`run_summary.json` | inspect、diagnosis、recovery |
| **A3** no-diagnostic-hints | 结构化 `error_code` / `diagnostic_hints` | fault localization |
| **A4** no-permission-model | `confirmation_required` gating | execution safety |

> **注：A2 缺失说明** — A2（no-standard-tables）在 v0.1 scoping 阶段被移除，因为 standard tables 的贡献已通过 G1/G2 基线对比间接覆盖。编号断层是有意为之，在论文中会明确说明。

### 4.3 固定变量

| 变量 | 固定值 |
|---|---|
| Agent harness | Python 直连 agent（`direct_agent.py`） |
| LLM | 同一版本，所有组相同 |
| Temperature | 0（最低可用值） |
| Max agent steps | 50 |
| Timeout | 每任务 20 分钟 |
| Workspace | 每 task/group/replicate 独立 |
| Network | v0.1 关闭 |
| 真实生信执行 | v0.1 禁止（dry-run 模式） |

---

## 5. 八维能力评估模型

| 能力维度 | 内容 | 对应任务 |
|---|---|---|
| **可发现性** (Discoverability) | 发现可用的 analysis types | T01 |
| **可规划性** (Plannability) | 构建合法 execution plan | T02, T09 |
| **可预演性** (Dry-runnability) | 完成 dry-run 并生成完整 artifact | T03, T10 |
| **可检查性** (Inspectability) | 读取 provenance 并给出下一步 | T04, T11 |
| **可诊断性** (Diagnosability) | 定位 missing input/resource/tool | T05, T06, T07 |
| **安全性** (Safety) | 遵守执行确认边界 | T08 |
| **可解释性** (Interpretability) | 理解标准表结构，不过度生物学解读 | T12 |
| **可移植性** (Portability) | 同一 ABI 驱动两类分析 | T09, T10, T11 |

---

## 6. 任务设计

### 6.1 任务总览

| 任务 | 名称 | 插件 | 类型 | 分值 |
|---|---|---|---|---|
| T01 | List analysis types | both | discovery | 5 |
| T02 | Plan metagenomic plasmid | metagenomic_plasmid | planning | 10 |
| T03 | Dry-run metagenomic plasmid | metagenomic_plasmid | dry-run | 12 |
| T04 | Inspect plasmid dry-run | metagenomic_plasmid | inspection | 8 |
| T05 | Diagnose missing input | metagenomic_plasmid | diagnosis | 10 |
| T06 | Diagnose missing resource | metagenomic_plasmid | diagnosis | 10 |
| T07 | Diagnose tool-not-found | metagenomic_plasmid | diagnosis | 8 |
| T08 | Permission-gated run | metagenomic_plasmid | safety | 10 |
| T09 | Plan metatranscriptomics | metatranscriptomics | portability | 8 |
| T10 | Dry-run metatranscriptomics | metatranscriptomics | portability | 10 |
| T11 | Inspect metatranscriptomics | metatranscriptomics | inspection | 5 |
| T12 | Interpret standard tables | both | interpretation | 4 |

**v0.1 总分：100 分** | **v0.6 总分（47 任务）：~450 分** | **v0.9 总分（61 任务，7 套件）：~600 分**

### 6.2 任务生命周期链

任务沿着 agent lifecycle 设计，而非随机组合：

```
T01 (discovery)
  └─→ T02 / T09 (planning)
        └─→ T03 / T10 (dry-run)
              ├─→ T04 / T11 (inspect)
              ├─→ T12 (interpret tables)
              └─→ T05 / T06 / T07 (diagnose)
                    └─→ T08 (safety gate)
```

### 6.3 三层故障注入

| 任务 | 故障类型 | 难度 |
|---|---|---|
| T05 | missing input（文件路径不存在） | 文件级 |
| T06 | missing resource（数据库未安装） | 配置级 |
| T07 | tool not found（工具不在 PATH） | 环境级 |

难度递增：直接可检查 → 需理解 config→resource 映射 → 需理解 tool registry 和 env。

### 6.4 v0.6 新增任务模块（T36-T47）

v0.6 在 v0.1-v0.5 基础上新增 12 个任务，覆盖 4 个新模块：

| 模块 | 任务 | 说明 |
|---|---|---|
| **Figure Validation** | T36, T37, T38 | Sciplot 科学图表验证、诊断、数据一致性检查 |
| **Progressive Repair** | T39, T40, T41 | 单故障恢复、多故障恢复、资源自配置 |
| **Cross-Platform** | T42, T43, T44 | Local/Nextflow/Docker 跨平台输出一致性、溯源审计 |
| **Multi-Agent** | T45, T46, T47 | Planner-reviewer 协作、跨模型验证（比较独立 review）、零样本迁移 |

### 6.5 v0.9 新增任务模块（T59-T61）与评测套件

v0.9 新增 3 个跨插件隐藏鲁棒性诊断任务，并将全部 61 个任务按 claim role 分为 7 个评测套件：

| 套件 | Claim Role | 任务数 | 说明 |
|------|-----------|--------|------|
| `causal_core_v0_8` | primary_causal | 24 | 主因果评估，提示词不命名 ABI |
| `hidden_robustness_v0_9` | causal_robustness | 3 (T59-T61) | 跨插件 hidden diagnosis，public/hidden 配对 fixture |
| `mechanism_probes_v0_8` | mechanism_descriptive | 32 | ABI 原生机制探针，不与主因果混合 |
| `real_execution_case_studies_v0_8` | case_study | 5 (T31-T35) | 真实执行案例证据 |
| `heldout_plugin_v0_8` | external_validity | 3 (T48-T50) | 外部有效性：easymetagenome + viral_viwrap |
| `ablation_v0_8` | component_ablation | 6 (T03-T08) | 组件消融（附录） |
| `full_descriptive_v0_8` | descriptive_only | 61 (T01-T61) | 全量描述性覆盖 |

**T59-T61 设计要点：**
- T59：RNA-seq genome index 缺失诊断（`rnaseq_hidden_missing_resource`）
- T60：WGS AMRFinder 数据库缺失诊断（`wgs_hidden_single_missing_resource`）
- T61：Shotgun metagenomics Kraken2 数据库缺失诊断（`easymeta_hidden_single_missing_resource`）
- 每题均有 public/hidden 两个语义等价但标识符不同的 fixture
- 所有实验组 (G1-G4) 均可运行，单独报告 G3−G1/G3−G2/G3−G4

**T36-T47 证据评分变更（v0.9）：**
- 不再使用 `check_final_answer_contains` 关键词匹配
- 改为交叉验证：final_answer.json 字段、workspace 文件、配置变更、agent trace
- T46 改为比较两个独立预生成的 review artifact，不再要求模型"假装另一个模型"
- 安全检查在 trace 缺失时失败，不再默认通过
- 静态审计 (`audit_benchmark.py --strict`) 检测未知评分函数、fixture 多故障混杂、rubric 间接关键词评分

---

## 7. 评分体系

### 7.1 三项设计原则

1. **基于 artifact，不基于主观**：检查文件是否存在、字段是否正确、内容是否合法
2. **二进制 pass/fail**：不引入"部分正确"的模糊判断
3. **集中管理，任务引用**：所有 check 定义在 `scoring/rubric.yaml`，任务 YAML 通过 key 引用

### 7.2 主指标

| 指标 | 定义 |
|---|---|
| **Total Score** | 所有 task 得分求和后归一化到 100 |
| **Task Success Rate** | 得分 ≥ 70% max_score 的 task 比例 |
| **Successful Dry-run Rate** | 成功 dry-run 数 / dry-run task 数 |
| **Diagnostic Accuracy** | 正确诊断数 / 诊断 task 数 |
| **Unsafe Execution Rate** | 未授权真实执行数 / 执行相关 task 数 |

### 7.3 失败分类体系

| Failure Code | 含义 |
|---|---|
| `artifact_missing` | 必需 artifact 缺失 |
| `invalid_status` | step status 不合法 |
| `real_execution_violation` | 未授权真实执行 |
| `diagnosis_wrong` / `diagnosis_incomplete` | 错误诊断 / 不完整 |
| `overclaim_result` | 把 dry-run 当真实 biological finding |
| `timeout` / `agent_loop` | 超时 / 无效重复 |

### 7.4 主 claim 支持条件

ABI-Bench v0.1 **仅当以下全部满足**时，才支持"ABI 改进了 agent-operability"的主 claim：

1. G3 总分 ≥ 80
2. G3 - G1 总分差 ≥ 20
3. G3 - G2 总分差 ≥ 12
4. G3 diagnostic accuracy ≥ 0.75
5. G3 unsafe execution rate = 0
6. G3 在两个插件上都完成 successful dry-run

---

## 8. 环境准备

### 8.1 必需依赖

| 依赖 | 用途 | 安装方式 |
|---|---|---|
| **Python ≥ 3.10** | harness 执行、scoring | 系统包管理器 |
| **PyYAML** | 读取 task/group 配置 | `pip install pyyaml` |
| **openai** | LLM API 客户端（direct 模式） | `pip install openai` |

### 8.2 Agent 执行模式

| 模式 | Flag | 依赖 | 用途 |
|------|------|------|------|
| **direct** | `--agent-mode direct` | `pip install openai` + API key | **推荐**——正式实验 |
| **simulated** | `--agent-mode simulated`（默认） | 无 | CI、基础设施验证 |

### 8.3 Direct 模式配置（推荐）

```bash
# 安装依赖
pip install pyyaml openai

# 配置 bench/.env
cp bench/.env.example bench/.env
# 编辑 bench/.env — 填入你的 provider 和 API key

# 运行
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py \
  --group G3 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set main --fixture-set public
```

---

## 9. 快速开始

```bash
# 1. 安装依赖
pip install pyyaml openai

# 2. 配置 LLM provider
cp bench/.env.example bench/.env
# 编辑 bench/.env，填入你的 provider 和 API key
# 支持: anthropic, openai, deepseek, google, openai-compatible

# 3. 模拟模式验证（不依赖 LLM，纯本地跑评分逻辑）
python bench/harness/run_group.py --group G3 --tasks T01,T02,T03 --replicates 1

# 4. 并行模拟（加速验证）
python bench/harness/run_group.py --group G3 --tasks mvp --replicates 1 --parallel --workers 4

# 5. Direct 模式真实运行（推荐）
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py \
  --group G3 --tasks mvp --replicates 3 --agent-mode direct --parallel --workers 4

# 6. 聚合评分（指定套件）
python bench/scoring/aggregate_scores.py \
  --results bench/results --experiment-set main --fixture-set public \
  --suite causal_core_v0_8 \
  --output bench/results/leaderboard.tsv --summary bench/results/summary.json

# 7. 统计分析
python bench/scoring/claim_preflight.py \
  --results bench/results --experiment-set main --fixture-set public \
  --suite causal_core_v0_8 --min-replicates 5
python bench/scoring/compute_statistics.py \
  --results bench/results --experiment-set main --fixture-set public \
  --suite causal_core_v0_8 \
  --output bench/results/statistics.json

# 8. 静态设计审计（实验前必须通过）
python bench/validation/audit_benchmark.py --strict
```

---

## 10. 执行流程

### 10.1 单任务执行（5 步）

```
[1/5] Reset workspace      从 fixture 复制干净副本
[2/5] Export agent context  根据 group profile 注入 tool permission
[3/5] Launch agent          启动 direct 或模拟 agent
[4/5] Collect traces        保存 agent_trace.jsonl / tool_calls.jsonl
[5/5] Score                 自动生成 score.json
```

### 10.2 运行模式与并行加速

| 模式 | 用途 | 命令 |
|---|---|---|
| **direct** | **推荐**——Python 直连 LLM API，快速可靠 | `--agent-mode direct` |
| **simulated** | 本地快速验证评分逻辑，无需 LLM/API | `--agent-mode simulated`（默认） |

Direct 模式下，agent 通过 `openai` SDK 直接调用 LLM API，在 Python 进程内完成完整的
tool-calling 循环。无需启动外部 server，无需轮询。

模拟模式下，harness 为每个 group/task 生成对应的 artifact 和 final_answer。消融组
（A1/A3/A4）的模拟 agent 会产生**刻意不完整**的输出——A1 不生成 provenance、A3 
诊断模糊、A4 绕过 permission gate。这使得评分逻辑可以在不消耗 API 调用的情况下完整验证。

**并行执行**（`--parallel --workers N`）：同一 replicate batch 内的 task 通过线程池
并发执行，每个 task 使用独立的 workspace/trace/results 目录，互不冲突。

### 10.3 三组主实验

```bash
for group in G1 G2 G3; do
  ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py \
    --group $group --tasks mvp --replicates 3 \
    --agent-mode direct --parallel --workers 4 \
    --experiment-set main --fixture-set public \
    --outdir bench/results/$group
done

python bench/scoring/aggregate_scores.py \
  --results bench/results --experiment-set main --fixture-set public \
  --output bench/results/leaderboard.tsv --summary bench/results/summary.json
```

---

## 11. 目录结构

```text
bench/
├── BENCHMARK_SPEC.yaml              # 全局规范
├── README.md                        # 本文档
│
├── agent_profiles/                  # Agent 权限配置 (YAML)
│   ├── G1_readme_shell.yaml         #   G1: 仅文档 + shell
│   ├── G2_plain_tool_calling.yaml   #   G2: 普通工具调用
│   ├── G3_abi_control_layer.yaml    #   G3: 完整 ABI lifecycle
│   ├── A1_no_provenance.yaml        #   消融: 移除 provenance
│   ├── A3_no_diagnostic_hints.yaml  #   消融: 移除 diagnostic hints
│   └── A4_no_permission_model.yaml  #   消融: 移除 permission model
│
├── tasks/                           # 61 个任务定义 (YAML, T01-T61)
│   ├── T01_list_types.yaml
│   ├── ...
│   └── T61_easymeta_hidden_diagnosis.yaml
│
├── validation/                      # 静态设计审计 (v0.9)
│   └── audit_benchmark.py           #   检测未知评分函数、fixture 多故障混杂等
│
├── evaluation_suites.yaml           # v0.9 套件定义 (7 suites)
│
├── fixtures/                        # 隔离测试 fixture
│   ├── plasmid_valid/
│   ├── plasmid_missing_input/
│   ├── plasmid_missing_resource/
│   ├── plasmid_tool_missing/
│   └── transcriptomics_valid/
│
├── harness/                         # 执行基础设施 (Python + TypeScript)
│   ├── run_task.py                  #   单任务 5 步编排（支持 2 种 agent 模式）
│   ├── run_group.py                 #   批量组运行（支持 --parallel 并行）
│   ├── direct_agent.py              #   **Python 直连 agent loop（推荐）**
│   ├── reset_workspace.py           #   workspace 重置
│   ├── export_agent_context.py      #   agent 上下文导出
│   ├── collect_trace.py             #   trace 收集
│   ├── diagnosis.py                 #   共享诊断工具（供 simulated agent 和 abi_cli 共用）
│   └── abi_cli.py                   #   ABI lifecycle CLI（G3 组 agent 可调用）
│
├── scoring/                         # 自动评分 (Python)
│   ├── rubric.yaml                  #   集中评分规则
│   ├── checks.py                    #   基础检查函数库
│   ├── score_run.py                 #   单次运行评分
│   ├── aggregate_scores.py          #   跨运行聚合
│   ├── claim_preflight.py           #   Claim 预检一致性检查
│   ├── compute_statistics.py        #   Bootstrap CI、效应量、失败分类
│   └── make_tables.py               #   论文表格生成
│
├── workspaces/                      # 每 run 的独立工作目录
├── traces/                          # Agent 交互记录
├── results/                         # 评分输出 (leaderboard, summary)
└── docs/                            # 方法学文档
```

---

## 12. 可复现性设计

1. **固定版本**：整个 benchmark 绑定固定 git commit
2. **隔离 workspace**：每 task/group/replicate 独立目录，agent 不能修改 fixture/scoring
3. **dry-run 为主**：v0.1 主评测不依赖真实生信工具执行结果
4. **无网络依赖**：v0.1 网络关闭，fixture 内嵌
5. **完整 trace**：每 run 保存完整 agent 交互记录
6. **自动评分**：脚本判断，无人类主观因素

---

## 13. v0.1 边界说明

### v0.1 做什么

- 三组主实验（G1/G2/G3）严格比较
- MVP 8 个任务 × 3 次重复
- 自动 artifact-based 评分
- 完整 trace 保存与 failure taxonomy 分析
- 两插件 cross-plugin dry-run 验证

### v0.1 不做什么（明确声明）

1. ❌ 不评估哪个 LLM 最强
2. ❌ 不评估哪个 agent 框架最强
3. ❌ 不评估哪个 pipeline 生物学结果最好
4. ❌ 不做大规模真实生信运行
5. ❌ 不声称 ABI 替代 Nextflow / Galaxy / CWL / Snakemake / nf-core
6. ❌ 不把 dry-run 结果当真实生物学发现
7. ❌ 不把 LLM 的自然语言能力归功于 ABI
8. ❌ 不只靠工具数量证明创新性

---

## 14. 开发里程碑

| Phase | 产品 | 关键交付 |
|---|---|---|
| **0** 冻结规范 | 规范完成 | `BENCHMARK_SPEC.yaml`、agent profiles、task YAML |
| **1** 准备 fixture | fixture 就绪 | 5 个 fixture（正常 + 三种故障 + 跨插件） |
| **2** 实现评分 | scoring 可用 | `checks.py`、`score_run.py`、`aggregate_scores.py` |
| **3** G3 自测 | 验证流程 | 单 replicate 排除 harness bug |
| **4** 三组实验 | 主结果 | 3 组 × 8 任务 × 3 replicate |
| **5** 消融实验 | 组件贡献 | A1/A3/A4 选择性消融 |
| **6** 论文材料 | 产出 | methods、leaderboard、failure analysis |
| **7** v0.7 扩展 | 新插件 + 特性任务 | T48-T58：easymetagenome、viral_viwrap、ABI query、doctor agent、sciplot CLI |
| **8** v0.8 套件化 | 因果完整性 | 7 套件架构，mechanism/causal 分离，suite-aware scoring |
| **9** v0.9 证据评分 | 鲁棒性 | T36-T47 证据评分，T46 独立 review 对比，T59-T61 hidden robustness，静态审计 |

---

完整执行规范见项目根目录下 `Plan.md`（中文）和 `bench/docs/methods.md`（英文）。
`bench/docs/evaluation_design_v0_9.md` 包含 v0.9 证据评分与隐藏鲁棒性设计细节。
