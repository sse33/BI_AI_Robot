# MCP Server — 测试用例文档

> 更新日期：2026-05-14
> 仪表板：1.2 单品图册(SKC版)（page_id: c38a7adbd12bc40eeaa00526）

---

## 一、测试工具

```bash
cd mcp_server
source .venv/bin/activate

# 完整 Agent 流程模拟（推荐）
python simulate_agent.py <SKC编码>

# 单工具测试
python test_client.py

# 原始取数验证
python -c "from bi_client import get_card_data; import json; print(json.dumps(get_card_data('<card_id>', filters={'skc编码': '<SKC>'}), ensure_ascii=False, indent=2))"
```

---

## 二、仪表板筛选器与卡片联动关系

| 卡片名称 | 类型 | 监听的筛选器 |
|---|---|---|
| 上周销额 | KPI_CARD | 全部 14 个筛选器（含 skc编码） |
| 上周销量 | KPI_CARD | 全部 14 个筛选器（含 skc编码） |
| 上周折扣 | KPI_CARD | 全部 14 个筛选器（含 skc编码） |
| 周转W | KPI_CARD | 全部 14 个筛选器（含 skc编码） |
| 上周消化率 | KPI_CARD | 全部 14 个筛选器（含 skc编码） |
| 2/4/8/16/20周消化率 | KPI_CARD | 全部 14 个筛选器（含 skc编码） |
| 单品图册(SKC版_竖排) | PIVOT_TABLE | 运营中类、商品期（**不含 skc编码**） |
| 单品图册(SKC版_横排) | PIVOT_TABLE | 全部 14 个筛选器（含 skc编码） |
| 单品图册(SKC版_横排)_副本 | PIVOT_TABLE | 无联动 |
| 单品图册(SKC版_横排)-简易采买版 | PIVOT_TABLE | 无联动 |
| 简易版-营运 | PIVOT_TABLE | 无联动（且为 SPU 粒度） |

> 结论：用 `skc编码` 筛选时，共 **7 张卡片**响应（6 KPI + 横排）。

---

## 三、已知卡片数据格式

### 3.1 KPI_CARD（标准布局）

- `column.values` = 指标名列表
- `row.values` = 空
- `data` = 1 行 × N 指标
- 解析结果：1 个 dict，key=指标名，value=数值

**字段说明：**
- 百分比字段（`▲销额%`、折扣、消化率）：小数，如 `-0.21 = -21%`
- 金额字段（销额）：原始元，如 `20489639 = 约 2049 万`
- 数量字段：整数件数

### 3.2 PIVOT_TABLE 横排（转置布局）

- `row.values` = 指标名列表（M 个指标）
- `column.values` = SKC 编码列表（K 个 SKC）
- `data` = M 行 × K 列（每行=一个指标，每列=一个 SKC）
- 解析结果：K 个 dict，每个 dict 包含 M 个指标→值

**注意：** 单 SKC 筛选时返回 1 个 dict，包含该 SKC 的所有属性和指标。

---

## 四、测试用例

### TC-001：按 SKC 查询汇总指标

**场景：** 用户给定一个 SKC 编码，查询其在仪表板上的所有汇总数据。

**测试命令：**
```bash
python simulate_agent.py 6M2JJ44500F37
```

**Agent 调用流程：**
1. `get_cards_by_filter("skc编码")` → 返回 7 张卡片
2. 对 7 张卡片分别调用 `get_card_data(card_id, filters={"skc编码": "6M2JJ44500F37"})`

**已验证结果（2026-05-14）：**

| 卡片 | 返回行数 | 关键数值 |
|---|---|---|
| 上周销额 | 1 | 上周销额: 2049 万，累计销额: 2049 万 |
| 上周销量 | 1 | 上周销量: 391，累计销量: 391 |
| 上周折扣 | 1 | 上周折扣: 91.5%，累计折扣: 91.5% |
| 周转W | 1 | 周转W: 4.37（周） |
| 上周消化率 | 1 | 上周消化率: 18.6%，累计消化率: 18.6% |
| 2/4/8/16/20周消化率 | 1 | 各节点均为 18.6%（新品首周）|
| 单品图册(SKC版_横排) | 1 | 运营波段: 5A-2，吊牌价: 1990，上市日期: 2026-05-14 |

**通过标准：**
- [ ] 7 张卡片均返回数据，无报错
- [ ] KPI 卡均返回 1 行
- [ ] 横排明细表返回 1 行（单 SKC 过滤后）
- [ ] 百分比字段为小数（如 `-0.21`，不是字符串 `"-21%"`）

---

### TC-002：按实际波段查询

**场景：** 用户查询某波段的汇总数据。

**测试命令：**
```bash
python -c "
from tools import get_cards_by_filter, get_card_data
import json
cards = get_cards_by_filter('实际波段')['cards']
print(f'响应卡片数: {len(cards)}')
# 取上周销额卡片
result = get_card_data('o6722f8db3ad0414f8a53c6a', filters={'实际波段': 'SS26'})
print(json.dumps(result, ensure_ascii=False, indent=2))
"
```

**通过标准：**
- [ ] `get_cards_by_filter('实际波段')` 返回 7 张卡片（同 skc编码）
- [ ] 按波段筛选返回该波段的聚合数值

---

### TC-003：无筛选条件（全量数据）

**场景：** 用户查询整个仪表板不加筛选时的汇总。

**测试命令：**
```bash
python -c "
from tools import get_card_data
import json
result = get_card_data('o6722f8db3ad0414f8a53c6a')
print(json.dumps(result, ensure_ascii=False, indent=2))
"
```

**通过标准：**
- [ ] 返回全量数据的聚合值，无 null

---

### TC-004：无效 SKC 筛选

**场景：** 传入不存在的 SKC，验证返回行为。

**测试命令：**
```bash
python -c "
from tools import get_card_data
import json
result = get_card_data('o6722f8db3ad0414f8a53c6a', filters={'skc编码': 'INVALID_SKC_000'})
print(json.dumps(result, ensure_ascii=False, indent=2))
"
```

**通过标准：**
- [ ] 不报错，返回 1 行但所有数值为 `null`

---

### TC-005：横排 PIVOT_TABLE 多 SKC 场景

**场景：** 按运营中类筛选，横排返回多 SKC 的场景（验证转置解析）。

**测试命令：**
```bash
python -c "
from tools import get_card_data
import json
# 横排按运营中类筛选，预期多 SKC 返回
result = get_card_data('x01a786e3b192412e81dda72', filters={'运营中类': '牛仔裤'}, limit=5)
print(f'返回行数: {result[\"row_count\"]}')
print('列名:', result['columns'][:5])
if result['data']:
    print('第1行:', json.dumps(result['data'][0], ensure_ascii=False)[:200])
"
```

**通过标准：**
- [ ] 返回多行（每行对应一个 SKC 或一个指标维度）
- [ ] 列名包含真实指标名称（非序号）

---

## 五、已知问题和注意事项

| 问题 | 描述 | 状态 |
|---|---|---|
| 周转W 单位 | 原始值为 `库存金额 / 上周销售吊牌额`，单位周，示例 SKC 原始值 4.37（约 4.4 周周转） | 已知，需在 Agent 展示时注明"周" |
| 上上周销额为0 | 新品首周上市，上上周无销售，环比（▲销额%）返回 null | 已知，正常业务场景 |
| 百分比为小数 | 所有比率字段为小数（0.186 = 18.6%），Agent 展示时需格式化 | 已知，需 Agent 处理 |
| 卡片 1000 行上限 | `card preview` 接口最多返回 1000 行 | 设计限制，多 SKC 场景需注意 |
| 竖排卡片不响应 skc编码 | 竖排(beba57f7)仅响应 运营中类、商品期 | 设计如此，非 bug |

---

## 六、回归测试

每次修改 `bi_client.py` 或 `tools.py` 后，运行：

```bash
# 快速回归
python test_client.py

# 完整场景回归
python simulate_agent.py 6M2JJ44500F37
```

预期：输出与上方 TC-001 已验证结果一致。
