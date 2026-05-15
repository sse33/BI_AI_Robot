"""
封装 guancli 调用，负责从观远 BI 取数。
通过 subprocess 调用已安装并登录的 guancli，使用 --raw 获取原始 API JSON，
再解析为 [{字段名: 值}] 格式。

内部 API 数据结构（response.chartMain）：
  - column.values: [[{title, ...}], ...]  各列的 header 信息（含多级列头）
  - row.values:    [[{title, ...}], ...]  各行维度的 header 信息（PIVOT_TABLE 用）
  - data:          [[{v, t_idx?}, ...]]  行数据，v 是值，t_idx 用于合并单元格
"""

import json
import subprocess
from typing import Optional


def _run_guancli(args: list[str]) -> str:
    """执行 guancli 命令，返回 stdout 字符串。失败时抛出 RuntimeError。"""
    cmd = ["guancli"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"guancli 调用失败 (exit {result.returncode})\n"
            f"命令: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _extract_column_names(col_values: list) -> list[str]:
    """
    从 column.values 提取列名。
    col_values 结构：[[{title, ...}, ...], ...]
    每个外层元素是一列，内层是该列的多级 header，取最后一级（最具体）作为列名。
    """
    names = []
    for group in col_values:
        if group:
            names.append(group[-1].get("title", ""))
    return names


def _extract_row_dim_names(row_values: list) -> list[str]:
    """
    从 row.values 提取行维度名（PIVOT_TABLE 用）。
    结构与 column.values 相同，取最后一级 title。
    """
    names = []
    for group in row_values:
        if group:
            names.append(group[-1].get("title", ""))
    return names


def _cell_value(cell):
    """提取单元格值，合并单元格（t_idx）直接取 v。"""
    if isinstance(cell, dict):
        return cell.get("v")
    return cell


def _parse_chart_main(chart_main: dict) -> list[dict]:
    """
    将 chartMain 解析为行记录列表，支持两种布局：

    标准布局（KPI / 竖排 PIVOT_TABLE）：
      - column.values = 指标名列表，row.values = 维度列表
      - data[i] = 第 i 行，每格对应一个指标
      - 输出：每行一个 dict，key=维度/指标名

    转置布局（横排 PIVOT_TABLE）：
      - row.values = 指标名列表，column.values = 维度值（如 SKC 编码）
      - data[i] = 第 i 个指标的所有维度值
      - len(data) == len(row.values) 是识别标志
      - 输出：每个维度值对应一个 dict，key=指标名
    """
    col_names = _extract_column_names(
        chart_main.get("column", {}).get("values", [])
    )
    row_dim_names = _extract_row_dim_names(
        chart_main.get("row", {}).get("values", [])
    )
    data = chart_main.get("data", [])

    if not data:
        return []

    # ── 转置布局检测 ──────────────────────────────────────────────
    # row.values 有内容且 data 行数 == row.values 条目数 → 转置
    if row_dim_names and len(data) == len(row_dim_names):
        num_cols = len(col_names) or (len(data[0]) if data else 1)
        records = [{} for _ in range(max(num_cols, 1))]
        for metric_name, raw_row in zip(row_dim_names, data):
            for j, record in enumerate(records):
                cell = raw_row[j] if j < len(raw_row) else None
                record[metric_name] = _cell_value(cell)
        return records

    # ── 标准布局 ──────────────────────────────────────────────────
    all_columns = row_dim_names + col_names
    rows = []
    for raw_row in data:
        record = {}
        for col_name, cell in zip(all_columns, raw_row):
            record[col_name] = _cell_value(cell)
        rows.append(record)
    return rows


def get_card_data(
    card_id: str,
    filters: Optional[dict[str, str | list]] = None,
    limit: int = 200,
) -> list[dict]:
    """
    获取卡片数据，返回行记录列表。

    Args:
        card_id: 卡片 ID（cdId）
        filters: 筛选条件，字段名 → 值
                 单值：EQ 精确匹配，例 {"实际波段": "SS26"}
                 列表：IN 多值匹配，例 {"商品标签": ["生意款", "生意款 亚洲大片"]}
        limit: 最多返回行数，卡片接口上限 1000

    Returns:
        行记录列表，每行是 {字段名: 值} 的 dict
    """
    limit = min(limit, 1000)
    args = ["card", "preview", card_id, "--raw", "--limit", str(limit)]

    if filters:
        for field, value in filters.items():
            if isinstance(value, list):
                vals = ",".join(str(v) for v in value)
                args += ["--filter", f"{field} IN {vals}"]
            else:
                args += ["--filter", f"{field} EQ {value}"]

    raw = _run_guancli(args)
    payload = json.loads(raw)
    chart_main = payload["response"]["chartMain"]
    return _parse_chart_main(chart_main)


def list_filter_values(ds_id: str, field: str, keyword: str) -> list[str]:
    """
    通过 CONTAINS 模糊查询获取数据集中某字段包含关键词的所有枚举值。
    用于多值字段（如商品标签）的枚举值发现：先找出所有含关键词的组合值，
    再将这些完整值列表传给 get_card_data 进行 IN 精确匹配。

    Args:
        ds_id: 数据集 ID
        field: 字段名（与仪表板筛选器字段名一致）
        keyword: 模糊搜索关键词

    Returns:
        去重后的枚举值列表，已排序
    """
    args = [
        "ds", "preview", ds_id,
        "--columns", field,
        "--filter", f"{field} CONTAINS {keyword}",
        "--limit", "1000",
        "-f", "json",
    ]
    raw = _run_guancli(args)
    payload = json.loads(raw)

    # ds preview -f json 返回结构：[{"字段名": "值"}, ...]
    values = set()
    rows = payload if isinstance(payload, list) else payload.get("data", [])
    for row in rows:
        if isinstance(row, dict):
            val = row.get(field)
        elif isinstance(row, list):
            val = row[0] if row else None
        else:
            val = row
        if val is not None and str(val).strip():
            values.add(str(val).strip())

    return sorted(values)
