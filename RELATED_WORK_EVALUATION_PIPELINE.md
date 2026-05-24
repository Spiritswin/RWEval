# Related Work Evaluation Pipeline

本文档描述当前仓库中已经实现的 related work evaluation pipeline。它不是最初的理想化设计稿，而是和当前代码行为保持一致的实现说明。

## 1. 任务定义

输入样本的标准 JSON 格式为：

```json
{
  "sample_id": "paper_001",
  "s_text": "candidate related work text",
  "s_references": "candidate reference list",
  "g_text": "ground-truth related work text",
  "g_references": "ground-truth reference list"
}
```

字段含义：

- `s_text`: 待评估的 related work 文本
- `s_references`: `s_text` 对应的 reference list
- `g_text`: ground-truth related work 文本
- `g_references`: `g_text` 对应的 reference list

系统输出：

- `overall`: 0-10 总分
- `scores`: 各项 metric 分数
- `diagnostics`: 便于人工检查的诊断信息
- `intermediate`: 解析、中间抽取和 judging 结果
- `metric_details`: 每个 metric 的详细计算结果
- `applied_caps`: 被触发的 cap 规则
- `warnings`: LLM / retrieval 等阶段的 warning
- `cleaning`: 输入清洗记录

## 2. 当前实现原则

当前项目采用的是：

```text
deterministic pipeline + local LLM judging + Semantic Scholar evidence / normalization
```

核心原则：

- pipeline 结构固定，最终打分由代码完成
- LLM 负责局部抽取和局部判断，不直接对整篇 related work 给总分
- Semantic Scholar 负责 reference normalization、metadata / abstract 获取，以及 citation 二次检索证据
- heuristic fallback 已被移除；LLM 是必需的
- citation 判断现在包含 pair-level、group-level、second-pass retrieval 和 overclaim 判断

## 3. 当前输入工作流

当前项目支持两种入口，但统一推荐的工作流是：

```text
4 个 txt -> 生成 sample_input.json -> 跑 evaluate pipeline
```

### 3.1 统一的四文件工作流

当目录下存在以下四个文件时：

```text
s_text.txt
s_reference.txt
g_text.txt
g_reference.txt
```

运行：

```bash
python -m rw_eval.cli evaluate-files \
  --directory examples/sample2 \
  --output outputs/sample2/report.json \
  --markdown-output outputs/sample2/report.md
```

当前 `evaluate-files` 的实际行为是：

1. 读取四个 txt
2. 先写出 `sample_input.json`
3. 再读取这个 JSON 并运行完整评测

默认情况下：

- 如果传 `--directory DIR`，中间 JSON 默认写到 `DIR/sample_input.json`
- 如果显式传四个 txt 且它们位于同一目录，中间 JSON 默认也写到那个目录下
- 可以用 `--sample-json-output` 显式指定中间 JSON 路径

### 3.2 直接使用 JSON

如果已经有样本 JSON，可以直接运行：

```bash
python -m rw_eval.cli evaluate \
  --input examples/sample_input.json \
  --output outputs/sample_report.json \
  --markdown-output outputs/sample_report.md
```

### 3.3 批量评测

批量模式读取 JSONL：

```bash
python -m rw_eval.cli batch \
  --input data/eval_samples.jsonl \
  --output outputs/reports.jsonl
```

## 4. 当前实现的指标

当前最终总分使用 7 个主指标：

| Metric | Weight |
|---|---:|
| `content_coverage` | 0.17 |
| `citation_quality` | 0.35 |
| `relevance` | 0.08 |
| `thematic_structure` | 0.14 |
| `synthesis_quality` | 0.10 |
| `writing_quality` | 0.08 |
| `length_conciseness` | 0.08 |

注意：

- 当前代码里没有单独进入总分聚合的 `factual_consistency` 主指标
- factual / unsupported / contradicted 信息主要通过 claim judging 和 citation judging 间接体现在诊断和其他分数里
- `scores` 中还会额外展示 citation 的 5 个子分项，但它们不是独立主指标

## 5. 各指标当前计算方式

### 5.1 Content Coverage

输入：

- `gold["key_points"]`
- alignment judgment

流程：

1. LLM 从 `g_text` 抽取 gold topics 和 gold key points
2. LLM 从 `s_text` 抽取 candidate claims
3. LLM 判断每个 gold point 是否被哪些 candidate claims 覆盖
4. 代码按 gold point importance 和覆盖状态计算分数

输出：

- 主分数 `content_coverage`
- `missing_points` 诊断

### 5.2 Relevance

输入：

- `gold["key_points"]`
- `candidate["claims"]`
- claim-level relevance judgment

流程：

1. claim judging 对每个 candidate claim 打 relevance score
2. 代码汇总平均分

输出：

- `relevance`

### 5.3 Thematic Structure

输入：

- gold topics
- candidate topics
- thematic judgment

当前子项：

- `topic_coverage`
- `topic_purity`
- `topic_coherence`
- `topic_granularity`
- `topic_ordering`

权重来自 `configs/rubric.json`：

```text
topic_coverage      0.30
topic_purity        0.25
topic_coherence     0.20
topic_granularity   0.15
topic_ordering      0.10
```

输出：

- `thematic_structure`
- `topic_structure_issues`

### 5.4 Synthesis Quality

输入：

- 原始 `s_text`
- gold 结构化信息
- candidate 结构化信息

流程：

- 由 LLM 做 synthesis / writing 联合判断
- 代码读取其中的 synthesis 分数

输出：

- `synthesis_quality`

### 5.5 Writing Quality

输入与流程同上。

输出：

- `writing_quality`

### 5.6 Length & Conciseness

输入：

- 解析后的 `s_doc` 和 `g_doc`
- `content_coverage` 分数
- `relevance` 分数

当前子项：

- `relative_length_score`
- `information_density_score`
- `redundancy_score`

当前阈值来自 `configs/rubric.json`：

- 无惩罚长度比区间：`0.75 - 1.35`
- redundancy similarity threshold：`0.82`

输出：

- `length_conciseness`
- `length_conciseness_issues`

### 5.7 Citation Quality

这是当前系统里最重的主指标。

当前 citation quality 由 5 个子项聚合：

| Subscore | Weight |
|---|---:|
| `citation_validity` | 0.25 |
| `citation_appropriateness` | 0.35 |
| `citation_coverage` | 0.20 |
| `citation_placement` | 0.10 |
| `citation_topic_consistency` | 0.10 |

#### a. Citation Validity

输入：

- 解析后的 references
- Semantic Scholar normalization 结果

流程：

1. 解析 reference list
2. 尝试匹配 DOI / arXiv / author-year / title
3. 调 Semantic Scholar 获取 canonical metadata
4. 根据解析和 metadata 判断 validity

当前会记录：

- resolved reference
- unresolved reference
- metadata mismatch

cap 规则：

- 任意 unresolved reference: `citation_quality <= 7.0`
- 任意 hallucinated / metadata mismatch: `citation_quality <= 5.0`
- hallucinated / metadata mismatch 数量较多时: `citation_quality <= 3.0`

#### b. Citation Appropriateness

输入：

- candidate claims
- claim 关联的 citation keys
- reference metadata

流程：

1. LLM 先做 pair-level citation judgment
2. 每个 claim-citation pair 输出：
   - `support`
   - `support_rationale`
   - `appropriateness_score`
   - `placement_score`
   - `topic_consistency_score`
   - `overclaim_status`
   - `overclaim_rationale`

当前 `support` 标签使用：

```text
yes / partial / weak / no / unknown
```

当前 overclaim 规则：

- 只有当 `support` 为 `yes` 或 `partial` 时，才允许出现 overclaim
- 如果 `support` 是 `weak` / `no` / `unknown`，则强制 `overclaim_status = none`

也就是说，当前实现里：

- unsupported / weak support 和 overclaim 被显式区分
- overclaim 是“有一定支持，但 claim 说过头了”
- weak / no 则表示“引用本身就没把 claim 支起来”

#### c. Citation Second Pass Retrieval

当前 citation pair judgment 不是一轮结束。

当出现以下情况之一时，会触发 second pass：

- `support` 属于 `weak` / `no` / `unknown`
- `appropriateness_score < 6`
- 缺少 rationale

second pass 流程：

1. 使用 Semantic Scholar 侧的 evidence retrieval 为该 claim-citation pair 检索额外证据
2. 将：
   - reference metadata
   - 初始 judgment
   - retrieved evidence snippets
   一起发给 LLM
3. 让 LLM 重新判断这一个 pair

报告中会保留：

- `retrieval_events`
- `second_pass_used`
- `retrieval_used`
- `retrieved_evidence`

#### d. Compound Citation / Citation Group Support

当前系统已经支持复合 citation 的整体判断。

逻辑是：

- 先做每个 claim-citation pair 的单独判断
- 如果一个 claim 对应多个 citation，再额外做一次 group-level judgment

group-level judgment 输出：

- `group_support`
- `group_rationale`
- `covered_aspects`
- `missing_aspects`
- `reference_keys`

如果只有单个 citation，也会生成一个 single-pair mirror group judgment，但在 markdown 诊断里会尽量过滤掉没有新增信息的冗余项。

因此，当前对复合 citation 的处理不是简单看单篇 paper，而是会把多个 citation 的信息综合后再判断它们是否整体支持 claim。

#### e. Citation Coverage

输入：

- `g_references` / `gold["key_references"]`
- `s_references`

流程：

- 代码判断 candidate 是否覆盖了 ground-truth 里的关键 references

#### f. Citation Placement / Topic Consistency

这两个子分主要来自 pair-level LLM judgment：

- `placement_score`
- `topic_consistency_score`

## 6. Citation Diagnostics 的当前含义

当前 markdown / json 报告里，citation 相关诊断主要有四类：

### 6.1 Bad Citation-Claim Pairs

来源：

- `citation_quality.details.problematic_citation_claim_pairs`

含义：

- 该 pair 的 citation support 不够好，通常是 `weak` / `no` / `unknown`
- 报告里会写出 `support` 和 `support_reason`

### 6.2 Overclaim Citation-Claim Pairs

来源：

- `citation_quality.details.overclaim_citation_claim_pairs`

含义：

- citation 对 claim 有一定支持，但 claim 的表述超出了 citation 实际支持范围
- 只在 `support = yes/partial` 时出现
- 报告里会写出 `support_reason` 和 `overclaim_reason`

### 6.3 Citation Group Support

来源：

- claim 级别的复合 citation 整体判断

含义：

- 多个 citation 合在一起时，对 claim 的整体支撑程度
- 更适合分析复合 citation 情况
- 当前 markdown 会过滤掉单 citation 的镜像项，以及没有新增信息的冗余项

### 6.4 Hallucinated References

当前 pipeline 里这部分是保守定义的。

当前 `diagnostics["hallucinated_references"]` 实际来自：

- validity 为 `metadata_mismatch` 的 references

也就是说，它更接近：

- reference metadata mismatch
- 可能的 citation hallucination

而不是“所有 unresolved references”的总集

## 7. 当前解析能力

### 7.1 Citation parsing

当前支持：

- author-year 括号引用：`(Smith et al., 2020)`
- author-year narrative：`Smith et al. (2020)`
- numeric：`[12]`, `[3, 7, 9]`, `[4-6]`
- BibTeX citation keys：`\cite{foo2024}`, `\citep{a,b}`, 以及一般形式的 `\cite...{...}`

### 7.2 Reference parsing

当前支持：

- 普通 reference list
- numeric label reference list
- BibTeX reference list

BibTeX 场景下：

- `g_text` / `s_text` 可以通过 bib key 进行文中引用
- `g_reference` / `s_reference` 可以直接是 BibTeX
- 系统会把 BibTeX key、author-year key、DOI、arXiv、title key 一并纳入 lookup

## 8. Semantic Scholar 在当前项目中的作用

当前 Semantic Scholar 的作用包括：

1. reference normalization
2. metadata retrieval
3. abstract retrieval
4. claim-citation second-pass evidence retrieval

当前 abstract / metadata 会进入：

- `reference_metadata`
- citation judging prompt 的输入

但要注意：

- Semantic Scholar 本身不是最后的 judge
- 最终 citation support / overclaim 判断仍由 LLM 完成
- Semantic Scholar 提供的是规范化后的论文元数据和证据材料

## 9. LLM 在当前项目中的作用

当前 LLM 负责：

1. gold extraction
2. candidate extraction
3. alignment judging
4. claim relevance judging
5. thematic judging
6. synthesis / writing judging
7. citation pair judging
8. citation pair second-pass recheck
9. citation group support judging

当前没有 heuristic fallback。

如果 `--no-llm`，评测会直接失败，而不是退回启发式模式。

## 10. Retry 和鲁棒性

### 10.1 LLM client

当前 LLM client 已支持：

- request retry
- JSON retry
- malformed JSON repair
- 429 / 5xx retry
- network / SSL / remote close retry

相关环境变量：

```text
LLM_TIMEOUT_SECONDS
LLM_REQUEST_RETRIES
LLM_JSON_RETRIES
LLM_RETRY_BACKOFF_SECONDS
LLM_JSON_MODE
```

### 10.2 Semantic Scholar client

当前实现也已经加了重试与缓存机制。

缓存目录由以下环境变量控制：

```text
RW_EVAL_CACHE_DIR
```

## 11. 输入清洗

当前 pipeline 在正式评测前会执行保守清洗：

- 已知编码残留修复
- LaTeX escape 清理，如 `\& -> &`
- 空白和换行规范化

默认不会主动修正常见 OCR 语义 typo。

如果需要，可以显式启用：

```bash
--normalize-ai-typos
```

例如：

- `Al-assisted -> AI-assisted`

清洗记录会写入：

- JSON 报告的 `cleaning`
- Markdown 报告的 `Input Cleaning`

## 12. 当前 overall cap

当前总分层面的 cap 规则只有一个：

- 如果 topic coverage 很低，且 content coverage 也很低，则触发 `topic_mismatch` cap
- 当前 cap 值为 `5.0`

## 13. 当前报告结构

Markdown 报告当前包含：

- Overall
- Metric Breakdown
- Input Cleaning
- Missing Points
- Hallucinated References
- Bad Citation-Claim Pairs
- Overclaim Citation-Claim Pairs
- Citation Group Support
- Topic Structure Issues
- Length / Conciseness Issues

JSON 报告除上述摘要外，还包含完整 `intermediate` 和 `metric_details`。

## 14. 当前代码结构

```text
rw_eval/
  cli.py
  pipeline.py
  input_files.py
  cleaning.py
  validation.py
  schemas.py
  config.py
  env.py
  utils.py

  parsing/
    text.py
    citations.py
    references.py

  external/
    semantic_scholar.py
    cache.py

  llm/
    client.py
    extraction.py
    judging.py
    prompts.py

  scoring/
    aggregate.py
    citation.py
    coverage.py
    length.py
    relevance.py
    synthesis.py
    thematic.py
    writing.py

  reporting/
    json_report.py
    markdown_report.py

configs/
  rubric.json

examples/
tests/
```

## 15. 当前和早期设计稿相比的关键变化

以下几点是当前实现中已经明确变化的地方：

1. 不再使用 heuristic fallback
2. 不再走 proposal-claim 分流
3. `evaluate-files` 现在统一为“先生成 `sample_input.json` 再运行”
4. 已支持 BibTeX citation keys 和 BibTeX reference parsing
5. citation judging 已加入 second-pass retrieval
6. 已加入 overclaim 诊断
7. 已加入 citation group support，用于复合 citation 的整体判断
8. 当前没有独立进入 overall 的 `factual_consistency` 主分项

## 16. 使用建议

如果要跑一个新样本目录，推荐使用：

```bash
python -m rw_eval.cli evaluate-files \
  --directory examples/sample2 \
  --sample-json-output examples/sample2/sample_input.json \
  --output outputs/sample2/user_txt_full_report_gpt54.json \
  --markdown-output outputs/sample2/user_txt_full_report_gpt54.md
```

这样可以同时保留：

- 原始四个 txt
- 中间 `sample_input.json`
- 最终 JSON 报告
- 最终 Markdown 报告

这也是当前项目里最稳定、最统一的运行方式。
