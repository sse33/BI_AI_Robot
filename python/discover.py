"""
discover.py — 仪表板元数据自动发现工具

Phase 1: /api/page/{pg_id} 获取卡片全集 + SELECTOR 完整配置
Phase 2: /api/card/{cdId}/data 获取每张卡片的列结构
Phase 3: 从 SELECTOR 卡片 content/settings 提取筛选器元数据
         （known_values、关联卡片列表、filter_template 全部来自 page API）
Phase 4: 双次采集对比，推断 collect_strategy
Phase 5: 输出 configs/{dashboard_id}/cards.yaml + filters.yaml

用法：
  python discover.py                           # 处理所有 enabled=true 的仪表板
  python discover.py --dashboard daily_sales   # 只处理指定仪表板
"""

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
import yaml
from dotenv import load_dotenv
from playwright.async_api import async_playwright

ROOT_DIR    = Path(__file__).parent.parent
CONFIGS_DIR = ROOT_DIR / "configs"
load_dotenv(ROOT_DIR / ".env")

BASE_URL = os.getenv("GY_BASE_URL", "")
ACCOUNT  = os.getenv("GY_ACCOUNT", "")
PASSWORD = os.getenv("GY_PASSWORD", "")


# ── 登录 ──────────────────────────────────────────────────────────────────────

async def playwright_login() -> str:
    """Playwright 登录，返回 cookie 字符串"""
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


def make_session(cookie_str: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Cookie": cookie_str, "Content-Type": "application/json"})
    return s


# ── Phase 1：获取卡片全集 ──────────────────────────────────────────────────────

def phase1_get_page_cards(pg_id: str, session: requests.Session) -> list[dict]:
    """GET /api/page/{pg_id} → 返回全部卡片列表"""
    r = session.get(f"{BASE_URL}/api/page/{pg_id}", timeout=15)
    r.raise_for_status()
    cards = r.json()["cards"]
    print(f"[phase1] 仪表板共 {len(cards)} 张卡片")
    return cards


# ── Phase 2：获取卡片列结构 ────────────────────────────────────────────────────

def phase2_get_card_schema(cd_id: str, session: requests.Session) -> dict:
    """POST /api/card/{cdId}/data (limit=1) → 列名 + 总行数"""
    url  = f"{BASE_URL}/api/card/{cd_id}/data"
    body = {"dynamicParams": [], "filters": [], "limit": 1, "offset": 0, "view": "GRID"}
    try:
        r = session.post(url, json=body, timeout=20)
        r.raise_for_status()
        cm = r.json().get("chartMain", {})
        # 复用 bi_card_fetcher 的列名解析
        from bi_card_fetcher import extract_column_names
        cols = extract_column_names(cm)
        return {
            "columns":   cols["all_cols"],
            "row_count": cm.get("count", 0),
        }
    except Exception as e:
        print(f"  [phase2] ⚠ {cd_id} 获取失败: {e}")
        return {"columns": [], "row_count": 0}


# ── Phase 3：提取筛选器元数据（含关联卡片和枚举值，全部来自 page API）────────

def phase3_parse_selector(card: dict) -> dict:
    """
    从 SELECTOR 卡片的 content + settings 提取完整元数据。

    known_values:   content.source.sorting[].customSort.sortOrder
    linked_cards:   settings.asFilter.columnMappings[].targetFields[]
                    每个 targetField 含 cdId/dsId/fdId/name，直接构成 filter_template
    """
    content  = card.get("content", {})
    settings = card.get("settings", {})
    selector_type = content.get("selectorType", "UNKNOWN")

    meta = {
        "cd_id":         card["cdId"],
        "name":          card["name"],
        "selector_type": selector_type,
        "split_collect": False,
        "linked_cards":  [],
    }

    if selector_type == "DS_ELEMENTS":
        source = content.get("source", {})
        field  = source.get("field", {})
        meta["source"] = {
            "ds_id":      source.get("dsId", ""),
            "fd_id":      field.get("fdId", ""),
            "field_name": field.get("name", ""),
        }

        # known_values：优先取 customSort.sortOrder（有序），fallback 取 filters[].filterValue
        known_values: list[str] = []
        for sort in source.get("sorting", []):
            custom = sort.get("customSort", {})
            if custom.get("turnedOn") and custom.get("sortOrder"):
                known_values = custom["sortOrder"]
                break
        if not known_values:
            for f in source.get("filters", []):
                if f.get("filterValue"):
                    known_values = f["filterValue"]
                    break
        meta["known_values"] = known_values

        # linked_cards + filter_template：来自 settings.asFilter.columnMappings
        as_filter = settings.get("asFilter", {})
        linked: list[dict] = []
        for mapping in as_filter.get("columnMappings", []):
            for tf in mapping.get("targetFields", []):
                cd_id = tf.get("cdId", "")
                if not cd_id:
                    continue
                linked.append({
                    "cd_id": cd_id,
                    "filter_template": {
                        "cd_id":        cd_id,
                        "ds_id":        tf.get("dsId", ""),
                        "fd_id":        tf.get("fdId", ""),
                        "fd_type":      "STRING",
                        "filter_type":  content.get("filterType", "IN"),
                        "name":         tf.get("name", ""),
                        "source_cd_id": card["cdId"],
                    },
                })
        meta["linked_cards"] = linked
        print(f"  {card['name']:15} known_values={known_values}  linked={len(linked)} 张卡片")

    elif selector_type == "PARAMETER":
        meta["options"] = content.get("options", [])

    elif selector_type == "CALENDAR":
        dv = content.get("defaultValue", {})
        expr = dv.get("expr", [])
        meta["default_macro"] = expr[0] if expr else ""

    return meta


# ── Phase 4（原 Phase 5）：推断采集策略 ───────────────────────────────────────

def phase5_detect_strategy(
    cd_id: str,
    filter_info: dict,
    session: requests.Session,
) -> str:
    """
    比较有无筛选器时的数据，推断是否需要分拆采集。
    返回 "single" 或 "split_by_filter"
    """
    known_values  = filter_info.get("known_values", [])
    filter_tmpl   = filter_info.get("linked_cards", {}).get(cd_id)
    if not filter_tmpl or not known_values:
        return "single"

    url  = f"{BASE_URL}/api/card/{cd_id}/data"
    body_base = {"dynamicParams": [], "filters": [], "limit": 5, "offset": 0, "view": "GRID"}

    try:
        r_base = session.post(url, json=body_base, timeout=20)
        data_base = r_base.json().get("chartMain", {})
        cols_base = set(data_base.get("row", {}).get("meta", [{}])[0].keys())

        # 如果列名里已包含筛选字段名 → 数据已有维度，单次采集足够
        field_name = filter_tmpl.get("name", "")
        if any(field_name in str(m.get("title", "")) or field_name in str(m.get("alias", ""))
               for m in data_base.get("row", {}).get("meta", [])):
            return "single"

        # 带筛选器拉一次
        test_filter = {
            "name":         filter_tmpl["name"],
            "fdId":         filter_tmpl["fd_id"],
            "dsId":         filter_tmpl["ds_id"],
            "cdId":         filter_tmpl["cd_id"],
            "fdType":       filter_tmpl["fd_type"],
            "filterType":   filter_tmpl["filter_type"],
            "sourceCdId":   filter_tmpl["source_cd_id"],
            "filterValue":  [known_values[0]],
            "displayValue": [],
        }
        body_filtered = {**body_base, "filters": [test_filter]}
        r_filt = session.post(url, json=body_filtered, timeout=20)
        data_filt = r_filt.json().get("chartMain", {})

        # 比较总行数 & 第一行数据
        count_base = data_base.get("count", 0)
        count_filt = data_filt.get("count", 0)
        if count_base != count_filt:
            return "split_by_filter"

        rows_base = data_base.get("data", [[]])
        rows_filt = data_filt.get("data", [[]])
        if rows_base and rows_filt and rows_base[0] != rows_filt[0]:
            return "split_by_filter"

    except Exception as e:
        print(f"  [phase5] ⚠ {cd_id} 策略检测失败: {e}")

    return "single"


# ── Phase 6：写入 YAML ────────────────────────────────────────────────────────

_PRESERVED_FIELDS = ("key", "collect_strategy", "collect", "skip")


def _load_existing_card_fields(dashboard_id: str) -> dict[str, dict]:
    """读取已有 cards.yaml 中需保留的字段，避免重跑时覆盖人工设置值"""
    path = CONFIGS_DIR / dashboard_id / "cards.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        c["cd_id"]: {f: c[f] for f in _PRESERVED_FIELDS if f in c}
        for c in data.get("cards", [])
    }


def write_cards_yaml(dashboard_id: str, cards: list[dict]):
    path = CONFIGS_DIR / dashboard_id / "cards.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_existing_card_fields(dashboard_id)

    for c in cards:
        saved = existing.get(c["cd_id"], {})
        c["key"]              = saved.get("key", c["cd_id"])
        c["collect_strategy"] = saved.get("collect_strategy", c["collect_strategy"])
        c["collect"]          = saved.get("collect", c["collect"])
        c["skip"]             = saved.get("skip", c["skip"])

    out = {
        "dashboard_id":  dashboard_id,
        "generated_at":  datetime.now().isoformat(timespec="seconds"),
        "cards":         cards,
    }
    path.write_text(
        yaml.dump(out, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"[output] cards.yaml → {path}")


def write_filters_yaml(dashboard_id: str, filters: list[dict]):
    path = CONFIGS_DIR / dashboard_id / "filters.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)

    # 保留已有 filters.yaml 中人工确认的 split_collect 标志
    existing_split: dict[str, bool] = {}
    if path.exists():
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for f in existing.get("filters", []):
            if f.get("split_collect"):
                existing_split[f["cd_id"]] = True

    for f in filters:
        if f["cd_id"] in existing_split:
            f["split_collect"] = True

    out = {
        "dashboard_id": dashboard_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "filters":      filters,
    }
    path.write_text(
        yaml.dump(out, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"[output] filters.yaml → {path}")


# ── 主流程 ────────────────────────────────────────────────────────────────────

async def discover_dashboard(cfg: dict, cookie_str: str):
    pg_id        = cfg["pg_id"]
    dashboard_id = cfg["id"]

    session = make_session(cookie_str)

    # Phase 1：获取卡片全集（含 SELECTOR 的 content + settings）
    all_cards      = phase1_get_page_cards(pg_id, session)
    data_cards     = [c for c in all_cards if c["cdType"] in ("CHART", "DRILL")]
    selector_cards = [c for c in all_cards if c["cdType"] == "SELECTOR"]
    print(f"[phase1] 数据卡片 {len(data_cards)} 张，筛选器 {len(selector_cards)} 张")

    # Phase 2：获取每张数据卡片的列结构
    print("[phase2] 获取卡片列结构...")
    cards_out = []
    for c in data_cards:
        schema = phase2_get_card_schema(c["cdId"], session)
        cards_out.append({
            "cd_id":            c["cdId"],
            "cd_type":          c["cdType"],
            "name":             c["name"],
            "collect":          True,
            "skip":             False,
            "collect_strategy": "single",   # Phase 4 更新
            "columns":          schema["columns"],
            "row_count":        schema["row_count"],
        })
        print(f"  ✓ {c['name']:25} {len(schema['columns'])} 列 / {schema['row_count']} 行")

    # Phase 3：从 page API 提取筛选器元数据（known_values + linked_cards + filter_template）
    print("[phase3] 提取筛选器元数据...")
    filters_out = [phase3_parse_selector(c) for c in selector_cards]

    # Phase 4：推断采集策略（仅对 cards.yaml 中尚未设置 strategy 的新卡片）
    print("[phase4] 推断采集策略...")
    existing_fields = _load_existing_card_fields(dashboard_id)

    # 只对「有筛选器关联」且「尚无已保存策略」的卡片进行双次对比
    # 策略已存在的卡片直接沿用，不重新检测（split_collect 是业务判断，非自动覆盖）
    filter_map: dict[str, dict] = {}
    for f in filters_out:
        if f.get("selector_type") != "DS_ELEMENTS" or not f.get("known_values"):
            continue
        linked = {lc["cd_id"]: lc["filter_template"] for lc in f.get("linked_cards", [])}
        for card_cd_id, tmpl in linked.items():
            # 同一卡片可能关联多个筛选器，只取第一个（通常是最主要的）
            if card_cd_id not in filter_map:
                filter_map[card_cd_id] = {
                    "known_values": f.get("known_values", []),
                    "linked_cards": linked,
                }

    for card in cards_out:
        cd_id = card["cd_id"]
        if cd_id not in filter_map:
            continue
        if cd_id in existing_fields and "collect_strategy" in existing_fields[cd_id]:
            # 已有人工/上次确认的策略，直接沿用，不覆盖
            print(f"  {card['name']:25} → {existing_fields[cd_id]['collect_strategy']} (保留)")
            continue
        # 新卡片：运行双次对比推断
        strategy = phase5_detect_strategy(cd_id, filter_map[cd_id], session)
        card["collect_strategy"] = strategy
        print(f"  {card['name']:25} → {strategy} (新推断)")
        if strategy == "split_by_filter":
            for f in filters_out:
                if any(lc["cd_id"] == cd_id for lc in f.get("linked_cards", [])):
                    f["split_collect"] = True

    # Phase 5：写出 YAML
    write_cards_yaml(dashboard_id, cards_out)
    write_filters_yaml(dashboard_id, filters_out)


async def main():
    parser = argparse.ArgumentParser(description="仪表板元数据自动发现")
    parser.add_argument("--dashboard", help="只处理指定 dashboard id")
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
        print(f"\n{'='*60}")
        print(f"仪表板: {cfg['name']} ({cfg['id']})")
        print(f"{'='*60}")
        await discover_dashboard(cfg, cookie_str)


if __name__ == "__main__":
    asyncio.run(main())
