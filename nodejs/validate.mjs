/**
 * validate.mjs — Puppeteer 完整验证流程
 * 1. 浏览器登录观远 BI
 * 2. 提取 session cookie
 * 3. 抓取全部卡片数据
 * 4. 输出到 outputs/manifest_test.json
 * 5. 打印每张卡片行数和前3行数据
 *
 * 使用前复制 .env.example 为 .env 并填入账号密码
 * 运行：node validate.mjs
 */

import puppeteer from 'puppeteer';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

// 加载 .env（如有）
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const envPath = path.join(__dirname, '..', '.env');
if (fs.existsSync(envPath)) {
  const lines = fs.readFileSync(envPath, 'utf8').split('\n');
  for (const line of lines) {
    const m = line.match(/^\s*([^#=\s]+)\s*=\s*(.*)\s*$/);
    if (m) process.env[m[1]] = m[2];
  }
}

import { GuanyuanClient, fetchDailyReport, CARD_IDS } from './bi_card_fetcher_v2.mjs';

const BASE_URL = process.env.GY_BASE_URL || 'https://bi.trendy-global.com';
const ACCOUNT  = process.env.GY_ACCOUNT  || '';
const PASSWORD = process.env.GY_PASSWORD || '';

if (!ACCOUNT || !PASSWORD) {
  console.error('请在 .env 中设置 GY_ACCOUNT 和 GY_PASSWORD');
  process.exit(1);
}

async function loginAndGetCookies() {
  console.log('[puppeteer] 启动浏览器...');
  const browser = await puppeteer.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
  const page    = await browser.newPage();

  try {
    console.log('[puppeteer] 打开登录页...');
    await page.goto(`${BASE_URL}/auth/login`, { waitUntil: 'networkidle2', timeout: 30000 });

    // 点击右上角电脑图标切换到账密登录
    const pcIconSel = '[class*="pc-login"], [data-testid="pc-login"], .login-switch-btn';
    const pcIcon = await page.$(pcIconSel);
    if (pcIcon) {
      await pcIcon.click();
      await page.waitForTimeout(1000);
    }

    // 点击右上角图标切换到账密登录（默认显示飞书扫码）
    console.log('[puppeteer] 切换到账密登录...');
    await page.waitForSelector('img[alt="切换登录方式"]', { timeout: 10000 });
    await page.click('img[alt="切换登录方式"]');
    await page.waitForFunction(
      () => document.querySelector('.loginSection')?.style.display !== 'none',
      { timeout: 5000 }
    );

    console.log('[puppeteer] 填写账号密码...');
    // 用 nativeInputValueSetter 触发 React 受控组件更新
    await page.evaluate((account, password) => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      const accountInput  = document.querySelector('input#loginId, input[placeholder="账号"]');
      const passwordInput = document.querySelector('input#password, input[placeholder="密码"]');
      setter.call(accountInput,  account);  accountInput.dispatchEvent(new Event('input', { bubbles: true }));
      setter.call(passwordInput, password); passwordInput.dispatchEvent(new Event('input', { bubbles: true }));
    }, ACCOUNT, PASSWORD);

    await new Promise(r => setTimeout(r, 300));

    console.log('[puppeteer] 点击登录按钮...');
    await page.click('#loginBtn');

    // 等待登录成功（URL 离开 /auth）
    await page.waitForFunction(
      () => !location.pathname.startsWith('/auth'),
      { timeout: 30000 }
    );

    const cookies = await page.cookies();
    const cookieStr = cookies.map(c => `${c.name}=${c.value}`).join('; ');
    console.log(`[puppeteer] 登录成功，提取到 ${cookies.length} 个 cookie`);
    return cookieStr;
  } finally {
    await browser.close();
  }
}

const DASHBOARD_URL = 'https://bi.trendy-global.com/home/web-app/i752edbfe9d7d48ef8da1cde';

async function getDashboardTitle(cookieStr) {
  const browser = await puppeteer.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
  const page    = await browser.newPage();
  try {
    // 注入 cookie 后直接访问看板，获取页面标题
    const cookieObjs = cookieStr.split('; ').map(pair => {
      const [name, ...rest] = pair.split('=');
      return { name, value: rest.join('='), domain: 'bi.trendy-global.com' };
    });
    await page.setCookie(...cookieObjs);
    await page.goto(DASHBOARD_URL, { waitUntil: 'networkidle2', timeout: 60000 });
    const title = await page.title();
    console.log(`[puppeteer] 看板标题: ${title}`);
    return title;
  } catch (e) {
    console.warn('[puppeteer] 获取看板标题失败:', e.message.slice(0, 60));
    return null;
  } finally {
    await browser.close();
  }
}

async function main() {
  const cookies = await loginAndGetCookies();
  const client  = new GuanyuanClient({ cookies });

  console.log('\n[fetch] 开始抓取所有卡片...');
  const report = await fetchDailyReport(client);

  // 抓取看板标题
  console.log('\n[puppeteer] 获取看板标题...');
  report.dashboardTitle = await getDashboardTitle(cookies);

  // 识别未知卡片
  console.log('\n[fetch] 抓取未知卡片...');
  try {
    const unknown = await client.fetchAllRows(CARD_IDS.UNKNOWN_CARD);
    report.unknownCard = { columns: unknown.columns, rows: unknown.rows };
    console.log(`[unknown] 列名: ${unknown.columns.join(', ')}`);
    console.log(`[unknown] 前5行:`);
    unknown.rows.slice(0, 5).forEach((r, i) => console.log(`  [${i}]`, r));
  } catch (e) {
    console.warn('[unknown] 抓取失败:', e.message);
  }

  // 写入输出文件
  const outDir  = path.join(__dirname, '..', 'outputs');
  const outFile = path.join(outDir, 'manifest_test.json');
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(outFile, JSON.stringify(report, null, 2));
  console.log(`\n[output] 已写入 ${outFile}`);

  // 打印各卡片摘要
  const cards = [
    ['每日销售概况',  report.dailySalesOverview],
    ['SKC TOP10',    report.skcTop10],
    ['近期销售趋势',  report.salesTrend],
    ['运营中类结构',  report.categoryStructure],
    ['SKC动销率',    report.skcSellThrough],
  ];
  console.log('\n===== 验证摘要 =====');
  for (const [name, card] of cards) {
    console.log(`\n【${name}】共 ${card.rows.length} 行`);
    console.log('列名:', card.columns.join(', '));
    card.rows.slice(0, 3).forEach((r, i) => console.log(`  [${i}]`, r));
  }
}

main().catch(err => { console.error(err); process.exit(1); });
