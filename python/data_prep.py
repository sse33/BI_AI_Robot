"""
data_prep.py — 分析元数据驱动的数据压缩模块

将 manifest JSON 按 analysis_*.yaml 中 data_prep 规则转换为 LLM 可读文本。

支持三种 mode：
  full_rows   全量行，配合 include_cols / exclude_cols / col_pattern_include /
              row_filter / sort_by / derived 使用
  aggregate   按 group_by 维度聚合，agg[] 中声明聚合函数（sum / weighted_avg / count）
  alert_only  只传满足 alerts 预警条件的行
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Any


# ── 元数据加载 ────────────────────────────────────────────────────────────────

def load_analysis_meta(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ── 列解析 ────────────────────────────────────────────────────────────────────

def resolve_cols(card_data: dict, prep: dict) -> list[str]:
    """根据 data_prep 规则确定列顺序"""
    all_cols = card_data.get("columns", [])
    always   = prep.get("always_include_cols", [])

    if "include_cols" in prep:
        # 保持 spec 顺序，只保留实际存在的列
        existing = set(all_cols)
        return [c for c in prep["include_cols"] if c in existing]

    if "exclude_cols" in prep:
        excl = set(prep["exclude_cols"])
        return [c for c in all_cols if c not in excl]

    if "col_pattern_include" in prep:
        patterns = prep["col_pattern_include"]
        metric_cols = [
            c for c in all_cols
            if c not in always and any(p in c for p in patterns)
        ]
        return always + metric_cols

    return all_cols


# ── 行过滤 ────────────────────────────────────────────────────────────────────

def _eval_filter(row: dict, expr: str) -> bool:
    """解析并求值过滤表达式，支持 or / and 组合及 any(pattern列) 特殊形式"""
    if not expr:
        return True

    # any(pattern列) op threshold  ← 动销率宽列场景
    m = re.match(r"any\((.+?)列\)\s*([<>=!]+)\s*([0-9.]+)", expr)
    if m:
        pattern, op, threshold = m.group(1), m.group(2), float(m.group(3))
        values = [
            v for k, v in row.items()
            if pattern in k and isinstance(v, (int, float)) and v is not None
        ]
        return bool(values) and _cmp_any(values, op, threshold)

    # or / and 递归
    if " or " in expr:
        return any(_eval_filter(row, p.strip()) for p in expr.split(" or "))
    if " and " in expr:
        return all(_eval_filter(row, p.strip()) for p in expr.split(" and "))

    return _eval_simple(row, expr.strip())


def _cmp_any(values: list, op: str, threshold: float) -> bool:
    fns = {
        "<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
        ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
        "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
    }
    fn = fns.get(op, lambda *_: False)
    return any(fn(v, threshold) for v in values)


def _eval_simple(row: dict, expr: str) -> bool:
    # col == 'string'
    m = re.match(r"(.+?)\s*(==|!=)\s*'(.+?)'", expr)
    if m:
        col, op, val = m.group(1).strip(), m.group(2), m.group(3)
        rval = str(row.get(col, ""))
        return rval == val if op == "==" else rval != val

    # col op number
    m = re.match(r"(.+?)\s*(==|!=|<=|>=|<|>)\s*([0-9.]+)", expr)
    if m:
        col, op, val = m.group(1).strip(), m.group(2), float(m.group(3))
        rval = row.get(col)
        if rval is None or rval == "":
            return False
        try:
            fns = {
                "==": lambda a, b: a == b, "!=": lambda a, b: a != b,
                "<": lambda a, b: a < b,  "<=": lambda a, b: a <= b,
                ">": lambda a, b: a > b,  ">=": lambda a, b: a >= b,
            }
            return fns[op](float(rval), val)
        except (ValueError, TypeError):
            return False

    return True


# ── 衍生列 ────────────────────────────────────────────────────────────────────

def add_derived(rows: list[dict], derived_specs: list[dict]) -> list[dict]:
    """计算简单二元运算衍生列（col1 op col2）"""
    for spec in (derived_specs or []):
        name    = spec["name"]
        formula = spec["formula"]
        m = re.match(r"(.+?)\s*([-+*/])\s*(.+)", formula)
        if not m:
            continue
        left, op, right = m.group(1).strip(), m.group(2), m.group(3).strip()
        for row in rows:
            try:
                lv = float(row.get(left, 0) or 0)
                rv = float(row.get(right, 0) or 0)
                if   op == "-": row[name] = lv - rv
                elif op == "+": row[name] = lv + rv
                elif op == "*": row[name] = lv * rv
                elif op == "/" and rv != 0: row[name] = lv / rv
                else: row[name] = None
            except (ValueError, TypeError):
                row[name] = None
    return rows


# ── 聚合 ──────────────────────────────────────────────────────────────────────

def aggregate(rows: list[dict], group_by: list[str], agg_specs: list[dict]) -> list[dict]:
    """按 group_by 聚合，支持 sum / count / weighted_avg"""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        key = tuple(str(row.get(g, "")) for g in group_by)
        groups[key].append(row)

    result = []
    for key, grp in groups.items():
        agg_row = dict(zip(group_by, key))
        for spec in agg_specs:
            col  = spec["col"]
            func = spec["func"]
            if func == "sum":
                agg_row[col] = sum(float(r.get(col, 0) or 0) for r in grp)
            elif func == "count":
                agg_row[col] = len(grp)
            elif func == "weighted_avg":
                weight_col = spec.get("weight_col", "")
                total_w    = sum(float(r.get(weight_col, 0) or 0) for r in grp)
                if total_w:
                    agg_row[col] = sum(
                        float(r.get(col, 0) or 0) * float(r.get(weight_col, 0) or 0)
                        for r in grp
                    ) / total_w
                else:
                    agg_row[col] = 0.0
        result.append(agg_row)
    return result


# ── 预警求值 ──────────────────────────────────────────────────────────────────

_OP_ALIASES = {"lte": "<=", "gte": ">=", "lt": "<", "gt": ">", "eq": "==", "ne": "!="}

def _norm_op(op: str) -> str:
    return _OP_ALIASES.get(op, op)

def evaluate_alerts(section: dict, manifest: dict) -> dict[str, list[dict]]:
    """对 section 中所有 alerts 求值，返回 {alert_id: [触发行]}"""
    triggered: dict[str, list[dict]] = {}
    for alert in section.get("alerts", []):
        aid      = alert["id"]
        card_key = alert.get("card", "")
        rows     = manifest.get(card_key, {}).get("rows", [])
        matching: list[dict] = []

        if "conditions" in alert:
            logic = alert.get("logic", "AND")
            for row in rows:
                results = [
                    _eval_simple(row, f"{c['metric']} {_norm_op(c['op'])} {c['value']}")
                    for c in alert["conditions"]
                ]
                hit = all(results) if logic == "AND" else any(results)
                if hit:
                    matching.append(row)

        elif "metric" in alert:
            metric = alert["metric"]
            op     = _norm_op(alert["op"])
            value  = alert["value"]
            for row in rows:
                if metric.startswith("_"):          # 列名 pattern
                    cols = [k for k in row if metric.lstrip("_") in k]
                    if any(_eval_simple(row, f"{c} {op} {value}") for c in cols):
                        matching.append(row)
                else:
                    if _eval_simple(row, f"{metric} {op} {value}"):
                        matching.append(row)

        triggered[aid] = matching
    return triggered


# ── 数值格式化 ────────────────────────────────────────────────────────────────

def _fmt(v: Any) -> str:
    if v is None or v == "":
        return "-"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float):
        if v == int(v):                      # 整数值浮点（如 sum 结果）不作百分比处理
            iv = int(v)
            return f"{iv:,}" if abs(iv) >= 1000 else str(iv)
        if 0 < abs(v) <= 1.0 + 1e-9:
            return f"{v * 100:.1f}%"
        if abs(v) >= 1000:
            return f"{round(v):,}"
        return f"{v:.2f}"
    if isinstance(v, int) and abs(v) >= 1000:
        return f"{v:,}"
    return str(v)


# ── 行列表 → 文本 ─────────────────────────────────────────────────────────────

def rows_to_text(rows: list[dict], cols: list[str], label: str) -> str:
    if not rows:
        return f"[{label}] 无数据"
    lines = [f"[{label}]"]
    for row in rows:
        parts = [f"{c}={_fmt(row.get(c))}" for c in cols]
        lines.append("  " + " | ".join(parts))
    return "\n".join(lines)


# ── 单条 data_prep 规则应用 ───────────────────────────────────────────────────

def apply_prep(prep: dict, card_data: dict, alert_results: dict[str, list]) -> str:
    """对单条 data_prep 规则求值，返回格式化文本段落"""
    mode     = prep["mode"]
    card_key = prep.get("card", "")
    _label   = prep.get("label", card_key)
    # 在 header 中同时显示人类可读标签和 manifest card key，供 AI citations 使用
    label = f"{_label} (card={card_key})" if card_key and _label != card_key else _label
    rows  = [dict(r) for r in card_data.get("rows", [])]   # 浅拷贝

    # ── alert_only ────────────────────────────────────────
    if mode == "alert_only":
        aid     = prep.get("alert_id", "")
        matched = alert_results.get(aid, [])
        cols    = list(matched[0].keys()) if matched else []
        return rows_to_text(matched, cols, label)

    # ── 衍生列（full_rows / aggregate 共用）──────────────
    rows = add_derived(rows, prep.get("derived", []))

    # ── aggregate ─────────────────────────────────────────
    if mode == "aggregate":
        group_by  = prep.get("group_by", [])
        agg_specs = prep.get("agg", [])
        rows = aggregate(rows, group_by, agg_specs)
        cols = group_by + [s["col"] for s in agg_specs]
        return rows_to_text(rows, cols, label)

    # ── full_rows ──────────────────────────────────────────
    # 行过滤
    row_filter = prep.get("row_filter", "")
    if row_filter:
        filtered = [r for r in rows if _eval_filter(r, row_filter)]
        # 若过滤后为空（如总计行不存在），回退到全量
        rows = filtered if filtered else rows

    # 排序
    sort_by = prep.get("sort_by")
    if sort_by:
        rows.sort(
            key=lambda r: float(r.get(sort_by, 0) or 0),
            reverse=bool(prep.get("sort_desc", False)),
        )

    # 行数限制
    top_n = prep.get("top_n")
    if top_n:
        rows = rows[:int(top_n)]

    # 列解析
    cols = resolve_cols(card_data, prep)
    # 补充衍生列（derived 已写入 row，但可能不在 card_data columns 里）
    derived_names = [s["name"] for s in prep.get("derived", [])]
    if derived_names and rows:
        existing = set(rows[0].keys())
        cols = cols + [n for n in derived_names if n in existing and n not in cols]

    return rows_to_text(rows, cols, label)


# ── 章节数据文本 ──────────────────────────────────────────────────────────────

def build_section_data(section: dict, manifest: dict) -> str:
    """为一个章节生成完整数据文本（供 LLM 参考）"""
    alert_results = evaluate_alerts(section, manifest)
    parts = []
    for prep in section.get("data_prep", []):
        card_key  = prep.get("card", "")
        card_data = manifest.get(card_key, {"columns": [], "rows": []})
        parts.append(apply_prep(prep, card_data, alert_results))
    return "\n\n".join(parts)


# ── 全量数据文本（所有章节）─────────────────────────────────────────────────

def build_data_text(analysis_meta: dict, manifest: dict) -> str:
    """遍历所有 sections，生成供 LLM 使用的完整数据摘要"""
    parts = []
    for section in analysis_meta.get("sections", []):
        header = f"\n{'─' * 6} {section['title']} {'─' * 6}"
        body   = build_section_data(section, manifest)
        parts.append(header + "\n" + body)
    return "\n".join(parts)


# ── 分析指令文本（从 meta 的 questions / alerts / output_hints 生成）──────────

def build_analysis_instructions(analysis_meta: dict) -> str:
    """将各章节的分析问题、预警规则、格式要求拼成 LLM 指令段"""
    lines = ["【分析指令（按章节顺序执行）】"]
    for section in analysis_meta.get("sections", []):
        lines.append(f"\n▶ {section['title']}")
        for q in section.get("questions", []):
            lines.append(f"  • {q}")
        for alert in section.get("alerts", []):
            lines.append(f"  ⚠ 预警规则：{alert['message']}")
        for hint in section.get("output_hints", []):
            lines.append(f"  → 输出格式：{hint}")
    return "\n".join(lines)
