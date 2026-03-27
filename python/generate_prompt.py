"""
generate_prompt.py — 从 analysis yaml 渲染生成可追溯的提示词文件

读取 analysis_{dashboard_id}.yaml 中的 prompts + sections，
生成 configs/{dashboard_id}/prompt_{dashboard_id}.md：
  - SYSTEM PROMPT
  - USER PROMPT 模板（含各节分析指令，数据占位符用 {data_text} 表示）

用法：
  python generate_prompt.py                          # 处理所有 enabled 仪表板
  python generate_prompt.py --dashboard daily_sales  # 只处理指定仪表板
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR    = Path(__file__).parent.parent
CONFIGS_DIR = ROOT_DIR / "configs"
PYTHON_DIR  = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")


def find_analysis_yaml(dashboard_id: str) -> Path | None:
    """查找仪表板对应的 analysis yaml"""
    candidates = [
        CONFIGS_DIR / dashboard_id / f"analysis_{dashboard_id}.yaml",  # 标准路径
        PYTHON_DIR / f"analysis_{dashboard_id}.yaml",                   # 旧路径 fallback
        PYTHON_DIR / "analysis_city.yaml",                              # 历史文件名 fallback
    ]
    for p in candidates:
        if p.exists():
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            if data.get("dashboard_id") == dashboard_id or p.stem == f"analysis_{dashboard_id}":
                return p
    return None


def build_section_instructions(sections: list[dict]) -> str:
    """将 sections 的 questions/alerts/output_hints 渲染为分析指令文本"""
    lines = []
    for sec in sections:
        lines.append(f"【{sec['title']}】")
        if sec.get("intent"):
            lines.append(f"分析意图：{sec['intent']}")
        for q in sec.get("questions", []):
            lines.append(f"- {q}")
        for alert in sec.get("alerts", []):
            lines.append(f"⚠ 预警：{alert.get('message', '')}")
        for hint in sec.get("output_hints", []):
            lines.append(f"  输出格式：{hint}")
        lines.append("")
    return "\n".join(lines).strip()


def render_prompt(analysis_yaml_path: Path, dashboard_id: str) -> str:
    """渲染完整提示词文档"""
    meta = yaml.safe_load(analysis_yaml_path.read_text(encoding="utf-8"))
    prompts  = meta.get("prompts", {})
    sections = meta.get("sections", [])
    context  = meta.get("analysis_context", {})

    system_prompt  = prompts.get("system", "").strip()
    output_format  = prompts.get("output_format", "").strip()
    global_rules   = prompts.get("global_output_rules", [])
    rules_text     = "\n".join(f"- {r}" for r in global_rules)
    section_instrs = build_section_instructions(sections)

    user_prompt_template = f"""以下是今日观远BI销售数据：

{{data_text}}

---
{section_instrs}

---
【通用输出格式要求】
{rules_text}

{output_format}""".strip()

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    doc = f"""# {context.get('subject', dashboard_id)} — 分析提示词
> 生成时间：{now}
> 来源：{analysis_yaml_path.name}
> 仪表板：{dashboard_id}  粒度：{context.get('granularity', '')}  受众：{context.get('audience', '')}

---

## SYSTEM PROMPT

```
{system_prompt}
```

---

## USER PROMPT 模板

> `{{data_text}}` 为运行时注入的压缩数据文本

```
{user_prompt_template}
```
"""
    return doc


def generate_prompt_for_dashboard(dashboard_id: str):
    analysis_path = find_analysis_yaml(dashboard_id)
    if not analysis_path:
        print(f"[generate_prompt] ⚠ 未找到 {dashboard_id} 的 analysis yaml，跳过")
        return

    doc = render_prompt(analysis_path, dashboard_id)

    out_path = CONFIGS_DIR / dashboard_id / f"prompt_{dashboard_id}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(doc, encoding="utf-8")
    print(f"[generate_prompt] ✓ {out_path.relative_to(ROOT_DIR)}")


def main():
    parser = argparse.ArgumentParser(description="从 analysis yaml 生成提示词文件")
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

    for cfg in targets:
        generate_prompt_for_dashboard(cfg["id"])


if __name__ == "__main__":
    main()
