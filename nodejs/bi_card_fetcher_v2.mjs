/**
 * bi_card_fetcher.mjs
 *
 * 观远 BI 卡片数据抓取模块（实测可用版）
 * 通过浏览器 session cookie 直接调用内部 /api/card/{id}/data 接口
 *
 * 实测环境：bi.trendy-global.com（赫基集团）
 * 实测时间：2026-03-18
 * 实测结论：
 *   - 接口路径是 /api/card/{id}/data（非 public-api）
 *   - 认证方式：依赖浏览器登录后的 session cookie，无需单独 token
 *   - 数据格式：透视表结构，行维度在 chartMain.row.meta，列维度在 chartMain.column.values
 *
 * ── 已确认的 cardId 映射表 ──────────────────────────────────────────────────
 *
 *   peaee175ceeb24483995edf1  →  每日销售概况（渠道×城市，正价+奥莱，39行）
 *                                 列：渠道/城市 + 业绩/店数/店均业绩/UPT/店均单数/客单价/入机折扣/实销折扣
 *
 *   k02a7d3097d94489381bbed7  →  每日销售 SKC TOP10
 *
 *   va60ffe8f39e94e2db7d1917  →  近期销售趋势（含实销折损/新旧货比）
 *
 *   cc9cdfd9a603d427c9292b80  →  运营中类结构（新/旧货×运营中类，42行）
 *
 *   n078e9c5ad540455889f3216  →  待识别（需切换渠道后再验证）
 *
 *   f88647253435141e8a88cac8  →  近六波 SKC 动销率（城市×波段）
 */

// ── cardId 常量表 ─────────────────────────────────────────────────────────────

export const CARD_IDS = {
  DAILY_SALES_OVERVIEW: 'peaee175ceeb24483995edf1',
  SKC_TOP10:            'k02a7d3097d94489381bbed7',
  SALES_TREND:          'va60ffe8f39e94e2db7d1917',
  CATEGORY_STRUCTURE:   'cc9cdfd9a603d427c9292b80',
  UNKNOWN_CARD:         'n078e9c5ad540455889f3216',
  SKC_SELL_THROUGH:     'f88647253435141e8a88cac8',
};

// ── 列名解析 ───────────────────────────────────────────────────────────────────

/** 去除 HTML 标签（如列名中的 <br>） */
function stripHtml(str) {
  return String(str ?? '').replace(/<[^>]+>/g, '').trim();
}

/**
 * 从观远 chartMain 透视表结构中提取列名
 *
 * 结构说明：
 *   column.values 是**列索引**数组：colValues[i] = 第 i 个指标列的层级描述数组
 *     colValues[i][0]    = 分组头（如 "正价"、"T+1销售"），有 zoneType:"METRIC_GROUP"
 *     colValues[i][last] = 指标定义（如 "业绩"、"金额"），有 type:"metric"
 *   row.meta = 行维度字段定义（如 "渠道", "城市", "skc编码"）
 *
 * @param {object} chartMain
 * @returns {{ dimCols: string[], metricCols: string[], allCols: string[] }}
 */
export function extractColumnNames(chartMain) {
  const rowMeta   = chartMain.row?.meta || [];
  const colValues = chartMain.column?.values || [];

  // 行维度列名
  const dimCols = rowMeta.map(m => stripHtml(m.alias || m.title || m.originTitle || `dim_${m.fdId}`));

  // 指标列名：colValues[i] = [level0, level1, ..., metricDef]
  // 将所有层的 title 拼接，保证列名唯一且完整反映层级
  const metricCols = colValues.map(colLevels => {
    const parts = colLevels.map(lvl => stripHtml(lvl.alias || lvl.title || '')).filter(Boolean);
    // 去除相邻重复（同一层名连续出现时只保留一次）
    const deduped = parts.filter((p, i) => i === 0 || p !== parts[i - 1]);
    return deduped.join('_');
  });

  return { dimCols, metricCols, allCols: [...dimCols, ...metricCols] };
}

// ── 数据行解析 ─────────────────────────────────────────────────────────────────

/**
 * 解析观远透视表行数据
 *
 * 结构说明：
 *   row.values[rowIdx][dimIdx].title  = 行维度的展示值（字符串）
 *   data[rowIdx][metricIdx]           = 指标值对象 { v, d } 或 null
 *
 * @param {object} chartMain
 * @returns {object[]}  每行是 { 列名: 值 } 的对象
 */
export function parseRows(chartMain) {
  const { dimCols, metricCols } = extractColumnNames(chartMain);
  const rowValues = chartMain.row?.values || [];
  const dataRows  = chartMain.data || [];

  return dataRows.map((metricRow, rowIdx) => {
    const dimVals = rowValues[rowIdx] || [];
    const obj = {};

    // 行维度值（文本）
    dimCols.forEach((col, i) => {
      obj[col] = dimVals[i]?.title ?? '';
    });

    // 指标值（数值）
    metricCols.forEach((col, i) => {
      const cell = metricRow?.[i];
      if (cell == null)              obj[col] = '';
      else if (typeof cell === 'object') obj[col] = cell.v ?? cell.d ?? '';
      else                           obj[col] = cell;
    });

    return obj;
  });
}

// ── Markdown 输出 ─────────────────────────────────────────────────────────────

/**
 * 对象数组 → Markdown 表格（用于塞进 LLM prompt）
 * @param {object[]} records
 * @param {string[]} [colOrder]
 */
export function toMarkdownTable(records, colOrder) {
  if (!records || records.length === 0) return '（无数据）';
  const cols   = colOrder || Object.keys(records[0]);
  const header = `| ${cols.join(' | ')} |`;
  const sep    = `| ${cols.map(() => '---').join(' | ')} |`;
  const body   = records.map(r =>
    `| ${cols.map(c => {
      const v = r[c] ?? '';
      if (typeof v === 'number') {
        if (v > 1000)                              return Math.round(v).toLocaleString();
        if (Number.isInteger(v))                   return v;
        if (Math.abs(v) <= 1 + 1e-9)              return (v * 100).toFixed(1) + '%';
        return v.toFixed(2);
      }
      return v;
    }).join(' | ')} |`
  ).join('\n');
  return [header, sep, body].join('\n');
}

// ── 主抓取类 ──────────────────────────────────────────────────────────────────

export class GuanyuanClient {
  /**
   * @param {object} opts
   * @param {string} opts.baseUrl  - 观远部署地址，默认 https://bi.trendy-global.com
   * @param {string} opts.cookies  - 登录后的 cookie 字符串
   *                                 从 Puppeteer 提取：
   *                                   const cookies = await page.cookies();
   *                                   const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join('; ');
   */
  constructor(opts = {}) {
    this.baseUrl = (opts.baseUrl || process.env.GY_BASE_URL || 'https://bi.trendy-global.com').replace(/\/$/, '');
    this.cookies = opts.cookies || process.env.GY_COOKIES || '';
  }

  /**
   * 抓取单张卡片（单页）
   *
   * @param {string} cardId
   * @param {object} opts
   * @param {number} opts.limit          - 每页条数，默认 500
   * @param {number} opts.offset         - 偏移量，默认 0
   * @param {Array}  opts.filters        - 过滤条件
   * @param {Array}  opts.dynamicParams  - 动态参数
   * @returns {{ cardId, columns, rows, totalCount, hasMoreData, rawChartMain }}
   */
  async fetchCard(cardId, opts = {}) {
    const {
      limit         = 500,
      offset        = 0,
      filters       = [],
      dynamicParams = [],
    } = opts;

    const headers = { 'Content-Type': 'application/json' };
    if (this.cookies) headers['Cookie'] = this.cookies;

    const resp = await fetch(`${this.baseUrl}/api/card/${cardId}/data`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ dynamicParams, filters, limit, offset, view: 'GRID' }),
    });

    if (!resp.ok) {
      throw new Error(`[fetchCard] HTTP ${resp.status} for cardId=${cardId}: ${await resp.text()}`);
    }

    const json = await resp.json();
    const cm   = json.chartMain;

    const { allCols } = extractColumnNames(cm);
    const rows        = parseRows(cm);

    return {
      cardId,
      columns:      allCols,
      rows,
      totalCount:   cm.count || rows.length,
      hasMoreData:  cm.hasMoreData || false,
      rawChartMain: cm,
    };
  }

  /**
   * 自动翻页，拉取卡片全量数据
   */
  async fetchAllRows(cardId, opts = {}) {
    const pageSize = opts.limit || 200;
    let offset     = 0;
    let allRows    = [];
    let columns    = null;

    while (true) {
      const result = await this.fetchCard(cardId, { ...opts, limit: pageSize, offset });
      if (!columns) columns = result.columns;
      allRows = allRows.concat(result.rows);

      if (!result.hasMoreData || result.rows.length < pageSize) break;
      offset += pageSize;
      console.log(`[fetchAllRows] cardId=${cardId} 已拉取 ${allRows.length} 行...`);
    }

    return { cardId, columns, rows: allRows };
  }
}

// ── 三渠道批量抓取 ─────────────────────────────────────────────────────────────

/**
 * 按渠道分别抓取同一张卡片
 *
 * @param {GuanyuanClient} client
 * @param {string}         cardId
 * @param {string}         channelField  - 渠道字段原始名，默认 '管理渠道名称_终端属性'
 * @returns {{ 自营: object[], 托管: object[], 联营: object[] }}
 */
export async function fetchByChannels(client, cardId, channelField = '管理渠道名称_终端属性') {
  const channels = ['自营', '托管', '联营'];
  const result   = {};
  for (const ch of channels) {
    console.log(`[fetchByChannels] 抓取 ${ch}...`);
    const data  = await client.fetchAllRows(cardId, {
      filters: [{ name: channelField, filterType: 'IN', filterValue: [ch] }],
    });
    result[ch] = data.rows;
  }
  return result;
}

// ── 完整日报数据抓取入口 ───────────────────────────────────────────────────────

/**
 * 一次性抓取日报所需全部卡片数据
 *
 * @param {GuanyuanClient} client
 * @returns {object}  包含所有模块数据的结构化对象，可直接序列化进 manifest.json
 */
export async function fetchDailyReport(client) {
  console.log('[fetchDailyReport] 开始并发抓取所有卡片...');

  const [overview, skcTop10, trend, categoryStructure, skcSellThrough] = await Promise.all([
    client.fetchAllRows(CARD_IDS.DAILY_SALES_OVERVIEW),
    client.fetchAllRows(CARD_IDS.SKC_TOP10),
    client.fetchAllRows(CARD_IDS.SALES_TREND),
    client.fetchAllRows(CARD_IDS.CATEGORY_STRUCTURE),
    client.fetchAllRows(CARD_IDS.SKC_SELL_THROUGH),
  ]);

  const report = {
    fetchedAt:           new Date().toISOString(),
    dailySalesOverview:  { columns: overview.columns,          rows: overview.rows },
    skcTop10:            { columns: skcTop10.columns,          rows: skcTop10.rows },
    salesTrend:          { columns: trend.columns,             rows: trend.rows },
    categoryStructure:   { columns: categoryStructure.columns, rows: categoryStructure.rows },
    skcSellThrough:      { columns: skcSellThrough.columns,    rows: skcSellThrough.rows },
  };

  console.log(`[fetchDailyReport] 完成。各模块行数：
  - 每日销售概况:  ${overview.rows.length}
  - SKC TOP10:     ${skcTop10.rows.length}
  - 销售趋势:      ${trend.rows.length}
  - 运营中类结构:  ${categoryStructure.rows.length}
  - 近六波动销率:  ${skcSellThrough.rows.length}`);

  return report;
}

// ── 与 bi_daily_capture.mjs 的集成示例 ───────────────────────────────────────
//
// 在 bi_daily_capture.mjs 里，登录成功后提取 cookie，然后调用：
//
//   import { GuanyuanClient, fetchDailyReport } from './bi_card_fetcher.mjs';
//
//   // Puppeteer 登录后
//   const cookies    = await page.cookies();
//   const cookieStr  = cookies.map(c => `${c.name}=${c.value}`).join('; ');
//   const client     = new GuanyuanClient({ cookieStr });
//   const reportData = await fetchDailyReport(client);
//
//   // 写入 manifest.json
//   fs.writeFileSync('outputs/manifest.json', JSON.stringify(reportData, null, 2));
//

// ── CLI 自测入口 ───────────────────────────────────────────────────────────────
// 用法：GY_COOKIES="SESSION=xxx" node bi_card_fetcher.mjs [cardId]

if (process.argv[1]?.endsWith('bi_card_fetcher.mjs')) {
  const cardId = process.argv[2] || CARD_IDS.DAILY_SALES_OVERVIEW;
  const client = new GuanyuanClient();
  const result = await client.fetchCard(cardId, { limit: 10 });

  console.log('\n列名:', result.columns.join(', '));
  console.log('\n前5行:');
  console.log(toMarkdownTable(result.rows.slice(0, 5)));
  console.log(`\n总计 ${result.totalCount} 行`);
}
