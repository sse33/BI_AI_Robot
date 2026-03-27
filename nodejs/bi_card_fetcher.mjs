/**
 * bi_card_fetcher.mjs
 *
 * 观远 BI 卡片数据 API 抓取模块
 * 替代截图 + OCR 方案，直接通过 Public API 获取结构化数据
 *
 * 使用方式：
 *   import { GuanyuanClient } from './bi_card_fetcher.mjs';
 *   const client = new GuanyuanClient({ baseUrl, domain, email, password });
 *   await client.login();
 *   const data = await client.fetchCardData(cardId, { channel: '自营' });
 *
 * 环境变量（推荐放在 .env 或 agents/openai.yaml 里）：
 *   GY_BASE_URL   观远部署地址，如 https://bi.yourcompany.com
 *   GY_DOMAIN     观远域名（系统内部域，非网址），如 yourcompany
 *   GY_EMAIL      登录邮箱
 *   GY_PASSWORD   登录密码（明文，脚本内部会做 base64 encode）
 */

import { Buffer } from 'node:buffer';

// ─── 工具函数 ────────────────────────────────────────────────────────────────

/**
 * 对密码做 base64 encode（观远 API 要求）
 */
function encodePassword(plaintext) {
  return Buffer.from(plaintext, 'utf8').toString('base64');
}

/**
 * 简单重试包装
 */
async function withRetry(fn, retries = 3, delayMs = 1500) {
  let lastError;
  for (let i = 0; i < retries; i++) {
    try {
      return await fn();
    } catch (err) {
      lastError = err;
      if (i < retries - 1) {
        console.warn(`[retry ${i + 1}/${retries}] ${err.message}, 等待 ${delayMs}ms...`);
        await new Promise((r) => setTimeout(r, delayMs));
      }
    }
  }
  throw lastError;
}

// ─── 主类 ────────────────────────────────────────────────────────────────────

export class GuanyuanClient {
  /**
   * @param {object} opts
   * @param {string} opts.baseUrl   - 观远部署地址，末尾不带斜杠
   * @param {string} opts.domain    - 观远系统域名（内部域）
   * @param {string} opts.email     - 登录邮箱
   * @param {string} opts.password  - 登录密码（明文）
   */
  constructor(opts = {}) {
    this.baseUrl  = (opts.baseUrl  || process.env.GY_BASE_URL  || '').replace(/\/$/, '');
    this.domain   = opts.domain   || process.env.GY_DOMAIN   || '';
    this.email    = opts.email    || process.env.GY_EMAIL    || '';
    this.password = opts.password || process.env.GY_PASSWORD || '';
    this.token    = null;
    this.tokenExpireAt = null;

    if (!this.baseUrl || !this.domain || !this.email || !this.password) {
      throw new Error(
        '缺少必要配置：GY_BASE_URL / GY_DOMAIN / GY_EMAIL / GY_PASSWORD'
      );
    }
  }

  // ── 认证 ──────────────────────────────────────────────────────────────────

  async login() {
    if (this.token && this.tokenExpireAt && new Date() < new Date(this.tokenExpireAt)) {
      return;
    }

    const url  = `${this.baseUrl}/public-api/sign-in`;
    const body = {
      domain:   this.domain,
      email:    this.email,
      password: encodePassword(this.password),
    };

    const res = await fetch(url, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body:    JSON.stringify(body),
    });

    if (!res.ok) throw new Error(`[login] HTTP ${res.status}: ${await res.text()}`);

    const json = await res.json();
    if (json.result !== 'ok') throw new Error(`[login] 登录失败: ${JSON.stringify(json)}`);

    this.token         = json.response.token;
    this.tokenExpireAt = json.response.expireAt;
    console.log(`[login] 登录成功，token 有效期至 ${this.tokenExpireAt}`);
  }

  // ── 卡片数据 ──────────────────────────────────────────────────────────────

  async fetchCardData(cardId, opts = {}) {
    if (!this.token) await this.login();

    const {
      view          = 'GRID',
      limit         = 500,
      offset        = 0,
      filters       = [],
      dynamicParams = [],
    } = opts;

    const url  = `${this.baseUrl}/public-api/card/${cardId}/data`;
    const body = { dynamicParams, filters, limit, offset, view };

    const doFetch = async () => {
      const res = await fetch(url, {
        method:  'POST',
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
          'X-Auth-Token': this.token,
        },
        body: JSON.stringify(body),
      });

      if (res.status === 401) {
        console.warn('[fetchCardData] token 失效，重新登录...');
        this.token = null;
        await this.login();
        throw new Error('token_expired');
      }

      if (!res.ok) throw new Error(`[fetchCardData] HTTP ${res.status}: ${await res.text()}`);

      const json = await res.json();
      if (json.result !== 'ok') throw new Error(`[fetchCardData] 接口返回错误: ${JSON.stringify(json)}`);

      return json.response;
    };

    return withRetry(doFetch, 3, 1500);
  }

  async fetchAllRows(cardId, opts = {}) {
    const pageSize = opts.limit || 200;
    let offset     = 0;
    let allRows    = [];
    let columns    = null;

    while (true) {
      const data    = await this.fetchCardData(cardId, { ...opts, view: 'GRID', limit: pageSize, offset });
      const gridMain = data.gridMain || data;
      const header   = gridMain.header || [];
      const rows     = gridMain.rows   || [];

      if (!columns) columns = header.map((h) => h.name || h.displayName || h);
      allRows = allRows.concat(rows);

      if (rows.length < pageSize) break;
      offset += pageSize;
      console.log(`[fetchAllRows] cardId=${cardId} 已拉取 ${allRows.length} 行...`);
    }

    console.log(`[fetchAllRows] cardId=${cardId} 完成，共 ${allRows.length} 行`);
    return { columns, rows: allRows };
  }
}

// ─── 数据结构化解析器 ─────────────────────────────────────────────────────────

export function parseGridToObjects(rawData) {
  const { columns, rows } = rawData;
  return rows.map((row) => {
    const obj = {};
    columns.forEach((col, i) => { obj[col] = row[i]; });
    return obj;
  });
}

export function toMarkdownTable(records, colOrder) {
  if (!records || records.length === 0) return '（无数据）';
  const cols   = colOrder || Object.keys(records[0]);
  const header = `| ${cols.join(' | ')} |`;
  const sep    = `| ${cols.map(() => '---').join(' | ')} |`;
  const body   = records
    .map((r) => `| ${cols.map((c) => (r[c] ?? '')).join(' | ')} |`)
    .join('\n');
  return [header, sep, body].join('\n');
}

// ─── CLI 自测入口 ─────────────────────────────────────────────────────────────
if (process.argv[1].endsWith('bi_card_fetcher.mjs')) {
  const cardId  = process.argv[2];
  const channel = process.argv[3] || null;

  if (!cardId) {
    console.error('用法: node bi_card_fetcher.mjs <cardId> [channel]');
    process.exit(1);
  }

  const client = new GuanyuanClient();
  await client.login();

  const filters = channel
    ? [{ name: 'channel', filterType: 'IN', filterValue: [channel] }]
    : [];

  const raw     = await client.fetchAllRows(cardId, { filters });
  const records = parseGridToObjects(raw);

  console.log('\n--- Markdown 预览 ---');
  console.log(toMarkdownTable(records.slice(0, 10)));
  console.log(`\n共 ${records.length} 条记录`);
}
