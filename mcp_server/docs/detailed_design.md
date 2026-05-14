# MCP Server — 详细设计文档

> 更新日期：2026-05-14
> 状态：第一迭代完成，本地验证通过

---

## 一、整体架构

```
飞书 Agent
    │  HTTP SSE（MCP 协议）
    ▼
MCP Server（server.py）
    │  Python subprocess
    ▼
guancli CLI（本机已安装并登录）
    │  观远 BI 内部 API
    ▼
观远 BI 仪表板数据
```

MCP Server 是无状态的轻量服务：
- 不持久化任何数据
- 不管理会话，每次工具调用独立执行
- 多轮对话上下文由飞书 Agent 自行维护

---

## 二、文件结构

```
mcp_server/
├── docs/
│   ├── design.md            # 概要设计（项目启动文档）
│   ├── detailed_design.md   # 本文档（详细设计）
│   └── usage.md             # 安装与使用说明
├── server.py                # FastMCP 主入口，注册工具，处理 HTTP SSE
├── tools.py                 # MCP 工具逻辑层（list_cards / get_card_data）
├── bi_client.py             # 数据层，封装 guancli subprocess 调用
├── config.py                # 硬编码仪表板配置（第一迭代）
├── test_client.py           # 本地调试脚本
└── requirements.txt         # fastmcp, python-dotenv
```

依赖关系（单向）：
```
server.py → tools.py → bi_client.py
                     → config.py
```

---

## 三、配置管理

### 3.1 环境变量

server.py 启动时从根目录 `.env` 加载（与 `python/` 版本共用同一文件）：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MCP_HOST` | `0.0.0.0` | 监听地址，公网部署保持默认；仅本机访问改为 `127.0.0.1` |
| `MCP_PORT` | `8000` | 监听端口 |
| `MCP_TRANSPORT` | `sse` | `sse`：飞书 Agent 使用；`stdio`：本地调试 |

优先级：**命令行参数 > 环境变量 > 默认值**

### 3.2 仪表板配置（config.py）

第一迭代硬编码，包含：
- `page_id`：仪表板页面 ID
- `cards[]`：数据卡片列表（已排除 SELECTOR / TEXT 类型）
  - `card_id`、`card_name`、`card_type`、`business_description`
- `available_filters`：可用筛选维度名称列表

后续迭代：接入知识库后改为动态从 `guancli page get --raw` 解析。

---

## 四、工具规格

### 4.1 list_cards

**用途：** 返回当前仪表板所有数据卡片及业务描述，供 Agent 选卡。

**无输入参数。**

**返回结构：**
```json
{
  "dashboard_name": "1.2 单品图册(SKC版)",
  "available_filters": ["实际波段", "运营中类", "skc编码", "..."],
  "cards": [
    {
      "card_id": "o6722f8db3ad0414f8a53c6a",
      "card_name": "上周销额",
      "card_type": "KPI_CARD",
      "business_description": "上周及累计销售额汇总..."
    }
  ]
}
```

**数据来源：** 直接读 `config.py`，无 BI 网络请求。

---

### 4.2 get_card_data

**用途：** 获取指定卡片的实时数据。

**输入参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `card_id` | string | 是 | 从 `list_cards` 结果中获取 |
| `filters` | dict | 否 | 筛选条件，字段名→值（单值 EQ）；不传则按仪表板默认 |
| `limit` | int | 否 | 最多返回行数，默认 200，上限 1000（卡片接口限制） |

**filters 示例：**
```json
{"实际波段": "SS26", "运营中类": "牛仔裤"}
```

**返回结构：**
```json
{
  "card_id": "o6722f8db3ad0414f8a53c6a",
  "card_name": "上周销额",
  "row_count": 1,
  "columns": ["▲销额%", "▲线下销额%", "上周销额", "上上周销额", "累计销额"],
  "data": [
    {
      "▲销额%": -0.2117,
      "▲线下销额%": -0.4153,
      "上周销额": 20489639,
      "上上周销额": 25990900,
      "累计销额": 2474340011
    }
  ]
}
```

**数值说明：**
- 数值字段直接返回原始 float/int，**不做单位换算**（BI 展示时才除以 10000 显示"万"）
- 百分比字段为小数（`-0.2117` = `-21.17%`）
- Agent 展示时需自行格式化

---

## 五、数据解析逻辑（bi_client.py）

guancli `card preview --raw` 返回观远 BI 内部 API 的原始 JSON，结构如下：

```
response.chartMain
├── column.values   → [[{title, ...}], ...]   列 header（多级时取最后一级）
├── row.values      → [[{title, ...}], ...]   行维度 header（PIVOT_TABLE 用）
└── data            → [[{v, t_idx?}, ...]]    行数据，v 是值，t_idx 是合并单元格引用
```

解析规则：
1. `column.values` 每个元素取 `[-1]["title"]` 作为列名（多级列头取最深层）
2. `row.values` 同理，提取行维度列名
3. 最终列顺序 = 行维度列 + 指标列
4. `t_idx` 合并单元格：直接取 `v` 值（对 AI 分析场景可接受，忽略跨单元格引用）

---

## 六、已验证卡片类型

| 类型 | 验证状态 | 说明 |
|---|---|---|
| KPI_CARD | ✅ | 单行聚合，解析正常 |
| PIVOT_TABLE | 待验证 | 有行维度，结构更复杂 |

---

## 七、后续迭代规划

| 迭代 | 内容 |
|---|---|
| 当前（第一迭代） | 硬编码仪表板，KPI_CARD 已验证，跑通飞书 Agent 全链路 |
| 第二迭代 | 验证 PIVOT_TABLE 解析；补充 `list_dashboards` 工具；接入知识库 |
| 第三迭代 | 认证升级：httpx 直调（读取 guancli config.json token，避免 subprocess） |
| 后续 | 支持 `ds preview`（60k 行上限）覆盖更大数据量需求 |
