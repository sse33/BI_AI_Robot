"""本地调试脚本，验证 bi_client 和 tools 是否正常工作。"""
import json
from bi_client import get_card_data
from tools import list_cards, get_card_data as tool_get_card_data

print("=== 测试 list_cards ===")
result = list_cards()
print(json.dumps(result, ensure_ascii=False, indent=2))

print("\n=== 测试 get_card_data（上周销额 KPI 卡片）===")
result = tool_get_card_data("o6722f8db3ad0414f8a53c6a")
print(json.dumps(result, ensure_ascii=False, indent=2))

print("\n=== 测试 get_card_data + filters ===")
result = tool_get_card_data("o6722f8db3ad0414f8a53c6a", filters={"实际波段": "SS26"})
print(json.dumps(result, ensure_ascii=False, indent=2))
