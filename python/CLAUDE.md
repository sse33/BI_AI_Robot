# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Python 版本说明

使用 `requests` 调用 BI 内部 API，`playwright` 仅用于登录获取 cookie，`python-dotenv` 加载环境变量，多 AI Provider 支持。

## 虚拟环境（必须使用，禁止修改全局 Python 环境）

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
deactivate
```

## 常用命令

```bash
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium       # 首次安装需要

# 数据采集
python collect.py                          # 采集所有 enabled=true 的仪表板
python collect.py --dashboard daily_sales  # 只采集指定仪表板

# 截图
python screenshot_dashboard.py

# AI 分析
python analyze.py                 # 验证 → AI 分析 → 事实核查 → 飞书推送
python analyze.py --no-feishu    # 跳过飞书推送（调试用）
python analyze.py --no-vision    # 跳过 Vision 截图核对（截图非当日时使用）

# 切换 AI provider（也可在 .env 中设置 AI_PROVIDER=）
AI_PROVIDER=claude python analyze.py
AI_PROVIDER=azure  python analyze.py
AI_PROVIDER=gemini python analyze.py   # 默认

# 元数据发现与提示词生成
python discover.py --dashboard daily_sales        # 发现仪表板卡片/筛选器 → cards.yaml / filters.yaml
python generate_analysis.py --dashboard daily_sales  # AI 生成分析框架 → analysis_{id}.yaml
python generate_prompt.py --dashboard daily_sales    # 渲染提示词 → configs/{id}/prompt_{id}.md
```

## 文件职责

| 文件 | 职责 |
|---|---|
| `bi_card_fetcher.py` | `GuanyuanClient`（cookie 认证）、`fetch_all_rows()`，纯 `requests`，不依赖 Playwright |
| `collect.py` | Playwright 登录 → 提取 cookie → 并发采集所有卡片 → `outputs/{dashboard_id}/manifest_{YYYYMMDD}.json` |
| `discover.py` | 调用页面 API 发现卡片/筛选器元数据 → `configs/{id}/cards.yaml` + `filters.yaml` |
| `generate_analysis.py` | 读 cards.yaml → AI 推断分析意图 → `analysis_{id}.yaml`（analysis_context + sections） |
| `generate_prompt.py` | 读 analysis yaml → 渲染 → `configs/{id}/prompt_{id}.md` |
| `analyze.py` | 编排主流程：验证 → AI 分析 → 事实核查 → 飞书推送 |
| `data_prep.py` | 按 analysis yaml 的 data_prep 规则预处理 manifest，生成传给 LLM 的数据文本 |
| `validate_data.py` | manifest 结构/时效校验（`validate_manifest`）+ Vision 截图核对（`vision_verify`） |
| `ai_client.py` | 统一 AI 调用封装，支持 gemini/claude/azure/openai，流式/Vision/thinking，所有模块复用 |
| `fact_check.py` | Citations 模式核查报告数字（主）+ 正则模式降级（`fact_check_report`、`write_factcheck_log`） |
| `notify.py` | 飞书 Webhook 推送（`send_to_feishu`） |
| `screenshot_dashboard.py` | Playwright 打开看板截图（全页 + 各卡片） |
| `validate.py` | 旧版 Playwright 登录+抓取脚本，输出 `manifest_test.json`，兼容保留 |

## 目录结构

```
BI_AI_Robot/
├── python/                  # 主力 Python 版本
├── configs/
│   ├── dashboards.yaml      # 所有仪表板注册表（enabled/id/name）
│   ├── meta/
│   │   ├── generate_analysis_prompt.yaml  # 架构师角色提示词（章节生成逻辑，全局通用）
│   │   └── citations_prompt.yaml          # 数据核对员提示词（citations 格式与规则，全局通用）
│   └── {dashboard_id}/
│       ├── cards.yaml       # 卡片元数据（cd_id、key、collect_strategy、validate 规则）
│       ├── filters.yaml     # 筛选器元数据（known_values、linked_cards、split_collect）
│       ├── analysis_{id}.yaml   # 分析框架（analysis_context + sections + prompts）
│       └── prompt_{id}.md   # 渲染后的完整提示词（SYSTEM + USER 模板）
├── outputs/
│   └── {dashboard_id}/
│       └── manifest_{YYYYMMDD}.json
└── .env                     # 共享环境变量
```

## 系统角色与分析流程

系统由三个角色和一条数据流水线构成：

### 角色一：BI 数据分析架构师（一次性配置）
读懂仪表板元数据，规划分析结构——章节划分、数据压缩方式、预警规则。
输出的是框架设计，不是业务报告。
提示词：`configs/meta/generate_analysis_prompt.yaml`（全局通用）

```
cards.yaml
    ↓ [架构师] generate_analysis.py
analysis_{id}.yaml（analysis_context + sections）
    ↓ [架构师] generate_prompt.py
prompt_{id}.md（可追溯的完整提示词，含 SYSTEM + USER 模板）
```

### 角色二：零售业务高级数据分析师（每日运行）
基于当日真实数据，按框架生成管理层可用的日报。输出有具体数字和结论的业务报告。
提示词：`configs/{dashboard_id}/analysis_{id}.yaml` → `prompts` 块（仪表板特定，手工维护）

```
manifest_{YYYYMMDD}.json
    ↓ data_prep.py（按 analysis yaml 的 data_prep 规则压缩数据）
数据文本（注入 USER PROMPT）
    ↓ [高级分析师] AI（Gemini / Claude / Azure）
analysis_report_{YYYYMMDD}.md + [CITATIONS] JSON
```

### 角色三：数据核对员（每日运行，随报告自动触发）
对照 manifest 源数据，逐条核查报告中引用的数字，检测幻觉。纯 Python，不调用 AI。
提示词（注入给分析师，指导其生成 citations）：`configs/meta/citations_prompt.yaml`（全局通用）

```
[CITATIONS] JSON（由高级分析师在生成报告时同步输出）
    ↓ fact_check.py（card key + row filter + field 三层定位，1.5% 容差）
factcheck_{stamp}.md（核查报告）
    ↓ notify.py
飞书推送
```

### 职责边界
- **架构师**：决定"分析什么、怎么组织数据"——仪表板结构变化时重跑
- **高级分析师**：决定"怎么写报告、什么风格"——每日自动运行，prompts 块只能手工维护
- **数据核对员**：决定"数字是否准确"——随分析师报告自动触发，citations_prompt 全局通用
- **提示词分层**：全局通用放 `configs/meta/`，仪表板特定放 `configs/{dashboard_id}/`

## 关键注意事项

- `.env` 在上级目录（`../`），所有脚本用 `load_dotenv(Path(__file__).parent.parent / ".env")` 加载
- `outputs/` 也在上级目录（`ROOT_DIR / "outputs"`）
- Playwright 仅用于登录：`collect.py` 的 `playwright_login()` 和 `screenshot_dashboard.py`
- `bi_card_fetcher.py` 只依赖 `requests`，接收 cookie 字符串即可工作
- Gemini 用 `requests` 流式（`stream=True`）+ `iter_content` 解析 SSE，避免企业代理超时
- `collect.py` 是异步的（`asyncio.run(main())`），`analyze.py` 是同步的
- `data_prep.py` 由 analysis yaml 的 `data_prep` 规则驱动，不硬编码字段名；section header 格式为 `标签 (card=key)`，供 AI 在 citations 中写入正确 key
- `validate_data.py` 校验规则从 `cards.yaml` 的 `validate` 块动态读取（min_rows / required_cols / summary_row / vision），不硬编码
- `fact_check.py` citations 模式：row filter 匹配到多行时标为"无法核实"而非误判，避免聚合数字核查误报
- 所有模块通过 `ai_client.py` 的 `call_ai()` 调用 AI，大请求必须用 `stream=True` 避免企业代理超时
