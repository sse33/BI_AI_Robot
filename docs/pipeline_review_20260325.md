# 日报流程复盘（2026-03-25）

## 当前完整流程

### 1. 数据收集 (`validate.py`)

```
Playwright 自动登录 bi.trendy-global.com
  → 提取 session cookie
  → GuanyuanClient (bi_card_fetcher.py)
      ├── 普通卡片：fetch_all_rows() 直接拉全量
      └── 5张需渠道分拆的卡片：fetch_by_channel()
           ├── 自营 filter → 拉数据
           ├── 托管 filter → 拉数据
           └── 联营 filter → 拉数据，合并 + 加"渠道"列
  → 并发 8 线程抓取所有卡片
  → 输出 outputs/daily_sales_manifest.json
```

**卡片清单（reports_meta.yaml 管理）：**

| 卡片 key | 抓取方式 | 说明 |
|---|---|---|
| `dailySalesOverview` | 单次 | 已含渠道维度 |
| `salesTrend` | 单次 | 已含渠道维度 |
| `categoryStructureRegular` | 按渠道×3 | 正价品类结构 |
| `categoryStructureOutlet` | 按渠道×3 | 奥莱品类结构 |
| `skcTop10` | 按渠道×3 | SKC TOP10 |
| `skcSellThroughCity` | 按渠道×3 | 近六波段城市动销率 |
| `drillCategoryBandSellThroughCity` | 按渠道×3 | 品类×波段铺货结构 |
| `drillSkcRankingStore` | 单次 | SKC店铺分布 |

---

### 2. 数据压缩 (`data_prep.py` + `analysis_city.yaml`)

```
manifest.json → build_data_text()
  按5个章节处理，每章节有 data_prep 规则：
  ├── mode: full_rows   → 过滤行/列，排序，top_n 限制
  ├── mode: aggregate   → group_by 聚合（sum/weighted_avg/count）
  └── mode: alert_only  → 只传预警触发行
  → 输出 ~21k tokens 的结构化文本
```

**5章节压缩策略：**

| 章节 | 数据视角 | ~tokens |
|---|---|---|
| 一、渠道城市业绩 | 渠道聚合 + 城市明细 + 折扣预警行 | 2,586 |
| 二、货品折扣结构 | 过滤总计行，只传占比/折损列 | 4,061 |
| 三、品类结构诊断 | 正价+奥莱，渠道×中类，预计算差值 | 4,772 |
| 四、SKC效率 | TOP10明细 + 店铺存货分布 | 3,083 |
| 五、波段动销铺货 | 城市动销率 + 品类×渠道铺货聚合 | 6,988 |

---

### 3. AI 分析 (`analyze.py`)

```
数据文本 + 分析指令（questions/alerts/output_hints）
  → Gemini 2.5 Pro 流式调用（SSE，避免代理超时）
  → 输出结构化报告（8个章节）
  → 保存 outputs/daily_sales_city_YYYYMMDD.md
  → 保存 outputs/_prompt_daily_sales_city_YYYYMMDD.txt（调试用）
```

---

### 4. 事实核查 + 推送

```
报告 → fact_check_report()
  → 抽样关键数字对照 manifest 核验
  → 输出核查通过率

报告 → 飞书 Webhook
  → 分段推送（markdown 格式）
```

---

## 当前已知局限

1. **Section 5 动销率全 0**：26A/26B 新波段尚无销售，已改为铺货风险分析，等有销售数据后可直接启用动销比较
2. **`drillSkcRankingStore` 未压缩**：94行全量传入 Section 4，后续可考虑按 SKC 匹配 TOP10 过滤
3. **每日覆盖写入**：同日运行两次会覆盖报告文件（无时间戳后缀）

---

## 各步骤待讨论优化空间

> 以下为待探讨项，尚未实施

### Step 1：数据收集
- [ ] Cookie 过期自动检测与重新登录（当前每次都走 Playwright 登录，可改为 cookie 有效时跳过）
- [ ] 卡片拉取失败时的重试与降级策略
- [ ] manifest 加版本/日期戳，支持历史回溯对比（如今日 vs 昨日）

### Step 2：数据压缩
- [ ] `drillSkcRankingStore` 压缩：只传与 TOP10 SKC 匹配的店铺行，而非全部 94 行
- [ ] Section 5 动销率：当新波段有销售数据时，自动切换回动销比较模式（而非当前的硬编码铺货分析）
- [ ] `data_prep.py` 的 `aggregate` 模式补充 `sort_by` / `top_n` 支持
- [ ] 货品折扣结构（Section 2）：当前按城市全量传入，可改为只传各渠道总计行，进一步压缩

### Step 3：AI 分析
- [ ] 多模板支持：`analysis_city.yaml`（当前）vs `analysis_store.yaml`（待完善）两套框架并行
- [ ] 历史对比维度：加入昨日/上周同期数据，让 AI 输出趋势判断而非单日截面
- [ ] System Prompt 优化：当前无角色定义，可加"资深零售分析师"角色设定提升分析深度

### Step 4：核查 & 推送
- [ ] 事实核查样本量偏少（当前仅抽查 4 条），可扩大到每章节各抽 2-3 条关键数字
- [ ] 飞书推送格式：当前纯文本 markdown，可考虑加卡片消息（富文本/图表截图）
- [ ] 推送失败重试机制
