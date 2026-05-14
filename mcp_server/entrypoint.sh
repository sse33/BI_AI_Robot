#!/bin/sh
set -e

# 非交互式登录观远 BI（凭证从环境变量注入）
guancli auth login \
  --profile default \
  --url "${GY_BASE_URL}" \
  --domain "${GY_DOMAIN:-}" \
  --login-id "${GY_ACCOUNT}" \
  --password "${GY_PASSWORD}" \
  --default

echo "guancli login OK"

# 启动 MCP Server
exec python server.py
