"""
validate.py — Playwright 完整验证流程
1. 浏览器登录观远 BI
2. 提取 session cookie
3. 抓取全部卡片数据
4. 输出到 outputs/manifest_test.json
5. 打印每张卡片行数和前3行数据

使用前复制 .env.example 为 .env 并填入账号密码
运行：python validate.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

# ── 加载 .env ─────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

from bi_card_fetcher import GuanyuanClient, CARD_IDS, fetch_daily_report  # noqa: E402

BASE_URL  = os.environ.get("GY_BASE_URL", "https://bi.trendy-global.com")
ACCOUNT   = os.environ.get("GY_ACCOUNT", "")
PASSWORD  = os.environ.get("GY_PASSWORD", "")

DASHBOARD_URL = "https://bi.trendy-global.com/home/web-app/i752edbfe9d7d48ef8da1cde"

if not ACCOUNT or not PASSWORD:
    print("请在 .env 中设置 GY_ACCOUNT 和 GY_PASSWORD", file=sys.stderr)
    sys.exit(1)


async def login_and_get_cookies() -> str:
    """登录后返回 cookie 字符串"""
    print("[playwright] 启动浏览器...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        context = await browser.new_context(viewport={"width": 1600, "height": 900})
        page    = await context.new_page()

        try:
            print("[playwright] 打开登录页...")
            await page.goto(f"{BASE_URL}/auth/login", wait_until="domcontentloaded", timeout=30000)

            # 切换到账密登录（默认显示飞书扫码）
            print("[playwright] 切换到账密登录...")
            await page.wait_for_selector('img[alt="切换登录方式"]', timeout=10000)
            await page.click('img[alt="切换登录方式"]')
            await page.wait_for_function(
                "() => document.querySelector('.loginSection')?.style.display !== 'none'",
                timeout=5000,
            )

            print("[playwright] 填写账号密码...")
            # 用 nativeInputValueSetter 触发 React 受控组件更新
            await page.evaluate(
                """([account, password]) => {
                    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                    const ai = document.querySelector('input#loginId, input[placeholder="账号"]');
                    const pi = document.querySelector('input#password, input[placeholder="密码"]');
                    setter.call(ai, account); ai.dispatchEvent(new Event('input', { bubbles: true }));
                    setter.call(pi, password); pi.dispatchEvent(new Event('input', { bubbles: true }));
                }""",
                [ACCOUNT, PASSWORD],
            )
            await page.wait_for_timeout(300)

            print("[playwright] 点击登录按钮...")
            await page.click("#loginBtn")

            # 等待登录成功（URL 离开 /auth）
            await page.wait_for_function(
                "() => !location.pathname.startsWith('/auth')",
                timeout=30000,
            )

            cookies = await context.cookies()
            cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
            print(f"[playwright] 登录成功，提取到 {len(cookies)} 个 cookie")
            return cookie_str

        finally:
            await browser.close()


async def get_dashboard_title_and_screenshot(cookie_str: str) -> str | None:
    """注入 cookie 访问看板，截取验证截图，返回页面标题"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            args=["--window-size=1920,1080"],
        )
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page    = await context.new_page()
        try:
            cookie_objs = []
            for pair in cookie_str.split("; "):
                if "=" in pair:
                    name, _, value = pair.partition("=")
                    cookie_objs.append({
                        "name": name, "value": value,
                        "domain": "bi.trendy-global.com", "path": "/",
                    })
            await context.add_cookies(cookie_objs)

            await page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(10000)  # 等待卡片数据渲染完成

            title = await page.title()
            print(f"[playwright] 看板标题: {title}")

            # 清空筛选器，确保截图显示全渠道总计
            try:
                clear_btn = page.locator('button:has-text("清空"), span:has-text("清空")')
                if await clear_btn.count() > 0:
                    await clear_btn.first.click()
                    await page.wait_for_timeout(3000)  # 等待表格刷新
                    print("[playwright] 已清空筛选器，等待全渠道数据刷新")
            except Exception as e:
                print(f"[playwright] 清空筛选器失败（{str(e)[:60]}），截图可能含过滤数据")

            out_path = ROOT_DIR / "outputs" / "verify_overview.png"
            await page.screenshot(path=str(out_path), full_page=False)
            print(f"[playwright] 验证截图已保存: outputs/verify_overview.png")

            return title
        except Exception as e:
            print(f"[playwright] 截图失败: {str(e)[:80]}", file=sys.stderr)
            return None
        finally:
            await browser.close()


async def main():
    cookies = await login_and_get_cookies()
    client  = GuanyuanClient(cookies=cookies)

    print("\n[fetch] 开始抓取所有卡片...")
    report = fetch_daily_report(client)

    # 抓取看板标题 + 验证截图
    print("\n[playwright] 访问看板，截取验证截图...")
    report["dashboardTitle"] = await get_dashboard_title_and_screenshot(cookies)

    # 识别未知卡片
    print("\n[fetch] 抓取未知卡片...")
    try:
        unknown = client.fetch_all_rows(CARD_IDS["UNKNOWN_CARD"])
        report["unknownCard"] = {"columns": unknown["columns"], "rows": unknown["rows"]}
        print(f"[unknown] 列名: {', '.join(unknown['columns'])}")
        print("[unknown] 前5行:")
        for i, row in enumerate(unknown["rows"][:5]):
            print(f"  [{i}]", row)
    except Exception as e:
        print(f"[unknown] 抓取失败: {e}", file=sys.stderr)

    # 写入输出文件（文件名从 reports_meta.yaml 读取）
    from bi_card_fetcher import _REPORT_META
    out_dir  = ROOT_DIR / "outputs"
    out_file = out_dir / _REPORT_META.get("manifest_file", "manifest.json")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[output] 已写入 {out_file}")

    # 打印各卡片摘要
    cards = [
        ("每日销售概况", report.get("dailySalesOverview")),
        ("SKC TOP10",    report.get("skcTop10")),
        ("近期销售趋势", report.get("salesTrend")),
        ("运营中类结构", report.get("categoryStructure")),
        ("SKC动销率",    report.get("skcSellThrough")),
    ]
    print("\n===== 验证摘要 =====")
    for name, card in cards:
        if not card:
            continue
        rows = card.get("rows", [])
        cols = card.get("columns", [])
        print(f"\n【{name}】共 {len(rows)} 行")
        print("列名:", ", ".join(cols))
        for i, row in enumerate(rows[:3]):
            print(f"  [{i}]", row)


if __name__ == "__main__":
    asyncio.run(main())
