# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

双版本自动化日报系统，直接从观远 BI（Guanyuan BI）内部 API 抓取卡片数据，调用 AI 生成分析报告并推送飞书。

## 目录结构

```
BI_AI_Robot/
├── nodejs/                      # Node.js 版本（已稳定）
│   ├── bi_card_fetcher_v2.mjs   # 核心：cookie 认证，抓取卡片数据
│   ├── validate.mjs             # Puppeteer 登录 → 抓取 → outputs/manifest_test.json
│   ├── screenshot_dashboard.mjs # Puppeteer 截图看板
│   ├── analyze.mjs              # AI 分析 → 报告 + 飞书推送
│   └── package.json
├── python/                      # Python 版本（主力）
│   ├── bi_card_fetcher.py       # 核心：cookie 认证，抓取卡片数据
│   ├── collect.py               # Playwright 登录 → 并发采集 → outputs/{id}/manifest_{YYYYMMDD}.json
│   ├── discover.py              # 发现仪表板卡片/筛选器元数据 → cards.yaml / filters.yaml
│   ├── clarify.py               # 需求调研员：交互式补全卡片 business_description
│   ├── generate_analysis.py     # AI 生成分析框架 → analysis_{id}.yaml
│   ├── analyze.py               # AI 分析 → 报告 + 飞书推送
│   └── requirements.txt
├── outputs/                     # 共享输出目录（不提交内容）
├── .env                         # 共享环境变量（不提交）
└── .env.example
```

## 常用命令

**Python 版本（推荐）：**
```bash
cd python

# 首次创建虚拟环境（仅一次）
python3 -m venv .venv

# 激活虚拟环境（每次开发前）
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium   # 首次需要

# 日常运行
python collect.py             # 登录 → 采集所有仪表板 → outputs/{id}/manifest_{YYYYMMDD}.json
python analyze.py             # AI 分析 → outputs/{id}/analysis_report_*.md → 飞书推送
python analyze.py --no-feishu # 跳过飞书（调试用）

# 新仪表板初始化
python discover.py --dashboard daily_sales
python clarify.py --dashboard daily_sales
python generate_analysis.py --dashboard daily_sales
```

**Node.js 版本：**
```bash
cd nodejs
npm install

node validate.mjs             # 登录 → 抓取
node analyze.mjs              # AI 分析
```

## 环境变量（`.env` 在根目录，两个版本共用）

| 变量 | 用途 |
|---|---|
| `GY_BASE_URL` | 观远 BI 部署地址，如 `https://your-bi-domain.com` |
| `GY_DASHBOARD_URL` | 仪表板完整 URL（截图和旧版 validate.py 使用）|
| `GY_ACCOUNT` | 登录工号 |
| `GY_PASSWORD` | 登录密码 |
| `AI_PROVIDER` | `gemini` / `claude` / `azure` / `openai` |
| `GEMINI_API_KEY` | Gemini API Key（默认 provider） |
| `GEMINI_MODEL` | 模型名，默认 `gemini-2.5-pro` |
| `ANTHROPIC_API_KEY` | Claude API Key |
| `AZURE_OPENAI_*` | Azure OpenAI 相关配置 |
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook URL |

## 架构与关键设计

**数据流：** `collect.py` 登录并采集 → `outputs/{id}/manifest_{YYYYMMDD}.json` → `analyze.py` 读取并分析

**AI 调用（`analyze.py`）**：
- Gemini 使用流式 SSE（`streamGenerateContent?alt=sse`），避免企业代理因响应慢导致的 socket 超时
- `build_data_summary()` 预处理原始数据，消除 LLM 混淆：全量城市、全量波段×城市、只传店铺维度动销率、预先计算差值

**数据解析要点（`bi_card_fetcher.py`）**：
- 多层列头：顶层含 `colSpan` 的列展开配对底层指标，生成 `正价_业绩` 格式列名
- 合并单元格：`cell.t_idx = "rowIndex:colIndex"` 指向实际值所在行

**报告防歧义设计**：
- 品类结构：传预计算的 `差值=销售吊牌%-总进吊牌%`，口径统一
- 动销率：只传 `_动销率_店铺` 列，不传城市维度，并在数据中注明
- 波段调拨方向：动销率高的城市 → 动销率低的城市（高→低调拨货品）

## 已确认卡片 ID

| `CARD_IDS` 键 | 模块 | 说明 |
|---|---|---|
| `DAILY_SALES_OVERVIEW` | 每日销售概况（渠道×城市）| ~39行 |
| `SKC_TOP10` | SKC TOP10 | 10行 |
| `SALES_TREND` | 近期销售趋势 | ~37行 |
| `CATEGORY_STRUCTURE` | 运营中类结构 | ~42行 |
| `SKC_SELL_THROUGH` | 近六波 SKC 动销率 | — |
| `UNKNOWN_CARD` | 待识别 | — |

## 初始化流程

新仪表板接入时，按以下顺序运行一次：

```
discover.py   → cards.yaml（卡片元数据）
clarify.py    → cards.yaml（补全 business_description）
generate_analysis.py → analysis_{id}.yaml（分析框架，含 prompts）
```

之后每日只运行：`collect.py` → `analyze.py`

详细说明见 `python/CLAUDE.md`。
