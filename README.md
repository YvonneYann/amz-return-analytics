# 亚马逊退货标签与数据方案

> 完整聊天记录位于 `prompt/`（原始 `*.pdf` 及抽取文本），本 README 仅保留核心结论，方便快速对齐目标与方案。

## 项目目标

- 以 iSPECLE 可伸缩水槽沥水架为样本，梳理美国买家关注点与典型退货话术。
- 提炼 **MECE 的退货标签库**，支撑运营、产品和客服统一判责。
- 设计 Doris/StarRocks 的落库方案与 ETL 流程，承接 LLM（DeepSeek）输出的打标结果。

## 核心产出

- **用户洞察**：16 个购买关注点（尺寸匹配、场景伸缩、材质防锈、承重稳定、容量分区、安装方式、颜色外观、价格优惠、物流退货、销量口碑等），并给出一一对应的退货留言示例，说明高风险槽点。
- **终版退货标签库（主标签示例）**
  - *适配与场景*：尺寸/兼容性不符、场景适配不足、变体/选型指引不清。
  - *结构与承载*：稳定性/防倾倒不足、容量/有效面积不足、分区/配件设计不合理、自重过大/移动不便。
  - *材质与外观*：材质/防锈失效、外观/颜色与实物不符、台面/器具保护不足、清洁/维护成本高。
  - *信息与体验*：安装/调节/固定性差、规格参数与宣传不一致、页面信息缺失/误导、社会证明与体验不符。
  - *价格与政策*：价格/促销不透明、价值/对比劣势、退换信息/政策体验不佳。
  - *履约与服务*：物流时效异常、包装防护不足、损坏到货（DOA/受损）、品牌/店铺服务不达标。
  - 附带打标SOP：每条留言 1 个主标签 + 1~2 个直接相关从标签，可扩二级原因码（如“刀叉篮过高”）。
- **打标示例**：对真实评论进行“翻译-情感-标签-原文证据”拆解，作为训练运营小白的模板。

## 数据建模与落库

- **维表**
  - `dim_tag`：tag_id、tag_code、中文/英文名、定义、一级/二级分类、优先级。
  - `dim_tag_conflict`：互斥关系及冲突优先保留规则。
  - `dim_tag_example`：正反例语料（human/model/real_review 来源）。
  - `dim_product`：ASIN、标题、品牌、状态。
- **事实层**
  - `dwd_review`：留言原文/翻译、星级、验证标记，启用 inverted index 便于检索。
  - `fct_review_tag`：多对多桥表，存 review_id、tag_id、主/从角色、confidence、source、model_version。
  - 轻量追溯表 `return_review_fact_min_v1` + `return_review_tag_fact`，支撑快速看板。
  - 原始落地表 `return_fact_llm`（UNIQUE KEY review_id，字段：review_id、payload JSON、created_at）用于保存 LLM 产出的极简 JSON。

## LLM 输出规范

```json
{
  "review_id": "702-9563280-0645818_FPL1001M",
  "review_source": 2,          // 0=return,1=voc,2=review
  "review_en": "...",
  "review_cn": "...",
  "sentiment": -1,              // -1/0/1
  "tags": [
    {
      "tc": "PARTS_DESIGN",
      "tag_name_cn": "分区/配件设计不合理",
      "ev": "silverware cup doesn’t clip on because the bar is in the way"
      // 可选: "r":1 (primary), "cf":0.82
    }
  ]
}
```

- 提示词优化：锁定短键名、无值字段不返回、证据只保留触发表述、Stream Load 使用 gzip、服务端做 JSON Schema 校验。
- `ON DUPLICATE KEY UPDATE payload = VALUES(payload)` 结合 `enable_unique_key_merge_on_write=true`，保证幂等。

## 入库与 ETL 流程

1. **Raw 层**：DeepSeek 产出的 JSON 直接通过 Stream Load 写入 `return_fact_llm`（或 `return_review_raw`）。
2. **解析层**：Python（pymysql）按天读取 raw JSON → 插入 `return_review_fact_min_v1`（review 主体） → 展开 `tags` 写入 `return_review_tag_fact`。
3. **校验**：常用 SQL 示例 —— `SELECT review_id, json_length(tags) ...` / `SELECT review_id, tag_code, evidence_text ...` 检查入库结果。

## 打标与运营使用建议

- 统一使用终版标签库，先锁主标签（最能解释退货原因），再酌情叠加从标签。
- 若留言涵盖“功能缺陷 + 价值感差”，优先记录功能标签，再考虑“价值/对比劣势”。
- 结合二级原因码可输出整改优先级（如“稳定性/杯架缺挡杆”“材质/48h 生锈”）。
- LLM 打标若需扩展字段（如 ASIN、主/从、置信度），只需在 JSON 中追加短键并调整解析脚本，raw 表结构可保持不变。

## 目录提示

- `prompt/chat.pdf`：原始对话，含用户关注点、退货话术、标签库、SQL/ETL 方案。
- `prompt/chat.txt`：提取好的纯文本，便于检索。

> 如需更多上下文（完整聊天、SQL 细节、Python 样例），请直接查阅 `prompt/` 目录。
