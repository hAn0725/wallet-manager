import type { Account, Transaction, TxType } from './book-data';

export const EXPENSE_CATEGORIES = [
  '餐饮',
  '交通',
  '学习',
  '购物',
  '娱乐',
  '住房',
  '医疗',
  '其他',
] as const;
export const INCOME_CATEGORIES = [
  '生活费',
  '兼职',
  '奖学金',
  '报销',
  '其他收入',
] as const;

export type AiTransactionDraft = Omit<Transaction, 'id'>;
export type AiAccount = Pick<Account, 'name' | 'type'>;

type CompletionResponse = {
  choices?: Array<{ message?: { content?: string } }>;
  error?: { message?: string };
};

export class AiTransactionError extends Error {
  readonly status: number;

  constructor(message: string, status = 500) {
    super(message);
    this.status = status;
  }
}

function isDateKey(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const [, year, month, day] = match.map(Number);
  const date = new Date(year, month - 1, day);
  return (
    date.getFullYear() === year &&
    date.getMonth() === month - 1 &&
    date.getDate() === day
  );
}

function parseJsonContent(content: string): unknown {
  const trimmed = content.trim();
  const withoutFence = trimmed
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```$/, '');
  try {
    return JSON.parse(withoutFence);
  } catch {
    throw new AiTransactionError(
      'AI 返回的记账信息格式不正确，请换一种说法重试。',
      502,
    );
  }
}

function normalizeType(value: unknown): TxType | null {
  if (value === 'expense' || value === '支出') return 'expense';
  if (value === 'income' || value === '收入') return 'income';
  return null;
}

function normalizeAmount(value: unknown): number {
  if (typeof value === 'number') return value;
  if (
    typeof value === 'string' &&
    /^\s*[¥￥]?\s*\d+(?:\.\d{1,2})?\s*(?:元)?\s*$/.test(value)
  ) {
    return Number(value.replace(/[¥￥元\s]/g, ''));
  }
  return Number.NaN;
}

export function normalizeAiTransaction(
  value: unknown,
  accounts: AiAccount[],
): AiTransactionDraft {
  if (!value || typeof value !== 'object') {
    throw new AiTransactionError(
      'AI 没有识别出有效账目，请补充金额和用途。',
      422,
    );
  }
  const candidate = value as Partial<AiTransactionDraft>;
  const type = normalizeType(candidate.type);
  const amount = normalizeAmount(candidate.amount);
  const categories = type === 'income' ? INCOME_CATEGORIES : EXPENSE_CATEGORIES;
  const accountNames = new Set(accounts.map((account) => account.name));

  if (
    !type ||
    !Number.isFinite(amount) ||
    amount <= 0 ||
    amount > 100_000_000
  ) {
    throw new AiTransactionError(
      'AI 没有识别出有效金额或收支类型，请补充后重试。',
      422,
    );
  }
  if (
    typeof candidate.category !== 'string' ||
    !(categories as readonly string[]).includes(candidate.category)
  ) {
    throw new AiTransactionError('AI 返回了不支持的分类，请重试。', 502);
  }
  if (
    typeof candidate.account !== 'string' ||
    !accountNames.has(candidate.account)
  ) {
    throw new AiTransactionError(
      'AI 未能匹配现有账户，请在描述中注明账户。',
      422,
    );
  }
  if (!isDateKey(candidate.date)) {
    throw new AiTransactionError('AI 返回的日期无效，请重试。', 502);
  }

  const note =
    typeof candidate.note === 'string' && candidate.note.trim()
      ? candidate.note.trim().slice(0, 100)
      : candidate.category;
  return {
    type,
    amount: Math.round(amount * 100) / 100,
    category: candidate.category,
    account: candidate.account,
    date: candidate.date,
    note,
  };
}

export async function classifyTransaction(options: {
  text: string;
  accounts: AiAccount[];
  today: string;
  apiKey: string;
  endpoint?: string;
  fetcher?: typeof fetch;
}): Promise<AiTransactionDraft> {
  const text = options.text.trim();
  if (!text || text.length > 2_000) {
    throw new AiTransactionError('请输入 1 到 2000 个字符的账目信息。', 400);
  }
  if (!options.accounts.length || options.accounts.length > 50) {
    throw new AiTransactionError('账户信息无效。', 400);
  }
  if (!isDateKey(options.today)) {
    throw new AiTransactionError('当前日期无效。', 400);
  }
  if (!options.apiKey) {
    throw new AiTransactionError(
      '尚未配置智谱 API Key，请先查看 README 完成设置。',
      503,
    );
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25_000);
  let response: Response;
  try {
    response = await (options.fetcher ?? fetch)(
      options.endpoint ??
        'https://open.bigmodel.cn/api/paas/v4/chat/completions',
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${options.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: 'glm-4.7-flash',
          messages: [
            {
              role: 'system',
              content:
                '你是个人记账分类器。只返回一个 JSON 对象，不要解释、不要添加 Markdown。必须包含且只能包含 type、amount、category、account、date、note 六个字段，例如：{"type":"expense","amount":18.5,"category":"餐饮","account":"微信钱包","date":"2026-09-07","note":"学校食堂午饭"}。type 只能是英文 expense 或 income，amount 只能是数字；支出 category 只能是：' +
                `${EXPENSE_CATEGORIES.join('、')}；收入 category 只能是：${INCOME_CATEGORIES.join('、')}。` +
                'amount 必须是正数；account 必须从给定账户中选择；date 使用 YYYY-MM-DD；note 简短概括用途。信息未明确时，结合语义选择最合理值，未提账户时使用第一个账户，未提日期时使用今天。',
            },
            {
              role: 'user',
              content: JSON.stringify({
                text,
                today: options.today,
                accounts: options.accounts.map(({ name, type }) => ({
                  name,
                  type,
                })),
              }),
            },
          ],
          thinking: { type: 'disabled' },
          temperature: 0.1,
          max_tokens: 300,
          response_format: { type: 'json_object' },
        }),
        signal: controller.signal,
      },
    );
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new AiTransactionError('AI 响应超时，请稍后重试。', 504);
    }
    throw new AiTransactionError(
      '暂时无法连接智谱 AI，请检查网络后重试。',
      502,
    );
  } finally {
    clearTimeout(timer);
  }

  let body: CompletionResponse;
  try {
    body = (await response.json()) as CompletionResponse;
  } catch {
    throw new AiTransactionError('智谱 AI 返回了无法读取的响应。', 502);
  }
  if (!response.ok) {
    const detail = body.error?.message?.trim();
    throw new AiTransactionError(
      detail
        ? `智谱 AI 请求失败：${detail}`
        : '智谱 AI 请求失败，请检查 API Key。',
      response.status === 401 ? 401 : 502,
    );
  }
  const content = body.choices?.[0]?.message?.content;
  if (!content) {
    throw new AiTransactionError('智谱 AI 没有返回记账结果，请重试。', 502);
  }
  return normalizeAiTransaction(parseJsonContent(content), options.accounts);
}
