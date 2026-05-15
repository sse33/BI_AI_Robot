"""
MCP 工具定义。
工具均为无状态，每次调用独立执行。

标准调用流程：
  1. list_dashboards()                          → 获取所有可用仪表板及其 dashboard_id
  2. list_cards(dashboard_id)                   → 获取该仪表板的卡片列表和可用筛选器
  3. get_cards_by_filter(dashboard_id, filter)  → （可选）按筛选器缩小卡片范围
  4. get_card_data(dashboard_id, card_id, ...)  → 取数据
"""

from typing import Optional

from config import DASHBOARDS
from bi_client import get_card_data as _get_card_data


def _get_dashboard(dashboard_id: str) -> dict:
    """内部：按 dashboard_id 查找配置，不存在则抛出。"""
    d = DASHBOARDS.get(dashboard_id)
    if not d:
        available = list(DASHBOARDS.keys())
        raise ValueError(f"dashboard_id '{dashboard_id}' 不存在，可用：{available}")
    return d


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
    return {
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


def list_cards(dashboard_id: str) -> dict:
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
    d = _get_dashboard(dashboard_id)
    return {
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


def get_cards_by_filter(dashboard_id: str, filter_name: str) -> dict:
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
    d = _get_dashboard(dashboard_id)
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
    return {
        "filter_name": filter_name,
        "matched_card_count": len(matched),
        "cards": matched,
    }


def get_card_data(
    dashboard_id: str,
    card_id: str,
    filters: Optional[dict] = None,
    limit: int = 200,
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
    d = _get_dashboard(dashboard_id)
    card_name = next(
        (c["card_name"] for c in d["cards"] if c["card_id"] == card_id),
        card_id,
    )
    rows = _get_card_data(card_id, filters=filters, limit=limit)
    return {
        "dashboard_id": dashboard_id,
        "card_id": card_id,
        "card_name": card_name,
        "row_count": len(rows),
        "columns": list(rows[0].keys()) if rows else [],
        "data": rows,
    }
