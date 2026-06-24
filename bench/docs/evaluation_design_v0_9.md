# ABI-Bench v0.9：证据评分与隐藏鲁棒性

v0.9 保留 v0.8 的主因果 suite 和 `model_id × replicate` 配对估计量，集中修复
机制任务可通过关键词自报得分、故障 fixture 缺少真实证据，以及跨插件隐藏覆盖
不足的问题。

## 证据优先评分

T36–T47 不再使用 `check_final_answer_contains`。评分器按任务交叉验证：

- final_answer.json 的类型、枚举、计数和嵌套字段；
- Agent 报告的路径、文件大小与 workspace 实际文件；
- source table、SVG 内容、figure spec 和已知故障记录；
- commands.log/tool_calls.jsonl 中真实发生的 lint、恢复和平台命令；
- 修复后的 config.yaml，而不是“已修复”的文字声明；
- local/Docker 文件内容、provenance 六维完整性；
- original/revised plan 两个独立 artifact；
- 两个预生成独立 review，而不是要求单模型假装另一个模型。

静态审计要求任务分值预算一致、因果提示不命名 ABI、诊断 expected answer 与
fixture config 一致，并阻止 missing-resource fixture 同时缺少输入文件。

## 隐藏鲁棒性 suite

`hidden_robustness_v0_9` 包含：

- T59：RNA-seq genome index 缺失；
- T60：WGS AMRFinder 数据库缺失；
- T61：shotgun metagenomics Kraken2 数据库缺失。

每题都有 public 和 hidden 两个语义等价、标识符与路径不同的 fixture。该 suite
单独报告 G3−G1、G3−G2、G3−G4，不混入 `causal_core_v0_8` 总分。

```bash
python bench/validation/audit_benchmark.py --strict

python bench/harness/run_multi_model.py \
  --tier all --groups G1,G2,G3,G4 \
  --tasks hidden_robustness_v0_9 --replicates 5 \
  --experiment-set paper --fixture-set hidden --seed 42

python bench/scoring/compute_statistics.py \
  --results bench/results --experiment-set paper --fixture-set hidden \
  --suite hidden_robustness_v0_9 \
  --output bench/results/robustness_statistics.json

python bench/scoring/claim_preflight.py \
  --results bench/results --experiment-set paper --fixture-set hidden \
  --suite hidden_robustness_v0_9 --min-replicates 5
```

## 仍需单独声明的边界

- hidden diagnosis 尚未覆盖 metatranscriptomics、amplicon_16s 和 viral_viwrap；
- viral_viwrap 目前只有 planning，没有对应 dry-run；
- mechanism suite 用于解释 ABI 如何工作，不能替代主因果 suite；
- 真实执行任务仍是案例证据，不进入 agent-operability ATE。
