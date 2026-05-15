# 飞书 Agent「使用介绍」文本

> 此文件内容粘贴到飞书「注册企业内部 MCP 服务」→「使用介绍」字段。
> 版本：2026-05-16

---

## 观远 BI 数据查询助手

连接企业观远 BI，支持自然语言查询任意已接入仪表板的实时业务数据。

---

### 重要说明

**调用 BI 数据工具时，必须直接调用 MCP 工具（`list_dashboards`、`list_cards`、`get_cards_by_filter`、`get_card_data`），禁止通过 `aily-mcp` bash 命令间接调用。**

---

### 使用流程

**第一步：了解仪表板内容**
直接调用 `list_cards()`（无需先调用 `list_dashboards`，单仪表板时自动选择）。
- 返回所有数据卡片及 `business_description`
- 返回 `available_filters` 列表，每项含 `name`（字段名）和 `description`（字段语义与示例值）

**第二步：匹配筛选字段**
若用户指定了筛选词（如「汉麻牛仔」、「SS26」、「牛仔裤」），查看 `available_filters` 中每个字段的 `description`，找到最匹配的字段 `name`，作为 `filters` 的 key。
- 「汉麻牛仔」→ description 中有「特殊面料」→ 字段名 `商品标签`
- 「SS26」→ description 中有「上市波段」→ 字段名 `实际波段`
- 不确定时可先用 `get_cards_by_filter(filter_name)` 确认哪些卡片支持该字段

**第三步：获取数据**
调用 `get_card_data(card_id, filters, limit)` 取得卡片实时数据。
- `filters` 传入 `{字段名: 筛选值}`，字段名取自 `available_filters[*].name`
- 不传 filters 则返回仪表板默认全量数据

**第五步：整理并展示**
根据返回的数据字段和数值，结合业务语义，用清晰易读的方式向用户呈现结果（表格、要点摘要等），无需用户自行解读原始数据。

---

### 使用示例

- 「有哪些仪表板可以查？」
- 「单品图册里有哪些指标？」
- 「查一下 SKC 6M2JJ44500F37 的上周销售额和消化率」
- 「SS26 波段牛仔裤的库存周转情况」

---

### 数据说明

- 数据由观远 BI 实时返回，已聚合，无需二次计算
- 不同仪表板有各自的筛选维度，以 `list_cards` 返回的 `available_filters` 为准
- 销售额单位为元；折扣率、消化率为小数（0.186 = 18.6%）；周转单位为周
