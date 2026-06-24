# ABI-Bench v0.9

> [English Version (英文版)](README.md)

## Agent-Bioinformatics Interface Benchmark · 智能体-生物信息学接口基准测试

> 📋 **提交指南**: [English](SUBMISSION.md) | [中文版](SUBMISSION.zh.md)

---

## 1. 什么是 ABI-Bench

**ABI-Bench**（Agent-Bioinformatics Interface Benchmark）用于评估结构化的
**ABI 控制层**是否能提升通用 LLM agent 操作生物信息学工作流的可靠性。v0.9
将 T36–T47 改为基于结构化产物、workspace 文件和 trace 的证据评分，并新增
RNA-seq、WGS 和 shotgun metagenomics 的 public/hidden 配对诊断任务。v0.8
将主因果任务与 ABI 原生机制探针、真实执行案例分离，避免把“题目要求调用 ABI”
误计为 ABI 对通用 Agent 的增益。此前 v0.6
聚焦**脚手架效应**（scaffolding effect）：ABI 能否降低模型完成可靠生信操作
所需的能力门槛，并将评估扩展到真实生信工具执行 (T31-T35)、科学图表验证
(T36-T38)、渐进式修复 (T39-T41)、跨平台等价性 (T42-T44) 和多智能体协作
(T45-T47)。

ABI-Bench 回答三个核心问题：

> 1. **ABI 控制层**能否比非结构化基线（README + Shell、Plain Tool Calling）
>    更可靠地帮助 agent 完成生信工作流的规划、预演、检查、诊断和报告？

> 2. ABI 是否对**弱模型帮助更大**——作为领域脚手架降低能力门槛，
>    而非对强模型的能力倍增器？

> 3. 同一套 ABI 生命周期能否**跨多个工作流插件**复用（宏基因组质粒、
>    宏转录组、16S 扩增子、RNA-seq 表达、WGS 细菌、easymetagenome、
>    viral_viwrap）？

---

## 2. 核心声明 (v0.9)

### 2.1 主声明：ABI 提升 Agent 可操作性

跨多个 LLM（强/中/弱）和五种工作流插件，G3（ABI 控制层）一致性地
优于 G1（README + Shell）和 G2（Plain Tool Calling）。效果通过顺序
随机区组实验设计和 bootstrap 置信区间验证。

### 2.2 脚手架声明：ABI 帮助弱模型更多

**脚手架增益**（Scaffolding Gain）= (G3−G1)_weak − (G3−G1)_strong，
量化弱模型比强模型多受益的程度。正增益表明 ABI 的主要价值在于降低
模型推理负担，而非为已有强模型赋能。

### 2.3 跨插件声明：ABI 生命周期可移植

同一套 ABI 生命周期（list-types → plan → dry-run → inspect → report）
在 metagenomic_plasmid、metatranscriptomics、amplicon_16s、rnaseq_expression
和 wgs_bacteria 五个插件上无需修改即可工作。

### 2.4 G4 对照：生命周期 API > 等价文档

G4 获得与 G3 的 ABI 生命周期相同信息量的静态文档，但没有生命周期 API。
G3 > G4 证明结构化的生命周期接口（CLI + JSON envelope + 标准 artifact 路径）
的价值超出了单纯提供更多文档。

### 2.5 图表验证声明：ABI 赋能科学图表质量控制

ABI 的 sciplot 集成使 agent 能够验证、诊断和检查发表级科学图表的数据一致性
(T36-T38)。G3 图表验证通过率超过基线。

### 2.6 渐进式修复声明：ABI 赋能自主错误恢复

ABI 的诊断提示和资源清单使 agent 能够从单故障和多故障场景中恢复，包括自主
资源配置 (T39-T41)。

### 2.7 跨平台声明：ABI 流水线平台可移植

ABI 工作流在本地、Docker 和 Nextflow 执行平台上产生等价输出，拥有完整的
溯源审计轨迹 (T42-T44)。

### 2.8 多智能体声明：ABI 生命周期支持智能体协作

ABI 的结构化 JSON envelope 和标准 artifact 路径使规划者-审查者协作、
跨模型验证（比较两个独立生成的 review artifact）和零-shot 平台迁移成为可能 (T45-T47)。

### 2.9 证据评分声明：基于 Artifact 的评分比关键词匹配更可靠

v0.9 将 T36–T47 的评分从关键词匹配（`final_answer_contains`）改为基于
证据的评分：JSON 字段校验、workspace 文件交叉比对、配置变更验证和 trace
检查。这消除了自报声明的假阳性，确保 agent 实际执行了操作而非仅描述了它。

### 2.10 隐藏鲁棒性声明：诊断能力可迁移至未见过的插件

T59–T61 测试诊断能力是否可迁移至 RNA-seq、细菌 WGS 和 shotgun metagenomics，
使用 public/hidden 配对 fixture（相同故障类型，不同标识符和路径）。这些任务
构成独立的 `hidden_robustness_v0_9` 套件，与主因果评估分开报告。

---

## 3. 实验组架构

| 组 | 名称 | 核心差异 |
|---|------|---------|
| **G1** | README + Shell | 仅文档 + bash |
| **G2** | Plain Tool Calling | 通用工具，无生命周期 |
| **G3** | ABI Control Layer | 完整 ABI CLI + 生命周期 API |
| **G4** | Info-Matched Docs | 与 G3 等量文档，无生命周期 API |
| **A1** | No Provenance | G3 减去溯源信息（附录） |
| **A3** | No Diagnostic Hints | G3 减去结构化错误码（附录） |
| **A4** | No Permission Model | G3 减去确认门控（附录） |

---

## 4. 快速开始

### 环境要求

- Python ≥ 3.10
- `pip install pyyaml openai scipy`
- 开发工具（可选）：`pip install pytest ruff`

### 配置

复制 `bench/.env.example` 到 `bench/.env` 并设置 provider 凭证。
工具支持任何兼容 OpenAI 的接口，包括自托管模型（Ollama、vLLM、llama.cpp）：

```bash
# 本地模型示例 (vLLM)
ABI_BENCH_PROVIDER=openai-compatible
ABI_BENCH_API_BASE=http://localhost:8000/v1
ABI_BENCH_MODEL=Qwen3-14B
ABI_BENCH_TEMPERATURE=0.3
ABI_BENCH_MAX_TOKENS=4096
```

所有配置选项（包括重试设置、推理模型支持和 provider 专用说明）见
`bench/.env.example`。

### 运行单个任务

```bash
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_task.py \
  --group G3 --task T01 --replicate 1 \
  --agent-mode direct --experiment-set dev --fixture-set public
```

### 运行整组

```bash
ABI_BENCH_MAX_TOKENS=8000 python bench/harness/run_group.py \
  --group G3 --tasks causal_core_v0_8 --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set main --fixture-set public
```

### 多模型实验

```bash
python bench/harness/run_multi_model.py \
  --tier all --groups G1,G2,G3,G4 \
  --tasks causal_core_v0_8 --replicates 5 \
  --experiment-set paper --fixture-set public \
  --workers 4 --seed 42
```

### 评分与分析

```bash
# 聚合所有分数
python bench/scoring/aggregate_scores.py \
  --results bench/results --experiment-set main \
  --suite causal_core_v0_8 \
  --output bench/results/leaderboard.tsv \
  --summary bench/results/summary.json

# 统计分析（含脚手架指标）
python bench/scoring/compute_statistics.py \
  --results bench/results --experiment-set main \
  --suite causal_core_v0_8 \
  --output bench/results/statistics.json
```

正式运行前执行静态设计审计：

```bash
python bench/validation/audit_benchmark.py --strict
python bench/scoring/claim_preflight.py \
  --results bench/results --experiment-set paper --fixture-set hidden \
  --suite causal_core_v0_8 --min-replicates 5
```

v0.9 的证据评分与隐藏鲁棒性设计见
[`bench/docs/evaluation_design_v0_9.md`](bench/docs/evaluation_design_v0_9.md)。

---

## 5. 任务模块

| 模块 | 任务 | 描述 |
|------|------|------|
| 发现 | T01 | 列出可用分析类型 |
| 规划 | T02, T09, T13, T15, T17 | 跨插件创建执行计划 |
| 预演 | T03, T10, T14, T16, T18 | 无真实执行验证计划 |
| 检查 | T04, T11, T25, T26 | 读取溯源，识别占位符 |
| 诊断 | T05, T06, T07 | 单故障诊断 |
| 复杂诊断 | T22, T23 | 多故障和干扰诊断 |
| 安全 | T08, T24 | 权限边界和压力测试 |
| 解读 | T12, T19 | 表格解读，过度声明防护 |
| 作业控制 | T20 | 提交、监控、取消、检索 |
| 跨插件 | T21 | 零-shot 新插件操作 |
| 合约 | T27, T28, T29 | 合约检查、Nextflow 导出、违规检测 |
| 报告质量 | T30 | 报告完整性和结构 |
| 真实执行 | T31-T35 | 真实生信工具执行 (v0.5) |
| 图表验证 | T36-T38 | Sciplot 图表验证、诊断、数据一致性 (v0.6) |
| 渐进式修复 | T39-T41 | 单故障与多故障恢复、资源自配置 (v0.6) |
| 跨平台 | T42-T44 | 本地/Nextflow/Docker 比较、溯源审计 (v0.6) |
| 多智能体 | T45-T47 | 规划者-审查者、跨模型验证、零-shot 迁移 (v0.6) |
| 隐藏诊断 | T59-T61 | 跨插件隐藏鲁棒性：RNA-seq、WGS、easymetagenome (v0.9) |

---

## 6. 评测套件 (v0.9)

v0.9 将 61 个任务组织为 7 个评测套件，各有明确的 claim role，防止机制
任务污染主因果评估：

| 套件 | Claim Role | 任务数 | 实验组 |
|------|-----------|--------|--------|
| `causal_core_v0_8` | primary_causal | 24 任务 (T01–T19, T25–T26, T48–T50) | G1, G2, G3, G4 |
| `hidden_robustness_v0_9` | causal_robustness | 3 任务 (T59–T61) | G1, G2, G3, G4 |
| `mechanism_probes_v0_8` | mechanism_descriptive | 32 任务 | G3, A1, A3, A4 |
| `real_execution_case_studies_v0_8` | case_study | 5 任务 (T31–T35) | G3 |
| `heldout_plugin_v0_8` | external_validity | 3 任务 (T48–T50) | G1, G2, G3, G4 |
| `ablation_v0_8` | component_ablation | 6 任务 (T03–T08) | G3, A1, A3, A4 |
| `full_descriptive_v0_8` | descriptive_only | 61 任务 (T01–T61) | 全组 |

使用 `--suite <name>` 参数在 `aggregate_scores.py`、`compute_statistics.py`
和 `claim_preflight.py` 中指定套件。

---

## 7. 仓库结构

```
bench/
  harness/          # Agent 循环、ABI CLI、工作区重置、追踪收集
    direct_agent.py   # LLM API agent 循环 (OpenAI SDK)
    abi_cli.py        # ABI 生命周期 CLI
    run_task.py       # 单任务运行器
    run_group.py      # 组运行器（并行）
    run_sequential.py # 顺序随机区组运行器
    run_multi_model.py  # v0.3: 多模型实验运行器
    path_guard.py     # 文件系统访问控制
  scoring/          # 评分框架
    score_run.py      # 单次运行评分器
    checks.py         # 检查函数实现
    rubric.yaml       # 集中化检查定义
    aggregate_scores.py  # 分数聚合（支持 --suite）
    compute_statistics.py  # Bootstrap CI、效应量、脚手架分析
    claim_preflight.py  # 提交前完整性检查
  validation/       # 静态设计审计 (v0.9)
    audit_benchmark.py  # 检测未知评分函数、fixture 多故障混杂、
                       #   rubric 间接关键词评分、per-plugin 字段不匹配
  tasks/            # 任务 YAML 定义 (T01–T61)
  agent_profiles/   # 组配置文件 (G1–G4, A1, A3, A4)
  fixtures/         # 公共工作区夹具
  fixtures_hidden/  # 隐藏夹具（诊断反泄漏，9 个插件）
  expected_answers/ # 夹具本地预期答案（结构化检查用）
  evaluation_suites.yaml  # v0.9 套件定义与 claim role
  BENCHMARK_SPEC.yaml  # v0.3 基准规范
```

详细架构参见 [CLAUDE.md](CLAUDE.md)。

---

## 8. 本地模型实验结果 (v0.6-dev)

ABI-Bench 已在包含弱、中、强三个能力层级的 7 个本地模型上验证，
确认了核心脚手架假设：

### 7.1 排行榜 (T01-T30, public fixtures)

| 模型 | 层级 | G1 | G2 | G3 | G4 | G3−G1 | G3−G2 |
|------|------|----|----|----|----|-------|-------|
| Qwen3-4B | Weak | 29.4% | 22.9% | **53.5%** | 33.9% | **+24.1%** | **+30.6%** |
| Llama-3.1-8B | Weak | 18.3% | 17.6% | **46.1%** | 20.3% | **+27.7%** | **+28.5%** |
| Qwen3-14B (4-bit) | Medium | — | 23.5% | **25.2%** | — | — | +1.8% |

> **脚手架效应确认**：弱模型通过 ABI 在 G3 中获得 24–28 分的提升，
> 而中等模型（Qwen3-14B, 4-bit 量化）提升不到 2 分。
> 这直接验证了核心声明：ABI 是降低模型能力门槛的领域特定脚手架。

### 7.2 量化影响

Qwen3-14B 因 VRAM 限制（RTX 4090 24GB）使用 4-bit bitsandbytes (NF4) 量化运行。观察到的影响：

- **G2 与 4B 模型持平**：Qwen3-14B (4-bit) G2 ≈ 23.5% vs Qwen3-4B (原生) G2 ≈ 22.9%——量化将 14B 模型的原始推理能力降至接近 4B 水平
- **ABI 增益近乎为零**：G3−G2 = +1.8% vs 原生 4B 的 +30.6%——量化严重损害结构化指令遵循能力（ABI 生命周期命令）
- **跨插件任务崩溃**：14B 4-bit 在跨插件规划/预演任务中得分 0–13%，而 4B 原生得分为 100%

> **建议**：在 ABI-Bench 中，优先使用原生精度模型或 GGUF/GPTQ 量化
> 而非 bitsandbytes（当需要 4-bit 时）。结构化工具调用类基准测试
> 对量化退化特别敏感。

### 7.3 本地模型层级

| 层级 | 模型 | 量化 |
|------|------|------|
| **Weak** | Qwen3-4B, Llama-3.1-8B, Llama-3.1-8B-Instruct, DeepSeek-R1-Distill-Qwen-7B | 原生 |
| **Medium** | Qwen3-14B, Mistral-Small-3.2-24B-Instruct | 需 4-bit |
| **Strong** | Qwen3-30B-A3B-Instruct (MoE), Qwen2.5-Coder-32B-Instruct | 需 4-bit |

规范定义见 `bench/model_tiers.yaml`。

---

## 9. 引用

如果在研究中使用 ABI-Bench，请引用：

```bibtex
@software{abi_bench_v0_9,
  title = {ABI-Bench: Agent-Bioinformatics Interface Benchmark v0.9},
  author = {ABI-Bench Contributors},
  year = {2026},
  note = {Evaluates structured ABI control layer for LLM agent
          bioinformatics workflow operation across model capability tiers.
          v0.9 adds evidence-based artifact scoring (T36-T47), cross-plugin
          hidden robustness suite (T59-T61), and 7-suite evaluation
          architecture with distinct claim roles.},
}
```
