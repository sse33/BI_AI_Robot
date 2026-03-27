# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Node.js 版本说明

ESM 脚本（`.mjs`），使用 Puppeteer 登录、`node-fetch`/`undici` 抓取数据，多 AI Provider 支持。

## 常用命令

```bash
npm install

node validate.mjs             # 登录 → 抓取全部卡片 → ../outputs/manifest_test.json
node screenshot_dashboard.mjs # 截图看板
node analyze.mjs              # AI 分析 → ../outputs/analysis_report_*.md → 飞书推送

# 切换 AI provider
AI_PROVIDER=claude node analyze.mjs
AI_PROVIDER=azure  node analyze.mjs
AI_PROVIDER=gemini node analyze.mjs   # 默认
```

## 文件职责

| 文件 | 职责 |
|---|---|
| `bi_card_fetcher_v2.mjs` | `GuanyuanClient`（cookie 认证）、`fetchDailyReport()`、`CARD_IDS` |
| `validate.mjs` | Puppeteer 登录 → 提取 cookie → 并发抓取 → 输出 JSON + 验证摘要 |
| `screenshot_dashboard.mjs` | Puppeteer 打开看板截图（全页 + 各卡片） |
| `analyze.mjs` | 读 manifest → `buildDataSummary()` → 调用 AI → 保存报告 → 推送飞书 |

## 关键注意事项

- `.env` 在上级目录（`../`），所有脚本用 `path.join(__dirname, '..', '.env')` 加载
- `outputs/` 也在上级目录（`../outputs/`）
- Puppeteer 使用系统 Chrome：`executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'`
- Gemini 必须用流式 SSE（`streamGenerateContent?alt=sse`），否则企业代理会超时断开
- `analyze.mjs` 中 `buildDataSummary()` 只传 `_动销率_店铺` 列给 LLM，不传城市维度
