"""
validate_data.py — manifest 数据质量校验

函数：
  validate_manifest(manifest, path)  → list[dict]   结构/时效校验
  vision_verify(manifest, screenshot_path) → list[dict]   Vision 截图核对
  write_validation_log(issues, passed, out_dir)       追加写入 validation.log
"""

import json
import time
from datetime import datetime
from pathlib import Path

import yaml
from ai_client import call_ai

_ROOT_DIR   = Path(__file__).parent.parent
_CONFIGS_DIR = _ROOT_DIR / "configs"

_MAX_MANIFEST_AGE_HOURS = 26


def _load_card_checks(dashboard_id: str) -> list[dict]:
    """从 cards.yaml 中读取带 validate 块的卡片，构建校验规则列表。"""
    cards_path = _CONFIGS_DIR / dashboard_id / "cards.yaml"
    if not cards_path.exists():
        return []
    cards_data = yaml.safe_load(cards_path.read_text(encoding="utf-8"))
    checks = []
    for c in cards_data.get("cards", []):
        v = c.get("validate")
        if not v:
            continue
        entry = {
            "key":           c["key"],
            "name":          c.get("name", c["key"]),
            "min_rows":      v.get("min_rows", 1),
            "required_cols": v.get("required_cols", []),
        }
        if "summary_row" in v:
            entry["summary_row"] = v["summary_row"]
        if "vision" in v:
            entry["vision"] = v["vision"]
        checks.append(entry)
    return checks


def validate_manifest(manifest: dict, path: Path) -> list[dict]:
    """
    校验 manifest 数据质量。
    返回问题列表，每项含 level("error"|"warning")、check、message。
    空列表表示全部通过。
    """
    issues = []

    # 1. 时效：manifest 文件名日期必须是今天（T+1 数据，同一自然日内可复用）
    import re as _re
    _date_match = _re.search(r"manifest_(\d{8})", path.name)
    if _date_match:
        from datetime import date as _date
        manifest_date = _date(
            int(_date_match.group(1)[:4]),
            int(_date_match.group(1)[4:6]),
            int(_date_match.group(1)[6:8]),
        )
        today = _date.today()
        from datetime import timedelta as _timedelta
        if manifest_date < today - _timedelta(days=1):
            issues.append({
                "level": "error",
                "check": "时效",
                "message": f"manifest 日期为 {manifest_date}，今天是 {today}，请先重新运行 collect.py",
            })
    else:
        # 旧命名格式 fallback：用文件修改时间
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        if age_hours > _MAX_MANIFEST_AGE_HOURS:
            issues.append({
                "level": "error",
                "check": "时效",
                "message": f"数据已 {age_hours:.1f}h 未更新（阈值 {_MAX_MANIFEST_AGE_HOURS}h），请先重新运行 collect.py",
            })

    # 2. 卡片完整性、行数、必需列、汇总行有效性（从 cards.yaml 的 validate 块派生）
    dashboard_id = path.parent.name
    card_checks  = _load_card_checks(dashboard_id)
    for spec in card_checks:
        card = manifest.get(spec["key"])
        if not card:
            issues.append({"level": "error", "check": spec["name"], "message": f"卡片缺失（key={spec['key']}）"})
            continue

        rows = card.get("rows", [])
        cols = set(card.get("columns", []))

        if len(rows) < spec["min_rows"]:
            issues.append({
                "level": "error",
                "check": spec["name"],
                "message": f"行数不足：期望 >={spec['min_rows']}，实际 {len(rows)}",
            })

        missing = [c for c in spec["required_cols"] if c not in cols]
        if missing:
            issues.append({
                "level": "error",
                "check": spec["name"],
                "message": f"核心列缺失：{', '.join(missing)}",
            })

        sr = spec.get("summary_row")
        if sr:
            total_row = next((r for r in rows if r.get(sr["filter_col"]) == sr["filter_val"]), None)
            if total_row is None:
                issues.append({
                    "level": "error",
                    "check": spec["name"],
                    "message": f"找不到 {sr['filter_col']}={sr['filter_val']} 的汇总行",
                })
            elif not (total_row.get(sr["nonzero_col"]) or 0):
                issues.append({
                    "level": "warning",
                    "check": spec["name"],
                    "message": f"汇总行 {sr['nonzero_col']} 为 0，可能是节假日或数据未到账，请人工确认",
                })

    # 3. 值域检查：折扣/占比类列值应在 0~1，超出则为异常数据
    _ratio_keywords = ("折扣", "占比", "折损", "动销率")
    for card_key, card in manifest.items():
        if not isinstance(card, dict):
            continue
        rows = card.get("rows", [])
        cols = card.get("columns", [])
        ratio_cols = [c for c in cols if any(kw in c for kw in _ratio_keywords)]
        for col in ratio_cols:
            anomalies = [
                r for r in rows
                if isinstance(r.get(col), (int, float)) and r[col] > 1
            ]
            if anomalies:
                dim_col = cols[0] if cols else "行"
                samples = ", ".join(
                    f"{r.get(dim_col, '?')}={r[col]:.4f}" for r in anomalies[:3]
                )
                issues.append({
                    "level": "warning",
                    "check": f"值域异常[{card_key}]",
                    "message": f"列「{col}」存在 >1 的异常值（应为 0~1 小数）：{samples}{'…' if len(anomalies) > 3 else ''}",
                })

    return issues


def vision_verify(manifest: dict, screenshot_path: Path, dashboard_id: str) -> list[dict]:
    """
    用 Gemini Vision 读取看板截图中的关键数字，与抓取数据比对。
    从 cards.yaml 的 validate.vision 块读取采样配置，完全数据驱动。
    返回问题列表，格式同 validate_manifest()。
    """
    import base64

    issues = []

    if not screenshot_path.exists():
        issues.append({
            "level": "warning",
            "check": "Vision核对",
            "message": f"未找到验证截图 {screenshot_path.name}，请先运行 screenshot_dashboard.py",
        })
        return issues

    # 从 cards.yaml 找第一个有 validate.vision 配置的卡片
    card_checks = _load_card_checks(dashboard_id)
    vision_spec = next((s for s in card_checks if s.get("vision")), None)
    if not vision_spec:
        issues.append({"level": "warning", "check": "Vision核对", "message": "cards.yaml 中无 validate.vision 配置，跳过核对"})
        return issues

    vcfg        = vision_spec["vision"]
    sample_by   = vcfg["sample_by"]
    exclude_vals = vcfg.get("exclude_vals", {})
    verify_cols  = vcfg["verify_cols"]
    card_name    = vision_spec["name"]

    card_rows = manifest.get(vision_spec["key"], {}).get("rows", [])

    def _is_excluded(row: dict) -> bool:
        return any(row.get(col) == val for col, val in exclude_vals.items())

    sample_rows = [r for r in card_rows if r.get(sample_by) and not _is_excluded(r)][:2]
    if len(sample_rows) < 2:
        issues.append({"level": "warning", "check": "Vision核对", "message": f"「{card_name}」可用采样行不足，跳过核对"})
        return issues

    scraped = {
        r[sample_by]: {col: r.get(col) or 0 for col in verify_cols}
        for r in sample_rows
    }
    sample_desc = "、".join(
        f"{r[sample_by]}（" + "，".join(f"{c}={r.get(c):,.0f}" for c in verify_cols) + "）"
        for r in sample_rows
    )

    img_b64      = base64.b64encode(screenshot_path.read_bytes()).decode()
    sample_keys  = [r[sample_by] for r in sample_rows]
    json_template = "".join(
        f'  "{k}": {{' + ", ".join(f'"{c}": <数字或null>' for c in verify_cols) + "},\n"
        for k in sample_keys
    )
    prompt = (
        f"这是一张BI看板截图，包含「{card_name}」表格。\n"
        f"请找到「{sample_by}」列中「{'」和「'.join(sample_keys)}」所在的行，"
        f"提取每行的「{'」和「'.join(verify_cols)}」数字。\n"
        "只返回如下 JSON，不要其他文字：\n"
        "{\n" + json_template + "}\n"
        "注意：数字可能含逗号分隔符，返回时去掉逗号。找不到则返回 null。"
    )

    try:
        raw = call_ai("", prompt, provider="gemini", temperature=0,
                      stream=False, image_b64=img_b64)
        raw = raw.strip().strip("`").removeprefix("json").strip()
        vision_data = json.loads(raw)

    except Exception as e:
        issues.append({
            "level": "warning",
            "check": "Vision核对",
            "message": f"Vision 解析失败（{e}），跳过核对",
        })
        return issues

    TOLERANCE = 0.01
    print(f"  [Vision] 核对样本：{sample_desc}")
    for key_val, api_fields in scraped.items():
        vision_row = vision_data.get(key_val)
        if not vision_row:
            issues.append({
                "level": "warning",
                "check": f"Vision核对/{key_val}",
                "message": f"截图中未识别到「{sample_by}={key_val}」，抓取值={api_fields}",
            })
            continue

        for field, api_val in api_fields.items():
            raw_v = vision_row.get(field)
            if raw_v is None:
                issues.append({
                    "level": "warning",
                    "check": f"Vision核对/{key_val}/{field}",
                    "message": f"截图未返回该字段，抓取值={api_val}",
                })
                continue
            try:
                vision_val = float(str(raw_v).replace(",", ""))
            except ValueError:
                issues.append({
                    "level": "warning",
                    "check": f"Vision核对/{key_val}/{field}",
                    "message": f"Vision 返回值无法解析：{raw_v}",
                })
                continue

            if api_val == 0 and vision_val == 0:
                print(f"  ✓ {key_val}/{field}: 0  截图=0")
                continue

            base   = max(abs(api_val), abs(vision_val), 1)
            diff_r = abs(api_val - vision_val) / base
            if diff_r > TOLERANCE:
                issues.append({
                    "level": "error",
                    "check": f"Vision核对/{key_val}/{field}",
                    "message": (
                        f"数据与截图不一致：抓取={api_val:,.0f}，"
                        f"截图识别={vision_val:,.0f}，偏差={diff_r * 100:.1f}%"
                    ),
                })
            else:
                print(f"  ✓ {key_val}/{field}: 抓取={api_val:,.0f}  截图={vision_val:,.0f}  偏差={diff_r * 100:.2f}%")

    return issues


def write_validation_log(issues: list[dict], passed: bool, out_dir: Path):
    """追加写入 out_dir/validation.log"""
    log_file = out_dir / "validation.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "PASS" if passed else "FAIL"
    lines  = [f"[{ts}] 验证结果: {status}"]
    for issue in issues:
        lines.append(f"  [{issue['level'].upper()}] [{issue['check']}] {issue['message']}")
    if not issues:
        lines.append("  所有检查项通过")

    entry = "\n".join(lines)
    with log_file.open("a", encoding="utf-8") as f:
        f.write(entry + "\n\n")
    print(entry)
