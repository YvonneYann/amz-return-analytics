# 退货标签与数据方案

> 说明：完整打磨记录保存在 `chat/` 目录；本 README 仅抽取关键结论，便于快速对齐目标与实现路径。

## 1. 项目背景

本项目旨在搭建一套可持续迭代、满足 MECE 原则的退货标签体系，并基于 Doris/StarRocks 与 DeepSeek LLM，构建“候选抽取 → 模型标注 → 原始入仓 → 结构化解析”的可追溯数据闭环：

- **统一话语体系**\
  让运营、产品、客服在讨论“退货原因”时使用同一套标签语言，减少口径歧义。
- **覆盖完整用户旅程**\
  以内生的用户行为主线为骨架（**看到页面 → 收货 → 使用 → 售后/退货**），将退货原因拆解为 5 个标签大类。
- **全链路可追溯**\
  利用 Doris/StarRocks 与 DeepSeek LLM 打标流程，将每条标签与其原文、定义及边界说明关联，支持审计与回溯。

---

## 2. 标签体系（家居类示例）

围绕“页面认知—实物体验—使用过程—服务履约”建立 5 个标签大类：

- **产品结构 / 适配体验**\
  衡量整体结构与场景适配程度，包括稳定性、容量/布局、分区配件设计以及尺寸、排水等与实际使用空间的契合度。

- **材质与外观**\
  聚焦材质耐久度与表面观感，例如防锈、防刮、涂层、气味、做工等，用于识别做工或保护力不足的问题。

- **安装与使用体验**\
  描述安装、组装及日常调节/固定的易用度；当操作繁琐或无法稳定使用时，均归入此类。

- **预期与价值感知**\
  聚焦商品宣传信息与买家实际体验之间的落差，包括规格描述、页面信息以及价格/价值感受等方面的失真。

- **履约与服务**\
  覆盖履约链路体验，如物流及时性、包装防护、到货完整度，以及客服/品牌在售后环节的响应情况。

---

## 3. 视图 / 表结构

- **return\_dim\_tag**（标签维表）

  - 内容：存放标签维度信息，为事实表提供标签定义、边界以及版本/生效期等维度信息，保证分析口径一致性。
  - 主键：`tag_code`

输出示例：

```json
{
"return_dim_tag": [
	{
		"tag_code" : "FIT_COMPAT",
		"tag_name_cn" : "尺寸\/兼容性不符",
		"category_code" : "CAT_STRUCT_FIT",
		"category_name_cn" : "产品结构\/适配体验",
		"level" : 2,
		"definition" : "与目标位置\/设备（如水槽、台面、柜体等）尺寸不匹配，导致无法放入、无法跨放，或间隙过大严重影响使用。",
		"boundary_note" : "尺寸能放下且主要问题为某特定场景下出现倾斜\/回流水等→“沥水\/排水问题”或“整体稳定性差\/易晃动”；仅为轻微缝隙、基本不影响使用→可不打本标签；由页面规格错误引起的认知偏差将由页面描述评估单独处理，本标签不区分该类客观误差。",
		"is_active" : 1,
		"version" : 2,
		"effective_from" : "2025-11-01",
		"effective_to" : null,
		"created_at" : "2025-11-17 04:55:33",
		"updated_at" : "2025-11-17 04:55:33"
	}
 ]
}
```

- **view\_return\_review\_snapshot**（候选视图）

  - 内容：从 MySQL `jj_review` 与 `jj_return_orders` 过滤出低星评论和退货留言，作为 LLM 输入的候选文本集合。

输出示例：

```json
{
"view_return_review_snapshot": [
	{
		"country" : "US",
		"fasin" : "B0BGHGXYJX",
		"asin" : "B0BGHH2L23",
		"review_date" : "2025-10-12 00:00:00",
		"review_id" : "R384TSBX2ZQOS",
		"review_source" : 2,
		"review_en" : "The design of this is so shockingly bad that I’m actually angry about it. The mechanism that makes it sizable causes you to have a “ledge” where dishes can’t sit evenly. Even though my sink fits firmly between the sizing the silverware cup doesn’t clip on because the bar is in the way. Additionally it doesn’t actually sit straight because it’s bent out of shape."
	}
 ]
}
```

- **return\_fact\_llm**（Raw 表）

  - 内容：存放 DeepSeek 返回的 JSON 字符串，payload 保留完整结构，便于审计与回溯。
  - 主键：`review_id`

LLM 输出规范：

```json
{
  "review_id": "R384TSBX2ZQOS",
  "review_source": 2,
  "review_en": "...",
  "review_cn": "...",
  "sentiment": -1,
  "tags": [
    {
      "tag_code": "FIT_COMPAT",
      "tag_name_cn": "尺寸\/兼容性不符",
      "evidence": "the silverware cup doesn’t clip on because the bar is in the way."
    }
  ]
}
```

- **return\_fact\_details**（结构化事实表）

  - 内容：对 Raw 数据按标签展开，形成标签粒度的结构化事实表，可与维度表进行多维分析。
  - 主键：`review_id`、`tag_code`

输出示例：

```json
{
"return_fact_details": [
	{
		"review_id" : "R384TSBX2ZQOS",
		"tag_code" : "FIT_COMPAT",
		"review_source" : 2,
		"review_en" : "The design of this is so shockingly bad that I’m actually angry about it. The mechanism that makes it sizable causes you to have a “ledge” where dishes can’t sit evenly. Even though my sink fits firmly between the sizing the silverware cup doesn’t clip on because the bar is in the way. Additionally it doesn’t actually sit straight because it’s bent out of shape.",
		"review_cn" : "这款产品的设计糟糕到让我感到愤怒。可调节大小的机制导致出现一个“凸起”，使得餐具无法平稳放置。尽管我的水槽尺寸合适，但银器杯却因为横杆的阻挡无法固定。此外，产品本身形状弯曲，无法直立。",
		"sentiment" : -1,
		"tag_name_cn" : "尺寸\/兼容性不符",
		"evidence" : "the silverware cup doesn’t clip on because the bar is in the way.",
		"created_at" : "2025-11-18 01:18:52",
		"updated_at" : "2025-11-18 01:18:52"
	}
 ]
}
```

---

## 4. ETL 流程

整体链路：

`view_return_review_snapshot` 提供原始文本 + `return_dim_tag` 提供标签定义\
→ DeepSeek 打标并写入 `return_fact_llm`\
→ ETL 展开写入 `return_fact_details`\
→ 形成“候选抽取 → 模型标注 → 原始入仓 → 结构化解析”的闭环。

**步骤拆解：**

1. **候选抽取**

   - 从 `view_return_review_snapshot` 拉取差评与退货留言。
   - 携带字段：`review_id`、`review_source`、`review_en`。

2. **模型标注 & 原始入仓**

   - 使用 DeepSeek 对文本进行打标，输出 JSON。
   - 脚本可选择：
     - 直接写入 `return_fact_llm`，或
     - 先将结果缓存到 `payloads.jsonl`（通过 `--skip-db-write` 参数控制）。

3. **结构化解析**

   - 使用 Python 解析 `payload`：
     - 将每个标签拆分为独立行写入 `return_fact_details`。
     - 若 `tags` 为空，则写入占位记录（例如 \`tag\_code = "NO\_TAG"）。