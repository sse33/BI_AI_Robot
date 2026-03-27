/**
 * analyze.mjs
 *
 * 读取 outputs/manifest_test.json，将各卡片数据转为 Markdown 表格，
 * 调用 AI API 进行日报分析，输出8节管理报告。
 *
 * 运行：node analyze.mjs
 * 切换模型：AI_PROVIDER=azure node analyze.mjs
 *           AI_PROVIDER=claude node analyze.mjs
 *           AI_PROVIDER=openai node analyze.mjs
 *
 * 支持的 AI_PROVIDER 值：
 *   claude  — Anthropic Claude（默认）
 *   azure   — Azure OpenAI
 *   openai  — OpenAI 官方
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// ── 加载 .env ─────────────────────────────────────────────────────────────────
const envPath = path.join(__dirname, '..', '.env');
if (fs.existsSync(envPath)) {
  for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
    const m = line.match(/^\s*([^#=\s]+)\s*=\s*(.*)\s*$/);
    if (m) process.env[m[1]] = m[2];
  }
}

// ── 数字格式化 ────────────────────────────────────────────────────────────────
function formatNum(v) {
  if (typeof v !== 'number') return v ?? '';
  if (v > 1000)                  return Math.round(v).toLocaleString();
  if (Number.isInteger(v))       return v;
  if (Math.abs(v) <= 1 + 1e-9)  return (v * 100).toFixed(1) + '%';
  return v.toFixed(2);
}

// ── 对象数组 → Markdown 表格 ──────────────────────────────────────────────────
function toMarkdownTable(records, colOrder) {
  if (!records || records.length === 0) return '（无数据）';
  const cols   = colOrder || Object.keys(records[0]);
  const header = `| ${cols.join(' | ')} |`;
  const sep    = `| ${cols.map(() => '---').join(' | ')} |`;
  const body   = records.map(r =>
    `| ${cols.map(c => formatNum(r[c] ?? '')).join(' | ')} |`
  ).join('\n');
  return [header, sep, body].join('\n');
}

// ── 读取数据 ──────────────────────────────────────────────────────────────────
const manifestPath = path.join(__dirname, 'outputs', 'manifest_test.json');
if (!fs.existsSync(manifestPath)) {
  console.error('未找到 outputs/manifest_test.json，请先运行 validate.mjs');
  process.exit(1);
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const { dailySalesOverview, skcTop10, salesTrend, categoryStructure, skcSellThrough } = manifest;

// ── 数据预计算：全量城市 + 全量波段×城市，保留完整分析视角 ──────────────────

function buildDataSummary({ dailySalesOverview, skcTop10, salesTrend, categoryStructure, skcSellThrough }) {
  const rows = dailySalesOverview.rows;

  function fmtPct(v) { return v == null ? '' : `(${(v * 100).toFixed(1)}%)`; }
  function fmtMoney(v) { return v > 1000 ? Math.round(v).toLocaleString() : (v?.toFixed(0) || 0); }
  function fmtD(v) { return (v && v > 0) ? `${(v * 100).toFixed(1)}折` : '-'; }
  function fmtR(v) { return (v != null && typeof v === 'number' && Math.abs(v) <= 1 + 1e-9) ? `${(v*100).toFixed(1)}%` : (v ?? ''); }

  // 1. 渠道汇总（含折扣加权均值）
  const channelSum = {};
  for (const r of rows) {
    const ch = r['渠道'];
    if (!ch) continue;
    if (!channelSum[ch]) channelSum[ch] = { 正价业绩: 0, 正价店数: 0, 正价折扣加权: 0, 奥莱业绩: 0, 奥莱店数: 0, 奥莱折扣加权: 0 };
    const s = channelSum[ch];
    s.正价业绩       += r['正价_业绩'] || 0;
    s.正价店数       += r['正价_店数'] || 0;
    s.正价折扣加权   += (r['正价_实销折扣'] || 0) * (r['正价_业绩'] || 0);
    s.奥莱业绩       += r['奥莱_业绩'] || 0;
    s.奥莱店数       += r['奥莱_店数'] || 0;
    s.奥莱折扣加权   += (r['奥莱_实销折扣'] || 0) * (r['奥莱_业绩'] || 0);
  }

  // 2. 全量城市明细（有正价或奥莱的行均输出，按渠道+正价店均降序）
  const cityRows = rows
    .filter(r => r['城市'] && r['渠道'])
    .map(r => ({
      渠道:     r['渠道'],
      城市:     r['城市'],
      正价业绩: r['正价_业绩'] || 0,
      正价店数: r['正价_店数'] || 0,
      正价店均: r['正价_店均业绩'] || 0,
      正价UPT:  r['正价_UPT'] || 0,
      正价客单: r['正价_客单价'] || 0,
      正价折扣: r['正价_实销折扣'] || 0,
      奥莱业绩: r['奥莱_业绩'] || 0,
      奥莱店数: r['奥莱_店数'] || 0,
      奥莱店均: r['奥莱_店均业绩'] || 0,
      奥莱UPT:  r['奥莱_UPT'] || 0,
      奥莱客单: r['奥莱_客单价'] || 0,
      奥莱折扣: r['奥莱_实销折扣'] || 0,
    }))
    .filter(r => r.正价店数 > 0 || r.奥莱店数 > 0)
    .sort((a, b) => b.正价店均 - a.正价店均);

  // 折扣异常（≤70%）
  const discountAlert = cityRows.filter(r => r.正价折扣 > 0 && r.正价折扣 <= 0.70);

  // 3. 运营中类结构（全量）
  const catRows   = categoryStructure.rows;
  const catCols   = categoryStructure.columns;

  // 4. 销售趋势（全量）
  const trendRows = salesTrend.rows;
  const trendCols = salesTrend.columns;

  // 5. TOP10 SKC（全列）
  const top10    = skcTop10.rows;
  const top10cols = skcTop10.columns;
  const t1Zero   = top10.filter(r => {
    const entry = Object.entries(r).find(([k]) => k.includes('T+1') && k.includes('销售'));
    return entry && (entry[1] === 0 || entry[1] === '0' || entry[1] === '' || entry[1] == null);
  });

  // 6. 近六波动销：全量城市×波段（保留每行每波段数据）
  const sellThroughCols  = skcSellThrough.columns;
  const waveBands = [...new Set(
    sellThroughCols
      .filter(c => c.includes('动销率'))
      .map(c => c.replace(/_动销率_.+/, ''))
  )];

  // ── 组装摘要文本 ──────────────────────────────────────────────────────────
  const lines = [];

  // 一、渠道汇总
  lines.push('【一、渠道汇总（含折扣加权均值）】');
  for (const [ch, s] of Object.entries(channelSum)) {
    const 正均  = s.正价店数 ? Math.round(s.正价业绩 / s.正价店数) : 0;
    const 奥均  = s.奥莱店数 ? Math.round(s.奥莱业绩 / s.奥莱店数) : 0;
    const 正折  = s.正价业绩 ? fmtD(s.正价折扣加权 / s.正价业绩) : '-';
    const 奥折  = s.奥莱业绩 ? fmtD(s.奥莱折扣加权 / s.奥莱业绩) : '-';
    lines.push(`${ch}: 正价${fmtMoney(s.正价业绩)}(${s.正价店数}店 均${fmtMoney(正均)} 折${正折}) 奥莱${fmtMoney(s.奥莱业绩)}(${s.奥莱店数}店 均${fmtMoney(奥均)} 折${奥折})`);
  }

  // 二、全量城市明细（正价+奥莱，按正价店均降序）
  lines.push('\n【二、城市明细（全量，正价店均降序）】');
  lines.push('渠道_城市 | 正价业绩 正价店数 正价店均 正价UPT 正价客单 正价折扣 | 奥莱业绩 奥莱店数 奥莱店均 奥莱UPT 奥莱客单 奥莱折扣');
  for (const r of cityRows) {
    const 正 = r.正价店数 > 0
      ? `正价${fmtMoney(r.正价业绩)}(${r.正价店数}店 均${fmtMoney(r.正价店均)} UPT${r.正价UPT?.toFixed(2)} 客单${fmtMoney(r.正价客单)} ${fmtD(r.正价折扣)})`
      : '正价-';
    const 奥 = r.奥莱店数 > 0
      ? `奥莱${fmtMoney(r.奥莱业绩)}(${r.奥莱店数}店 均${fmtMoney(r.奥莱店均)} UPT${r.奥莱UPT?.toFixed(2)} 客单${fmtMoney(r.奥莱客单)} ${fmtD(r.奥莱折扣)})`
      : '奥莱-';
    lines.push(`${r.渠道}_${r.城市}: ${正} ${奥}`);
  }

  // 三、折扣预警
  if (discountAlert.length) {
    lines.push('\n【三、折扣预警（正价实销折扣≤70%）⚠️】');
    for (const r of discountAlert) {
      lines.push(`${r.渠道}_${r.城市}: 实销折扣${fmtD(r.正价折扣)} 店均${fmtMoney(r.正价店均)} UPT${r.正价UPT?.toFixed(2)}`);
    }
  }

  // 四、运营中类结构（预算销售吊牌%-总进吊牌%差值，口径统一）
  lines.push('\n【四、运营中类结构（新/旧货 × 中类）】');
  lines.push('注：差值=销售吊牌%-总进吊牌%，正数=销售>库存（畅销），负数=销售<库存（滞销）');
  for (const r of catRows) {
    const sale = r['销售吊牌%'] ?? 0;
    const inv  = r['总进吊牌%'] ?? 0;
    const diff = (typeof sale === 'number' && typeof inv === 'number')
      ? `差值${((sale - inv) * 100).toFixed(1)}%`
      : '';
    lines.push(
      `${r['新/旧货']} ${r['运营中类']}: 销售吊牌%${fmtR(sale)} 总进吊牌%${fmtR(inv)} ${diff}`
    );
  }

  // 五、销售趋势（全量，加列说明避免混淆）
  lines.push('\n【五、销售趋势（新旧货结构）】');
  lines.push('注：扣券占比=该货型销售额占总销售比例；实销折损=该货型的实际折扣率。两者含义不同，勿混用。');
  for (const r of trendRows) {
    lines.push(trendCols.map(c => `${c}:${fmtR(r[c])}`).join(' '));
  }

  // 六、TOP10 SKC（过滤掉照片URL列）
  const top10colsFiltered = top10cols.filter(c => c !== '照片');
  lines.push('\n【六、TOP10 SKC】');
  for (const r of top10) {
    lines.push(top10colsFiltered.map(c => `${c}:${r[c] ?? ''}`).join(' '));
  }
  if (t1Zero.length) {
    lines.push(`⚠️ T+1销售=0的款: ${t1Zero.map(r => r[top10cols[0]] || '').join('、')}（共${t1Zero.length}款，疑似断码/曝光不足）`);
  }

  // 七、近六波动销：只传店铺动销率（比城市动销率更精准），避免两个维度混用
  lines.push('\n【七、近六波动销率（店铺维度，按波段降序）】');
  lines.push('注：此处动销率均为店铺维度（有动销店数/投放店数），勿与城市维度混用。');
  for (const wb of waveBands) {
    const shopCol = `${wb}_动销率_店铺`;
    const valid = skcSellThrough.rows
      .filter(r => r['城市'] && r[shopCol] != null)
      .sort((a, b) => (b[shopCol] || 0) - (a[shopCol] || 0));
    if (!valid.length) continue;
    const detail = valid.map(r => {
      const warn = (r[shopCol] || 0) < 0.05 ? '⚠️' : '';
      return `${warn}${r['城市']}${fmtPct(r[shopCol])}`;
    }).join(' | ');
    lines.push(`${wb}: ${detail}`);
  }

  return lines.join('\n');
}

// ── 构建数据文本 ───────────────────────────────────────────────────────────────
const dataText = buildDataSummary({ dailySalesOverview, skcTop10, salesTrend, categoryStructure, skcSellThrough });

// ── 提示词 ────────────────────────────────────────────────────────────────────
const systemPrompt = `你是赫基集团零售业务高级数据分析师。输出风格：数字密集、结论前置、每句话都有具体数值支撑，禁止泛泛而谈。引用数据时采用紧凑内嵌格式，如：自营广佛正价54,916（5店，店均10,983，UPT 3.04，客单1,961，折扣82.8%）。直接输出报告正文，不得有任何开场白、确认语或结束语。`;

const userPrompt = `以下是今日观远BI销售数据：

${dataText}

---
【分析前必须逐一核查，触发则在报告中明确体现】
• 折扣预警：正价实销折扣≤70%的城市逐一点名，给出折扣值+店均
• 断码预警：TOP10中T+1销售=0且店存消化率>40%的款，判定为断码/曝光不足，给出48h指令
• 动销红线：城市×波段店铺动销率<5%逐一列出，标注调拨来源城市→目的地
• 新旧货挤压：旧货吊牌占比 vs 旧货销售占比，点出差值说明去化压力
• 城市分级：正价店均<3,000→🔴，3,000-6,000→🟡，>6,000→🟢（结合UPT/折扣/动销综合判断）

【输出格式要求】
- 每节数字必须内嵌在叙述句中，格式如：城市名（店数店，店均X，UPT X.XX，客单X，折X折）
- 波段动销节必须列出每个波段下所有城市的具体动销率百分比，格式：城市A(X%)、城市B(X%)
- 执行动作必须含：[方向] 具体动作→时限→量化目标（含数字）
- 禁止使用"较高""偏低""有所"等无数字的模糊表述

请按以下八节输出日报：

一、核心结论（≤3条，每条一句话含关键数字，覆盖：整体量级、最大结构问题、最紧迫风险）

二、关键指标证据（8个，格式：【指标名】具体值→一句话含义）
必须含：正价/奥莱整体规模（业绩+店数+店均+UPT+客单+折扣）、最强/最弱城市对比、折扣异常城市、新旧货吊牌vs销售占比差、TOP3滞销中类（含吊牌%vs销售%差值）、TOP10断码状态、压力最大波段+最低城市动销率

三、结构诊断
1. 渠道：自营/托管/联营各自 业绩/店均/折扣，哪个渠道是正价主引擎/奥莱主引擎
2. 城市：最强2城（内嵌数据+原因）、最弱2城（内嵌数据+原因）、调拨承接候选
3. 品类：新旧货吊牌vs销售占比差值、TOP3畅销/滞销中类（含占比）、最危险波段

四、TOP10 SKC结论（波段/品类/价格带分布；断码款逐一给出48h补货或陈列核查指令）

五、近六波动销（每波段列出所有城市具体动销率；按南区/北区/中西部分区汇总；点名调拨出去的城市×波段→调拨目的地）

六、城市优先级
🔴红区（2-3城）：问题类型（动销/价盘/客单）+ 具体指标值
🟡黄区（2-3城）：观察重点 + 升红触发条件（含阈值）
🟢绿区（2-3城）：核心优势 + 是否可作调拨承接或打法模板

七、执行动作（4条，格式：[方向] 动作→时限→量化目标，覆盖：调拨补货/陈列连带/折扣管控/品类结构）

八、复盘指标（3个，Markdown表格：指标名|当前值|下次目标值|监控原因）`.trim();

// ── AI Provider 工厂 ──────────────────────────────────────────────────────────

const PROVIDER = (process.env.AI_PROVIDER || 'claude').toLowerCase();

async function runAnalysis() {
  let fullText = '';

  // ── Claude (Anthropic) ────────────────────────────────────────────────────
  if (PROVIDER === 'claude') {
    const { default: Anthropic } = await import('@anthropic-ai/sdk');
    const client = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const model  = process.env.CLAUDE_MODEL || 'claude-opus-4-6';

    console.log(`[Claude] 使用模型: ${model}\n`);

    const stream = client.messages.stream({
      model,
      max_tokens: 8000,
      thinking:   { type: 'adaptive' },
      system:     systemPrompt,
      messages:   [{ role: 'user', content: userPrompt }],
    });

    stream.on('text', delta => {
      process.stdout.write(delta);
      fullText += delta;
    });

    const msg = await stream.finalMessage();
    console.log(`\n\n[tokens] 输入 ${msg.usage.input_tokens}，输出 ${msg.usage.output_tokens}`);

  // ── Azure OpenAI（fetch）─────────────────────────────────────────────────
  } else if (PROVIDER === 'azure') {
    const endpoint   = process.env.AZURE_OPENAI_ENDPOINT;
    const apiKey     = process.env.AZURE_OPENAI_API_KEY;
    const deployment = process.env.AZURE_OPENAI_DEPLOYMENT || 'gpt-4o';
    const apiVersion = process.env.AZURE_OPENAI_API_VERSION || '2025-01-01-preview';
    const url        = `${endpoint}/openai/deployments/${deployment}/chat/completions?api-version=${apiVersion}`;

    console.log(`[Azure OpenAI] deployment: ${deployment}\n（等待响应，可能需要1-2分钟...）`);

    const resp = await fetch(url, {
      method:  'POST',
      headers: {
        'Content-Type': 'application/json',
        'api-key':      apiKey,
      },
      body: JSON.stringify({
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user',   content: userPrompt   },
        ],
      }),
    });

    if (!resp.ok) throw new Error(`Azure API 返回错误 ${resp.status}: ${await resp.text()}`);
    const json = await resp.json();
    fullText = json.choices[0].message.content ?? '';
    process.stdout.write(fullText);

  // ── OpenAI 官方 ───────────────────────────────────────────────────────────
  } else if (PROVIDER === 'openai') {
    const { default: OpenAI } = await import('openai');
    const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const model  = process.env.OPENAI_MODEL || 'gpt-4o';

    console.log(`[OpenAI] 使用模型: ${model}\n`);

    const stream = await client.chat.completions.create({
      model,
      stream:   true,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user',   content: userPrompt   },
      ],
    });

    for await (const chunk of stream) {
      const delta = chunk.choices[0]?.delta?.content ?? '';
      process.stdout.write(delta);
      fullText += delta;
    }

  // ── Google Gemini（流式，避免代理超时）────────────────────────────────────
  } else if (PROVIDER === 'gemini') {
    const apiKey = process.env.GEMINI_API_KEY;
    const model  = process.env.GEMINI_MODEL || 'gemini-2.5-pro';
    const url    = `https://generativelanguage.googleapis.com/v1beta/models/${model}:streamGenerateContent?alt=sse&key=${apiKey}`;

    console.log(`[Gemini] 使用模型: ${model}（流式输出）\n`);

    const resp = await fetch(url, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        systemInstruction: { parts: [{ text: systemPrompt }] },
        contents: [{ role: 'user', parts: [{ text: userPrompt }] }],
        generationConfig: { temperature: 0.3 },
      }),
    });

    if (!resp.ok) throw new Error(`Gemini API 返回错误 ${resp.status}: ${await resp.text()}`);

    // 解析 SSE 流
    const decoder = new TextDecoder();
    let   buf     = '';
    for await (const chunk of resp.body) {
      buf += decoder.decode(chunk, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop(); // 保留未完整的行
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (data === '[DONE]') continue;
        try {
          const json  = JSON.parse(data);
          const delta = json.candidates?.[0]?.content?.parts?.[0]?.text ?? '';
          if (delta) {
            process.stdout.write(delta);
            fullText += delta;
          }
        } catch { /* 忽略解析失败的行 */ }
      }
    }

  } else {
    console.error(`不支持的 AI_PROVIDER: "${PROVIDER}"，可选值：claude / azure / openai / gemini`);
    process.exit(1);
  }

  return fullText;
}

// ── 发送到飞书 ────────────────────────────────────────────────────────────────

async function sendToFeishu(text) {
  const webhookUrl = process.env.FEISHU_WEBHOOK;
  if (!webhookUrl) {
    console.log('[飞书] 未配置 FEISHU_WEBHOOK，跳过发送');
    return;
  }

  // 飞书单条消息限制约 4000 字，超长时分段发送
  const MAX_LEN = 3800;
  const chunks  = [];

  // 优先用 BI 看板真实标题，回退到日期
  const biTitle = manifest.dashboardTitle
    ? manifest.dashboardTitle.replace(/\s*[-–|].*$/, '').trim()  // 去掉" - 观远BI"之类的后缀
    : null;
  const today   = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric' });
  const header  = `📊 ${biTitle || 'BI 日报'}（${today}）\n${'─'.repeat(30)}\n`;
  let current  = header;

  for (const line of text.split('\n')) {
    if ((current + line + '\n').length > MAX_LEN) {
      chunks.push(current);
      current = '';
    }
    current += line + '\n';
  }
  if (current.trim()) chunks.push(current);

  console.log(`\n[飞书] 共 ${chunks.length} 段，开始发送...`);

  for (let i = 0; i < chunks.length; i++) {
    const suffix = chunks.length > 1 ? ` (${i + 1}/${chunks.length})` : '';
    const resp = await fetch(webhookUrl, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({
        msg_type: 'text',
        content:  { text: chunks[i] + suffix },
      }),
    });
    const result = await resp.json();
    if (result.code !== 0 && result.StatusCode !== 0) {
      console.warn(`[飞书] 第${i + 1}段发送失败:`, JSON.stringify(result));
    } else {
      console.log(`[飞书] 第${i + 1}段发送成功`);
    }
    // 段间稍作间隔，避免频率限制
    if (i < chunks.length - 1) await new Promise(r => setTimeout(r, 500));
  }
}

// ── 执行 ──────────────────────────────────────────────────────────────────────
console.log(`正在调用 AI（provider=${PROVIDER}）分析数据，请稍候...\n`);

const fullText = await runAnalysis();

const now      = new Date();
const stamp    = now.toISOString().replace(/[:.]/g, '-').slice(0, 19); // 2026-03-18T14-30-00
const outFile  = `analysis_report_${stamp}.md`;
const outPath  = path.join(__dirname, 'outputs', outFile);
fs.writeFileSync(outPath, fullText, 'utf8');
console.log(`\n✅ 分析报告已保存至 outputs/${outFile}`);

await sendToFeishu(fullText);
