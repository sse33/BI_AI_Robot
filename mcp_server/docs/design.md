# MCP Server — 概要设计文档

> 创建日期：2026-05-14
> 状态：启动阶段（第一次迭代）

---

## 一、背景与目标

### 背景

现有系统（`python/`）是**定时批量日报**模式：`collect.py` 定时采集 → `analyze.py` 生成报告 → 推送飞书。

本次新增一套独立的 **MCP Server**，目标是支持**飞书 Agent 按需问数**。

### 目标

将观远 BI 仪表板的数据取数能力封装为 MCP 工具，供飞书自研 Agent 调用。

用户只需用自然语言与飞书 Agent 对话，Agent 自动调用 MCP 工具取数并组织回复。

---

## 二、核心设计决策

| 决策点 | 结论 | 理由 |
|---|---|---|
| 语言 | Python | 与现有代码库一致，维护方便 |
| API 调用方式 | subprocess 调 `guancli card preview -f json` | 第一迭代最简单；`-f json` 输出稳定；后期可升级为 httpx 直调 |
| MCP Transport | HTTP SSE | 飞书自研 Agent 需要 HTTP 可寻址的 MCP Server |
| 多轮会话 | 不处理 | 多轮上下文由飞书 Agent 自行管理，MCP 工具保持无状态 |
| 第一迭代范围 | 硬编码单个仪表板 | 先跑通链路，仪表板知识库治理完成后再开放动态选择 |
| 不动现有代码 | `python/` 目录完全不变 | 两套体系独立演进 |

---

## 三、问数模式说明

本系统**不是 NL2SQL**，也不依赖 ChatBI 自然语言转查询。

核心思路：**BI 仪表板已经是答案**。

- 仪表板已按"总分结构"设计好：汇总卡片 + 明细卡片分页管理
- MCP 工具的职责只是**取数**（把卡片/数据集上的结果数据结构化返回）
- Agent 负责**理解意图 + 选卡片 + 组织语言回复**
- 无需二次计算和统计，BI 已完成所有聚合

```
用户问 Agent
    ↓
Agent 判断去哪个卡片取数（依据：cards 知识库中的 business_description）
    ↓
Agent 调用 MCP 工具（get_card_data）
    ↓
MCP 返回结构化表格数据
    ↓
Agent 组织语言，回复用户
```

---

## 四、工具设计（第一迭代）

### 4.1 list_cards

**用途：** 列出当前仪表板的所有卡片及其业务描述，供 Agent 选择目标卡片。

**输入：** 无（硬编码仪表板）

**输出：**
```json
[
  {
    "card_id": "cd_xxx",
    "card_name": "城市销售汇总",
    "card_type": "table",
    "business_description": "展示各城市当日销售业绩，含销售额、件数、达成率"
  }
]
```

> 第一迭代：card 列表来自硬编码配置（`config.py`），或读取对应 `cards.yaml`。
> 后续迭代：接入知识库治理后，动态从 `guancli page get` 获取。

---

### 4.2 get_card_data

**用途：** 获取指定卡片的当前数据。

**输入：**
```
card_id: str        # 卡片 ID
filters: dict?      # 可选筛选条件，如 {"城市": "上海"}，无则按仪表板默认
limit: int?         # 默认 200，最大 1000（卡片接口限制）
```

**输出：**
```json
{
  "card_id": "cd_xxx",
  "card_name": "城市销售汇总",
  "row_count": 20,
  "columns": ["城市", "销售额", "件数", "达成率"],
  "data": [
    {"城市": "上海", "销售额": 1200000, "件数": 3200, "达成率": 0.95},
    ...
  ]
}
```

**底层调用：**
```bash
guancli card preview <card_id> -f json [--filter "城市 EQ 上海"] [--limit 200]
```

---

## 五、目录结构

```
mcp_server/
├── docs/
│   └── design.md          # 本文档
├── server.py              # MCP Server 主入口（HTTP SSE）
├── tools.py               # MCP tool 定义（list_cards / get_card_data）
├── bi_client.py           # 封装 guancli subprocess 调用
├── config.py              # 硬编码仪表板配置（page_id + 卡片列表）
└── requirements.txt
```

与现有目录的关系：
- `configs/{dashboard}/cards.yaml`：可复用 `business_description` 字段（知识库治理后）
- `python/`：完全独立，不引用

---

## 六、试验仪表板

| 字段 | 值 |
|---|---|
| page_id | `c38a7adbd12bc40eeaa00526` |
| 获取卡片列表 | `guancli page get c38a7adbd12bc40eeaa00526 -f json` |
| 取单张卡片数据 | `guancli card preview <card_id> -f json` |

---

## 七、后续迭代规划

| 迭代 | 内容 |
|---|---|
| 第一迭代（当前） | 硬编码仪表板，跑通 Agent → MCP → BI 全链路 |
| 第二迭代 | 补充 `list_dashboards` 工具，接入仪表板知识库 |
| 第三迭代 | 认证升级：从 subprocess → httpx 直调（token 从 guancli config 读取） |
| 后续 | 支持 `ds preview`（数据集级别，60k 行上限），覆盖更大数据量场景 |

---

## 八、技术依赖

```
mcp[server]     # Anthropic MCP Python SDK（HTTP SSE transport）
fastmcp         # 可选，更简洁的封装（待确认）
```

guancli 需已安装并完成 `auth login`，MCP Server 复用其 session。
