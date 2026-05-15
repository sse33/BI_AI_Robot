"""
MCP Server 主入口。
使用 FastMCP，支持 HTTP SSE transport，供飞书 Agent 调用。

配置优先级：命令行参数 > 环境变量（.env）> 默认值

启动方式：
    python server.py                      # 读取 .env，默认 0.0.0.0:8000
    python server.py --port 9000          # 覆盖端口
    python server.py --host 127.0.0.1     # 仅本机访问
    python server.py --transport stdio    # stdio 模式（本地调试用）

认证：
    设置环境变量 MCP_API_KEY，所有 SSE 请求须携带请求头：
        Authorization: Bearer <MCP_API_KEY>
    未设置 MCP_API_KEY 则不启用认证（仅限内网/本地使用）。
"""

import argparse
import os
from pathlib import Path
from typing import Optional

import uvicorn
from dotenv import load_dotenv
from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.responses import Response
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


class ApiKeyMiddleware:
    """纯 ASGI middleware，检查 Authorization: Bearer <key> 请求头。
    不使用 BaseHTTPMiddleware，避免其缓冲行为破坏 SSE 流式响应。
    """

    def __init__(self, app, api_key: str):
        self.app = app
        self.api_key = api_key

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # DELETE is session cleanup (Streamable HTTP), allow without auth
            if scope.get("method", "").upper() != "DELETE":
                headers = {k.lower(): v for k, v in scope.get("headers", [])}
                auth = headers.get(b"authorization", b"").decode()
                if auth != f"Bearer {self.api_key}":
                    response = Response("Unauthorized", status_code=401)
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)


@mcp.tool(description=tools.list_dashboards.__doc__)
def list_dashboards() -> dict:
    return tools.list_dashboards()


@mcp.tool(description=tools.list_cards.__doc__)
def list_cards(dashboard_id: Optional[str] = None) -> dict:
    return tools.list_cards(dashboard_id)


@mcp.tool(description=tools.get_cards_by_filter.__doc__)
def get_cards_by_filter(filter_name: str, dashboard_id: Optional[str] = None) -> dict:
    return tools.get_cards_by_filter(filter_name, dashboard_id)


@mcp.tool(description=tools.list_filter_values.__doc__)
def list_filter_values(
    filter_name: str,
    keyword: str,
    dashboard_id: Optional[str] = None,
) -> dict:
    return tools.list_filter_values(filter_name, keyword, dashboard_id)


@mcp.tool(description=tools.get_card_data.__doc__)
def get_card_data(
    card_id: str,
    filters: Optional[dict] = None,
    limit: int = 200,
    dashboard_id: Optional[str] = None,
) -> dict:
    return tools.get_card_data(card_id, filters=filters, limit=limit, dashboard_id=dashboard_id)


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
        choices=["streamable-http", "sse", "stdio"],
        default=os.getenv("MCP_TRANSPORT", "streamable-http"),
        help="传输模式：streamable-http（飞书 Agent，默认）/ sse（旧版）/ stdio（本地调试）",
    )
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        api_key = os.getenv("MCP_API_KEY", "")
        middleware = [Middleware(ApiKeyMiddleware, api_key=api_key)] if api_key else []
        if api_key:
            print("认证已启用（MCP_API_KEY）")
        else:
            print("警告：MCP_API_KEY 未设置，服务无认证保护")
        # streamable-http：无状态，每次调用独立 POST，适合飞书 Agent
        # sse：有状态长连接，会话断开后工具调用失败
        transport = args.transport
        endpoint = "/mcp" if transport == "streamable-http" else "/sse"
        print(f"MCP Server 启动: http://{args.host}:{args.port}{endpoint} (transport={transport})")
        app = mcp.http_app(transport=transport, middleware=middleware)
        uvicorn.run(app, host=args.host, port=args.port)
