import {
  AiTransactionError,
  classifyTransaction,
  type AiAccount,
} from '@/lib/ai-transaction';
import { env } from 'cloudflare:workers';

type AiEnv = {
  ZHIPU_API_KEY?: string;
  ZHIPU_API_BASE_URL?: string;
};

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      text?: unknown;
      accounts?: unknown;
      today?: unknown;
    };
    const aiEnv = env as AiEnv;
    const draft = await classifyTransaction({
      text: typeof body.text === 'string' ? body.text : '',
      accounts: Array.isArray(body.accounts)
        ? (body.accounts as AiAccount[])
        : [],
      today: typeof body.today === 'string' ? body.today : '',
      apiKey: aiEnv.ZHIPU_API_KEY ?? process.env.ZHIPU_API_KEY ?? '',
      endpoint: aiEnv.ZHIPU_API_BASE_URL ?? process.env.ZHIPU_API_BASE_URL,
    });
    return Response.json({ draft });
  } catch (error) {
    const status = error instanceof AiTransactionError ? error.status : 500;
    const message =
      error instanceof Error
        ? error.message
        : 'AI 记账暂时不可用，请稍后重试。';
    return Response.json({ error: message }, { status });
  }
}
