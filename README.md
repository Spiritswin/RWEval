# Related Work Evaluator

这是一个用于评价 related work 文本质量的可复现 evaluation pipeline。

输入包括：

- `s_text`：待评价的 related work。
- `s_reference`：待评价文本对应的 reference list。
- `g_text`：ground-truth related work。
- `g_reference`：ground-truth reference list。

Pipeline 会结合代码打分、LLM 局部语义判断，以及 Semantic Scholar 的引用验证，输出 JSON 和 Markdown 报告。

## 评价指标

当前总分为 0-10，包含 8 个 metric：

| Metric | 权重 | 说明 |
|---|---:|---|
| `content_coverage` | 17% | `s` 是否覆盖 `g` 中的关键主题、方法、限制和 gap |
| `factual_consistency` | 15% | `s` 中的 factual claims 是否与 `g` 或引用元数据一致 |
| `relevance` | 8% | `s` 写的内容是否相关，有无跑题或泛泛背景 |
| `thematic_structure` | 14% | paragraph/topic 划分是否合理，段落主题是否清晰 |
| `synthesis_quality` | 10% | 是否真正综合已有工作，而不是罗列论文 |
| `citation_quality` | 20% | 引用是否真实、恰当、覆盖关键文献、支撑对应 claim |
| `writing_quality` | 8% | 学术表达、清晰度、简洁性和术语一致性 |
| `length_conciseness` | 8% | 长度是否合适，信息密度和重复度是否合理 |

## 配置

运行 API-backed evaluation 前，先填写 `.env`：

```text
LLM_API_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
LLM_TIMEOUT_SECONDS=60
LLM_JSON_MODE=false

SEMANTIC_SCHOLAR_API_KEY=
SEMANTIC_SCHOLAR_BASE_URL=https://api.semanticscholar.org/graph/v1
SEMANTIC_SCHOLAR_TIMEOUT_SECONDS=30

RW_EVAL_CACHE_DIR=.cache/rw_eval
```

LLM endpoint 需要兼容 OpenAI 的 `POST /chat/completions` 格式。中转 API 可以直接填在 `LLM_API_BASE_URL`。

`.env` 已经被 `.gitignore` 忽略，不会被提交。

## 用四个 TXT 文件评价

如果目录中有这四个文件：

```text
s_text.txt
s_reference.txt
g_text.txt
g_reference.txt
```

可以直接运行：

```bash
python -m rw_eval.cli evaluate-files \
  --directory examples \
  --output outputs/user_txt_full_report.json \
  --markdown-output outputs/user_txt_full_report.md
```

也可以显式指定路径：

```bash
python -m rw_eval.cli evaluate-files \
  --s-text examples/s_text.txt \
  --s-references examples/s_reference.txt \
  --g-text examples/g_text.txt \
  --g-references examples/g_reference.txt \
  --sample-id user_txt \
  --sample-json-output examples/sample_input.json \
  --output outputs/user_txt_full_report.json \
  --markdown-output outputs/user_txt_full_report.md
```

输出：

- `*.json`：完整结构化结果，包含所有中间产物、metric details、diagnostics、warnings。
- `*.md`：人类可读报告，包含总分、分项分数、遗漏点、unsupported claims、citation 问题等。

## 用 JSON 输入评价

单样本 JSON 格式示例见 `examples/sample_input.json`。

运行：

```bash
python -m rw_eval.cli evaluate \
  --input examples/sample_input.json \
  --output outputs/sample_report.json \
  --markdown-output outputs/sample_report.md
```

## 批量评价

输入为 JSONL，每一行一个 sample：

```bash
python -m rw_eval.cli batch \
  --input data/eval_samples.jsonl \
  --output outputs/reports.jsonl
```

## 文本清洗

默认会做非常保守的清洗：

- 修复已知编码残留。
- 清理 LaTeX escape，例如 `\& -> &`。
- 规范空白和多余换行。

默认不会改语义 typo，例如 `Al-assisted -> AI-assisted`。

关闭清洗：

```bash
python -m rw_eval.cli evaluate-files \
  --directory examples \
  --output outputs/file_report.json \
  --no-clean
```

如果确实想启用 OCR-style typo 修复：

```bash
python -m rw_eval.cli evaluate-files \
  --directory examples \
  --output outputs/file_report.json \
  --normalize-ai-typos
```

清洗记录会写入报告的 `cleaning` 字段和 Markdown 的 `Input Cleaning` 小节。

## 调试模式

如果 LLM endpoint 出错，默认会记录 warning，并对对应步骤 fallback 到 heuristic。

如果希望 LLM 出错时直接失败，使用：

```bash
python -m rw_eval.cli evaluate-files \
  --directory examples \
  --output outputs/file_report.json \
  --strict-llm
```

如果只想本地 smoke test，不调用 LLM 和 Semantic Scholar：

```bash
python -m rw_eval.cli evaluate-files \
  --directory examples \
  --output outputs/local_report.json \
  --markdown-output outputs/local_report.md \
  --no-llm \
  --no-semantic-scholar
```

## 当前实现说明

Pipeline 主体在 `rw_eval/pipeline.py`。

主要模块：

- `rw_eval/parsing/`：文本、引用、reference list 解析。
- `rw_eval/external/semantic_scholar.py`：Semantic Scholar Graph API client。
- `rw_eval/llm/`：LLM client、prompt、extraction、judging。
- `rw_eval/scoring/`：所有 metric 的代码计算。
- `rw_eval/reporting/`：JSON/Markdown report 输出。
- `configs/rubric.json`：权重、cap rules、thresholds。

LLM client 已支持：

- OpenAI-compatible chat completion。
- JSON response parsing。
- malformed JSON repair。
- 网络/SSL/5xx retry。

## 验证

运行测试：

```bash
python -B -m unittest discover -s tests
```

语法检查：

```bash
python -B -c "import ast, pathlib; files=list(pathlib.Path('rw_eval').rglob('*.py'))+list(pathlib.Path('tests').rglob('*.py')); [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in files]; print(f'parsed {len(files)} python files')"
```
