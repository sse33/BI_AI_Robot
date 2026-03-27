# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

双版本自动化日报系统，直接从观远 BI（Guanyuan BI）内部 API 抓取卡片数据，调用 AI 生成分析报告并推送飞书，供赫基集团（TRENDY GROUP）零售日报使用。

## 目录结构

```
BI_AI_Robot/
├── nodejs/                      # Node.js 版本（已稳定）
│   ├── bi_card_fetcher_v2.mjs   # 核心：cookie 认证，抓取卡片数据
│   ├── validate.mjs             # Puppeteer 登录 → 抓取 → outputs/manifest_test.json
│   ├── screenshot_dashboard.mjs # Puppeteer 截图看板
│   ├── analyze.mjs              # AI 分析 → 报告 + 飞书推送
│   └── package.json
├── python/                      # Python 版本（主力迁移目标）
│   ├── bi_card_fetcher.py       # 核心：cookie 认证，抓取卡片数据
│   ├── validate.py              # Playwright 登录 → 抓取 → outputs/manifest_test.json
│   ├── screenshot_dashboard.py  # Playwright 截图看板
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

python validate.py            # 登录 → 抓取全部卡片 → outputs/manifest_test.json
python screenshot_dashboard.py  # 截图看板
python analyze.py             # AI 分析 → outputs/analysis_report_*.md → 飞书推送
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
| `GY_BASE_URL` | `https://bi.trendy-global.com` |
| `GY_ACCOUNT` | 登录工号 |
| `GY_PASSWORD` | 登录密码 |
| `AI_PROVIDER` | `gemini` / `claude` / `azure` / `openai` |
| `GEMINI_API_KEY` | Gemini API Key（默认 provider） |
| `GEMINI_MODEL` | 模型名，默认 `gemini-2.5-pro` |
| `ANTHROPIC_API_KEY` | Claude API Key |
| `AZURE_OPENAI_*` | Azure OpenAI 相关配置 |
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook URL |

## 架构与关键设计

**数据流：** `validate.py` 登录并抓取 → `outputs/manifest_test.json` → `analyze.py` 读取并分析

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

## 待完成任务

1. **识别 `UNKNOWN_CARD`**（`n078e9c5ad540455889f3216`）：运行 `validate.py` 后查看 `manifest_test.json` 中 `unknownCard` 字段的列名和前5行，对照看板确认模块用途
2. **`--no-feishu` 标志**：`analyze.py` 当前无法临时跳过飞书推送（需清空 env var 或加命令行参数）
