"""
MCP 工具定义。
工具均为无状态，每次调用独立执行。
"""

from typing import Optional

from config import DASHBOARD
from bi_client import get_card_data as _get_card_data


def get_cards_by_filter(filter_name: str) -> list[dict]:
    """
    返回监听指定筛选器的所有数据卡片列表。
    Agent 在用特定条件（如 skc编码、实际波段）筛选时，先调用此工具
    确定哪些卡片会响应该筛选条件，再对这些卡片调用 get_card_data。

    Args:
        filter_name: 筛选器字段名，必须来自 list_cards 返回的 available_filters，
                     例：'skc编码'、'实际波段'、'运营中类'

    Returns:
        与 list_cards 格式相同的卡片列表，仅包含监听该筛选器的卡片
    """
    matched = [
        {
            "card_id": c["card_id"],
            "card_name": c["card_name"],
            "card_type": c["card_type"],
            "business_description": c["business_description"],
            "filter_listeners": c["filter_listeners"],
        }
        for c in DASHBOARD["cards"]
        if filter_name in c.get("filter_listeners", [])
    ]
    return {
        "filter_name": filter_name,
        "matched_card_count": len(matched),
        "cards": matched,
    }


def list_cards() -> list[dict]:
    """
    列出当前仪表板的所有数据卡片及其业务描述。
    Agent 根据 business_description 判断用哪张卡片回答用户问题，再调用 get_card_data。

    返回示例：
    [
      {
        "card_id": "o6722f8db3ad0414f8a53c6a",
        "card_name": "上周销额",
        "card_type": "KPI_CARD",
        "business_description": "上周及累计销售额汇总..."
      },
      ...
    ]

    附加信息：
    - dashboard_name: 仪表板名称
    - available_filters: 可用筛选维度列表（传给 get_card_data 的 filters 参数时使用这些字段名）
    """
    return {
        "dashboard_name": DASHBOARD["name"],
        "available_filters": DASHBOARD["available_filters"],
        "cards": [
            {
                "card_id": c["card_id"],
                "card_name": c["card_name"],
                "card_type": c["card_type"],
                "business_description": c["business_description"],
            }
            for c in DASHBOARD["cards"]
        ],
    }


def get_card_data(
    card_id: str,
    filters: Optional[dict] = None,
    limit: int = 200,
) -> dict:
    """
    获取指定卡片的当前数据。

    Args:
        card_id: 卡片 ID，从 list_cards 结果中获取
        filters: 可选筛选条件，字段名 → 值（单值精确匹配）
                 字段名必须来自 list_cards 返回的 available_filters
                 例：{"实际波段": "SS26", "运营中类": "牛仔裤"}
                 不传则使用仪表板默认条件（返回全量数据）
        limit: 最多返回行数，默认 200，最大 1000

    Returns:
        {
          "card_id": ...,
          "card_name": ...,
          "row_count": ...,
          "columns": [...],
          "data": [{字段: 值, ...}, ...]
        }
    """
    # 从配置中找卡片名称
    card_name = next(
        (c["card_name"] for c in DASHBOARD["cards"] if c["card_id"] == card_id),
        card_id,
    )

    rows = _get_card_data(card_id, filters=filters, limit=limit)

    columns = list(rows[0].keys()) if rows else []

    return {
        "card_id": card_id,
        "card_name": card_name,
        "row_count": len(rows),
        "columns": columns,
        "data": rows,
    }
