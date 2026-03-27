"""
collect.py — 基于元数据驱动的通用数据采集工具

读取 configs/dashboards.yaml → configs/{dashboard_id}/cards.yaml + filters.yaml
按 collect_strategy 决定采集方式：
  single          → 直接拉全量
  split_by_filter → 按筛选器值逐一拉取，合并后加「筛选维度」列

输出：outputs/{dashboard_id}/manifest_{YYYYMMDD}.json

用法：
  python collect.py                          # 采集所有 enabled=true 的仪表板
  python collect.py --dashboard daily_sales  # 只采集指定仪表板
"""

import argparse
import asyncio
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from playwright.async_api import async_playwright

ROOT_DIR    = Path(__file__).parent.parent
CONFIGS_DIR = ROOT_DIR / "configs"
OUTPUTS_DIR = ROOT_DIR / "outputs"
load_dotenv(ROOT_DIR / ".env")

BASE_URL = os.getenv("GY_BASE_URL", "")
ACCOUNT  = os.getenv("GY_ACCOUNT", "")
PASSWORD = os.getenv("GY_PASSWORD", "")


# ── 登录 ──────────────────────────────────────────────────────────────────────

async def playwright_login() -> str:
    print("[login] 启动浏览器登录...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )
        ctx  = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(f"{BASE_URL}/auth/login", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_selector('img[alt="切换登录方式"]', timeout=10000)
        await page.click('img[alt="切换登录方式"]')
        await page.wait_for_function(
            "() => document.querySelector('.loginSection')?.style.display !== 'none'",
            timeout=5000,
        )
        await page.evaluate(
            """([a, p]) => {
                const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                const ai = document.querySelector('input#loginId, input[placeholder="账号"]');
                const pi = document.querySelector('input#password, input[placeholder="密码"]');
                s.call(ai, a); ai.dispatchEvent(new Event('input', { bubbles: true }));
                s.call(pi, p); pi.dispatchEvent(new Event('input', { bubbles: true }));
            }""",
            [ACCOUNT, PASSWORD],
        )
        await page.click("#loginBtn")
        await page.wait_for_function(
            "() => !location.pathname.startsWith('/auth')", timeout=30000
        )
        cookies = await ctx.cookies()
        await browser.close()
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    print(f"[login] 成功，获取 {len(cookies)} 个 cookie")
    return cookie_str


# ── 采集核心 ──────────────────────────────────────────────────────────────────

def fetch_single(cd_id: str, client) -> dict:
    """单次采集全量数据"""
    return client.fetch_all_rows(cd_id)


def fetch_split(cd_id: str, filter_meta: dict, client) -> dict:
    """
    按筛选器值逐一采集，合并结果并在首列插入筛选维度。
    filter_meta: {col_name, known_values, template}
    """
    col_name     = filter_meta["col_name"]
    known_values = filter_meta["known_values"]
    tmpl         = filter_meta["template"]

    all_rows = []
    columns  = None

    for val in known_values:
        f_obj = {
            "name":         tmpl["name"],
            "fdId":         tmpl["fd_id"],
            "dsId":         tmpl["ds_id"],
            "cdId":         tmpl["cd_id"],
            "fdType":       tmpl["fd_type"],
            "filterType":   tmpl["filter_type"],
            "sourceCdId":   tmpl["source_cd_id"],
            "filterValue":  [val],
            "displayValue": [],
        }
        data = client.fetch_all_rows(cd_id, filters=[f_obj])
        if columns is None:
            columns = [col_name] + data["columns"]
        for row in data["rows"]:
            all_rows.append({col_name: val, **row})

    return {"columns": columns or [], "rows": all_rows}


# ── 元数据加载 ────────────────────────────────────────────────────────────────

def load_dashboard_meta(dashboard_id: str) -> tuple[list[dict], list[dict]]:
    """返回 (cards, filters)"""
    cards_path   = CONFIGS_DIR / dashboard_id / "cards.yaml"
    filters_path = CONFIGS_DIR / dashboard_id / "filters.yaml"

    cards   = yaml.safe_load(cards_path.read_text(encoding="utf-8")).get("cards", [])
    filters = yaml.safe_load(filters_path.read_text(encoding="utf-8")).get("filters", [])
    return cards, filters


def build_split_map(cards: list[dict], filters: list[dict]) -> dict[str, dict]:
    """
    构建 {card_cd_id: {col_name, known_values, template}} 映射。
    只包含 split_by_filter 且有完整 filter_template 的卡片。
    """
    split_map: dict[str, dict] = {}

    for f in filters:
        if not f.get("split_collect"):
            continue
        known_values = f.get("known_values", [])
        if not known_values:
            continue
        col_name = f["name"]   # 筛选器名称作为新增列名（如"渠道"）

        for lc in f.get("linked_cards", []):
            cd_id = lc["cd_id"]
            tmpl  = lc.get("filter_template")
            if not tmpl:
                continue
            # 仅覆盖 collect_strategy=split_by_filter 的卡片
            card = next((c for c in cards if c["cd_id"] == cd_id), None)
            if card and card.get("collect_strategy") == "split_by_filter":
                split_map[cd_id] = {
                    "col_name":     col_name,
                    "known_values": known_values,
                    "template":     tmpl,
                }

    return split_map


# ── 主采集流程 ────────────────────────────────────────────────────────────────

def _fetch_dashboard_title(pg_id: str, session) -> str:
    """从 /api/page/{pg_id} 获取仪表板真实标题"""
    try:
        import requests as _req
        r = session.get(f"{BASE_URL}/api/page/{pg_id}", timeout=15)
        return r.json().get("name", "") or ""
    except Exception:
        return ""


def collect_dashboard(cfg: dict, cookie_str: str) -> dict:
    import requests as _req
    from bi_card_fetcher import GuanyuanClient

    dashboard_id = cfg["id"]
    print(f"\n[collect] 仪表板: {cfg['name']}")

    cards, filters = load_dashboard_meta(dashboard_id)
    split_map      = build_split_map(cards, filters)

    # 过滤出需要采集的卡片
    to_collect = [
        c for c in cards
        if c.get("collect", True) and not c.get("skip", False)
    ]
    print(f"[collect] 共 {len(to_collect)} 张卡片待采集，"
          f"其中 {sum(1 for c in to_collect if c['cd_id'] in split_map)} 张需分拆")

    # 从 page API 获取真实标题
    session = _req.Session()
    session.headers.update({"Cookie": cookie_str})
    pg_id           = cfg.get("pg_id", "")
    dashboard_title = _fetch_dashboard_title(pg_id, session) if pg_id else ""
    if dashboard_title:
        print(f"[collect] 仪表板标题: {dashboard_title}")

    client  = GuanyuanClient(cookies=cookie_str)
    results = {}

    def _fetch(card: dict) -> tuple[str, dict]:
        key   = card["key"]       # 当前为 cd_id，日后替换为语义名
        cd_id = card["cd_id"]
        if cd_id in split_map:
            data = fetch_split(cd_id, split_map[cd_id], client)
        else:
            data = fetch_single(cd_id, client)
        return key, {"columns": data["columns"], "rows": data["rows"]}

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch, card): card for card in to_collect}
        for future in as_completed(futures):
            card = futures[future]
            try:
                key, data = future.result()
                results[key] = data
                print(f"  ✓ {card['name']:30} {len(data['rows']):4} 行  "
                      f"({'split' if card['cd_id'] in split_map else 'single'})")
            except Exception as e:
                print(f"  ✗ {card['name']:30} 失败: {e}")
                results[card["key"]] = {"columns": [], "rows": []}

    manifest = {
        "fetchedAt":      datetime.now().isoformat(),
        "dashboardId":    dashboard_id,
        "dashboardTitle": dashboard_title,
        **results,
    }

    # 输出文件
    out_dir  = OUTPUTS_DIR / dashboard_id
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    out_file = out_dir / f"manifest_{date_str}.json"
    out_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[collect] 已写入 {out_file}")

    return manifest


# ── 入口 ──────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="仪表板数据采集")
    parser.add_argument("--dashboard", help="只采集指定 dashboard id")
    args = parser.parse_args()

    dashboards_path = CONFIGS_DIR / "dashboards.yaml"
    if not dashboards_path.exists():
        print(f"找不到 {dashboards_path}", file=sys.stderr)
        sys.exit(1)

    all_dashboards = yaml.safe_load(dashboards_path.read_text(encoding="utf-8"))["dashboards"]

    if args.dashboard:
        targets = [d for d in all_dashboards if d["id"] == args.dashboard]
    else:
        targets = [d for d in all_dashboards if d.get("enabled", False)]

    if not targets:
        print("没有找到符合条件的仪表板")
        sys.exit(0)

    cookie_str = await playwright_login()

    for cfg in targets:
        collect_dashboard(cfg, cookie_str)


if __name__ == "__main__":
    asyncio.run(main())
