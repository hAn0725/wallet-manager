import assert from 'node:assert/strict';
import {
  AiTransactionError,
  classifyTransaction,
  normalizeAiTransaction,
} from '../lib/ai-transaction.ts';

const accounts = [
  { id: 'wechat', name: '微信钱包', type: '电子钱包', opening: 100 },
  { id: 'card', name: '银行卡', type: '储蓄卡', opening: 500 },
];
const expected = {
  type: 'expense',
  amount: 18.5,
  category: '餐饮',
  account: '微信钱包',
  date: '2026-09-07',
  note: '学校食堂午饭',
};

assert.deepEqual(normalizeAiTransaction(expected, accounts), expected);
assert.deepEqual(
  normalizeAiTransaction(
    { ...expected, type: '支出', amount: '￥18.50元' },
    accounts,
  ),
  expected,
);
assert.throws(
  () => normalizeAiTransaction({ ...expected, category: '随便' }, accounts),
  AiTransactionError,
);
assert.throws(
  () => normalizeAiTransaction({ ...expected, account: '不存在' }, accounts),
  AiTransactionError,
);

let outbound;
const draft = await classifyTransaction({
  text: '今天学校食堂午饭，微信付了18.5元',
  accounts,
  today: '2026-09-07',
  apiKey: 'test-key',
  endpoint: 'https://example.test/chat/completions',
  fetcher: async (url, init) => {
    outbound = { url, init };
    return new Response(
      JSON.stringify({
        choices: [
          {
            message: {
              content: `\`\`\`json\n${JSON.stringify(expected)}\n\`\`\``,
            },
          },
        ],
      }),
      { status: 200, headers: { 'content-type': 'application/json' } },
    );
  },
});

assert.deepEqual(draft, expected);
assert.equal(outbound.url, 'https://example.test/chat/completions');
assert.equal(outbound.init.headers.Authorization, 'Bearer test-key');
const requestBody = JSON.parse(outbound.init.body);
assert.equal(requestBody.model, 'glm-5.3-flash');
assert.equal(requestBody.thinking.type, 'enabled');
assert.equal(requestBody.reasoning_effort, 'high');
assert.equal(requestBody.response_format.type, 'json_object');
assert.doesNotMatch(requestBody.messages[1].content, /opening/);

console.log('AI 请求、结构化响应与账目安全校验通过');
