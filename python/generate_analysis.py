"""
generate_analysis.py — 从仪表板元数据自动生成分析框架

读取 configs/{dashboard_id}/cards.yaml + dashboards.yaml，
调用 AI 推断每张卡片的分析意图，自动分组成逻辑章节，
生成 analysis_{dashboard_id}.yaml（仅 analysis_context + sections 部分）。

prompts 块由 generate_prompt.py 另行生成，两阶段分离。

用法：
  python generate_analysis.py --dashboard daily_sales
  python generate_analysis.py --dashboard daily_sales --provider claude
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from ai_client import call_ai

ROOT_DIR    = Path(__file__).parent.parent
CONFIGS_DIR = ROOT_DIR / "configs"
PYTHON_DIR  = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")


# ── 构建给 AI 的输入描述 ──────────────────────────────────────────────────────

def _summarize_columns(columns: list[str]) -> str:
    """全量列名，不压缩，确保 AI 能看到完整的列结构。"""
    return f"共 {len(columns)} 列: " + "、".join(columns)


def build_cards_summary(dashboard_cfg: dict, cards: list[dict]) -> str:
    """将 cards.yaml 内容整理为 AI 可理解的描述，列名全量传入并提取重复结构"""
    lines = [
        f"仪表板名称：{dashboard_cfg['name']}",
        f"仪表板ID：{dashboard_cfg['id']}",
        "",
        "卡片列表（共 {} 张，仅数据卡片）：".format(len(cards)),
    ]
    for c in cards:
        strategy = c.get("collect_strategy", "single")
        cols_str = _summarize_columns(c.get("columns", []))
        lines.append(
            f"- {c['name']}（key={c['key']}，{c['cd_type']}，{strategy}，"
            f"约{c.get('row_count', '?')}行）\n"
            f"  列：{cols_str}"
        )
    return "\n".join(lines)


# ── 加载元提示词配置 ──────────────────────────────────────────────────────────

_PROMPT_CFG_PATH = CONFIGS_DIR / "meta" / "generate_analysis_prompt.yaml"

def _load_prompt_cfg() -> dict:
    if not _PROMPT_CFG_PATH.exists():
        print(f"[generate_analysis] ⚠ 未找到提示词配置 {_PROMPT_CFG_PATH}，使用空配置", file=sys.stderr)
        return {}
    return yaml.safe_load(_PROMPT_CFG_PATH.read_text(encoding="utf-8"))

_prompt_cfg = _load_prompt_cfg()

SYSTEM_PROMPT = _prompt_cfg.get("system", "").strip()

def build_user_prompt(dashboard_cfg: dict, cards_summary: str) -> str:
    requirements = _prompt_cfg.get("requirements", [])
    schema_example = _prompt_cfg.get("schema_example", "").strip()
    reqs_text = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(requirements))
    return f"""根据以下仪表板卡片元数据，生成分析框架 YAML。

{cards_summary}

要求：
{reqs_text}

同时参考以下 schema 格式（不要复制内容，只参考结构）：
{schema_example}

只输出 YAML，从 analysis_context: 开始，不要有任何前置说明。
"""




# ── 主流程 ────────────────────────────────────────────────────────────────────

def generate_analysis(dashboard_cfg: dict, provider: str, force: bool, analysis: str = ""):
    dashboard_id = dashboard_cfg["id"]
    suffix       = f"_{analysis}" if analysis else ""

    # 输出路径：configs/{dashboard_id}/analysis_{dashboard_id}[_{analysis}].yaml
    out_path = CONFIGS_DIR / dashboard_id / f"analysis_{dashboard_id}{suffix}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 若已有文件，读取现有 version 和 prompts（prompts 永远保留，不受 --force 影响）
    existing_prompts = None
    existing_version = 0
    if out_path.exists():
        existing = yaml.safe_load(out_path.read_text(encoding="utf-8"))
        existing_version = existing.get("version", 0)
        if existing.get("prompts"):
            existing_prompts = existing["prompts"]
            print(f"[generate_analysis] 保留现有 prompts 块")

    # 读取 cards.yaml
    cards_path = CONFIGS_DIR / dashboard_id / "cards.yaml"
    if not cards_path.exists():
        print(f"[generate_analysis] ⚠ 找不到 {cards_path}，请先运行 discover.py")
        return

    cards_data = yaml.safe_load(cards_path.read_text(encoding="utf-8"))
    cards = [c for c in cards_data.get("cards", []) if c.get("collect", True) and not c.get("skip", False)]

    cards_summary = build_cards_summary(dashboard_cfg, cards)
    # 分析变体说明：让 AI 知道当前要生成的是哪种粒度的分析框架
    analysis_hint = f"\n\n【分析变体】本次生成「{analysis}」粒度的分析框架，请聚焦于该粒度最相关的卡片和分析角度。" if analysis else ""
    user_prompt   = build_user_prompt(dashboard_cfg, cards_summary) + analysis_hint

    print(f"[generate_analysis] 调用 {provider} 生成分析框架...")
    raw = call_ai(SYSTEM_PROMPT, user_prompt, provider, temperature=0.2, max_tokens=8192)

    # 清理可能的 markdown 代码块包裹
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        if raw.endswith("```"):
            raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    # 解析验证
    try:
        generated = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        print(f"[generate_analysis] ✗ AI 返回内容不是合法 YAML: {e}")
        debug_path = PYTHON_DIR / f"_debug_analysis_{dashboard_id}.txt"
        debug_path.write_text(raw, encoding="utf-8")
        print(f"  原始输出已保存至 {debug_path.name}")
        return

    # 组装最终文件
    output = {
        "dashboard_id":    dashboard_id,
        "analysis":        analysis or "default",
        "generated_at":    datetime.now().strftime("%Y-%m-%d"),
        "version":         existing_version + 1,
        "analysis_context": generated.get("analysis_context", {}),
        "sections":        generated.get("sections", []),
    }
    # 变体标题后缀（从 dashboards.yaml 的 analysis_variants 读取）
    if analysis:
        _variant_label = dashboard_cfg.get("analysis_variants", {}).get(analysis, "")
        if _variant_label:
            output["report_title_suffix"] = _variant_label
            print(f"  report_title_suffix: {_variant_label}")
    if existing_prompts:
        output["prompts"] = existing_prompts

    out_path.write_text(
        yaml.dump(output, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"[generate_analysis] ✓ {out_path.relative_to(ROOT_DIR)}")
    print(f"  analysis_context: {list(output['analysis_context'].keys())}")
    print(f"  sections: {len(output['sections'])} 个章节")
    for s in output["sections"]:
        print(f"    - {s.get('title', s.get('id', '?'))}  cards={s.get('cards', [])}")

    # 卡片覆盖检查
    all_card_keys = {c["key"] for c in cards}
    covered = {c for s in output["sections"] for c in s.get("cards", [])}
    excluded_cards = output["analysis_context"].get("excluded_cards", [])
    excluded_keys = {e["key"] for e in excluded_cards if isinstance(e, dict)}
    missed = all_card_keys - covered - excluded_keys
    if excluded_cards:
        print(f"  AI 主动排除的卡片（含原因）：")
        for e in excluded_cards:
            print(f"    - {e.get('key')}: {e.get('reason', '未说明')}")
    if missed:
        print(f"  ⚠ 以下卡片未被覆盖也未被说明原因：{sorted(missed)}")


def main():
    parser = argparse.ArgumentParser(description="从仪表板元数据自动生成分析框架")
    parser.add_argument("--dashboard", required=True, help="dashboard id")
    parser.add_argument("--analysis",  default="", help="分析变体名（如 store），默认为空即城市/渠道粒度")
    parser.add_argument("--provider",  default="gemini", choices=["gemini", "claude"], help="AI provider")
    parser.add_argument("--force",     action="store_true", help="强制重新生成 sections/analysis_context（prompts 块始终保留）")
    args = parser.parse_args()

    dashboards_path = CONFIGS_DIR / "dashboards.yaml"
    all_dashboards  = yaml.safe_load(dashboards_path.read_text(encoding="utf-8"))["dashboards"]
    cfg = next((d for d in all_dashboards if d["id"] == args.dashboard), None)
    if not cfg:
        print(f"找不到 dashboard: {args.dashboard}", file=sys.stderr)
        sys.exit(1)

    generate_analysis(cfg, args.provider, args.force, args.analysis)


if __name__ == "__main__":
    main()
