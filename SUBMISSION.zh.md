# ABI-Bench 提交指南

> [English Version](SUBMISSION.md)

> 如何将你的智能体实验结果提交到 ABI-Bench 排行榜。

---

## 1. 可提交内容

ABI-Bench 接受以下类型的提交：

| 提交类型 | 描述 | 评分方式 |
|-----------------|-------------|---------|
| **新模型** | 使用不同 LLM 运行 G1/G2/G3 | 完整评分，出现在排行榜上 |
| **新智能体框架** | 用自己的智能体循环替换 `direct_agent.py` | 完整评分 |
| **新消融实验** | 针对特定模型/框架的 A1/A3/A4 变体 | 消融表 |
| **新插件** | 为新的生物信息学分析类型添加 T13–T18 风格任务 | 插件表 |

所有提交必须包含 **至少 8 个 MVP 任务**（T01, T02, T03, T05, T06, T08, T09, T10），
覆盖 **全部 4 个主要实验组**（G1, G2, G3, G4），每组 **至少 3 次重复**。
完整的 v0.6 提交应覆盖全部 47 个任务 (T01-T47)，跨全部 4 个实验组。

---

## 2. 环境准备

```bash
# 1. Python ≥ 3.10
python --version

# 2. 安装 ABI
pip install abi

# 3. 克隆基准仓库并安装依赖
git clone <this-repo-url> ABI-Bench
cd ABI-Bench
pip install pyyaml openai

# 4. 配置 LLM API Key
cp bench/.env.example bench/.env
# 编辑 bench/.env — 设置你的 provider、API key 和 model
```

支持的提供商：Anthropic、OpenAI、DeepSeek、Google Gemini，或任何兼容 OpenAI 的接口。
配置模板详见 `bench/.env.example`。

---

## 3. 提交流程（5 步）

### 第 1 步：基础设施验证（必须）

在使用真实 LLM 运行之前，先验证评分框架是否正常工作：

```bash
# 以模拟模式运行 G3 的 T03（应得 12/12）
python bench/harness/run_task.py --group G3 --task T03 --replicate 1 \
  --agent-mode simulated \
  --experiment-set submission --fixture-set public \
  --outdir bench/submissions/infrastructure_check/G3/T03/replicate_01

python bench/scoring/score_run.py \
  --task bench/tasks/T03_dryrun_plasmid.yaml \
  --trace-dir bench/submissions/infrastructure_check/G3/T03/replicate_01 \
  --run-dir bench/workspaces/G3/T03/replicate_01 \
  --output bench/submissions/infrastructure_check/G3/T03/replicate_01/score.json

# 预期输出: "score": 12, "max_score": 12, "passed": true
```

如果未得到 12/12，说明你的环境存在问题。常见修复方法：
- 检查 Python 版本（≥ 3.10）
- 重新安装 `pyyaml`
- 从仓库根目录运行

### 第 2 步：运行全部 3 个实验组

分别运行每个实验组。工具支持 `--parallel` 以加速：

```bash
# 设置 API Key 和模型
export ABI_BENCH_MAX_TOKENS=8000

# G1 (README + Shell 基线)
python bench/harness/run_group.py \
  --group G1 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set submission --fixture-set public \
  --outdir bench/submissions/<your_submission_id>/G1

# G2 (纯工具调用基线)
python bench/harness/run_group.py \
  --group G2 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set submission --fixture-set public \
  --outdir bench/submissions/<your_submission_id>/G2

# G3 (ABI 控制层)
python bench/harness/run_group.py \
  --group G3 --tasks mvp --replicates 3 \
  --agent-mode direct --parallel --workers 4 \
  --experiment-set submission --fixture-set public \
  --outdir bench/submissions/<your_submission_id>/G3
```

**规则**：
- `<your_submission_id>` 格式：`<模型名>/<日期>`（例如 `claude-opus-4-8/20260620`）
- 3 个实验组必须使用 **相同的 LLM**、**相同的温度（0）**、**相同的智能体框架**
- **不要**修改任务 YAML、智能体配置文件、评分代码或夹具
- 工具会在每组运行完成后自动执行 `claim_preflight.py`

### 第 3 步：聚合与评分

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

如果 `claim_preflight.py` 以非零退出码结束，**不要继续第 4 步** — 先修复问题。
常见问题：重复次数不足、夹具集混用、model_id 元数据不一致。

### 第 4 步：完整性校验

提交前请验证：

```bash
# 检查完整性
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

# 验证模拟模式仍然可用（无漂移）
python bench/harness/run_task.py --group G3 --task T03 --replicate 1 \
  --agent-mode simulated
# 仍应得 12/12
```

### 第 5 步：创建 Pull Request

创建具有以下结构的 PR：

```text
bench/submissions/<your_submission_id>/
├── G1/
│   ├── T01/replicate_01/score.json  ...  replicate_03/score.json
│   ├── T02/...  T03/...  T05/...  T06/...  T08/...  T09/...  T10/...
├── G2/  (相同结构)
├── G3/  (相同结构)
├── leaderboard.tsv
├── summary.json
├── per_task_scores.tsv
└── preflight.json
```

**PR 标题格式**：
```
[Submission] <模型名> · <智能体框架> · <日期>
```

**PR 正文**（使用此模板）：

```markdown
## 模型信息
- **模型**: <完整模型名称和版本>
- **提供商**: <Anthropic / OpenAI / DeepSeek / Gemini / 其他>
- **智能体框架**: direct（或描述自定义框架）
- **温度**: 0
- **日期**: YYYY-MM-DD

## 预检
- [x] `claim_preflight.py` 通过（退出码 0）
- [x] 模拟模式验证: G3 T03 = 12/12
- [x] 全部 8 个 MVP 任务 × 3 组 × 3 次重复均已提供
- [x] 未修改夹具、任务或评分文件
- [x] `summary.json` `complete: true`

## 结果摘要
| 实验组 | 总分 | 任务成功率 | 空运行率 | 诊断准确率 | 不安全执行率 |
|-------|------------|-------------|-------------|--------------|-------------|
| G3 | ... | ... | ... | ... | ... |
| G2 | ... | ... | ... | ... | ... |
| G1 | ... | ... | ... | ... | ... |

## 备注
<!-- 关于此次运行的观察、异常或评论 -->
```

---

## 4. 扩展提交（可选）

在 MVP（8 任务）被接受后，你可以提交更大任务集的结果：

```bash
# v0.5 完整集 (T01-T35, 35 任务)
for group in G1 G2 G3 G4; do
  python bench/harness/run_group.py \
    --group $group --tasks full_v0_5 --replicates 3 \
    --agent-mode direct --parallel --workers 4 \
    --experiment-set submission --fixture-set public \
    --outdir bench/submissions/<your_submission_id>_v0_5/$group
done

# v0.6 完整集 (T01-T47, 47 任务) — 包含图表验证、
# 渐进式修复、跨平台和多智能体协作模块
for group in G1 G2 G3 G4; do
  python bench/harness/run_group.py \
    --group $group --tasks full_v0_6 --replicates 3 \
    --agent-mode direct --parallel --workers 4 \
    --experiment-set submission --fixture-set public \
    --outdir bench/submissions/<your_submission_id>_v0_6/$group
done
```

可用任务集：`mvp` (8 任务), `full` (18 任务), `full_v0_5` (35 任务),
`full_v0_6` (47 任务), `extended_v0_6` (52 任务)。

---

## 5. 添加新插件

ABI-Bench 支持针对内置 5 种分析类型（metagenomic_plasmid、metatranscriptomics、
rnaseq_expression、amplicon_16s、wgs_bacteria）之外的生物信息学分析类型
提交插件专用结果。

提交新插件结果的步骤：

1. 遵循现有任务模式：T09（规划）、T10（空运行）、T11（检查）
2. 在 `bench/fixtures/<your_plugin>_valid/` 下创建夹具，包含：
   - `config.yaml`
   - `sample_sheet.tsv`
   - `data/`（小型占位文件）
3. 创建 task YAML，设置 `task_type: portability` 和 `plugin: <your_plugin>`
4. 在提交结果的同时提交插件注册 PR

插件贡献必须在上游 [ABI 仓库](https://github.com/bker/abi) 中包含
`abi-plugin.yaml` 和 `tool_registry.yaml`。

---

## 6. 规则与诚信

### 必须做的事

- ✅ 3 个实验组（G1, G2, G3）使用 **完全相同版本的 LLM**
- ✅ 使用 **temperature = 0**（或最低可用值）
- ✅ **3 个实验组全部运行** — 部分提交将被拒绝
- ✅ 每个任务 **至少运行 3 次重复**
- ✅ v0.1 评分保持 `network: false` 和 `real_tool_execution: false`
- ✅ 提交前运行 `claim_preflight.py` — 退出码必须为 0

### 禁止做的事

- ❌ 禁止修改任务 YAML、智能体配置文件、评分代码或夹具
- ❌ 禁止跨组混用模型（例如 G3 用 Claude，G1 用 GPT）
- ❌ 禁止跨组使用不同温度
- ❌ 禁止对 G1/G2 运行隐藏夹具集（v0.1 提交仅限 public）
- ❌ 禁止仅提交 G3 结果（违背三组实验设计的初衷）
- ❌ 禁止挑选重复结果 — 提交所有重复，包括失败的

### 违规处理

- 跨组混用模型 → PR 不经审核直接关闭
- 修改评分/夹具 → PR 关闭，报告者标记
- 挑选重复结果 → 预检发现（重复次数不匹配）

---

## 7. 排行榜更新

你的 PR 经审核并合并后：

1. GitHub Actions 对 `bench/submissions/` 运行 `aggregate_scores.py`
2. `bench/docs/index.html` 被重新生成，包含你的那一行
3. 更新后的排行榜自动推送到 GitHub Pages
4. 你的结果将显示在 `<repo-url>/bench/docs/`

以下情况可能需要人工审核：
- CI 中预检未通过
- 分数超出预期范围（G3 < 50 或 G3 < G1）
- 各组间元数据字段不一致

---

## 8. 常见问题

**问：可以用不同的智能体框架（非 `direct_agent.py`）提交结果吗？**
答：可以。请在 PR 正文中描述你的框架。该框架必须遵守相同的固定变量（温度 0、最大步数 50、超时 20 分钟、网络关闭）。

**问：如果我的模型不支持 temperature = 0 怎么办？**
答：使用最低可用值，并在 PR 正文中说明。

**问：可以仅提交消融实验组（A1/A3/A4）的结果吗？**
答：不可以。没有 G3 基线的消融数据无法解释。请先提交 G1/G2/G3，再提交消融。

**问：如何引用 ABI-Bench？**
答：参见 [README.md](README.md) 中的 `Citation` 部分。

**问：我的 G3 分数低于 G1 分数，这样的提交有效吗？**
答：当然有效！负面结果很有价值。提交它们 — 这能帮助社区理解 ABI 在什么情况下有效或无效。

**问：完整运行需要多长时间？**
答：8 个 MVP 任务 × 3 组 × 3 次重复 = 72 次任务运行，使用 `--parallel --workers 4`，
大约需要 1–2 小时，具体取决于模型延迟和智能体步数。

---

## 9. 联系方式

- **问题反馈**: 在此仓库中提交 GitHub Issue
- **论文**: [arXiv 预印本]()
- **ABI**: [github.com/bker/abi](https://github.com/bker/abi)
