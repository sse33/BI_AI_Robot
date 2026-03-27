"""
screenshot_dashboard.py
登录后截取看板各卡片截图，用于与 API 数据核对

运行：python screenshot_dashboard.py
"""

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from playwright.async_api import async_playwright

# ── 加载 .env ─────────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

BASE_URL    = os.environ.get("GY_BASE_URL", "")
ACCOUNT     = os.environ.get("GY_ACCOUNT", "")
PASSWORD    = os.environ.get("GY_PASSWORD", "")
DASHBOARD   = os.environ.get("GY_DASHBOARD_URL", "")
OUT_DIR     = ROOT_DIR / "outputs"

if not ACCOUNT or not PASSWORD:
    print("请在 .env 中设置 GY_ACCOUNT 和 GY_PASSWORD", file=sys.stderr)
    sys.exit(1)

OUT_DIR.mkdir(parents=True, exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            args=["--window-size=1600,900"],
        )
        context = await browser.new_context(viewport={"width": 1600, "height": 900})
        page    = await context.new_page()

        # ── 登录 ──────────────────────────────────────────────────────────────
        print("[1] 登录...")
        await page.goto(f"{BASE_URL}/auth/login", wait_until="networkidle")
        await page.wait_for_selector('img[alt="切换登录方式"]')
        await page.click('img[alt="切换登录方式"]')
        await page.wait_for_function(
            "() => document.querySelector('.loginSection')?.style.display !== 'none'"
        )
        await page.evaluate(
            """([account, password]) => {
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                const ai = document.querySelector('input#loginId');
                const pi = document.querySelector('input#password');
                setter.call(ai, account); ai.dispatchEvent(new Event('input', { bubbles: true }));
                setter.call(pi, password); pi.dispatchEvent(new Event('input', { bubbles: true }));
            }""",
            [ACCOUNT, PASSWORD],
        )
        await page.wait_for_timeout(300)
        await page.click("#loginBtn")
        await page.wait_for_function(
            "() => !location.pathname.startsWith('/auth')", timeout=30000
        )
        print("[1] 登录成功")

        # ── 打开看板 ──────────────────────────────────────────────────────────
        print("[2] 打开看板...")
        try:
            await page.goto(DASHBOARD, wait_until="networkidle", timeout=90000)
        except Exception as e:
            print(f"[2] 页面未完全加载，继续截图: {str(e)[:60]}")

        await page.wait_for_timeout(8000)  # 等待卡片渲染
        full_path = OUT_DIR / "dashboard_full.png"
        await page.screenshot(path=str(full_path), full_page=True)
        print(f"[2] 全页截图已保存：outputs/dashboard_full.png")

        # ── 截取各卡片容器 ────────────────────────────────────────────────────
        card_containers = await page.query_selector_all(
            '[class*="card"], [class*="widget"], [class*="chart"]'
        )
        print(f"[3] 找到 {len(card_containers)} 个卡片容器")

        saved = 0
        for i, container in enumerate(card_containers[:8]):
            try:
                box = await container.bounding_box()
                if box and box["width"] > 200 and box["height"] > 100:
                    card_path = OUT_DIR / f"card_{i + 1}.png"
                    await container.screenshot(path=str(card_path))
                    print(f"  card_{i + 1}.png  ({round(box['width'])}×{round(box['height'])})")
                    saved += 1
            except Exception:
                pass

        await browser.close()
        print(f"\n全部截图已保存到 outputs/ 目录（共 {saved} 张卡片 + 1 张全页）")


if __name__ == "__main__":
    asyncio.run(main())
