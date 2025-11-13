# 脚本与流程节点说明

本文描述当前仓库中与数据管道相关的脚本/模块，说明它们归属的流程节点，以及各自的输入/输出形式，方便按需独立运行或调试。

## 目录结构概览

```
pipeline/
  config.py
  doris_client.py
  deepseek_client.py
  models.py
  steps.py
scripts/
  pipeline.py
```

## 模块明细

### `pipeline/config.py`（公共配置模块）
- **流程节点**：全链路通用。
- **用途**：读取 `config/environment.yaml`，解析 Doris 与 DeepSeek 的连接参数。
- **输入**：YAML 配置文件路径。
- **输出**：`AppConfig` 数据类实例（包含 `DorisConfig`、`DeepSeekConfig`）。

### `pipeline/models.py`（数据模型定义）
- **流程节点**：全链路通用。
- **用途**：定义 `CandidateReview`、`TagFragment`、`LLMPayload`、`FactDetailRow` 等数据结构；负责 LLM payload 的 JSON 序列化。
- **输入**：无（模块级定义）。
- **输出**：供其他模块引用的数据类。

### `pipeline/doris_client.py`（Doris 访问层）
- **流程节点**：
  1. 候选采样（`view_return_review_snapshot`）。
  2. Raw 存储（`return_fact_llm`）。
  3. 解析写入（`return_fact_details`）。
  4. 维度查询（`return_dim_tag`）。
- **用途**：封装 Doris/MySQL 协议的 CRUD 操作，含 `fetch_candidates`、`upsert_return_fact_llm`、`fetch_payloads`、`insert_return_fact_details`、`fetch_dim_tag_map`。
- **输入**：`DorisConfig`；各函数的参数（limit、payload 等）。
- **输出**：候选列表、payload 列表或写入返回值（无显式返回）。

### `pipeline/deepseek_client.py`（LLM 调用层）
- **流程节点**：DeepSeek 打标阶段。
- **用途**：按 README 规范调用 DeepSeek Chat Completions API，返回结构化的 `LLMPayload`。
- **输入**：`CandidateReview`。
- **输出**：`LLMPayload`（含 `tags[]`）。

### `pipeline/steps.py`（单节点执行逻辑）
- **流程节点**：
  1. `step_fetch_candidates` → 候选视图。
  2. `step_call_llm` → DeepSeek 打标 + 写入 `return_fact_llm`。
  3. `step_parse_payloads` → 解析 payload → 写入 `return_fact_details`。
- **输入**：`DorisClient`、`DeepSeekClient`、可选 JSONL/内存对象。
- **输出**：列表（候选/ payload），或直接写 DB（解析步骤）。

### `scripts/pipeline.py`（命令行入口）
- **流程节点**：支持单节点或整链执行。
- **用途**：CLI 工具，通过 `--step` 切换执行阶段，并可用 JSONL 文件串联输入/输出，便于逐步调试。
- **输入**：
  - `--step {candidates,llm,parse,all}`
  - `--config config/environment.yaml`
  - `--limit N`
  - 可选 `--candidate-output/--candidate-input/--payload-output/--payload-input`
- **输出**：
  - `candidates` 步：输出候选日志 + 可选 JSONL 文件。
  - `llm` 步：写入 `return_fact_llm`，可选输出 payload JSONL。
  - `parse` 步：写入 `return_fact_details`。
  - `all` 步：串联以上三步，不生成额外文件。

## 典型运行姿势

1. **仅采样候选**  
   ```bash
   python scripts/pipeline.py --step candidates --limit 100 \
       --candidate-output data/candidates.jsonl
   ```
2. **离线调用 LLM（读取 JSONL）**  
   ```bash
   python scripts/pipeline.py --step llm \
       --candidate-input data/candidates.jsonl \
       --payload-output data/payloads.jsonl
   ```
3. **解析 payload 并写入 Doris**  
   ```bash
   python scripts/pipeline.py --step parse \
       --payload-input data/payloads.jsonl
   ```
4. **一次跑完**  
   ```bash
   python scripts/pipeline.py --step all --limit 200
   ```

通过上述拆分，可以按节点检查输入/输出数据，也方便在中断或调试时复用已有中间结果。
