"""
模拟飞书 Agent 问数全流程。
用法：python simulate_agent.py <SKC编码>
示例：python simulate_agent.py 6M2JJ44500F37
"""
import json
import sys
from tools import get_cards_by_filter, get_card_data

SKC = sys.argv[1] if len(sys.argv) > 1 else "6M2JJ44500F37"

SEP = "=" * 62

print(SEP)
print(f"用户: 请给我看 SKC {SKC} 在仪表板上的所有数据")
print(SEP)

# ── Step 1: Agent 调用 get_cards_by_filter ────────────────────────
print("\n[Agent] 调用 get_cards_by_filter('skc编码') ...")
result = get_cards_by_filter("skc编码")
cards = result["cards"]
print(f"  → 共 {result['matched_card_count']} 张卡片响应 skc编码 筛选器：")
for c in cards:
    print(f"     [{c['card_type']:12s}] {c['card_name']}")

# ── Step 2: Agent 逐卡取数 ────────────────────────────────────────
print(f"\n[Agent] 用 skc编码={SKC} 逐卡取数 ...\n")

all_data = {}
for card in cards:
    print(f"  调用 get_card_data('{card['card_id']}', filters={{'skc编码': '{SKC}'}})")
    data = get_card_data(card["card_id"], filters={"skc编码": SKC})
    data["card_type"] = card["card_type"]   # 补充 card_type 供展示用
    all_data[card["card_name"]] = data
    status = f"{data['row_count']} 行" if data["row_count"] else "无数据"
    print(f"  → {status}")

# ── Step 3: 输出汇总（模拟 Agent 组织语言） ────────────────────────
print(f"\n{SEP}")
print(f"[Agent 回复]")
print(f"{SEP}")
print(f"\nSKC {SKC} 的仪表板数据如下：\n")

_PCT_KEYWORDS = ("率", "折扣", "▲")

def fmt(field, value):
    """简单格式化，模拟 Agent 展示逻辑。"""
    if value is None:
        return "—"
    is_pct = any(kw in str(field) for kw in _PCT_KEYWORDS)
    if isinstance(value, float):
        if is_pct:
            return f"{value*100:.1f}%"
        elif abs(value) >= 10000:
            return f"{value/10000:.1f} 万"
    if isinstance(value, int) and abs(value) >= 10000:
        return f"{value/10000:.1f} 万"
    return str(value)

for card_name, result in all_data.items():
    if result["row_count"] == 0 or all(v is None for row in result["data"] for v in row.values()):
        print(f"  【{card_name}】无数据（当前筛选条件下无匹配）\n")
        continue

    print(f"  【{card_name}】（{result['card_type']}，{result['row_count']} 行）")

    if result["row_count"] == 1:
        # 单行：全字段展示（含 null）
        for field, value in result["data"][0].items():
            print(f"    {field}: {fmt(field, value)}")
    else:
        # 多行：全量展示
        print(f"    列: {result['columns']}")
        for i, row in enumerate(result["data"]):
            vals = {k: fmt(k, v) for k, v in row.items()}
            print(f"    行{i+1}: {vals}")
    print()

print(SEP)
print(f"[原始 JSON 输出已保存到 simulate_output_{SKC}.json]")
with open(f"simulate_output_{SKC}.json", "w", encoding="utf-8") as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2)
