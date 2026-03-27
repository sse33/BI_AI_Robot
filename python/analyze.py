"""
analyze.py

读取 outputs/manifest_test.json，将各卡片数据转为结构化摘要，
调用 AI API 进行日报分析，输出8节管理报告。

运行：python analyze.py
      python analyze.py --no-feishu   # 调试用，跳过飞书推送
切换模型：AI_PROVIDER=azure python analyze.py
          AI_PROVIDER=claude python analyze.py
          AI_PROVIDER=openai python analyze.py
          AI_PROVIDER=gemini python analyze.py

支持的 AI_PROVIDER 值：
  claude  — Anthropic Claude
  azure   — Azure OpenAI
  openai  — OpenAI 官方
  gemini  — Google Gemini（流式，避免代理超时，默认）
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from ai_client import call_ai
from data_prep import load_analysis_meta, build_data_text, build_analysis_instructions
from fact_check import fact_check_report, write_factcheck_log
from notify import send_to_feishu
from validate_data import validate_manifest, vision_verify, write_validation_log

# ── 加载 .env ─────────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).parent.parent
CONFIGS_DIR = ROOT_DIR / "configs"
load_dotenv(ROOT_DIR / ".env")

# ── 加载全局配置（configs/meta/）─────────────────────────────────────────────
import yaml as _yaml

_citations_cfg_path = CONFIGS_DIR / "meta" / "citations_prompt.yaml"
if not _citations_cfg_path.exists():
    print(f"未找到 {_citations_cfg_path}，请检查 configs/meta/ 目录", file=sys.stderr)
    sys.exit(1)
_CITATIONS_INSTRUCTION = _yaml.safe_load(
    _citations_cfg_path.read_text(encoding="utf-8")
).get("citations_instruction", "").strip()

_global_rules_cfg_path = CONFIGS_DIR / "meta" / "global_output_rules.yaml"
_GLOBAL_OUTPUT_RULES: list = []
if _global_rules_cfg_path.exists():
    _GLOBAL_OUTPUT_RULES = _yaml.safe_load(
        _global_rules_cfg_path.read_text(encoding="utf-8")
    ).get("global_output_rules", [])

# ── 读取数据（优先新架构 outputs/{dashboard_id}/manifest_*.json）────────────
def _find_latest_manifest() -> Path:
    """查找最新的 manifest 文件：先找新架构目录，再 fallback 旧路径"""
    outputs = ROOT_DIR / "outputs"
    # 新架构：outputs/{dashboard_id}/manifest_{YYYYMMDD}.json
    candidates = sorted(outputs.glob("*/manifest_*.json"), reverse=True)
    if candidates:
        return candidates[0]
    # 旧架构 fallback
    try:
        import yaml as _yaml
        _meta = _yaml.safe_load((Path(__file__).parent / "reports_meta.yaml").read_text())
        legacy = outputs / _meta["reports"][0].get("manifest_file", "manifest.json")
        if legacy.exists():
            return legacy
    except Exception:
        pass
    return outputs / "manifest.json"

manifest_path = _find_latest_manifest()
if not manifest_path.exists():
    print("未找到 manifest 文件，请先运行 collect.py 或 validate.py", file=sys.stderr)
    sys.exit(1)

print(f"[analyze] 使用 manifest: {manifest_path.relative_to(ROOT_DIR)}")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

# ── 加载分析元数据（从 manifest.dashboardId 自动定位）────────────────────────
def _find_analysis_yaml(dashboard_id: str, analysis: str = "") -> Path:
    suffix = f"_{analysis}" if analysis else ""
    candidates = [
        ROOT_DIR / "configs" / dashboard_id / f"analysis_{dashboard_id}{suffix}.yaml",
        Path(__file__).parent / f"analysis_{dashboard_id}{suffix}.yaml",   # 旧路径 fallback
        Path(__file__).parent / "analysis_city.yaml",                      # 历史文件名 fallback
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # 不存在时返回标准路径，让后续报错提示明确

_dashboard_id = manifest.get("dashboardId", "")
# 提前读取 --analysis 参数（模块级需要，argparse 后续再完整解析）
_analysis_variant = ""
for _i, _arg in enumerate(sys.argv):
    if _arg == "--analysis" and _i + 1 < len(sys.argv):
        _analysis_variant = sys.argv[_i + 1]

_analysis_meta_path = _find_analysis_yaml(_dashboard_id, _analysis_variant)
if not _analysis_meta_path.exists():
    _hint = f" --analysis {_analysis_variant}" if _analysis_variant else ""
    print(f"未找到分析元数据，请先运行 generate_analysis.py --dashboard {_dashboard_id}{_hint}", file=sys.stderr)
    sys.exit(1)
print(f"[analyze] 使用分析框架: {_analysis_meta_path.relative_to(ROOT_DIR)}")
analysis_meta = load_analysis_meta(_analysis_meta_path)

# 报告标题：仪表板标题 + 变体后缀（如"·门店粒度"）
import re as _re
_base_title = _re.sub(r"\s*[-–|].*$", "", manifest.get("dashboardTitle") or "").strip()
if not _base_title:
    # fallback：从 dashboards.yaml 读取 name
    import yaml as _yaml_dash
    _dashboards = _yaml_dash.safe_load((CONFIGS_DIR / "dashboards.yaml").read_text(encoding="utf-8")).get("dashboards", [])
    _dash_cfg   = next((d for d in _dashboards if d["id"] == _dashboard_id), {})
    _base_title = _re.sub(r"\s*[-–|].*$", "", _dash_cfg.get("name", "")).strip()
_title_suffix = analysis_meta.get("report_title_suffix", "")
REPORT_TITLE  = f"{_base_title}·{_title_suffix}" if _base_title and _title_suffix else (_base_title or None)


# ── 构建数据文本（由 analysis_city.yaml 的 data_prep 规则驱动）───────────────
data_text = build_data_text(analysis_meta, manifest)

# ── 提示词（从 analysis yaml 的 prompts 块读取，不再硬编码）─────────────────
_prompts = analysis_meta.get("prompts", {})

SYSTEM_PROMPT = _prompts.get("system", "").strip()
if not SYSTEM_PROMPT:
    print("[analyze] ⚠ analysis yaml 中未找到 prompts.system，请运行 generate_prompt.py", file=sys.stderr)
    sys.exit(1)

_analysis_instructions  = build_analysis_instructions(analysis_meta)
_output_format          = _prompts.get("output_format", "").strip()
# 全局规则（configs/meta/global_output_rules.yaml）+ 仪表板特有规则合并
_global_rules           = _GLOBAL_OUTPUT_RULES + _prompts.get("global_output_rules", [])
_rules_text             = "\n".join(f"- {r}" for r in _global_rules)
USER_PROMPT = f"""以下是今日观远BI销售数据：

{data_text}

---
{_analysis_instructions}

---
【通用输出格式要求】
{_rules_text}

{_output_format}

---
{_CITATIONS_INSTRUCTION}""".strip()


def _split_report_citations(full_text: str) -> tuple[str, list[dict]]:
    """从 AI 输出中拆出报告正文和 citations JSON。"""
    import re as _re
    match = _re.search(r'\[CITATIONS\]([\s\S]*?)\[/CITATIONS\]', full_text)
    if not match:
        return full_text.strip(), []
    report_text = full_text[:match.start()].strip()
    try:
        citations = json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        citations = []
    return report_text, citations


# ── AI Provider ───────────────────────────────────────────────────────────────

PROVIDER = os.environ.get("AI_PROVIDER", "gemini").lower()


def run_analysis() -> str:
    def _print(d: str):
        sys.stdout.write(d)
        sys.stdout.flush()

    return call_ai(
        SYSTEM_PROMPT, USER_PROMPT, PROVIDER,
        temperature=0.3, max_tokens=16000,
        on_delta=_print,
        thinking=(PROVIDER == "claude"),
    )


# ── 主流程 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BI 日报 AI 分析")
    parser.add_argument("--no-feishu", action="store_true", help="跳过飞书推送（调试用）")
    parser.add_argument("--no-vision", action="store_true", help="跳过 Vision 截图核对（截图非当日时使用）")
    parser.add_argument("--analysis",  default="", help="分析变体（如 store），对应 analysis_{id}_{variant}.yaml")
    parser.add_argument("--fact-check", choices=["citations", "regex"], default="citations",
                        help="事实核查模式：citations（默认，从报告提取引用后 Python 核查）或 regex（旧版正则模式）")
    parser.add_argument(
        "--send", metavar="REPORT_FILE",
        help="直接发送已有报告到飞书，跳过验证和 AI 分析",
    )
    args = parser.parse_args()

    # ── 模式 1：直接发送已有报告 ──────────────────────────────────────────────
    if args.send:
        report_path = Path(args.send)
        if not report_path.is_absolute():
            report_path = ROOT_DIR / "outputs" / args.send
        if not report_path.exists():
            print(f"❌ 报告文件不存在：{report_path}", file=sys.stderr)
            sys.exit(1)
        import re as _re
        report_text = report_path.read_text(encoding="utf-8")
        # 兼容文件中残留 citations 块的情况
        report_text, _ = _split_report_citations(report_text)
        print(f"[飞书] 读取报告：{report_path.name}")
        if args.no_feishu:
            print("[飞书] --no-feishu 已指定，跳过推送")
        else:
            send_to_feishu(report_text, title=REPORT_TITLE)
        sys.exit(0)


    # ── 模式 2：完整流程（验证 → AI 分析 → 事实核查 → 飞书）─────────────────
    # 所有输出统一写入仪表板专属目录
    dash_dir = ROOT_DIR / "outputs" / _dashboard_id
    dash_dir.mkdir(parents=True, exist_ok=True)

    print("── 数据验证 ──────────────────────────────────────────────────────────")

    issues = validate_manifest(manifest, manifest_path)

    if not args.no_vision:
        print("\n── Vision 截图核对 ───────────────────────────────────────────────────")
        screenshot_path = dash_dir / "verify_overview.png"
        issues += vision_verify(manifest, screenshot_path, _dashboard_id)
    else:
        print("\n[Vision] --no-vision 已指定，跳过截图核对")

    errors = [i for i in issues if i["level"] == "error"]
    passed = len(errors) == 0
    write_validation_log(issues, passed, dash_dir)
    if not passed:
        print(f"\n❌ 数据验证失败（{len(errors)} 个错误），已记录至 outputs/{_dashboard_id}/validation.log，终止分析。",
              file=sys.stderr)
        sys.exit(1)
    print("\n✅ 数据验证通过\n")

    print(f"正在调用 AI（provider={PROVIDER}）分析数据，请稍候...\n")

    full_text = run_analysis()

    # 拆分报告正文和 citations
    report_text, citations = _split_report_citations(full_text)
    if citations:
        print(f"\n[citations] 提取到 {len(citations)} 条数据引用")
    else:
        print("\n[citations] 未找到 citations 块，事实核查将跳过")

    stamp    = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    date_str = datetime.now().strftime("%Y%m%d")
    _pattern = analysis_meta.get("output_file_pattern", "analysis_report_{date}.md")
    _variant_suffix = f"_{_analysis_variant}" if _analysis_variant else ""
    out_name = _pattern.format(date=date_str)
    # 变体报告在文件名中插入后缀，如 analysis_report_store_20260327.md
    if _analysis_variant:
        stem, ext = out_name.rsplit(".", 1)
        out_name = f"{stem}{_variant_suffix}.{ext}"
    out_file = dash_dir / out_name
    out_file.write_text(report_text, encoding="utf-8")
    print(f"✅ 分析报告已保存至 outputs/{_dashboard_id}/{out_name}")

    # citations 原始存档（fact_check 后覆写为带状态版本）
    citations_file = dash_dir / f"_citations{_variant_suffix}_{stamp}.json" if citations else None
    if citations_file:
        citations_file.write_text(
            json.dumps(citations, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 保存压缩 prompt（供人工检查数据压缩逻辑）
    prompt_stem = out_name.replace(".md", "")
    prompt_file = dash_dir / f"_prompt_{prompt_stem}.txt"
    prompt_file.write_text(
        "=== SYSTEM PROMPT ===\n" + SYSTEM_PROMPT + "\n\n"
        "=== USER PROMPT ===\n" + USER_PROMPT,
        encoding="utf-8",
    )
    print(f"   压缩 prompt 已保存至 outputs/{_dashboard_id}/_prompt_{prompt_stem}.txt")

    # ── 事实核查（幻觉检测）──────────────────────────────────────────────────
    print("\n── 事实核查（对照源数据检测幻觉）─────────────────────────────────────")
    fc = fact_check_report(report_text, manifest, citations=citations)
    log_file = write_factcheck_log(fc, stamp, dash_dir)

    # 覆写 citations 为带核查状态的版本
    if citations_file and fc.get("annotated_citations"):
        citations_file.write_text(
            json.dumps(fc["annotated_citations"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if fc["passed"] is True:
        print(f"✅ 事实核查通过：正确 {fc['correct']} 条，通过率 {fc['pass_rate']:.1f}%")
        print(f"   详细报告：{log_file.name}")
    elif fc["passed"] is False:
        print(f"⚠️  发现 {fc['errors']} 处数据错误，通过率 {fc['pass_rate']:.1f}%，请查看 {log_file.name}")
        for line in fc["detail"].splitlines():
            if line.startswith("❌"):
                print(f"   {line}")
    else:
        print(f"⚠️  核查结果无法判断，详见 {log_file.name}")

    if args.no_feishu:
        print("\n[飞书] --no-feishu 已指定，跳过推送")
    else:
        send_to_feishu(report_text, title=REPORT_TITLE)
