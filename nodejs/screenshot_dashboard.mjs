/**
 * screenshot_dashboard.mjs
 * 登录后截取看板各卡片截图，用于与 API 数据核对
 */
import puppeteer from 'puppeteer';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const envPath = path.join(__dirname, '..', '.env');
if (fs.existsSync(envPath)) {
  for (const l of fs.readFileSync(envPath, 'utf8').split('\n')) {
    const m = l.match(/^([^#=\s]+)=(.*)$/);
    if (m) process.env[m[1]] = m[2].trim();
  }
}

const BASE_URL   = process.env.GY_BASE_URL;
const ACCOUNT    = process.env.GY_ACCOUNT;
const PASSWORD   = process.env.GY_PASSWORD;
const DASHBOARD  = 'https://bi.trendy-global.com/home/web-app/i752edbfe9d7d48ef8da1cde';
const OUT_DIR    = path.join(__dirname, '..', 'outputs');

fs.mkdirSync(OUT_DIR, { recursive: true });

const browser = await puppeteer.launch({ headless: true, executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', args: ['--window-size=1600,900'] });
const page    = await browser.newPage();
await page.setViewport({ width: 1600, height: 900 });

// 登录
console.log('[1] 登录...');
await page.goto(`${BASE_URL}/auth/login`, { waitUntil: 'networkidle2' });
await page.waitForSelector('img[alt="切换登录方式"]');
await page.click('img[alt="切换登录方式"]');
await page.waitForFunction(() => document.querySelector('.loginSection')?.style.display !== 'none');
await page.evaluate((a, p) => {
  const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  const ai = document.querySelector('input#loginId');
  const pi = document.querySelector('input#password');
  s.call(ai, a); ai.dispatchEvent(new Event('input', { bubbles: true }));
  s.call(pi, p); pi.dispatchEvent(new Event('input', { bubbles: true }));
}, ACCOUNT, PASSWORD);
await new Promise(r => setTimeout(r, 300));
await page.click('#loginBtn');
await page.waitForFunction(() => !location.pathname.startsWith('/auth'), { timeout: 30000 });
console.log('[1] 登录成功');

// 打开看板
console.log('[2] 打开看板...');
try {
  await page.goto(DASHBOARD, { waitUntil: 'networkidle0', timeout: 90000 });
} catch (e) {
  console.warn('[2] 页面未完全加载，继续截图:', e.message.slice(0, 60));
}
await new Promise(r => setTimeout(r, 8000)); // 等待卡片渲染
await page.screenshot({ path: path.join(OUT_DIR, 'dashboard_full.png'), fullPage: true });
console.log('[2] 全页截图已保存：outputs/dashboard_full.png');

// 截取各卡片
const cards = [
  { name: '每日销售概况', selector: null },
];

// 尝试截取页面中每个卡片容器
const cardContainers = await page.$$('[class*="card"], [class*="widget"], [class*="chart"]');
console.log(`[3] 找到 ${cardContainers.length} 个卡片容器`);

for (let i = 0; i < Math.min(cardContainers.length, 8); i++) {
  try {
    const box = await cardContainers[i].boundingBox();
    if (box && box.width > 200 && box.height > 100) {
      await cardContainers[i].screenshot({ path: path.join(OUT_DIR, `card_${i+1}.png`) });
      console.log(`  card_${i+1}.png  (${Math.round(box.width)}×${Math.round(box.height)})`);
    }
  } catch (e) {}
}

await browser.close();
console.log('\n全部截图已保存到 outputs/ 目录');
