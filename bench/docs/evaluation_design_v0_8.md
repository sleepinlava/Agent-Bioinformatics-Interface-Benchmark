# ABI-Bench v0.8 评测设计

## 1. 主问题与估计量

主问题不是“Agent 会不会调用 `abi` 命令”，而是：在模型、harness、任务、
fixture 和预算相同的条件下，向通用 Agent 提供 ABI 控制层，是否提高生物信息学
任务的可靠完成率。

主估计量为配对平均处理效应：

`ATE = mean(score_G3 - score_control)`

配对键是 `model_id × replicate`，G1、G2、G4 分别作为不同控制组。置信区间按
`model_id` 聚类 bootstrap，避免把同一模型完成的多个任务误当成独立样本。

## 2. 任务集分层

任务清单统一维护在 `bench/evaluation_suites.yaml`。

| Suite | 用途 | 可否支持 ABI 主因果声明 |
|---|---|---|
| `causal_core_v0_8` | 组间结果等价比较 | 可以 |
| `heldout_plugin_v0_8` | 新插件迁移/外部效度 | 单独支持迁移声明 |
| `mechanism_probes_v0_8` | ABI 原生命令与组件能力 | 不可以，只解释机制 |
| `real_execution_case_studies_v0_8` | 真实流水线案例 | 不可以，只作案例证据 |
| `ablation_v0_8` | ABI 组件消融 | 只支持组件声明 |
| `full_descriptive_v0_8` | 全覆盖汇总 | 不可以作为单一主分数 |

`causal_core_v0_8` 的提示只描述目标和约束，不告诉 Agent 应调用哪个 ABI 命令。
各组面对相同 outcome rubric；接口选择来自实验组配置，而不是题目提示。

## 3. 对照组解释

- G1 测量文档加 Shell 的非结构化基线。
- G2 测量通用工具调用基线。发布结果前必须证明 G2 暴露了真实的领域操作工具，
  而不只是给 G1 的 Shell 改名；否则 G2 只能作为探索性对照。
- G3 是 ABI 完整处理组。
- G4 控制信息量，测量结构化生命周期接口相对等价静态文档的增益。

主报告必须分别给出 G3−G1、G3−G2、G3−G4，不应只报告合并基线。

## 4. 模型与重复实验

模型层级在运行前固定于 `bench/model_tiers.yaml`。禁止用本 benchmark 的 G1 结果
事后划分强弱层级。量化方式、模型版本、provider、temperature、token/step 预算均
应作为运行元数据保存；不同量化配置按不同模型处理。

推荐至少每个层级 2 个模型、每个模型 5 个配对重复。若某层只有 1 个模型，只能
报告该模型的描述性增益，不能声称普遍的 Group × Tier 交互。

## 5. 评分证据优先级

评分按以下优先级设计：

1. 真实产物的 schema、内容值、checksum 和状态转换；
2. trace 中实际执行的工具调用及安全边界；
3. final answer 中与产物可交叉验证的结构化字段；
4. 关键词出现，仅允许作为低权重辅助项。

不得让超过任务一半分值仅依赖关键词。静态审计会对此发出警告。

## 6. 运行与发布门槛

```bash
python bench/validation/audit_benchmark.py --strict

python bench/harness/run_multi_model.py \
  --tier all --groups G1,G2,G3,G4 \
  --tasks causal_core_v0_8 --replicates 5 \
  --experiment-set paper --fixture-set hidden --seed 42

python bench/scoring/compute_statistics.py \
  --results bench/results --experiment-set paper \
  --fixture-set hidden --suite causal_core_v0_8 \
  --output bench/results/statistics.json

python bench/scoring/claim_preflight.py \
  --results bench/results --experiment-set paper --fixture-set hidden \
  --suite causal_core_v0_8 --min-replicates 5
```

发布主结论前还需满足：所有组具有相同 task set；配对单元完整；隐藏 fixture 覆盖
需要声明；机制探针和真实执行案例不得混入主 ATE；预注册阈值与事后阈值分别报告。
