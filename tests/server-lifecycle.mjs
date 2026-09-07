import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createServer } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const serverPath = path.join(projectRoot, 'scripts', 'desktop-server.mjs');
const port = 32146;
const aiPort = 32147;
const baseUrl = `http://127.0.0.1:${port}`;
let aiRequest;
const aiServer = createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  aiRequest = {
    headers: request.headers,
    body: JSON.parse(Buffer.concat(chunks).toString('utf8')),
  };
  response.writeHead(200, { 'content-type': 'application/json' }).end(
    JSON.stringify({
      choices: [
        {
          message: {
            content: JSON.stringify({
              type: 'expense',
              amount: 18.5,
              category: '餐饮',
              account: '微信钱包',
              date: '2026-09-07',
              note: '学校食堂',
            }),
          },
        },
      ],
    }),
  );
});
await new Promise((resolve) => aiServer.listen(aiPort, '127.0.0.1', resolve));
const env = {
  ...process.env,
  XIAOZHANGBEN_NO_OPEN: '1',
  XIAOZHANGBEN_PORT: String(port),
  ZHIPU_API_KEY: 'test-key',
  ZHIPU_API_BASE_URL: `http://127.0.0.1:${aiPort}`,
};

function startServer() {
  return spawn(process.execPath, [serverPath], {
    cwd: projectRoot,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
}

async function waitForServer(timeout = 8_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/api/health`);
      if (response.ok) return response;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error('本地服务未在预期时间内启动');
}

function waitForExit(child, timeout = 8_000) {
  return new Promise((resolve, reject) => {
    if (child.exitCode !== null) return resolve(child.exitCode);
    const timer = setTimeout(
      () => reject(new Error('本地服务未在预期时间内退出')),
      timeout,
    );
    child.once('exit', (code) => {
      clearTimeout(timer);
      resolve(code);
    });
  });
}

const primary = startServer();
try {
  const health = await waitForServer();
  assert.deepEqual(await health.json(), { ok: true, app: 'xiaozhangben' });

  const page = await fetch(`${baseUrl}/`);
  assert.equal(page.status, 200);
  assert.match(page.headers.get('content-type') || '', /^text\/html/);
  assert.match(await page.text(), /<div id="root"><\/div>/);

  const heartbeat = await fetch(`${baseUrl}/api/heartbeat`, { method: 'POST' });
  assert.equal(heartbeat.status, 204);

  const ai = await fetch(`${baseUrl}/api/ai/parse`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      text: '学校食堂午饭18.5元，微信支付',
      today: '2026-09-07',
      accounts: [
        { id: 'wechat', name: '微信钱包', type: '电子钱包', opening: 100 },
      ],
    }),
  });
  assert.equal(ai.status, 200);
  assert.deepEqual((await ai.json()).draft, {
    type: 'expense',
    amount: 18.5,
    category: '餐饮',
    account: '微信钱包',
    date: '2026-09-07',
    note: '学校食堂',
  });
  assert.equal(aiRequest.headers.authorization, 'Bearer test-key');
  assert.equal(aiRequest.body.model, 'glm-5.3-flash');
  assert.equal(aiRequest.body.thinking.type, 'enabled');
  assert.equal(aiRequest.body.reasoning_effort, 'high');
  assert.equal(aiRequest.body.messages[1].content.includes('opening'), false);

  const duplicate = startServer();
  assert.equal(await waitForExit(duplicate, 4_000), 0);
  assert.equal((await fetch(`${baseUrl}/api/health`)).status, 200);

  const goodbye = await fetch(`${baseUrl}/api/bye`, { method: 'POST' });
  assert.equal(goodbye.status, 204);
  assert.equal(await waitForExit(primary), 0);

  await assert.rejects(fetch(`${baseUrl}/api/health`), /fetch failed/);
  console.log('桌面服务启动、重复启动、静态页面、心跳与自动退出验证通过');
} finally {
  if (primary.exitCode === null) primary.kill();
  aiServer.close();
}
