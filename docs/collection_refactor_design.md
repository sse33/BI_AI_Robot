# 采集层重构设计（讨论记录）

> 讨论日期：2026-03-25
> 当前版本基准快照：`docs/baseline/daily_sales_manifest_v1_20260325.json`

---

## 核心目标

从"业务专用脚本"升级为"可接入任意观远仪表板的通用采集工具"。

---

## 当前版本的硬编码问题

| 问题 | 位置 | 表现 |
|---|---|---|
| 只读取第一个 report | `bi_card_fetcher.py` | `_load_meta()` 取 `reports[0]`，CARD_IDS 全局变量 |
| 仪表板 URL 写死 | `validate.py` | `DASHBOARD_URL = "https://..."` |
| 验证摘要写死卡片 key | `validate.py` | `report.get("dailySalesOverview")` 等 |
| `channel_filter` 是业务特定逻辑 | `bi_card_fetcher.py` | 按渠道拆3次是业务专属 |
| 筛选器分拆维度写死 | `reports_meta.yaml` cards[] | `channel_filter` 字段冗余于 `public_filters` |

---

## 目标架构：四层分离

```
dashboards.yaml       → "采哪些"（注册表 + 采集开关）
cards.yaml            → "有什么"（卡片列表 + 列结构，discover 自动生成）
filters.yaml          → "怎么关联"（筛选器-卡片参数，discover 自动生成）
analysis.yaml         → "怎么分析"（分析框架，待讨论是否也可自动生成）
```

### 文件结构

```
configs/
  dashboards.yaml                  # 全局注册表

  daily_sales/
    cards.yaml        ← 自动生成
    filters.yaml      ← 自动生成
    analysis.yaml     ← 待定（人工 or 自动）

outputs/
  daily_sales/
    manifest_20260325.json
```

### `dashboards.yaml` 结构

```yaml
dashboards:
  - id: daily_sales
    name: "OCH线下每日销售报告"
    dashboard_url: "https://your-bi-domain.com/home/web-app/iXXXX"
    pg_id: "YOUR_PAGE_GROUP_ID"
    enabled: true
    schedule: "daily"

  - id: weekly_brand
    name: "品牌周报"
    dashboard_url: "..."
    pg_id: "..."
    enabled: false        # 未就绪，暂不采集
```

---

## 自动发现流程（`discover.py`）

### Phase 1：API 获取卡片全集（ground truth）

```
GET /api/page/{pg_id}
  → 所有卡片：cdId + cdType + 名称 + 布局位置（标签页归属）
  → 过滤 SELECTOR / TEXT，保留 CHART / DRILL
  → 得到 Set_API（应采集卡片全集）
```

### Phase 2：直接 API 采集元数据

```
对 Set_API 中每张卡片：
  POST /api/card/{cdId}/data（无 filter，limit=1）
  → 获取列结构（schema）和数据样本
  → 标签页里的卡片也直接调，不需要 UI 切换
```

### Phase 3：Playwright 完整性校验

```
打开仪表板 + 滚动全页，拦截 /api/card/*/data 请求
  → 得到 Set_Playwright（实际触发的卡片）
  → Gap = Set_API - Set_Playwright = 懒加载卡片

对每张懒加载卡片，结合 Phase 1 位置信息判断触发策略：
  ├── 所属非默认标签页  → 策略: click_tab:{tab_name}
  ├── 滚动后仍未触发    → 策略: scroll_wait
  ├── 折叠区域          → 策略: click_expand
  └── 未知              → 策略: manual（标记，人工确认）

** 注：已知 API 卡片列表，懒加载只影响完整性校验，
      数据获取仍直接走 API，不依赖 UI 触发 **
```

### Phase 4：筛选器关联发现（Playwright 拦截）

```
Playwright 的核心职责：嗅探筛选器参数

对每个公共筛选器：
  1. 记录当前所有卡片的 baseline 请求体
  2. 点击筛选器选项A → 拦截重发请求
  3. 对比：重发的卡片 = 与该筛选器关联
           新 request_body 中的 filters[] = 完整字段参数
              (fdId / dsId / cdId / sourceCdId / fdType 全部自动获取)

产出 filters.yaml：筛选器定义 + 每张关联卡片的传参模板
```

### Phase 5：分拆采集策略推断

```
对每张"与筛选器关联"的卡片：
  A. 不带筛选器拉全量
  B. 带筛选器（值=X）拉全量
  对比：
    情况1：A 的列名中包含筛选字段 → 数据已分维度，单次采集即可
    情况2：行数相同但数值列变化  → 数据被重聚合，需按筛选值分拆
    情况3：A 和 B 完全一致       → 筛选器对该卡片实际无效

产出：cards.yaml 中每张卡片的 collect_strategy 字段
  collect_strategy: single          # 单次采集
  collect_strategy: split_by_filter # 按筛选器分拆，需逐值采集
```

---

## Playwright 职责边界（重构后）

| 职责 | 重构前 | 重构后 |
|---|---|---|
| 登录获取 Cookie | ✅ | ✅ 保留 |
| 滚动拦截卡片数据 | ✅ 主力 | ❌ 改为直接 API |
| 验证截图 | ✅ | ✅ 保留（数据核对用）|
| 完整性校验 | ❌ | ✅ 新增（发现懒加载）|
| 筛选器参数嗅探 | 半自动 | ✅ 全自动化 |

---

## 关于分析框架自动化

> 待深入讨论，预留此节

用户观点：分析框架（`analysis.yaml`）也应可自动生成，而非人工编写。
思路：基于仪表板的"反向工程"——从卡片的列名、数据类型、仪表板标题、卡片名称，
推断每张卡片的分析意图，自动生成 questions / data_prep 规则。

---

## 基准对照

重构完成后，用以下指标对比新旧版本：

| 指标 | v1 基准值 | 重构后目标 |
|---|---|---|
| 采集卡片数 | 15 张 | ≥ 15 张（不能少） |
| 各卡片行数 | 见 `manifest_summary_v1.json` | 逐卡片对比偏差 ≤ 1% |
| 各卡片列名 | 见 `manifest_summary_v1.json` | 完全一致 |
| 采集耗时 | 待测 | 对比 |

---

## v1 基准卡片清单（2026-03-25）

| 卡片 key | 行数 | 列数 | 备注 |
|---|---|---|---|
| `dailySalesOverview` | 42 | 18 | 含渠道维度，单次采集 |
| `salesTrend` | 40 | 18 | 含渠道维度，单次采集 |
| `categoryStructureRegular` | 110 | 6 | 按渠道分拆×3 |
| `categoryStructureOutlet` | 113 | 6 | 按渠道分拆×3 |
| `skcTop10` | 30 | 17 | 按渠道分拆×3 |
| `skcSellThroughCity` | 49 | 50 | 按渠道分拆×3 |
| `drillCategoryBandSellThroughCity` | 420 | 51 | 按渠道分拆×3 |
| `drillSkcRankingStore` | 96 | 3 | 单次采集 |
| `skcSellThroughStoreRegular` | 86 | 19 | 待纳入分析框架 |
| `skcSellThroughStoreOutlet` | 21 | 19 | 待纳入分析框架 |
| `storeDetailRegular` | 73 | 7 | 待纳入分析框架 |
| `storeDetailOutlet` | 21 | 7 | 待纳入分析框架 |
| `storeTrendRegular` | 73 | 9 | 待纳入分析框架 |
| `storeTrendOutlet` | 21 | 9 | 待纳入分析框架 |
| `drillSellThroughStoreCategoryRegular` | 916 | 20 | 待纳入分析框架 |
| `drillSellThroughStoreCategoryOutlet` | 171 | 20 | 待纳入分析框架 |
