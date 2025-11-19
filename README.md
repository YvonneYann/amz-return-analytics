# 亚马逊退货标签与数据方案

> 完整聊天记录保存在 `chat/` 目录；此 README 聚焦关键结论，便于快速对齐目标与实现路径。

## 项目目标

本项目旨在搭建一套可持续迭代的 MECE 退货标签库，确保运营、产品、客服在讨论“退货原因”时使用同一语言，并以内生的用户行为主线（看到页面 → 收货 → 使用 → 售后/退货）覆盖 5 个标签大类。同时，结合 Doris/StarRocks 与 DeepSeek LLM 打标流程构建“候选抽取 → 模型标注 → 原始入仓 → 结构化解析”的可追溯闭环，让每个标签都能回溯到原文及其定义/边界。

## 核心产出

- **退货标签库（示例）**
  - *产品结构/适配体验*：衡量整体结构与场景适配，包括稳定性、容量/布局、分区配件设计以及尺寸/排水等与实际使用空间的契合度。
  - *材质与外观*：关注材质耐久度与表面观感（防锈、防刮、涂层/气味/做工等），用于识别做工或保护力不足的问题。
  - *安装与使用体验*：描述安装、组装及日常调节/固定的易用度，当操作繁琐或无法稳定使用时都会落入此类。
  - *预期与价值感知*：聚焦于商品宣传信息与买家实际体验的落差，包括规格描述、页面信息以及价格/价值感受等失真。
  - *履约与服务*：覆盖履约链路的体验，如物流及时性、包装防护、到货完整度以及客服/品牌在售后环节的响应。
  - SOP：每条留言至少 1 个主标签，可叠加 1~2 个从标签；如需更细颗粒，可记录“二级原因码”（例：杯架缺挡杆）。
- **打标示例**：提供“留言原文+翻译+情感+标签/证据”的标准模板，便于培训与质检。

## 数据建模与落库

### 视图/表

- `view_return_review_snapshot`（候选视图）：从 MySQL `jj_review` 过滤出美国站低星评论，输出 `review_id`、`review_en`、`review_source=2` 等字段，作为 LLM 输入。
- `return_fact_llm`（Raw 表）：存放 DeepSeek 返回的 JSON 字符串，主键 `review_id`，`payload` 内含原文、翻译、情感、标签数组、证据。
- `return_fact_details`（结构化事实）：解析 Raw 后按标签展开，每行包含 `review_id`、`tag_code`、`review_source`、`review_en`/`review_cn`、`sentiment`、`tag_name_cn`、`evidence` 等。
- `return_dim_tag`（标签维表）：存放 `tag_code`、`tag_name_cn`、`category`、`definition`、`boundary_note`、`version`、生效区间、启用状态等。

### 核心事实表映射关系

- `view_return_review_snapshot` → 生成候选文本，`review_id` 贯穿全链路。
- `return_fact_llm` → 缓存 LLM 原始 JSON（Raw 层），字段 `payload` 保存完整结构。
- `return_fact_details` → 将 Raw 展开为标签粒度的结构化记录。
- `return_dim_tag` → 标签维度信息（定义、边界、一级类目、版本/生效期），供事实表关联。

### 入库与 ETL 流程

链路概览：`view_return_review_snapshot` 提供原始文本 → DeepSeek 打标并写入 `return_fact_llm` → ETL 展开写入 `return_fact_details` → 与 `return_dim_tag` 衔接维度，形成“候选抽取 → 模型标注 → 原始入仓 → 结构化解析”闭环。

1. **候选抽取**：从 `view_return_review_snapshot` 拉取差评文本，携带 `review_id`、`review_source`、`review_en`。
2. **模型标注&原始入仓**：DeepSeek 输出 JSON，脚本可选择直接写入 `return_fact_llm`，或先缓存 `payloads.jsonl`（`--skip-db-write`）。
3. **结构化解析**：Python 解析 `payload`，将每个标签拆为独立行写入 `return_fact_details`；若 `tags` 为空会写入占位记录（`tag_code="NO_TAG"`）。

## LLM 输出规范

```json
{
  "review_id": "702-9563280-0645818_FPL1001M",
  "review_source": 2,
  "review_en": "...",
  "review_cn": "...",
  "sentiment": -1,
  "tags": [
    {
      "tag_code": "PARTS_DESIGN",
      "tag_name_cn": "分区/配件设计不合理",
      "evidence": "silverware cup doesn’t clip on because the bar is in the way"
    }
  ]
}
```

- 字段与数据库列保持一致：`review_*` 字段写入 `return_fact_details`，`tags[].tag_code/tag_name_cn/evidence` 映射至标签列。
- 约束：`review_source` 取值 0=return、1=voc、2=review；`sentiment` 为 -1/0/1；若无标签则返回空数组。
- 容错：脚本会去掉 ```json fenced code```，并记录 `resp.status_code/resp.text` 便于排查。
- 请求示例与提示词：见 `docs/llm_request_template.json` 与 `prompt/deepseek_prompt.txt`。
- DeepSeek/Doris 连接：统一配置在 `config/environment.yaml`。
