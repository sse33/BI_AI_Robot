# BI AI Robot

赫基集团（TRENDY GROUP）零售日报自动化系统。

从观远 BI 内部 API 实时抓取销售数据，由 AI 生成管理层日报，自动推送飞书。

---

## 功能概述

- **自动数据采集**：Playwright 登录观远 BI，并发抓取多张数据卡片，输出结构化 JSON
- **多维度分析**：支持城市粒度、门店粒度等多种分析视角，各自独立成报
- **AI 分析报告**：支持 Gemini / Claude / Azure OpenAI 多 provider，流式输出，自动事实核查
- **飞书推送**：报告生成后自动通过 Webhook 推送至飞书群

---

## 快速开始

### 1. 环境准备

```bash
cd python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入观远 BI 账号、AI API Key、飞书 Webhook 等真实值
```

### 3. 每日运行

```bash
source .venv/bin/activate

# 采集数据（T+1，每天早上运行一次）
python collect.py

# AI 分析 → 事实核查 → 飞书推送
python analyze.py

# 门店粒度分析变体
python analyze.py --analysis store
```

---

## 系统架构

```
观远 BI API
    ↓ collect.py（Playwright 登录 + 并发抓取）
outputs/{dashboard_id}/manifest_{YYYYMMDD}.json
    ↓ analyze.py（数据预处理 + AI 分析）
analysis_report_{YYYYMMDD}.md + [CITATIONS] JSON
    ↓ fact_check.py（对照源数据逐条核查）
factcheck_{stamp}.md
    ↓ notify.py（飞书 Webhook）
飞书群消息
```

### 四角色分工

| 角色 | 脚本 | 运行时机 | 说明 |
|---|---|---|---|
| 需求调研员 | `clarify.py` | 初始化一次 | 识别语义模糊卡片，交互式补全业务描述 |
| 分析架构师 | `generate_analysis.py` | 初始化一次 | AI 设计分析框架（章节 / 预警 / 数据规则） |
| 数据分析师 | `analyze.py` | 每日自动 | 基于当日数据生成管理层日报 |
| 数据核对员 | `fact_check.py` | 每日自动 | 对照源数据核查报告数字，检测幻觉 |

---

## 新仪表板接入

```bash
# 1. 在 configs/dashboards.yaml 注册仪表板
# 2. 运行初始化流程
python discover.py --dashboard {id}        # 发现卡片元数据
python clarify.py --dashboard {id}         # 澄清业务语义
python generate_analysis.py --dashboard {id}  # 生成分析框架
```

---

## 目录结构

```
BI_AI_Robot/
├── python/                  # 主力 Python 版本
│   ├── collect.py           # 数据采集（Playwright + 并发）
│   ├── analyze.py           # AI 分析主流程
│   ├── clarify.py           # 需求调研员（初始化阶段）
│   ├── generate_analysis.py # 分析框架生成（初始化阶段）
│   ├── fact_check.py        # 事实核查
│   ├── data_prep.py         # 数据预处理
│   ├── ai_client.py         # AI 统一调用封装
│   └── notify.py            # 飞书推送
├── configs/
│   ├── dashboards.yaml      # 仪表板注册表
│   ├── meta/                # 全局提示词（各角色通用）
│   └── {dashboard_id}/      # 仪表板专属配置
│       ├── cards.yaml       # 卡片元数据
│       ├── filters.yaml     # 筛选器配置
│       └── analysis_{id}.yaml  # 分析框架 + 分析师提示词
├── outputs/                 # 输出目录（不提交）
│   └── {dashboard_id}/
│       ├── manifest_{YYYYMMDD}.json
│       └── analysis_report_{YYYYMMDD}.md
├── nodejs/                  # Node.js 版本（已稳定备用）
├── .env.example             # 环境变量模板
└── CLAUDE.md                # Claude Code 项目指引
```

---

## 环境变量说明

所有凭证通过 `.env` 文件管理（参考 `.env.example`），**不提交到版本库**。

| 变量 | 说明 |
|---|---|
| `GY_ACCOUNT` / `GY_PASSWORD` | 观远 BI 登录凭证 |
| `AI_PROVIDER` | `gemini`（默认）/ `claude` / `azure` / `openai` |
| `GEMINI_API_KEY` | Google Gemini API Key |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API Key |
| `FEISHU_WEBHOOK` | 飞书机器人 Webhook URL |

---

## 技术栈

- **Python 3.11+**：主力版本
- **Playwright**：浏览器自动化登录
- **requests**：BI API 数据抓取（纯 HTTP，不依赖浏览器）
- **Gemini / Claude / Azure OpenAI**：AI 分析，支持流式输出
- **PyYAML / python-dotenv**：配置管理
