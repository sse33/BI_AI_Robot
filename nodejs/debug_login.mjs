/**
 * debug_login.mjs — 调试登录页面结构
 */
import puppeteer from 'puppeteer';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const envPath = path.join(__dirname, '..', '.env');
if (fs.existsSync(envPath)) {
  for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
    const m = line.match(/^\s*([^#=\s]+)\s*=\s*(.*)\s*$/);
    if (m) process.env[m[1]] = m[2];
  }
}

const BASE_URL = process.env.GY_BASE_URL || 'https://bi.trendy-global.com';
const ACCOUNT  = process.env.GY_ACCOUNT  || '';
const PASSWORD = process.env.GY_PASSWORD || '';

const browser = await puppeteer.launch({ headless: true });
const page    = await browser.newPage();

await page.goto(`${BASE_URL}/auth/login`, { waitUntil: 'networkidle2', timeout: 30000 });
await page.screenshot({ path: 'outputs/debug_1_initial.png', fullPage: true });
console.log('[1] 初始页面已截图');

// 打印页面结构
const html = await page.evaluate(() => document.body.innerHTML.slice(0, 3000));
console.log('[HTML 前3000字符]:\n', html);

// 找所有按钮
const buttons = await page.$$eval('button', els => els.map(el => ({ text: el.textContent.trim(), class: el.className, type: el.type })));
console.log('[buttons]:', JSON.stringify(buttons, null, 2));

// 找所有 input
const inputs = await page.$$eval('input', els => els.map(el => ({ type: el.type, placeholder: el.placeholder, name: el.name, class: el.className })));
console.log('[inputs]:', JSON.stringify(inputs, null, 2));

// 用 React nativeInputValueSetter 填值
await page.evaluate((account, password) => {
  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  const allInputs = [...document.querySelectorAll('input')];
  const accountInput  = allInputs.find(i => i.type === 'text' || i.placeholder.includes('账号'));
  const passwordInput = allInputs.find(i => i.type === 'password' || i.placeholder.includes('密码'));
  if (accountInput) {
    nativeInputValueSetter.call(accountInput, account);
    accountInput.dispatchEvent(new Event('input', { bubbles: true }));
    accountInput.dispatchEvent(new Event('change', { bubbles: true }));
  }
  if (passwordInput) {
    nativeInputValueSetter.call(passwordInput, password);
    passwordInput.dispatchEvent(new Event('input', { bubbles: true }));
    passwordInput.dispatchEvent(new Event('change', { bubbles: true }));
  }
}, ACCOUNT, PASSWORD);

await new Promise(r => setTimeout(r, 500));
await page.screenshot({ path: 'outputs/debug_2_filled.png', fullPage: true });
console.log('[2] 填值后截图');

// 点击登录按钮
await page.evaluate(() => {
  const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('登录') || b.type === 'submit');
  console.log('clicking button:', btn?.textContent);
  btn?.click();
});

await new Promise(r => setTimeout(r, 3000));
await page.screenshot({ path: 'outputs/debug_3_after_click.png', fullPage: true });
console.log('[3] 点击后截图，当前 URL:', page.url());

await browser.close();
