"""
fact_check.py — 报告事实核查模块

对照 manifest 源数据，检测 AI 报告中的幻觉数字。
支持两种模式：
  - regex（默认）：正则抽取 + 逐条核验，速度快，但依赖报告格式
  - ai：将报告与源数据发给 AI 核查，通用性强，多一次 AI 调用
"""

import json
import re
from pathlib import Path

from ai_client import call_ai

ROOT_DIR  = Path(__file__).parent.parent
TOLERANCE = 0.015  # 默认 1.5% 容差


# ── AI 模式 ───────────────────────────────────────────────────────────────────

def _build_source_summary(manifest: dict) -> str:
    """从 manifest 提取核心数据表，供 AI 核查用。"""
    lines = []

    overview = manifest.get("dailySalesOverview", {})
    if overview.get("rows"):
        lines.append("=== 每日销售概况（渠道×城市）===")
        cols = overview.get("columns", [])
        lines.append("  " + " | ".join(cols))
        for r in overview["rows"]:
            lines.append("  " + " | ".join(str(r.get(c, "")) for c in cols))

    for key, label in [
        ("categoryStructureRegular", "运营中类结构（正价）"),
        ("categoryStructureOutlet",  "运营中类结构（奥莱）"),
    ]:
        card = manifest.get(key, {})
        if card.get("rows"):
            lines.append(f"\n=== {label} ===")
            cols = card.get("columns", [])
            lines.append("  " + " | ".join(cols))
            for r in card["rows"]:
                lines.append("  " + " | ".join(str(r.get(c, "")) for c in cols))

    return "\n".join(lines)


_AI_SYSTEM = (
    "你是一名严格的数据核查员。你的任务是从报告中找出所有引用的具体数字，"
    "逐条与源数据核对，判断是否一致（容差1.5%以内算正确）。"
    "只返回合法 JSON，不包含任何解释文字。"
)

_AI_USER_TMPL = """\
【源数据】
{source_data}

【报告文本】
{report_text}

请从报告中逐条找出所有具体数字引用（业绩、店数、店均、折扣、比率等），\
与源数据核对，返回如下 JSON：
{{
  "items": [
    {{
      "ref":      "报告中的原始片段（≤30字）",
      "field":    "核查字段名",
      "reported": 数值（数字类型）,
      "source":   数值或null（找不到时为null）,
      "status":   "correct" | "error" | "unverifiable",
      "note":     "简短说明"
    }}
  ]
}}
"""


def _call_ai_check(source_data: str, report_text: str, provider: str) -> list[dict]:
    """调用 AI 核查，返回 items 列表。流式避免代理超时。"""
    user = _AI_USER_TMPL.format(source_data=source_data, report_text=report_text)
    raw  = call_ai(_AI_SYSTEM, user, provider, temperature=0,
                   stream=True, max_tokens=16384)

    # 从响应中提取 JSON 块（兼容 markdown 代码块包裹）
    debug_path = ROOT_DIR / "outputs" / "_debug_factcheck_raw.txt"
    match = re.search(r'\{[\s\S]*\}', raw)
    if not match:
        debug_path.write_text(raw, encoding="utf-8")
        raise ValueError(f"AI 响应中未找到 JSON 块，原始输出已保存至 {debug_path.name}")

    try:
        return json.loads(match.group(0)).get("items", [])
    except json.JSONDecodeError as e:
        debug_path.write_text(raw, encoding="utf-8")
        raise ValueError(f"JSON 解析失败（{e}），原始输出已保存至 {debug_path.name}")


def _fact_check_ai(report_text: str, manifest: dict, provider: str) -> dict:
    """AI 模式：将报告和源数据发给 AI 核查，返回标准格式结果。"""
    source_data = _build_source_summary(manifest)
    try:
        items = _call_ai_check(source_data, report_text, provider)
    except Exception as e:
        return {
            "passed": None, "correct": 0, "errors": 0, "unverifiable": 1,
            "pass_rate": 0.0,
            "detail": f"⚠️ AI 核查调用失败：{e}",
        }

    correct = errors = unverifiable = 0
    detail_lines: list[str] = []

    for item in items:
        status = item.get("status", "unverifiable")
        ref    = item.get("ref", "")
        field  = item.get("field", "")
        note   = item.get("note", "")
        rep    = item.get("reported")
        src    = item.get("source")

        if status == "correct":
            correct += 1
            detail_lines.append(f"✅ 正确｜{ref}｜{field} 报告={rep} 源={src}")
        elif status == "error":
            errors += 1
            detail_lines.append(f"❌ 错误｜{ref}｜{field} 报告={rep} 源={src}  {note}")
        else:
            unverifiable += 1
            detail_lines.append(f"⚠️ 无法核实｜{ref}｜{note}")

    total     = correct + errors
    pass_rate = correct / total * 100 if total > 0 else 0.0
    passed    = (errors == 0) if total > 0 else None
    summary   = (
        f"【核查汇总】正确={correct} 错误={errors} "
        f"无法核实={unverifiable} 通过率={pass_rate:.1f}%"
    )
    detail = "\n".join(detail_lines) + ("\n\n" if detail_lines else "") + summary

    return {"passed": passed, "correct": correct, "errors": errors,
            "unverifiable": unverifiable, "pass_rate": pass_rate, "detail": detail}


# ── Citations 模式（主要模式）────────────────────────────────────────────────

def _fact_check_citations(citations: list[dict], manifest: dict) -> dict:
    """
    用 AI 生成报告时同步输出的 citations JSON 核查数据准确性。
    citations 格式：[{"card": "...", "row": {...}, "field": "...", "value": 数值}, ...]
    """
    correct = errors = unverifiable = 0
    detail_lines: list[str] = []

    for item in citations:
        card_key = item.get("card", "")
        row_filter = item.get("row", {})
        field = item.get("field", "")
        reported_val = item.get("value")

        label = f"{card_key}.{field} row={row_filter}"

        def _mark(status: str, note: str, source=None):
            item["_status"] = status
            item["_note"]   = note
            if source is not None:
                item["_source"] = source

        card_data = manifest.get(card_key, {})
        if not card_data:
            unverifiable += 1
            _mark("unverifiable", "卡片不在 manifest")
            detail_lines.append(f"⚠️ 无法核实｜{label}｜卡片不在 manifest")
            continue

        rows = card_data.get("rows", [])
        matched = [r for r in rows if all(str(r.get(k, "")) == str(v) for k, v in row_filter.items())]
        if not matched:
            unverifiable += 1
            _mark("unverifiable", "找不到匹配行")
            detail_lines.append(f"⚠️ 无法核实｜{label}｜找不到匹配行")
            continue
        if len(matched) > 1:
            unverifiable += 1
            _mark("unverifiable", f"row filter 匹配到 {len(matched)} 行，无法唯一定位")
            detail_lines.append(f"⚠️ 无法核实｜{label}｜row filter 匹配到 {len(matched)} 行，无法唯一定位")
            continue

        src_val = matched[0].get(field)
        if src_val is None:
            unverifiable += 1
            _mark("unverifiable", "字段不存在")
            detail_lines.append(f"⚠️ 无法核实｜{label}｜字段不存在")
            continue

        try:
            src_num = float(src_val)
            rep_num = float(reported_val)
        except (TypeError, ValueError):
            unverifiable += 1
            _mark("unverifiable", "值无法转为数字")
            detail_lines.append(f"⚠️ 无法核实｜{label}｜值无法转为数字")
            continue

        if src_num == 0 and rep_num == 0:
            correct += 1
            _mark("correct", "均为0", source=src_num)
            continue

        base   = max(abs(src_num), abs(rep_num), 1)
        diff_r = abs(rep_num - src_num) / base

        if diff_r <= TOLERANCE:
            correct += 1
            _mark("correct", f"偏差{diff_r*100:.2f}%", source=src_num)
            detail_lines.append(f"✅ 正确｜{label}｜报告={rep_num} 源={src_num}")
        else:
            errors += 1
            _mark("error", f"偏差{diff_r*100:.1f}%", source=src_num)
            detail_lines.append(
                f"❌ 错误｜{label}｜报告={rep_num} 源={src_num} 偏差={diff_r*100:.1f}%"
            )

    total     = correct + errors
    pass_rate = correct / total * 100 if total > 0 else 0.0
    passed    = (errors == 0) if total > 0 else None
    summary   = (
        f"【核查汇总】正确={correct} 错误={errors} "
        f"无法核实={unverifiable} 通过率={pass_rate:.1f}%"
    )
    detail = "\n".join(detail_lines) + ("\n\n" if detail_lines else "") + summary
    return {"passed": passed, "correct": correct, "errors": errors,
            "unverifiable": unverifiable, "pass_rate": pass_rate, "detail": detail,
            "annotated_citations": citations}


# ── 公共入口 ──────────────────────────────────────────────────────────────────

def fact_check_report(report_text: str, manifest: dict,
                      citations: list[dict] | None = None,
                      mode: str = "regex", provider: str = "gemini") -> dict:
    """
    核查报告数字是否与 manifest 源数据一致。
    citations 不为空时优先使用 citations 模式（推荐）。
    mode="regex" 作为无 citations 时的降级方案。
    返回 {"passed", "correct", "errors", "unverifiable", "pass_rate", "detail"}
    """
    if citations:
        return _fact_check_citations(citations, manifest)

    # ── regex 降级 ────────────────────────────────────────────────────────────
    overview = manifest.get("dailySalesOverview", {})
    rows = overview.get("rows", [])

    # 城市查找表
    city_map: dict[str, dict] = {
        f"{r.get('渠道','')}_{r.get('城市','')}": r
        for r in rows
        if r.get("渠道") and r.get("城市") and r.get("城市") != "总计"
    }

    correct = errors = unverifiable = 0
    detail_lines: list[str] = []
    seen: set[str] = set()

    # ── Pattern A：渠道_城市（N店，店均X[,XXX]，折扣X[折/%]）──────────────────
    pattern = re.compile(
        r'((?:自营|联营|托管)_?[\u4e00-\u9fff]{2,5})'
        r'[（(](\d+)店[，,]\s*店均([\d,]+)元?'
        r'(?:[，,][^）)]*?折扣([\d.]+)[折%])?'
        r'[）)]'
    )
    for m in pattern.finditer(report_text):
        raw_key = m.group(1)
        key = re.sub(r'^(自营|联营|托管)(?!_)', r'\1_', raw_key)
        if key in seen:
            continue
        seen.add(key)

        rep_stores       = int(m.group(2))
        rep_avg          = int(m.group(3).replace(",", ""))
        rep_discount_pct = float(m.group(4)) if m.group(4) else None

        if key not in city_map:
            detail_lines.append(f"⚠️ 无法核实｜{key}（{rep_stores}店，店均{rep_avg:,}）｜城市不在源数据")
            unverifiable += 1
            continue

        row = city_map[key]
        src_zj = row.get("正价_店数") or 0
        src_al = row.get("奥莱_店数") or 0

        if src_zj == rep_stores:
            src_avg, src_disc, ch = row.get("正价_店均业绩") or 0, row.get("正价_实销折扣") or 0, "正价"
        elif src_al == rep_stores:
            src_avg, src_disc, ch = row.get("奥莱_店均业绩") or 0, row.get("奥莱_实销折扣") or 0, "奥莱"
        else:
            detail_lines.append(
                f"❌ 错误｜{key}（{rep_stores}店）店数｜"
                f"报告={rep_stores} 源数据正价={src_zj}/奥莱={src_al}"
            )
            errors += 1
            continue

        ok = True
        snippet = f"{key}（{rep_stores}店，店均{rep_avg:,}）"
        if src_avg and abs(rep_avg - src_avg) / src_avg > TOLERANCE:
            detail_lines.append(
                f"❌ 错误｜{snippet}[{ch}店均]｜"
                f"报告={rep_avg:,} 源={src_avg:,} 偏差={abs(rep_avg-src_avg)/src_avg*100:.1f}%"
            )
            errors += 1; ok = False
        if rep_discount_pct is not None and src_disc:
            if abs(rep_discount_pct / 100 - src_disc) > TOLERANCE:
                detail_lines.append(
                    f"❌ 错误｜{key}[{ch}折扣]｜"
                    f"报告={rep_discount_pct:.1f}% 源={src_disc*100:.1f}%"
                )
                errors += 1; ok = False
        if ok:
            detail_lines.append(f"✅ 正确｜{snippet}｜{ch}店均={src_avg:,}")
            correct += 1

    # ── Pattern B：正价/奥莱总计行 ────────────────────────────────────────────
    total_row = next((r for r in rows if str(r.get("渠道", "")) == "总计"), {})
    if total_row:
        total_pattern = re.compile(
            r'(正价|奥莱)[^\n]*?销售([\d,]+)元[（(](\d+)店[，,]\s*店均([\d,]+)元?'
            r'(?:[^）)]*?折扣([\d.]+)[折%])?[）)]'
        )
        total_seen: set[str] = set()
        for m in total_pattern.finditer(report_text):
            prefix = m.group(1)
            if prefix in total_seen:
                continue
            total_seen.add(prefix)

            rep_rev    = int(m.group(2).replace(",", ""))
            rep_stores = int(m.group(3))
            rep_avg    = int(m.group(4).replace(",", ""))
            rep_disc   = float(m.group(5)) / 100 if m.group(5) else None

            src_rev    = int(total_row.get(f"{prefix}_业绩") or 0)
            src_stores = int(total_row.get(f"{prefix}_店数") or 0)
            src_avg    = total_row.get(f"{prefix}_店均业绩") or 0
            src_disc   = total_row.get(f"{prefix}_实销折扣") or 0
            label = f"{prefix}总计"
            ok = True

            for cond, rep_v, src_v in [
                ("业绩", rep_rev, src_rev),
                ("店均", rep_avg, src_avg),
            ]:
                if src_v and abs(rep_v - src_v) / src_v > TOLERANCE:
                    detail_lines.append(
                        f"❌ 错误｜{label}{cond}｜报告={rep_v:,} 源={src_v:,} "
                        f"偏差={abs(rep_v-src_v)/src_v*100:.1f}%"
                    )
                    errors += 1; ok = False
            if src_stores and rep_stores != src_stores:
                detail_lines.append(f"❌ 错误｜{label}店数｜报告={rep_stores} 源={src_stores}")
                errors += 1; ok = False
            if rep_disc and src_disc and abs(rep_disc - src_disc) > TOLERANCE:
                detail_lines.append(
                    f"❌ 错误｜{label}折扣｜报告={rep_disc*100:.1f}% 源={src_disc*100:.1f}%"
                )
                errors += 1; ok = False
            if ok:
                detail_lines.append(
                    f"✅ 正确｜{label}（{rep_stores}店，业绩{rep_rev:,}，店均{rep_avg:,}）"
                )
                correct += 1

    # ── Pattern C：品类差值 ───────────────────────────────────────────────────
    _cat_rows = (
        manifest.get("categoryStructureRegular", {}).get("rows", [])
        + manifest.get("categoryStructureOutlet", {}).get("rows", [])
    )
    cat_map: dict[str, float] = {
        f"{r.get('新/旧货','')}{r.get('运营中类','')}": (r.get("销售吊牌%") or 0) - (r.get("总进吊牌%") or 0)
        for r in _cat_rows
        if r.get("运营中类") and r.get("运营中类") != "小计"
    }
    cat_names = sorted(
        {r.get("运营中类", "") for r in _cat_rows if r.get("运营中类") and r.get("运营中类") != "小计"},
        key=len, reverse=True,
    )
    if cat_names:
        cat_pat = re.compile(
            r'(' + "|".join(re.escape(c) for c in cat_names) + r')'
            r'[（(][^）)]*?(?:销售|库存)[^）)]*?差值([+-][\d.]+)%[）)]'
        )
        cat_seen: set[str] = set()
        for m in cat_pat.finditer(report_text):
            name = m.group(1)
            if name in ("自营","联营","托管","正价","奥莱","旧货","新货") or name in cat_seen:
                continue
            cat_seen.add(name)
            rep_diff = float(m.group(2)) / 100
            key = next((f"{p}{name}" for p in ("新货","旧货") if f"{p}{name}" in cat_map), None)
            if key is None:
                detail_lines.append(f"⚠️ 无法核实｜{name} 差值={rep_diff*100:+.1f}%")
                unverifiable += 1; continue
            src_diff = cat_map[key]
            if abs(rep_diff - src_diff) > TOLERANCE:
                detail_lines.append(
                    f"❌ 错误｜{key}差值｜报告={rep_diff*100:+.1f}% 源={src_diff*100:+.1f}%"
                )
                errors += 1
            else:
                detail_lines.append(f"✅ 正确｜{key}差值={rep_diff*100:+.1f}%")
                correct += 1

    total     = correct + errors
    pass_rate = correct / total * 100 if total > 0 else 0.0
    passed    = (errors == 0) if total > 0 else None
    summary   = (
        f"【核查汇总】正确={correct} 错误={errors} "
        f"无法核实={unverifiable} 通过率={pass_rate:.1f}%"
    )
    detail = "\n".join(detail_lines) + ("\n\n" if detail_lines else "") + summary

    return {"passed": passed, "correct": correct, "errors": errors,
            "unverifiable": unverifiable, "pass_rate": pass_rate, "detail": detail}


def write_factcheck_log(result: dict, stamp: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / f"factcheck_{stamp}.md"
    passed_str = {True: "PASS", False: "FAIL", None: "UNKNOWN"}.get(result["passed"], "UNKNOWN")
    header = (
        f"# 报告事实核查 {stamp}\n\n"
        f"**结果**: {passed_str}  \n"
        f"**正确**: {result['correct']} 条  \n"
        f"**错误**: {result['errors']} 条  \n"
        f"**无法核实**: {result['unverifiable']} 条  \n"
        f"**通过率**: {result['pass_rate']:.1f}%\n\n---\n\n"
    )
    log_file.write_text(header + result["detail"], encoding="utf-8")
    return log_file
