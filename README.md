# BI AI Robot

> 对 Legacy BI 系统进行反向工程，提取分析框架与业务语义，赋能 AI 驱动的智能数据报告。

---

## 核心理念

传统 BI 工具（如观远 BI）积累了大量仪表板和报表，但这些分析资产往往：
- 分散在不同看板，缺乏统一治理
- 卡片命名技术化、重复，业务人员难以理解
- 无法自动生成可解读的管理层报告

**BI AI Robot** 的思路是：将 Legacy BI 系统作为数据源进行反向工程——通过 API 提取卡片元数据和实时数据，由 AI 推断分析意图、构建分析框架，最终生成有具体数字和结论的管理层日报，并自动推送飞书。

同时，这套工具也是一个 **BI 治理工具**：通过系统化盘点仪表板的卡片结构，可以发现重复指标、识别语义模糊的卡片、梳理分析体系的混乱之处，为整个组织的数据分析能力升级提供依据。

---

## 能做什么

| 能力 | 说明 |
|---|---|
| **仪表板元数据采集** | 通过 API 自动发现仪表板中的所有卡片、字段和筛选器 |
| **业务语义澄清** | AI 识别命名模糊的卡片，交互式向业务方确认真实用途 |
| **分析框架推断** | AI 读懂数据结构，自动设计章节划分、预警规则和数据压缩方式 |
| **每日 AI 分析报告** | 基于实时数据生成结论前置、数字密集的管理层日报 |
| **事实核查** | 对照源数据逐条验证报告中的每个数字，检测 AI 幻觉 |
| **飞书推送** | 报告生成后自动推送到飞书群 |
| **BI 治理** | 盘点重复卡片、语义模糊指标，为分析体系优化提供结构化输入 |

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
# 编辑 .env，填入 BI 系统地址、账号密码、AI API Key、飞书 Webhook
```

`.env` 中的关键变量：

```ini
GY_BASE_URL=https://your-bi-domain.com        # 观远 BI 部署地址
GY_ACCOUNT=your_account                        # 登录工号
GY_PASSWORD=your_password                      # 登录密码
GY_DASHBOARD_URL=https://your-bi-domain.com/home/web-app/YOUR_PAGE_ID

AI_PROVIDER=gemini                             # gemini / claude / azure / openai
GEMINI_API_KEY=your_api_key
FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_WEBHOOK_ID
```

### 3. 新仪表板初始化（一次性）

```bash
source .venv/bin/activate

python discover.py --dashboard daily_sales      # 发现卡片结构 → cards.yaml
python clarify.py --dashboard daily_sales       # 澄清语义模糊卡片 → 补全 business_description
python generate_analysis.py --dashboard daily_sales  # AI 推断分析框架 → analysis_{id}.yaml
```

### 4. 每日运行

```bash
python collect.py                              # 采集数据 → manifest_{YYYYMMDD}.json
python analyze.py                              # AI 分析 → 报告 → 事实核查 → 飞书推送
python analyze.py --analysis store             # 门店粒度变体
python analyze.py --no-feishu                  # 调试时跳过飞书
```

---

## 系统架构

```
观远 BI API
    ↓ collect.py（Playwright 登录 + 并发抓取）
manifest_{YYYYMMDD}.json（结构化卡片数据）
    ↓ analyze.py（data_prep.py 按规则压缩数据）
数据文本 → AI（Gemini / Claude / Azure）
    ↓ 流式输出
analysis_report_{YYYYMMDD}.md + [CITATIONS] JSON
    ↓ fact_check.py（对照源数据逐条核查）
factcheck_{stamp}.md → notify.py → 飞书
```

---

## 四角色架构

系统模拟四个协作角色，职责清晰分离：

| 角色 | 脚本 | 运行时机 | 职责 |
|---|---|---|---|
| 需求调研员 | `clarify.py` | 初始化一次 | 识别语义模糊卡片，与业务方确认真实含义 |
| 分析架构师 | `generate_analysis.py` | 初始化/结构变化时 | 读懂数据结构，设计分析框架 |
| 数据分析师 | `analyze.py` | 每日自动 | 基于实时数据生成管理层日报 |
| 数据核对员 | `fact_check.py` | 每日自动 | 核查报告每个数字，检测幻觉 |

**关键设计**：架构师负责"分析什么"，分析师负责"怎么写"，两者分离——仪表板结构变化时重跑架构师，分析风格调整只需手工编辑 `analysis_{id}.yaml` 中的 `prompts` 块。

---

## 目录结构

```
BI_AI_Robot/
├── python/                     # 主力 Python 版本
│   ├── collect.py              # 数据采集
│   ├── analyze.py              # AI 分析主流程
│   ├── clarify.py              # 需求调研员
│   ├── generate_analysis.py    # 分析架构师
│   ├── fact_check.py           # 事实核查
│   ├── data_prep.py            # 数据预处理
│   ├── ai_client.py            # AI 统一调用（多 provider）
│   └── notify.py               # 飞书推送
├── configs/
│   ├── dashboards.yaml         # 仪表板注册表（填入你的 BI 实例信息）
│   ├── meta/                   # 全局提示词（各角色通用）
│   └── {dashboard_id}/
│       ├── cards.yaml          # 卡片元数据 + 业务描述
│       ├── filters.yaml        # 筛选器配置
│       └── analysis_{id}.yaml  # 分析框架 + 分析师提示词
├── outputs/                    # 输出（gitignored）
│   └── {dashboard_id}/
│       ├── manifest_{YYYYMMDD}.json
│       └── analysis_report_{YYYYMMDD}.md
├── .env.example                # 环境变量模板
└── CLAUDE.md                   # Claude Code 项目指引
```

---

## 技术栈

- **Python 3.11+**
- **Playwright** — 浏览器自动化登录（仅用于获取 cookie）
- **requests** — BI API 数据抓取
- **Gemini / Claude / Azure OpenAI** — AI 分析，支持流式输出
- **PyYAML / python-dotenv** — 配置管理
