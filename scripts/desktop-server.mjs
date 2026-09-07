import { createServer } from 'node:http';
import { exec } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { loadEnvFile } from 'node:process';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
for (const envFile of ['.dev.vars', '.env.local']) {
  try {
    loadEnvFile(path.join(projectRoot, envFile));
  } catch (error) {
    if (error?.code !== 'ENOENT')
      console.error(`Unable to read ${envFile}`, error);
  }
}
const siteRoot = path.join(projectRoot, 'desktop-dist');
const host = '127.0.0.1';
const configuredPort = Number(process.env.XIAOZHANGBEN_PORT || 32145);
const port =
  Number.isInteger(configuredPort) &&
  configuredPort > 0 &&
  configuredPort <= 65535
    ? configuredPort
    : 32145;
const appUrl = `http://localhost:${port}`;
const healthUrl = `http://${host}:${port}`;
const heartbeatTimeout = 100_000;
const firstHeartbeatTimeout = 120_000;
const closeGrace = 4_000;
const startedAt = Date.now();
let lastHeartbeat = 0;
let closeTimer;
const expenseCategories = [
  '餐饮',
  '交通',
  '学习',
  '购物',
  '娱乐',
  '住房',
  '医疗',
  '其他',
];
const incomeCategories = ['生活费', '兼职', '奖学金', '报销', '其他收入'];

const mimeTypes = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.json': 'application/json; charset=utf-8',
};

function openAppWindow() {
  if (
    process.env.XIAOZHANGBEN_NO_OPEN === '1' ||
    process.argv.includes('--no-open')
  )
    return;
  exec(`start "" "${appUrl}"`, { windowsHide: true });
}

async function alreadyRunning() {
  try {
    const response = await fetch(`${healthUrl}/api/health`, {
      signal: AbortSignal.timeout(900),
    });
    if (!response.ok) return false;
    const data = await response.json();
    return data?.app === 'xiaozhangben';
  } catch {
    return false;
  }
}

async function readJson(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 32_000) throw new Error('请求内容过长');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

function sendJson(response, status, value) {
  response.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
  });
  response.end(JSON.stringify(value));
}

function validDate(value) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    return false;
  const [year, month, day] = value.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  return (
    date.getFullYear() === year &&
    date.getMonth() === month - 1 &&
    date.getDate() === day
  );
}

function normalizeType(value) {
  if (value === 'expense' || value === '支出') return 'expense';
  if (value === 'income' || value === '收入') return 'income';
  return null;
}

function normalizeAmount(value) {
  if (typeof value === 'number') return value;
  if (
    typeof value === 'string' &&
    /^\s*[¥￥]?\s*\d+(?:\.\d{1,2})?\s*(?:元)?\s*$/.test(value)
  )
    return Number(value.replace(/[¥￥元\s]/g, ''));
  return Number.NaN;
}

function normalizeDraft(value, accounts) {
  if (!value || typeof value !== 'object')
    throw new Error('AI 没有识别出有效账目');
  const type = normalizeType(value.type);
  const amount = normalizeAmount(value.amount);
  const categories = type === 'income' ? incomeCategories : expenseCategories;
  if (!type || !Number.isFinite(amount) || amount <= 0 || amount > 100_000_000)
    throw new Error('AI 没有识别出有效金额或收支类型');
  if (!categories.includes(value.category))
    throw new Error('AI 返回了不支持的分类');
  if (!accounts.some((account) => account.name === value.account))
    throw new Error('AI 未能匹配现有账户');
  if (!validDate(value.date)) throw new Error('AI 返回的日期无效');
  return {
    type,
    amount: Math.round(amount * 100) / 100,
    category: value.category,
    account: value.account,
    date: value.date,
    note:
      typeof value.note === 'string' && value.note.trim()
        ? value.note.trim().slice(0, 100)
        : value.category,
  };
}

async function classifyWithAi(request, response) {
  let body;
  try {
    body = await readJson(request);
  } catch {
    sendJson(response, 400, { error: '请求格式不正确。' });
    return;
  }
  const text = typeof body.text === 'string' ? body.text.trim() : '';
  const accounts = Array.isArray(body.accounts)
    ? body.accounts.filter(
        (account) =>
          account &&
          typeof account.name === 'string' &&
          typeof account.type === 'string',
      )
    : [];
  if (
    !text ||
    text.length > 2_000 ||
    !accounts.length ||
    accounts.length > 50 ||
    !validDate(body.today)
  ) {
    sendJson(response, 400, { error: '请输入有效的账目信息。' });
    return;
  }
  const apiKey = process.env.ZHIPU_API_KEY || '';
  if (!apiKey) {
    sendJson(response, 503, {
      error: '尚未配置智谱 API Key，请先查看 README 完成设置。',
    });
    return;
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25_000);
  try {
    const aiResponse = await fetch(
      process.env.ZHIPU_API_BASE_URL ||
        'https://open.bigmodel.cn/api/paas/v4/chat/completions',
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: 'glm-5.3-flash',
          messages: [
            {
              role: 'system',
              content: `你是个人记账分类器。只返回一个 JSON 对象，不要解释、不要添加 Markdown。必须包含且只能包含 type、amount、category、account、date、note 六个字段，例如：{"type":"expense","amount":18.5,"category":"餐饮","account":"微信钱包","date":"2026-09-07","note":"学校食堂午饭"}。type 只能是英文 expense 或 income，amount 只能是数字；支出 category 只能是：${expenseCategories.join('、')}；收入 category 只能是：${incomeCategories.join('、')}。account 从给定账户选择；date 为 YYYY-MM-DD；note 简短概括。未提账户用第一个，未提日期用今天。`,
            },
            {
              role: 'user',
              content: JSON.stringify({
                text,
                today: body.today,
                accounts: accounts.map(({ name, type }) => ({ name, type })),
              }),
            },
          ],
          thinking: { type: 'enabled' },
          reasoning_effort: 'high',
          temperature: 0.1,
          max_tokens: 300,
          response_format: { type: 'json_object' },
        }),
        signal: controller.signal,
      },
    );
    const result = await aiResponse.json();
    if (!aiResponse.ok) {
      sendJson(response, aiResponse.status === 401 ? 401 : 502, {
        error: result?.error?.message
          ? `智谱 AI 请求失败：${result.error.message}`
          : '智谱 AI 请求失败，请检查 API Key。',
      });
      return;
    }
    const content = result?.choices?.[0]?.message?.content;
    if (!content) throw new Error('智谱 AI 没有返回记账结果');
    const value = JSON.parse(
      content
        .trim()
        .replace(/^```(?:json)?\s*/i, '')
        .replace(/\s*```$/, ''),
    );
    sendJson(response, 200, { draft: normalizeDraft(value, accounts) });
  } catch (error) {
    sendJson(response, error?.name === 'AbortError' ? 504 : 502, {
      error:
        error?.name === 'AbortError'
          ? 'AI 响应超时，请稍后重试。'
          : `${error?.message || 'AI 识别失败'}，请重试。`,
    });
  } finally {
    clearTimeout(timer);
  }
}

function stop() {
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1000).unref();
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url || '/', appUrl);
  if (request.method === 'POST' && url.pathname === '/api/heartbeat') {
    lastHeartbeat = Date.now();
    if (closeTimer) {
      clearTimeout(closeTimer);
      closeTimer = undefined;
    }
    response.writeHead(204).end();
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/bye') {
    response.writeHead(204).end();
    if (!closeTimer) closeTimer = setTimeout(stop, closeGrace);
    return;
  }
  if (request.method === 'GET' && url.pathname === '/api/health') {
    response
      .writeHead(200, { 'content-type': 'application/json' })
      .end('{"ok":true,"app":"xiaozhangben"}');
    return;
  }
  if (request.method === 'POST' && url.pathname === '/api/ai/parse') {
    await classifyWithAi(request, response);
    return;
  }
  if (request.method !== 'GET' && request.method !== 'HEAD') {
    response.writeHead(405).end();
    return;
  }

  let requested;
  try {
    requested =
      url.pathname === '/'
        ? 'index.html'
        : decodeURIComponent(url.pathname.slice(1));
  } catch {
    response.writeHead(400).end();
    return;
  }
  const filePath = path.resolve(siteRoot, requested);
  if (
    !filePath.startsWith(siteRoot + path.sep) &&
    filePath !== path.join(siteRoot, 'index.html')
  ) {
    response.writeHead(403).end();
    return;
  }
  try {
    const data = await readFile(filePath);
    response.writeHead(200, {
      'content-type':
        mimeTypes[path.extname(filePath)] || 'application/octet-stream',
      'cache-control': 'no-store',
    });
    response.end(request.method === 'HEAD' ? undefined : data);
  } catch {
    response.writeHead(404).end();
  }
});

if (await alreadyRunning()) {
  openAppWindow();
  process.exit(0);
}

server.listen(port, host, () => {
  server.ref();
  console.log(`Xiaozhangben ready at ${appUrl}`);
  openAppWindow();
});
server.on('error', (error) => {
  console.error(error);
  process.exit(1);
});

setInterval(() => {
  const now = Date.now();
  if (lastHeartbeat === 0 && now - startedAt > firstHeartbeatTimeout) stop();
  if (lastHeartbeat > 0 && now - lastHeartbeat > heartbeatTimeout) stop();
}, 5000);

process.on('SIGINT', stop);
process.on('SIGTERM', stop);
