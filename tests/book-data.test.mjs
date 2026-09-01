import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { normalizeBook } from "../lib/book-data.ts";

const testRoot = path.dirname(fileURLToPath(import.meta.url));
const valid = JSON.parse(await readFile(path.join(testRoot, "fixtures", "valid-book.json"), "utf8"));
const invalid = JSON.parse(await readFile(path.join(testRoot, "fixtures", "invalid-book.json"), "utf8"));

assert.deepEqual(normalizeBook(valid), valid);
assert.equal(normalizeBook(invalid), null);
assert.equal(normalizeBook({ ...valid, budget: -1 }), null);
assert.equal(normalizeBook({ ...valid, accounts: [] }), null);
assert.equal(normalizeBook({ ...valid, accounts: [...valid.accounts, { ...valid.accounts[0], id: "duplicate" }] }), null);
assert.equal(normalizeBook({ ...valid, transactions: [{ ...valid.transactions[0], amount: 0 }] }), null);
assert.equal(normalizeBook({ ...valid, transactions: [{ ...valid.transactions[0], account: "不存在" }] }), null);

console.log("账本备份格式、金额、账户关联与日期校验通过");
