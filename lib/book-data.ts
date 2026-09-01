export type TxType = 'expense' | 'income';
export type Transaction = {
  id: string;
  type: TxType;
  amount: number;
  category: string;
  account: string;
  date: string;
  note: string;
};
export type Account = {
  id: string;
  name: string;
  type: string;
  opening: number;
};
export type Book = {
  transactions: Transaction[];
  accounts: Account[];
  budget: number;
};

function isValidDateKey(value: string) {
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

export function normalizeBook(value: unknown): Book | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as Partial<Book>;
  if (
    !Array.isArray(candidate.accounts) ||
    !Array.isArray(candidate.transactions)
  )
    return null;
  const accounts = candidate.accounts.filter((item): item is Account =>
    Boolean(
      item &&
      typeof item.id === 'string' &&
      item.id &&
      typeof item.name === 'string' &&
      item.name.trim() &&
      typeof item.type === 'string' &&
      Number.isFinite(item.opening),
    ),
  );
  if (accounts.length !== candidate.accounts.length || accounts.length === 0)
    return null;
  if (new Set(accounts.map((item) => item.name)).size !== accounts.length)
    return null;
  const accountNames = new Set(accounts.map((item) => item.name));
  const transactions = candidate.transactions.filter(
    (item): item is Transaction =>
      Boolean(
        item &&
        typeof item.id === 'string' &&
        item.id &&
        (item.type === 'expense' || item.type === 'income') &&
        Number.isFinite(item.amount) &&
        item.amount > 0 &&
        typeof item.category === 'string' &&
        item.category.trim() &&
        typeof item.account === 'string' &&
        accountNames.has(item.account) &&
        isValidDateKey(item.date) &&
        typeof item.note === 'string',
      ),
  );
  if (transactions.length !== candidate.transactions.length) return null;
  const budget = Number(candidate.budget);
  if (!Number.isFinite(budget) || budget <= 0) return null;
  return { accounts, transactions, budget };
}
