"""
MCP Server 主入口。
使用 FastMCP，支持 HTTP SSE transport，供飞书 Agent 调用。

配置优先级：命令行参数 > 环境变量（.env）> 默认值

启动方式：
    python server.py                      # 读取 .env，默认 0.0.0.0:8000
    python server.py --port 9000          # 覆盖端口
    python server.py --host 127.0.0.1     # 仅本机访问
    python server.py --transport stdio    # stdio 模式（本地调试用）
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastmcp import FastMCP
import tools

# 加载根目录 .env（与 python/ 版本共用同一个 .env 文件）
ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

mcp = FastMCP(
    name="BI Assistant",
    instructions=(
        "你可以查询观远 BI 仪表板上的数据。"
        "先调用 list_cards 了解当前仪表板有哪些卡片及其业务含义，"
        "再根据用户问题选择合适的卡片，调用 get_card_data 获取数据。"
        "数据由 BI 系统实时返回，已经是聚合后的结果，无需二次计算。"
    ),
)


@mcp.tool(description=tools.get_cards_by_filter.__doc__)
def get_cards_by_filter(filter_name: str) -> dict:
    return tools.get_cards_by_filter(filter_name)


@mcp.tool(description=tools.list_cards.__doc__)
def list_cards() -> dict:
    return tools.list_cards()


@mcp.tool(description=tools.get_card_data.__doc__)
def get_card_data(
    card_id: str,
    filters: Optional[dict] = None,
    limit: int = 200,
) -> dict:
    return tools.get_card_data(card_id, filters=filters, limit=limit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BI Assistant MCP Server")
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "0.0.0.0"),
        help="监听地址（默认读取 MCP_HOST 环境变量，fallback 0.0.0.0）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8000")),
        help="监听端口（默认读取 MCP_PORT 环境变量，fallback 8000）",
    )
    parser.add_argument(
        "--transport",
        choices=["sse", "stdio"],
        default=os.getenv("MCP_TRANSPORT", "sse"),
        help="传输模式：sse（飞书 Agent）或 stdio（本地调试）",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        print(f"MCP Server 启动: http://{args.host}:{args.port}/sse")
        mcp.run(transport="sse", host=args.host, port=args.port)
