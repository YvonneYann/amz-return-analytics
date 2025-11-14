# 脚本与流程说明

本文概述仓库中与流水线相关的脚本/模块，说明它们的职责以及常见组合方式，方便在本地或服务器上逐步调试。

## 目录结构

```
pipeline/
  config.py            # 读取环境、标签筛选配置
  doris_client.py      # Doris 读写封装
  deepseek_client.py   # DeepSeek API 封装
  models.py            # 数据模型（CandidateReview、LLMPayload 等）
  steps.py             # 单个流程节点的复用逻辑
scripts/
  pipeline.py          # CLI 入口，组合以上步骤
```

## 模块职责

### `pipeline/config.py`
- **作用**：读取 `config/environment.yaml`（Doris/DeepSeek 连接信息）及 `config/tag_filters.yaml`（标签筛选条件），返回统一的 `AppConfig`。

### `pipeline/models.py`
- **作用**：定义 `CandidateReview`、`LLMPayload`、`TagFragment` 等数据类，并提供 `LLMPayload.to_json()` 等序列化方法，便于读写 JSON/数据库。

### `pipeline/doris_client.py`
- **作用**：通过 MySQL 协议连接 Doris，提供：
  1. `fetch_candidates`：读取 `view_return_review_snapshot`
  2. `upsert_return_fact_llm`：写入 `return_fact_llm`（使用 `REPLACE INTO` 保证幂等）
  3. `fetch_payloads`：从 Raw 表取 payload 供解析
  4. `insert_return_fact_details`：写入 `return_fact_details`
  5. `fetch_dim_tag_map`：按筛选条件读取标签维表

### `pipeline/deepseek_client.py`
- **作用**：封装 DeepSeek Chat Completions 调用，自动注入角色/任务/标签库等提示词，并处理 LLM 返回的 ```json fenced code```，最终产出 `LLMPayload`。

### `pipeline/steps.py`
- **作用**：将常见节点抽象为函数，便于脚本组合：
  - `step_fetch_candidates`
  - `step_call_llm`（支持记录请求、控制是否写 Raw）
  - `step_parse_payloads`
  - `step_write_raw_from_cache`（将本地缓存批量写入 `return_fact_llm`）

### `scripts/pipeline.py`
- **作用**：命令行入口，可按步骤执行或一次跑完。主要参数：
  - `--step {candidates,llm,parse,raw,all}`
  - `--config config/environment.yaml`
  - `--limit N`
  - `--candidate-output/--candidate-input`
  - `--payload-output/--payload-input`
  - `--prompt-file`（默认 `prompt/deepseek_prompt.txt`）
  - `--llm-request-output`（记录请求 JSONL）
  - `--skip-db-write`（仅在 `--step llm` 生效；只缓存 JSON，不写 Doris）

## 典型执行顺序

1. **采样候选**
   ```bash
   python scripts/pipeline.py --step candidates --limit 100 --candidate-output data/candidates.jsonl
   ```

2. **调用 LLM，同时写入 Raw 表**
   ```bash
   python scripts/pipeline.py --step llm \
       --candidate-input data/candidates.jsonl \
       --payload-output data/payloads.jsonl \
       --llm-request-output data/llm_requests.jsonl
   ```

3. **调用 LLM 但只缓存 JSON（不写 Doris，节省 token）**
   ```bash
   python scripts/pipeline.py --step llm \
       --candidate-input data/candidates.jsonl \
       --payload-output data/payloads.jsonl \
       --llm-request-output data/llm_requests.jsonl \
       --skip-db-write
   ```

4. **将缓存写回 `return_fact_llm`**
   ```bash
   python scripts/pipeline.py --step raw --payload-input data/payloads.jsonl
   ```

5. **解析 payload 写入 `return_fact_details`**
   ```bash
   python scripts/pipeline.py --step parse --payload-input data/payloads.jsonl
   ```

6. **一次跑完**
   ```bash
   python scripts/pipeline.py --step all --limit 200
   ```

> **提示**  
> - DeepSeek 请求体模板见 `docs/llm_request_template.json`，可搭配 `prompt/deepseek_prompt.txt` 定制输出。  
> - 所有日志与缓存建议放在 `test/` 或 `data/` 目录，方便复现和回放。  
> - 运行前请确保 `.venv` 虚拟环境已激活，并在 `config/environment.yaml` 中配置正确的 Doris/DeepSeek 凭据。
