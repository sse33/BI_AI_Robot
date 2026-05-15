"""
MCP 工具定义。
工具均为无状态，每次调用独立执行。

标准调用流程：
  1. list_dashboards()                          → 获取所有可用仪表板及其 dashboard_id
  2. list_cards(dashboard_id)                   → 获取该仪表板的卡片列表和可用筛选器
  3. get_cards_by_filter(dashboard_id, filter)  → （可选）按筛选器缩小卡片范围
  4. get_card_data(dashboard_id, card_id, ...)  → 取数据
"""

import logging
import time
from typing import Optional

from config import DASHBOARDS
from bi_client import get_card_data as _get_card_data
from bi_client import list_filter_values as _list_filter_values

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("mcp.tools")


def _get_dashboard(dashboard_id: Optional[str]) -> dict:
    """内部：按 dashboard_id 查找配置。
    - 传 None 且只有一个仪表板时自动选择
    - 传 None 且有多个仪表板时抛出，提示用户先调用 list_dashboards
    """
    if dashboard_id is None:
        if len(DASHBOARDS) == 1:
            return next(iter(DASHBOARDS.values()))
        raise ValueError(
            f"有多个仪表板，请先调用 list_dashboards 获取 dashboard_id，"
            f"可用：{list(DASHBOARDS.keys())}"
        )
    d = DASHBOARDS.get(dashboard_id)
    if not d:
        available = list(DASHBOARDS.keys())
        raise ValueError(f"dashboard_id '{dashboard_id}' 不存在，可用：{available}")
    return d


def _log_call(fn_name: str, **kwargs) -> float:
    """记录工具调用入口，返回开始时间戳。"""
    params = ", ".join(f"{k}={v!r}" for k, v in kwargs.items() if v is not None)
    logger.info("[CALL] %s(%s)", fn_name, params)
    return time.time()


def _log_ok(fn_name: str, t0: float, detail: str = "") -> None:
    elapsed = int((time.time() - t0) * 1000)
    logger.info("[OK]   %s %s(%dms)", fn_name, detail, elapsed)


def _log_err(fn_name: str, t0: float, exc: Exception) -> None:
    elapsed = int((time.time() - t0) * 1000)
    logger.error("[ERR]  %s %s(%dms)", fn_name, exc, elapsed)


def list_dashboards() -> dict:
    """
    列出所有已接入的仪表板。
    Agent 应先调用此工具获取 dashboard_id，再调用 list_cards。

    Returns:
        {
          "dashboard_count": N,
          "dashboards": [
            {"dashboard_id": "...", "name": "...", "description": "..."},
            ...
          ]
        }
    """
    t0 = _log_call("list_dashboards")
    result = {
        "dashboard_count": len(DASHBOARDS),
        "dashboards": [
            {
                "dashboard_id": d["page_id"],
                "name": d["name"],
                "description": d.get("description", ""),
            }
            for d in DASHBOARDS.values()
        ],
    }
    _log_ok("list_dashboards", t0, f"{result['dashboard_count']} dashboards")
    return result


def list_cards(dashboard_id: Optional[str] = None) -> dict:
    """
    列出指定仪表板的所有数据卡片及其业务描述。
    Agent 根据 business_description 判断用哪张卡片回答用户问题，再调用 get_card_data。

    Args:
        dashboard_id: 仪表板 ID，从 list_dashboards 结果中获取

    Returns:
        {
          "dashboard_name": "...",
          "available_filters": [...],
          "cards": [
            {"card_id": "...", "card_name": "...", "card_type": "...", "business_description": "..."},
            ...
          ]
        }
    """
    t0 = _log_call("list_cards", dashboard_id=dashboard_id)
    try:
        d = _get_dashboard(dashboard_id)
    except ValueError as e:
        _log_err("list_cards", t0, e)
        raise
    result = {
        "dashboard_name": d["name"],
        "available_filters": d["available_filters"],
        "cards": [
            {
                "card_id": c["card_id"],
                "card_name": c["card_name"],
                "card_type": c["card_type"],
                "business_description": c["business_description"],
            }
            for c in d["cards"]
        ],
    }
    _log_ok("list_cards", t0, f"{len(result['cards'])} cards")
    return result


def get_cards_by_filter(filter_name: str, dashboard_id: Optional[str] = None) -> dict:
    """
    返回指定仪表板中监听某个筛选器的所有数据卡片。
    Agent 在用特定条件（如 skc编码、实际波段）筛选时，先调用此工具
    确定哪些卡片会响应该筛选条件，再对这些卡片调用 get_card_data。

    Args:
        dashboard_id: 仪表板 ID，从 list_dashboards 结果中获取
        filter_name: 筛选器字段名，必须来自 list_cards 返回的 available_filters，
                     例：'skc编码'、'实际波段'、'运营中类'

    Returns:
        {
          "filter_name": "...",
          "matched_card_count": N,
          "cards": [...]
        }
    """
    t0 = _log_call("get_cards_by_filter", dashboard_id=dashboard_id, filter_name=filter_name)
    try:
        d = _get_dashboard(dashboard_id)
    except ValueError as e:
        _log_err("get_cards_by_filter", t0, e)
        raise
    matched = [
        {
            "card_id": c["card_id"],
            "card_name": c["card_name"],
            "card_type": c["card_type"],
            "business_description": c["business_description"],
            "filter_listeners": c["filter_listeners"],
        }
        for c in d["cards"]
        if filter_name in c.get("filter_listeners", [])
    ]
    result = {
        "filter_name": filter_name,
        "matched_card_count": len(matched),
        "cards": matched,
    }
    _log_ok("get_cards_by_filter", t0, f"{result['matched_card_count']} matched")
    return result


def list_filter_values(
    filter_name: str,
    keyword: str,
    dashboard_id: Optional[str] = None,
) -> dict:
    """
    通过关键词模糊搜索筛选器的枚举值，适用于商品标签等多值字段。

    商品标签是多值字段：一个 SKC 可同时带多个标签，在数据库中以组合字符串存储
    （如 "生意款 亚洲大片 橱窗"）。直接用 EQ 筛选 "生意款" 无法匹配此类组合值。
    正确做法：先调用 list_filter_values 获取所有包含该关键词的完整枚举值，
    再将返回的 values 列表作为 filters 传给 get_card_data 进行精确 IN 匹配。

    示例流程：
      1. list_filter_values(filter_name="商品标签", keyword="生意款")
         → {"values": ["生意款", "生意款 亚洲大片", "生意款 橱窗", ...]}
      2. get_card_data(card_id=..., filters={"商品标签": ["生意款", "生意款 亚洲大片", ...]})

    Args:
        dashboard_id: 仪表板 ID，从 list_dashboards 结果中获取
        filter_name: 筛选器字段名，必须来自 list_cards 返回的 available_filters
                     当前支持：'商品标签'
        keyword: 搜索关键词（CONTAINS 模糊匹配）

    Returns:
        {
          "filter_name": "...",
          "keyword": "...",
          "matched_count": N,
          "values": ["完整枚举值1", "完整枚举值2", ...]
        }
    """
    t0 = _log_call("list_filter_values", filter_name=filter_name, keyword=keyword)
    try:
        d = _get_dashboard(dashboard_id)
        datasources = d.get("filter_datasources", {})
        if filter_name not in datasources:
            available = list(datasources.keys())
            raise ValueError(
                f"筛选器 '{filter_name}' 不支持枚举值查询，"
                f"当前支持：{available}"
            )
        cfg = datasources[filter_name]
        values = _list_filter_values(cfg["ds_id"], cfg["field"], keyword)
    except Exception as e:
        _log_err("list_filter_values", t0, e)
        raise
    result = {
        "filter_name": filter_name,
        "keyword": keyword,
        "matched_count": len(values),
        "values": values,
    }
    _log_ok("list_filter_values", t0, f"{len(values)} values matched '{keyword}'")
    return result


def get_card_data(
    card_id: str,
    filters: Optional[dict] = None,
    limit: int = 200,
    dashboard_id: Optional[str] = None,
) -> dict:
    """
    获取指定仪表板中某张卡片的当前数据。

    Args:
        dashboard_id: 仪表板 ID，从 list_dashboards 结果中获取
        card_id: 卡片 ID，从 list_cards 结果中获取
        filters: 可选筛选条件，字段名 → 值（单值精确匹配）
                 字段名必须来自 list_cards 返回的 available_filters
                 例：{"实际波段": "SS26", "运营中类": "牛仔裤"}
                 不传则使用仪表板默认条件（返回全量数据）
        limit: 最多返回行数，默认 200，最大 1000

    Returns:
        {
          "dashboard_id": ...,
          "card_id": ...,
          "card_name": ...,
          "row_count": ...,
          "columns": [...],
          "data": [{字段: 值, ...}, ...]
        }
    """
    t0 = _log_call("get_card_data", dashboard_id=dashboard_id, card_id=card_id, filters=filters)
    try:
        d = _get_dashboard(dashboard_id)
        card_name = next(
            (c["card_name"] for c in d["cards"] if c["card_id"] == card_id),
            card_id,
        )
        rows = _get_card_data(card_id, filters=filters, limit=limit)
    except Exception as e:
        _log_err("get_card_data", t0, e)
        raise
    result = {
        "dashboard_id": dashboard_id,
        "card_id": card_id,
        "card_name": card_name,
        "row_count": len(rows),
        "columns": list(rows[0].keys()) if rows else [],
        "data": rows,
    }
    _log_ok("get_card_data", t0, f"card='{card_name}' {result['row_count']} rows")
    return result
