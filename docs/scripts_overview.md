# 脚本与流程说明
本文梳理仓库中的核心脚本、模块职责与常见执行顺序，便于在本地或服务器逐步调试。

## 目录结构
```
pipeline/
  config.py          # 读取环境/标签筛选配置
  doris_client.py    # Doris 读写封装
  deepseek_client.py # DeepSeek API 封装
  models.py          # 数据模型（CandidateReview、LLMPayload 等）
  steps.py           # 单个流程节点的复用逻辑
scripts/
  pipeline.py        # CLI 入口
```

## 模块职责
### pipeline/config.py
- 读取 `config/environment.yaml`（Doris、DeepSeek 连接信息）与 `config/tag_filters.yaml`（可选的标签筛选条件），返回统一的 `AppConfig`。

### pipeline/models.py
- 定义 `CandidateReview`、`LLMPayload`、`TagFragment` 等数据类，并提供 JSON 序列化/反序列化方法。

### pipeline/doris_client.py
- 通过 MySQL 协议访问 Doris，提供：
  1. `fetch_candidates`：从 `view_return_review_snapshot` 拉取候选文本。
  2. `upsert_return_fact_llm`：写入 `return_fact_llm`（内部使用删除+插入，保证幂等）。
  3. `fetch_payloads`：读取 Raw payload，供本地解析。
  4. `insert_return_fact_details`：写入 `return_fact_details`，遇到空标签会写入占位记录。
  5. `fetch_dim_tag_map`：按配置读取标签维表。

### pipeline/deepseek_client.py
- 封装 DeepSeek Chat Completions 调用：
  - 自动注入角色/任务/要求/标签库（来自 `prompt/deepseek_prompt.txt` + `return_dim_tag`）。
  - 记录请求体（可选），并处理 LLM 输出中的 ```json fenced code```。
  - 支持 `--skip-db-write` 时仅返回 `LLMPayload`，不落库。

### pipeline/steps.py
- 将常见节点抽象为函数：
  - `step_fetch_candidates`
  - `step_call_llm`（可写 Raw 或仅缓存）
  - `step_parse_payloads`
  - `step_write_raw_from_cache`

### scripts/pipeline.py
- 命令行入口，可按步骤执行或一次跑完。常用参数：
  - `--step {candidates,llm,raw,parse,all}`
  - `--config CONFIG`（默认 `config/environment.yaml`）
  - `--limit N`（采样数量）
  - `--candidate-output / --candidate-input`
  - `--payload-output / --payload-input`
  - `--prompt-file`（默认 `prompt/deepseek_prompt.txt`）
  - `--llm-request-output`（记录请求 JSONL）
  - `--skip-db-write`（仅在 `--step llm` 时生效，结果只写本地文件）

## 典型执行顺序
以下示例均假设已激活 `.venv` 并位于仓库根目录。

1. **采样候选**
   ```bash
   python -m scripts.pipeline --step candidates --limit 100 --candidate-output test/candidates.jsonl
   ```

2. **调用 LLM并写 Raw（默认）**
   ```bash
   python -m scripts.pipeline --step llm \
       --candidate-input test/candidates.jsonl \
       --payload-output test/payloads.jsonl \
       --llm-request-output test/llm_requests.jsonl
   ```

3. **调用 LLM但只缓存（不写库，节省 token）**
   ```bash
   python -m scripts.pipeline --step llm \
       --candidate-input test/candidates.jsonl \
       --payload-output test/payloads.jsonl \
       --llm-request-output test/llm_requests.jsonl \
       --skip-db-write
   ```

4. **用缓存写入 `return_fact_llm`**
   ```bash
   python -m scripts.pipeline --step raw --payload-input test/payloads.jsonl
   ```

5. **解析 payload 写入 `return_fact_details`**
   ```bash
   python -m scripts.pipeline --step parse --payload-input test/payloads.jsonl
   ```

6. **一次跑完全链路（含写库）**
   ```bash
   python -m scripts.pipeline --step all --limit 200
   ```

> **提示**
> - DeepSeek 请求体模板：`docs/llm_request_template.json`；提示词可在 `prompt/deepseek_prompt.txt` 调整。
> - 环境与密钥配置：`config/environment.yaml`，如需过滤标签可在 `config/tag_filters.yaml` 配置。
> - 建议将临时输出放在 `test/` 目录，便于复现与回放。
