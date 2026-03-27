# BI Card Fetcher — Claude Code 接手上下文

> 由 Claude.ai 对话整理，时间：2026-03-18
> 目的：让 Claude Code 在本地直接接手，建项目、写文件、跑验证

---

## 背景

赫基集团（TRENDY GROUP）内部 BI 系统使用观远 BI，部署在：
- 地址：https://bi.trendy-global.com
- 目标看板：https://bi.trendy-global.com/home/web-app/i752edbfe9d7d48ef8da1cde
- 看板名称：och线下每日销售报告（宣总看板）

原有自动化项目路径：`~/.codex/skills/bi-daily-report-automation/`

原有项目已实现：BI 自动登录 → 切渠道 → 截图 → 结构化抽取 → 分析 → 飞书发送

**本次目标**：用 API 直接抓卡片数据，替代截图 + OCR 方案，提升稳定性和准确性。

---

## 实测发现（2026-03-18 当日验证）

### 接口信息

| 项目 | 值 |
|------|---|
| 接口路径 | `POST /api/card/{cardId}/data`（内部接口，非 public-api） |
| 认证方式 | 浏览器登录后的 session cookie，无需单独 token |
| 响应格式 | 透视表 JSON，核心字段在 `chartMain` |

### 已确认 cardId

| cardId | 模块 | 行数 |
|--------|------|------|
| `peaee175ceeb24483995edf1` | 每日销售概况（渠道×城市，正价+奥莱） | 39 |
| `k02a7d3097d94489381bbed7` | SKC TOP10 | 10 |
| `va60ffe8f39e94e2db7d1917` | 近期销售趋势 | 37 |
| `cc9cdfd9a603d427c9292b80` | 运营中类结构（新/旧货×运营中类） | 42 |
| `f88647253435141e8a88cac8` | 近六波 SKC 动销率 | — |
| `n078e9c5ad540455889f3216` | 待识别 | — |

### 响应数据结构要点

观远透视表有两个特殊结构需要处理：

1. **多层列头（colSpan）**
   - `chartMain.column.values[0]` 是顶层（如"正价"、"奥莱"），有 `colSpan` 字段
   - `chartMain.column.values[最后一层]` 是底层（如"业绩"、"UPT"）
   - 需要展开 colSpan 与底层配对，生成 `正价_业绩`、`奥莱_UPT` 这样的列名

2. **合并单元格（t_idx）**
   - `cell.t_idx = "rowIndex:colIndex"` 表示该格值引用自第 rowIndex 行
   - 解析时需要追踪引用，填入实际值

3. **行维度**在 `chartMain.row.meta`，每项有 `alias`/`title`/`originTitle` 字段

---

## 待完成的任务

Claude Code 接手后请完成以下工作：

### Task 1：建立独立项目

在本地创建项目：`~/.codex/skills/bi-daily-report-automation/scripts/bi-card-fetcher/`

文件结构：
```
bi-card-fetcher/
├── bi_card_fetcher.mjs       ← 原版（public-api + token，泛用）
├── bi_card_fetcher_v2.mjs    ← 实测版（session cookie，赫基专用）
├── package.json
├── README.md
└── .env.example
```

### Task 2：验证 v2 脚本

登录方式（账号密码登录，非扫码）：
- 登录页：https://bi.trendy-global.com/auth/login
- 登录步骤：点右上角电脑图标切换到账密登录
- **注意：账密已知，但请从环境变量读取，不要硬编码**

用 Puppeteer 跑一次完整流程：
1. 登录 → 提取 cookie
2. 调用 `fetchDailyReport(client)` 抓取全部5张卡片
3. 输出到 `outputs/manifest_test.json`
4. 打印每张卡片的行数和前3行数据做验证

### Task 3：识别 n078e9c5ad540455889f3216

这张卡片在之前的测试中未能识别模块名称，需要：
1. 登录后调用接口
2. 打印列名和前5行数据
3. 对照看板截图确认是哪个模块

### Task 4：集成到现有 bi_daily_capture.mjs

在原有脚本的截图抽取部分之后，加入 API 抓取：
```js
import { GuanyuanClient, fetchDailyReport } from './bi-card-fetcher/bi_card_fetcher_v2.mjs';

// Puppeteer 登录成功后（page 已存在）
const cookieStr  = (await page.cookies()).map(c => `${c.name}=${c.value}`).join('; ');
const client     = new GuanyuanClient({ cookies: cookieStr });
const reportData = await fetchDailyReport(client);
fs.writeFileSync('outputs/manifest.json', JSON.stringify(reportData, null, 2));
```

---

## 两个脚本的完整源码

### bi_card_fetcher.mjs（原版，泛用）

```js
/**
 * bi_card_fetcher.mjs  ── 原版（泛用）
 * 认证：public-api/sign-in → token
 * 环境变量：GY_BASE_URL / GY_DOMAIN / GY_EMAIL / GY_PASSWORD
 */

import { Buffer } from 'node:buffer';

function encodePassword(plaintext) {
  return Buffer.from(plaintext, 'utf8').toString('base64');
}

async function withRetry(fn, retries = 3, delayMs = 1500) {
  let lastError;
  for (let i = 0; i < retries; i++) {
    try { return await fn(); }
    catch (err) {
      lastError = err;
      if (i < retries - 1) {
        console.warn(`[retry ${i + 1}/${retries}] ${err.message}`);
        await new Promise(r => setTimeout(r, delayMs));
      }
    }
  }
  throw lastError;
}

export class GuanyuanClient {
  constructor(opts = {}) {
    this.baseUrl  = (opts.baseUrl  || process.env.GY_BASE_URL  || '').replace(/\/$/, '');
    this.domain   = opts.domain   || process.env.GY_DOMAIN   || '';
    this.email    = opts.email    || process.env.GY_EMAIL    || '';
    this.password = opts.password || process.env.GY_PASSWORD || '';
    this.token    = null;
    this.tokenExpireAt = null;
    if (!this.baseUrl || !this.domain || !this.email || !this.password)
      throw new Error('缺少必要配置：GY_BASE_URL / GY_DOMAIN / GY_EMAIL / GY_PASSWORD');
  }

  async login() {
    if (this.token && this.tokenExpireAt && new Date() < new Date(this.tokenExpireAt)) return;
    const res = await fetch(`${this.baseUrl}/public-api/sign-in`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ domain: this.domain, email: this.email, password: encodePassword(this.password) }),
    });
    if (!res.ok) throw new Error(`[login] HTTP ${res.status}: ${await res.text()}`);
    const json = await res.json();
    if (json.result !== 'ok') throw new Error(`[login] 登录失败: ${JSON.stringify(json)}`);
    this.token = json.response.token;
    this.tokenExpireAt = json.response.expireAt;
    console.log(`[login] 登录成功，token 有效期至 ${this.tokenExpireAt}`);
  }

  async fetchCardData(cardId, opts = {}) {
    if (!this.token) await this.login();
    const { view = 'GRID', limit = 500, offset = 0, filters = [], dynamicParams = [] } = opts;
    const doFetch = async () => {
      const res = await fetch(`${this.baseUrl}/public-api/card/${cardId}/data`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json; charset=utf-8', 'X-Auth-Token': this.token },
        body: JSON.stringify({ dynamicParams, filters, limit, offset, view }),
      });
      if (res.status === 401) { this.token = null; await this.login(); throw new Error('token_expired'); }
      if (!res.ok) throw new Error(`[fetchCardData] HTTP ${res.status}: ${await res.text()}`);
      const json = await res.json();
      if (json.result !== 'ok') throw new Error(`[fetchCardData] 接口错误: ${JSON.stringify(json)}`);
      return json.response;
    };
    return withRetry(doFetch, 3, 1500);
  }

  async fetchAllRows(cardId, opts = {}) {
    const pageSize = opts.limit || 200;
    let offset = 0, allRows = [], columns = null;
    while (true) {
      const data = await this.fetchCardData(cardId, { ...opts, view: 'GRID', limit: pageSize, offset });
      const gridMain = data.gridMain || data;
      const header = gridMain.header || [];
      const rows = gridMain.rows || [];
      if (!columns) columns = header.map(h => h.name || h.displayName || h);
      allRows = allRows.concat(rows);
      if (rows.length < pageSize) break;
      offset += pageSize;
    }
    return { columns, rows: allRows };
  }
}

export function parseGridToObjects(rawData) {
  const { columns, rows } = rawData;
  return rows.map(row => Object.fromEntries(columns.map((col, i) => [col, row[i]])));
}

export function toMarkdownTable(records, colOrder) {
  if (!records || records.length === 0) return '（无数据）';
  const cols = colOrder || Object.keys(records[0]);
  return [
    `| ${cols.join(' | ')} |`,
    `| ${cols.map(() => '---').join(' | ')} |`,
    ...records.map(r => `| ${cols.map(c => r[c] ?? '').join(' | ')} |`),
  ].join('\n');
}
```

### bi_card_fetcher_v2.mjs（实测版，赫基专用）

```js
/**
 * bi_card_fetcher_v2.mjs  ── 实测版（赫基集团专用）
 * 实测时间：2026-03-18
 * 接口路径：/api/card/{id}/data（内部接口）
 * 认证方式：Puppeteer session cookie
 * 环境变量：GY_BASE_URL / GY_COOKIES
 */

export const CARD_IDS = {
  DAILY_SALES_OVERVIEW: 'peaee175ceeb24483995edf1',
  SKC_TOP10:            'k02a7d3097d94489381bbed7',
  SALES_TREND:          'va60ffe8f39e94e2db7d1917',
  CATEGORY_STRUCTURE:   'cc9cdfd9a603d427c9292b80',
  UNKNOWN_CARD:         'n078e9c5ad540455889f3216',
  SKC_SELL_THROUGH:     'f88647253435141e8a88cac8',
};

export function extractColumnNames(chartMain) {
  const rowMeta   = chartMain.row?.meta || [];
  const colValues = chartMain.column?.values || [];
  const dimCols   = rowMeta.map(m => m.alias || m.title || m.originTitle || `dim_${m.fdId}`);
  const metricCols = [];
  if (colValues.length === 1) {
    colValues[0].forEach(c => metricCols.push(c.alias || c.title));
  } else if (colValues.length >= 2) {
    const expanded = [];
    colValues[0].forEach(cell => {
      const span = cell.colSpan || 1;
      for (let i = 0; i < span; i++) expanded.push(cell.alias || cell.title || '');
    });
    colValues[colValues.length - 1].forEach((cell, i) => {
      const prefix = expanded[i] ? `${expanded[i]}_` : '';
      metricCols.push(`${prefix}${cell.alias || cell.title}`);
    });
  }
  return { dimCols, metricCols, allCols: [...dimCols, ...metricCols] };
}

export function parseRows(chartMain) {
  const { allCols } = extractColumnNames(chartMain);
  const rawRows = chartMain.data || [];
  const resolveCell = (rowIdx, colIdx) => {
    const cell = rawRows[rowIdx]?.[colIdx];
    if (!cell && cell !== 0) return '';
    if (cell.t_idx !== undefined) {
      const [refRowIdx] = String(cell.t_idx).split(':').map(Number);
      const refCell = rawRows[refRowIdx]?.[colIdx];
      return refCell?.v ?? refCell?.d ?? '';
    }
    return cell.v ?? cell.d ?? '';
  };
  return rawRows.map((_, rowIdx) =>
    Object.fromEntries(allCols.map((col, colIdx) => [col, resolveCell(rowIdx, colIdx)]))
  );
}

export function toMarkdownTable(records, colOrder) {
  if (!records || records.length === 0) return '（无数据）';
  const cols = colOrder || Object.keys(records[0]);
  return [
    `| ${cols.join(' | ')} |`,
    `| ${cols.map(() => '---').join(' | ')} |`,
    ...records.map(r => `| ${cols.map(c => {
      const v = r[c] ?? '';
      if (typeof v === 'number') {
        if (v > 1000) return Math.round(v).toLocaleString();
        if (v > 0 && v < 1) return (v * 100).toFixed(1) + '%';
      }
      return v;
    }).join(' | ')} |`),
  ].join('\n');
}

export class GuanyuanClient {
  constructor(opts = {}) {
    this.baseUrl = (opts.baseUrl || process.env.GY_BASE_URL || 'https://bi.trendy-global.com').replace(/\/$/, '');
    this.cookies = opts.cookies || process.env.GY_COOKIES || '';
  }

  async fetchCard(cardId, opts = {}) {
    const { limit = 500, offset = 0, filters = [], dynamicParams = [] } = opts;
    const headers = { 'Content-Type': 'application/json' };
    if (this.cookies) headers['Cookie'] = this.cookies;
    const resp = await fetch(`${this.baseUrl}/api/card/${cardId}/data`, {
      method: 'POST', headers,
      body: JSON.stringify({ dynamicParams, filters, limit, offset, view: 'GRID' }),
    });
    if (!resp.ok) throw new Error(`[fetchCard] HTTP ${resp.status} cardId=${cardId}: ${await resp.text()}`);
    const json = await resp.json();
    const cm = json.chartMain;
    const rows = parseRows(cm);
    return { cardId, columns: extractColumnNames(cm).allCols, rows, totalCount: cm.count || rows.length, hasMoreData: cm.hasMoreData || false };
  }

  async fetchAllRows(cardId, opts = {}) {
    const pageSize = opts.limit || 200;
    let offset = 0, allRows = [], columns = null;
    while (true) {
      const result = await this.fetchCard(cardId, { ...opts, limit: pageSize, offset });
      if (!columns) columns = result.columns;
      allRows = allRows.concat(result.rows);
      if (!result.hasMoreData || result.rows.length < pageSize) break;
      offset += pageSize;
    }
    return { cardId, columns, rows: allRows };
  }
}

export async function fetchByChannels(client, cardId, channelField = '管理渠道名称_终端属性') {
  const result = {};
  for (const ch of ['自营', '托管', '联营']) {
    const data = await client.fetchAllRows(cardId, {
      filters: [{ name: channelField, filterType: 'IN', filterValue: [ch] }],
    });
    result[ch] = data.rows;
  }
  return result;
}

export async function fetchDailyReport(client) {
  console.log('[fetchDailyReport] 开始并发抓取...');
  const [overview, skcTop10, trend, category, sellThrough] = await Promise.all([
    client.fetchAllRows(CARD_IDS.DAILY_SALES_OVERVIEW),
    client.fetchAllRows(CARD_IDS.SKC_TOP10),
    client.fetchAllRows(CARD_IDS.SALES_TREND),
    client.fetchAllRows(CARD_IDS.CATEGORY_STRUCTURE),
    client.fetchAllRows(CARD_IDS.SKC_SELL_THROUGH),
  ]);
  const report = {
    fetchedAt:          new Date().toISOString(),
    dailySalesOverview: { columns: overview.columns,    rows: overview.rows },
    skcTop10:           { columns: skcTop10.columns,    rows: skcTop10.rows },
    salesTrend:         { columns: trend.columns,       rows: trend.rows },
    categoryStructure:  { columns: category.columns,    rows: category.rows },
    skcSellThrough:     { columns: sellThrough.columns, rows: sellThrough.rows },
  };
  console.log(`[fetchDailyReport] 完成：overview=${overview.rows.length} skcTop10=${skcTop10.rows.length} trend=${trend.rows.length} category=${category.rows.length} sellThrough=${sellThrough.rows.length}`);
  return report;
}
```

---

## 安全提示

⚠️ 本次 Claude.ai 对话中曾明文出现过登录账密，对话结束后建议去 BI 系统修改密码。

后续所有脚本中账密通过环境变量传入，不要硬编码：
```bash
# .env（加入 .gitignore，不提交）
GY_BASE_URL=https://bi.trendy-global.com
GY_ACCOUNT=2000018847
GY_PASSWORD=你的新密码
GY_COOKIES=  # Puppeteer 登录后自动填入，无需手动设置
```
