"""
clarify.py — 仪表板卡片业务语义澄清

读取 configs/{dashboard_id}/cards.yaml，让 AI 识别业务语义模糊的卡片，
逐一向用户提问并将回答写回 cards.yaml 的 business_description 字段。

已有 business_description 的卡片自动跳过，支持增量补充。

用法：
  python clarify.py --dashboard daily_sales
  python clarify.py --dashboard daily_sales --provider claude
  python clarify.py --dashboard daily_sales --force   # 重新澄清所有卡片（含已有描述）
"""

import argparse
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from ai_client import call_ai

ROOT_DIR    = Path(__file__).parent.parent
CONFIGS_DIR = ROOT_DIR / "configs"
PYTHON_DIR  = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")


# ── 加载提示词配置 ─────────────────────────────────────────────────────────────

_PROMPT_CFG_PATH = CONFIGS_DIR / "meta" / "clarify_prompt.yaml"

def _load_prompt_cfg() -> dict:
    if not _PROMPT_CFG_PATH.exists():
        print(f"[clarify] ⚠ 未找到提示词配置 {_PROMPT_CFG_PATH}", file=sys.stderr)
        sys.exit(1)
    return yaml.safe_load(_PROMPT_CFG_PATH.read_text(encoding="utf-8"))

_prompt_cfg = _load_prompt_cfg()
SYSTEM_PROMPT  = _prompt_cfg.get("system", "").strip()
OUTPUT_FORMAT  = _prompt_cfg.get("output_format", "").strip()


# ── 构建卡片摘要 ───────────────────────────────────────────────────────────────

def _build_cards_input(cards: list[dict], force: bool) -> tuple[list[dict], list[dict]]:
    """
    将卡片分为：需要澄清的（to_clarify）和已有描述的（already_done）。
    force=True 时全部重新澄清。
    """
    to_clarify  = []
    already_done = []
    for c in cards:
        if not force and c.get("business_description"):
            already_done.append(c)
        else:
            to_clarify.append(c)
    return to_clarify, already_done


def _build_user_prompt(cards: list[dict]) -> str:
    lines = [f"以下是仪表板中需要你评估业务语义清晰度的卡片（共 {len(cards)} 张）：", ""]
    for c in cards:
        cols = c.get("columns", [])
        col_str = "、".join(cols[:10]) + ("…" if len(cols) > 10 else "")
        lines.append(
            f"- key={c['key']}  name={c.get('name', '')}  "
            f"行数≈{c.get('row_count', '?')}  列({len(cols)}): {col_str}"
        )
    lines += ["", OUTPUT_FORMAT]
    return "\n".join(lines)


# ── 主流程 ─────────────────────────────────────────────────────────────────────

def clarify_dashboard(dashboard_id: str, provider: str, force: bool):
    cards_path = CONFIGS_DIR / dashboard_id / "cards.yaml"
    if not cards_path.exists():
        print(f"[clarify] 找不到 {cards_path}，请先运行 discover.py", file=sys.stderr)
        sys.exit(1)

    cards_data = yaml.safe_load(cards_path.read_text(encoding="utf-8"))
    all_cards  = cards_data.get("cards", [])
    collect_cards = [c for c in all_cards if c.get("collect", True) and not c.get("skip", False)]

    to_clarify, already_done = _build_cards_input(collect_cards, force)

    if already_done:
        print(f"[clarify] {len(already_done)} 张卡片已有 business_description，跳过")
    if not to_clarify:
        print("[clarify] ✓ 所有卡片已完成业务语义确认，无需澄清")
        return

    print(f"[clarify] 分析 {len(to_clarify)} 张卡片的业务语义...")
    user_prompt = _build_user_prompt(to_clarify)
    raw = call_ai(SYSTEM_PROMPT, user_prompt, provider, temperature=0.2, max_tokens=4096)

    # 清理 markdown 包裹
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    try:
        result = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        print(f"[clarify] ✗ AI 返回内容不是合法 YAML: {e}", file=sys.stderr)
        debug_path = PYTHON_DIR / f"_debug_clarify_{dashboard_id}.txt"
        debug_path.write_text(raw, encoding="utf-8")
        print(f"  原始输出已保存至 {debug_path.name}")
        return

    clarifications = result.get("clarifications", [])
    if not clarifications:
        print("[clarify] ✓ AI 判断所有卡片语义清晰，无需澄清")
        return

    print(f"\n[clarify] AI 识别到 {len(clarifications)} 张卡片需要澄清\n")
    print("─" * 60)

    # 建立 key → card 的映射，方便回写
    key_to_card = {c["key"]: c for c in all_cards}
    answered = 0

    for item in clarifications:
        key      = item.get("key", "")
        name     = item.get("name", key)
        reason   = item.get("reason", "")
        question = item.get("question", "")

        if not key or key not in key_to_card:
            continue

        # 已有描述且非 force 时跳过（双重保护）
        if not force and key_to_card[key].get("business_description"):
            continue

        print(f"卡片：{name}（key={key}）")
        print(f"原因：{reason}")
        print(f"问题：{question}")
        print()

        try:
            answer = input("你的回答（直接回车跳过）：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[clarify] 已中断")
            break

        if answer:
            key_to_card[key]["business_description"] = answer
            answered += 1
            print(f"  ✓ 已记录\n")
        else:
            print(f"  → 跳过\n")

        print("─" * 60)

    if answered > 0:
        # 写回 cards.yaml
        cards_data["cards"] = all_cards
        cards_path.write_text(
            yaml.dump(cards_data, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )
        print(f"\n[clarify] ✓ 已将 {answered} 条业务描述写入 {cards_path.relative_to(ROOT_DIR)}")
    else:
        print("\n[clarify] 未记录任何回答")


def main():
    parser = argparse.ArgumentParser(description="仪表板卡片业务语义澄清")
    parser.add_argument("--dashboard", required=True, help="dashboard id")
    parser.add_argument("--provider",  default="gemini", choices=["gemini", "claude"], help="AI provider")
    parser.add_argument("--force",     action="store_true", help="重新澄清所有卡片（含已有描述）")
    args = parser.parse_args()

    clarify_dashboard(args.dashboard, args.provider, args.force)


if __name__ == "__main__":
    main()
