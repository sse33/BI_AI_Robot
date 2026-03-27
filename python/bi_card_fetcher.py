"""
bi_card_fetcher.py

观远 BI 卡片数据抓取模块（赫基集团专用）
通过浏览器 session cookie 直接调用内部 /api/card/{id}/data 接口

卡片信息统一维护在 reports_meta.yaml，本模块从中动态加载。
"""

import os
import re
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── 从 reports_meta.yaml 加载卡片配置 ────────────────────────────────────────

def _load_meta() -> dict:
    """读取 reports_meta.yaml，返回第一份报告的配置"""
    try:
        import yaml
    except ImportError:
        return {}
    meta_path = Path(__file__).parent / "reports_meta.yaml"
    if not meta_path.exists():
        return {}
    with open(meta_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    reports = data.get("reports", [])
    return reports[0] if reports else {}

_REPORT_META = _load_meta()

# CARD_IDS：key=manifest键名，value=cd_id（仅 collect:true 的卡片）
CARD_IDS: dict[str, str] = {
    card["key"]: card["cd_id"]
    for card in _REPORT_META.get("cards", [])
    if card.get("collect") and not card["key"].startswith("_")
}

# ── 列名解析 ──────────────────────────────────────────────────────────────────

def strip_html(s: str) -> str:
    """去除 HTML 标签"""
    return re.sub(r"<[^>]+>", "", str(s or "")).strip()


def extract_column_names(chart_main: dict) -> dict:
    """
    从观远透视表结构中提取列名。
    返回 {"dim_cols": [...], "metric_cols": [...], "all_cols": [...]}
    """
    row_meta   = chart_main.get("row", {}).get("meta", [])
    col_values = chart_main.get("column", {}).get("values", [])

    dim_cols = [
        strip_html(m.get("alias") or m.get("title") or m.get("originTitle") or f"dim_{m.get('fdId', i)}")
        for i, m in enumerate(row_meta)
    ]

    metric_cols = []
    for col_levels in col_values:
        parts = [strip_html(lvl.get("alias") or lvl.get("title") or "") for lvl in col_levels]
        parts = [p for p in parts if p]
        deduped = [p for i, p in enumerate(parts) if i == 0 or p != parts[i - 1]]
        metric_cols.append("_".join(deduped))

    return {"dim_cols": dim_cols, "metric_cols": metric_cols, "all_cols": dim_cols + metric_cols}


def parse_rows(chart_main: dict) -> list[dict]:
    """
    解析观远透视表行数据。
    返回每行 {列名: 值} 的 dict 列表。
    """
    cols       = extract_column_names(chart_main)
    dim_cols   = cols["dim_cols"]
    metric_cols = cols["metric_cols"]

    row_values = chart_main.get("row", {}).get("values", [])
    data_rows  = chart_main.get("data", [])

    result = []
    for row_idx, metric_row in enumerate(data_rows):
        dim_vals = row_values[row_idx] if row_idx < len(row_values) else []
        obj = {}

        for i, col in enumerate(dim_cols):
            obj[col] = dim_vals[i].get("title", "") if i < len(dim_vals) else ""

        for i, col in enumerate(metric_cols):
            cell = metric_row[i] if metric_row and i < len(metric_row) else None
            if cell is None:
                obj[col] = ""
            elif isinstance(cell, dict):
                obj[col] = cell.get("v", cell.get("d", ""))
            else:
                obj[col] = cell

        result.append(obj)
    return result


def to_markdown_table(records: list[dict], col_order: list[str] = None) -> str:
    """对象列表 → Markdown 表格"""
    if not records:
        return "（无数据）"
    cols   = col_order or list(records[0].keys())
    header = "| " + " | ".join(cols) + " |"
    sep    = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows   = []
    for r in records:
        vals = []
        for c in cols:
            v = r.get(c, "")
            if isinstance(v, float):
                if v > 1000:
                    vals.append(f"{round(v):,}")
                elif v == int(v):
                    vals.append(str(int(v)))
                elif abs(v) <= 1 + 1e-9:
                    vals.append(f"{v * 100:.1f}%")
                else:
                    vals.append(f"{v:.2f}")
            else:
                vals.append(str(v) if v is not None else "")
        rows.append("| " + " | ".join(vals) + " |")
    return "\n".join([header, sep] + rows)


# ── 主抓取类 ──────────────────────────────────────────────────────────────────

class GuanyuanClient:
    def __init__(self, base_url: str = None, cookies: str = None):
        self.base_url = (base_url or os.getenv("GY_BASE_URL", "https://bi.trendy-global.com")).rstrip("/")
        self.cookies  = cookies or os.getenv("GY_COOKIES", "")
        self.session  = requests.Session()
        if self.cookies:
            self.session.headers["Cookie"] = self.cookies
        self.session.headers["Content-Type"] = "application/json"

    def fetch_card(self, card_id: str, limit: int = 500, offset: int = 0,
                   filters: list = None, dynamic_params: list = None) -> dict:
        """抓取单张卡片（单页）"""
        url  = f"{self.base_url}/api/card/{card_id}/data"
        body = {
            "dynamicParams": dynamic_params or [],
            "filters":       filters or [],
            "limit":         limit,
            "offset":        offset,
            "view":          "GRID",
        }
        resp = self.session.post(url, json=body, timeout=30)
        resp.raise_for_status()

        cm   = resp.json()["chartMain"]
        cols = extract_column_names(cm)
        rows = parse_rows(cm)

        return {
            "card_id":      card_id,
            "columns":      cols["all_cols"],
            "rows":         rows,
            "total_count":  cm.get("count", len(rows)),
            "has_more":     cm.get("hasMoreData", False),
        }

    def fetch_all_rows(self, card_id: str, page_size: int = 200,
                       filters: list = None, dynamic_params: list = None) -> dict:
        """自动翻页，拉取卡片全量数据"""
        offset   = 0
        all_rows = []
        columns  = None

        while True:
            result = self.fetch_card(card_id, limit=page_size, offset=offset,
                                     filters=filters, dynamic_params=dynamic_params)
            if columns is None:
                columns = result["columns"]
            all_rows.extend(result["rows"])

            if not result["has_more"] or len(result["rows"]) < page_size:
                break
            offset += page_size
            print(f"[fetch_all_rows] card_id={card_id} 已拉取 {len(all_rows)} 行...")

        return {"card_id": card_id, "columns": columns or [], "rows": all_rows}

    def fetch_by_channels(self, card_id: str, channel_field: str = "管理渠道名称_终端属性") -> dict:
        """按渠道（自营/托管/联营）分别抓取"""
        result = {}
        for ch in ["自营", "托管", "联营"]:
            print(f"[fetch_by_channels] 抓取 {ch}...")
            data       = self.fetch_all_rows(card_id, filters=[{
                "name": channel_field, "filterType": "IN", "filterValue": [ch]
            }])
            result[ch] = data["rows"]
        return result


# ── 日报数据一次性抓取 ────────────────────────────────────────────────────────

def fetch_daily_report(client: GuanyuanClient) -> dict:
    """并发抓取所有 collect:true 的卡片，返回结构化数据。
    有 channel_filter 的卡片按渠道分别抓取并合并（自动添加「渠道」列）。
    """
    print("[fetch_daily_report] 开始并发抓取所有卡片...")

    cards_meta = {
        card["key"]: card
        for card in _REPORT_META.get("cards", [])
        if card.get("collect") and not card["key"].startswith("_")
    }
    name_map = {k: v["name"] for k, v in cards_meta.items()}

    def _fetch_single(key: str, cid: str) -> tuple[str, dict]:
        """无渠道筛选，直接抓全量"""
        data = client.fetch_all_rows(cid)
        return key, {"columns": data["columns"], "rows": data["rows"]}

    def _fetch_by_channel(key: str, cid: str, channel_filter: dict) -> tuple[str, dict]:
        """按渠道逐一抓取，合并后添加「渠道」列"""
        values   = channel_filter.get("values", ["自营", "托管", "联营"])
        all_rows = []
        columns  = None
        for ch in values:
            f = {
                "name":       channel_filter["name"],
                "fdId":       channel_filter["fd_id"],
                "dsId":       channel_filter["ds_id"],
                "cdId":       channel_filter["cd_id"],
                "fdType":     "STRING",
                "filterType": "IN",
                "sourceCdId": channel_filter["source_cd_id"],
                "filterValue":  [ch],
                "displayValue": [],
            }
            data = client.fetch_all_rows(cid, filters=[f])
            if columns is None:
                columns = ["渠道"] + data["columns"]
            for row in data["rows"]:
                all_rows.append({"渠道": ch, **row})
        return key, {"columns": columns or [], "rows": all_rows}

    results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {}
        for key, cid in CARD_IDS.items():
            cf = cards_meta.get(key, {}).get("channel_filter")
            if cf:
                futures[executor.submit(_fetch_by_channel, key, cid, cf)] = key
            else:
                futures[executor.submit(_fetch_single, key, cid)] = key

        for future in as_completed(futures):
            key = futures[future]
            try:
                _, data = future.result()
                results[key] = data
                label = name_map.get(key, key)
                print(f"  ✓ {label}: {len(data['rows'])} 行")
            except Exception as e:
                label = name_map.get(key, key)
                print(f"  ✗ {label}: {e}")
                results[key] = {"columns": [], "rows": []}

    report = {"fetchedAt": __import__("datetime").datetime.now().isoformat(), **results}
    return report
