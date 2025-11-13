# 亚马逊退货标签与数据方案

> 完整聊天记录位于 `prompt/`（原始 PDF 与抽取文本）。本 README 仅保留关键结论，便于快速对齐目标与实现路径。

## 项目目标

- 以 iSPECLE 可伸缩水槽沥水架为样本，梳理美国买家关注点与典型退货话术。
- 输出 **MECE 的退货标签库**，确保运营、产品、客服对“退货原因”有统一语言。
- 设计 Doris/StarRocks 的落库方案，与 DeepSeek 等 LLM 打标结果对接。

## 核心产出

- **用户洞察**：16 个高频关注点（尺寸、场景、材质、防锈、承重、容量、安装、外观、价格、物流、社证等），并附真实留言示例，用于培训/质检。
- **终版退货标签库（示例）**
  - *适配与场景*：尺寸/兼容性不符、场景适配不足、变体/选型指引不清。
  - *结构与承载*：稳定性/防倾倒不足、容量/有效面积不足、分区/配件设计不合理、自重过大/移动不便。
  - *材质与外观*：材质/防锈失效、外观/颜色与实物不符、台面/器具保护不足、清洁/维护成本高。
  - *信息与体验*：安装/调节/固定性差、规格参数与宣传不一致、页面信息缺失/误导、社会证明与体验不符。
  - *价格与政策*：价格/促销不透明、价值/对比劣势、退换信息/政策体验不佳。
  - *履约与服务*：物流时效异常、包装防护不足、损坏到货（DOA/受损）、品牌/店铺服务不达标。
  - SOP：每条留言至少 1 个主标签，可叠加 1–2 个从标签，并支持“二级原因码”（如“刀叉篮过高”）。
- **打标示例**：提供“留言翻译 + 舆情判断 + 标签/证据”模板，帮助新同学快速上手。

## 数据建模与落库

### 现有表/视图

- `view_return_review_snapshot`（视图）：从 MySQL `jj_review` 过滤出美国站低星评论，输出 `review_id`、`review_en`、`review_source=2` 等字段，作为 LLM 打标的输入。
- `return_fact_llm`：DeepSeek 等 LLM 的原始输出表。`review_id` 为主键，`payload` 保存极简 JSON（含原文、翻译、情感、标签数组、证据）。
- `return_fact_details`：解析后的事实表，每条标签一行，字段包含 `review_id`、`tag_code`、`review_source`、`review_en`/`review_cn`、`sentiment`、`tag_name_cn`、`evidence` 等。
- `return_dim_tag`：标签维表，记录 `tag_code`、中文名、一级类目、定义、边界、生效区间、版本及启用状态。

### 入库与 ETL 流程

1. **候选采样**：从 `view_return_review_snapshot` 取差评文本，携带 `review_id`、`review_source` 进入 LLM Prompt。
2. **LLM 写入 Raw 层**：DeepSeek 产出极简 JSON，通过 Stream Load 插入 `return_fact_llm`，使用 `ON DUPLICATE KEY UPDATE` + Merge-on-Write 保证幂等。
3. **解析落地**：
   - Python(pymysql) 批量读取 `return_fact_llm.payload`。
   - 将顶层字段写入 `return_fact_details`（每条标签拆成一行），并校验 `tag_code` 必须存在于 `return_dim_tag`。
4. **质检**：通过 `SELECT review_id, json_length(payload->'$.tags')`、`SELECT review_id, tag_code, evidence` 等 SQL 监控条数与证据质量；必要时回查 `return_fact_llm` 获取原始 JSON。

### 核心事实表映射关系

- `view_return_review_snapshot`（候选留言视图）：输出 `review_id`、`review_en`、`review_source`，为 LLM 提供文本输入；`review_id` 在后续所有表中保持一致。
- `return_fact_llm`（Raw 层/LLM Output）：以 `review_id` 唯一标识，`payload` 保存完整 JSON，标签编码 `payload.tags[].tag_code` 必须与 `return_dim_tag.tag_code` 对齐。
- `return_fact_details`（结构化事实表）：记录 `review_id`、`tag_code`、`review_en`、`review_cn`、`sentiment`、`evidence` 等字段，来源于 `return_fact_llm.payload` 展开，每条标签一行，并引用 `return_dim_tag`。
- `return_dim_tag`（标签维表）：存放 `tag_code`、`tag_name_cn`、`category_name_cn`、`definition`、`boundary_note` 等元数据，为 `return_fact_details` 提供类目和定义说明。

链路总结：`view_return_review_snapshot` 提供原始文本 → DeepSeek 打标并写入 `return_fact_llm` → ETL 展开写入 `return_fact_details` → 与 `return_dim_tag` 衔接维度信息，形成可追溯的“候选 → Raw → 结构化 → 维度”闭环。

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

- 字段命名与数据库列保持一致：`review_*` 字段直接写入 `return_fact_details`，`tags[].tag_code`/`tag_name_cn`/`evidence` 对应 `tag_code`、`tag_name_cn`、`evidence` 列；如需主/从标签或置信度，可在后续版本扩展字段后同步更新解析脚本。
- 约束：无值字段不返回、证据只保留触发表述，Stream Load 开启 gzip；服务端做 JSON Schema 校验以兜底格式错误。
- 幂等：`INSERT ... ON DUPLICATE KEY UPDATE payload = VALUES(payload)`，结合 `enable_unique_key_merge_on_write=true` 避免重复。
- 参考资料：调用 DeepSeek 时传入的 JSON 模板示例见 `docs/llm_request_template.json`；默认提示词可直接编辑 `prompt/deepseek_prompt.txt`，脚本会自动加载。如需记录请求体，可在 CLI 中使用 `--llm-request-output` 输出 JSONL。

## 打标与运营使用建议

- 严格套用标签定义与边界描述：先锁定主标签（最能解释退货诉求），再选择直接相关的从标签。
- 若留言同时包含“功能缺陷 + 价值/价格抱怨”，优先记录功能性标签，再酌情追加“价值/对比劣势”。
- 将“二级原因码”写入备注或衍生字段，便于洞察（例：`STABILITY_TIP` 下区分“杯架缺挡杆”“止滑垫移位”）。
- 如需记录 ASIN、主从角色、置信度等，只需在 JSON 中新增字段，同时更新解析脚本；`return_fact_llm` 结构无需调整。

## 目录提示

- `prompt/chat.txt`：从 PDF 抽取的纯文本，便于全文搜索。
- `prompt/` 其他文件：包含 PDF 原件、SQL、Prompt 草稿、ETL 代码片段。

> 需要更多细节（完整对话、SQL 样例、Python 脚本）时，请直接查看 `prompt/` 目录。
