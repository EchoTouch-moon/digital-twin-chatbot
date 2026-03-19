# 评估模块使用说明

本模块用于数字孪生对话系统的评估实验，支持毕业论文所需的各项评估指标。

## 文件结构

```
backend/
├── evaluation.py           # 核心评估模块
├── run_experiments.py      # 完整实验运行脚本
├── test_evaluation.py      # 快速测试脚本
evaluation_results/         # 实验结果输出目录
```

## 快速开始

### 1. 测试评估模块

```bash
cd backend
conda activate wxdata
python test_evaluation.py
```

### 2. 运行完整实验

```bash
cd backend
conda activate wxdata

# 运行 persona_id=5 的评估实验
python run_experiments.py --persona_id 5 --num_samples 20
```

### 3. 通过 API 运行评估

```bash
# 评估单个回复质量
curl -X POST http://localhost:8000/api/evaluation/response-quality \
  -H "Content-Type: application/json" \
  -d '{"generated": "哈哈今天真开心", "reference": "今天太开心了"}'

# 运行完整实验
curl -X POST http://localhost:8000/api/evaluation/run-experiment \
  -H "Content-Type: application/json" \
  -d '{"persona_id": 5, "num_samples": 10, "include_ablation": true}'
```

## 评估指标

### 1. 回复质量评估 (ResponseQualityEvaluator)

| 指标 | 说明 | 范围 |
|------|------|------|
| BLEU Score | n-gram 重叠度 | 0-1 |
| Semantic Similarity | 语义相似度 | 0-1 |
| Length Ratio | 长度比例 | 0-1 |

### 2. 风格一致性评估 (PersonaStyleEvaluator)

| 指标 | 说明 |
|------|------|
| Style Consistency | 与 Persona 风格的一致性 |
| Phrase Match Rate | 口头禅匹配率 |
| Length Match | 回复长度匹配度 |

### 3. 表情包推荐评估 (EmojiRecommendationEvaluator)

| 指标 | 说明 |
|------|------|
| Emoji Appropriateness | 表情包与情境的匹配度 |
| Recommendation Diversity | 推荐多样性 |

## 实验设计

### Baseline 对比实验

对比三种方法：
1. **No Persona**: 普通聊天机器人（无风格迁移）
2. **Persona Only**: 仅使用 Persona（无 RAG）
3. **Full System**: 完整系统（Persona + RAG + Memory）

### 消融实验

分别移除以下组件：
- Memory System
- RAG (Similar Conversations)
- Few-shot Examples

## 输出文件

运行实验后会生成以下文件：

```
evaluation_results/
├── experiment_5_20250316_*.json  # 完整实验结果
├── comparison_table.tex          # LaTeX 表格（用于论文）
└── experiment_report.md          # Markdown 报告
```

## 论文写作建议

### 实验章节结构

1. **实验设置**
   - 数据集：微信聊天记录
   - Persona：数字孪生角色
   - 评估指标：BLEU、语义相似度、风格一致性

2. **Baseline 对比实验**
   - 使用 `comparison_table.tex` 中的表格
   - 分析各方法的优缺点

3. **消融实验**
   - 展示各组件的贡献
   - 分析关键组件的重要性

4. **案例分析**
   - 展示具体对话示例
   - 分析风格迁移效果

### LaTeX 表格示例

实验生成的 `comparison_table.tex` 可直接用于论文：

```latex
\begin{table}[htbp]
\centering
\caption{系统性能对比实验结果}
\begin{tabular}{lccc}
\toprule
方法 & BLEU & 语义相似度 & 样本数 \\
\midrule
baseline_no_persona & 0.1234 & 0.8765 & 20 \\
baseline_persona_only & 0.2345 & 0.9012 & 20 \\
full_system & 0.3456 & 0.9234 & 20 \\
\bottomrule
\end{tabular}
\end{table>
```

## 注意事项

1. 确保后端服务正常运行
2. 确保 Persona 有足够的聊天历史数据
3. 实验可能需要较长时间，建议使用较小的样本数进行初步测试
4. 表情包推荐评估需要 `emoji_classification.jsonl` 文件