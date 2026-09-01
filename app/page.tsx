"use client";

import { type SyntheticEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownLeft, ArrowUpRight, BarChart3, BookOpen, Download, Landmark, LayoutDashboard,
  Pencil, Plus, ReceiptText, Search, Settings, ShieldCheck, Target, Trash2, Upload,
  Utensils, WalletCards, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { normalizeBook, type Account, type Book, type Transaction, type TxType } from "@/lib/book-data";

type View = "dashboard" | "transactions" | "budget" | "reports" | "accounts" | "settings";

const expenseCategories = ["餐饮", "交通", "学习", "购物", "娱乐", "住房", "医疗", "其他"];
const incomeCategories = ["生活费", "兼职", "奖学金", "报销", "其他收入"];
const money = (value: number) => new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY" }).format(value);
const localDateKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const today = () => localDateKey(new Date());
const monthKey = (date = new Date()) => localDateKey(date).slice(0, 7);
const dateThisMonth = (daysAgo: number) => { const now = new Date(); return localDateKey(new Date(now.getFullYear(), now.getMonth(), Math.max(1, now.getDate() - daysAgo))); };
const uid = () => `${Date.now()}-${Math.random().toString(16).slice(2)}`;

const seedBook: Book = {
  budget: 3000,
  accounts: [
    { id: "cash", name: "现金", type: "现金", opening: 500 },
    { id: "wechat", name: "微信钱包", type: "电子钱包", opening: 1268.3 },
    { id: "card", name: "银行卡", type: "储蓄卡", opening: 5980 },
  ],
  transactions: [
    { id: "t1", type: "expense", amount: 18.5, category: "餐饮", account: "微信钱包", date: dateThisMonth(0), note: "校园食堂" },
    { id: "t2", type: "income", amount: 680, category: "兼职", account: "银行卡", date: dateThisMonth(1), note: "周末兼职" },
    { id: "t3", type: "expense", amount: 24, category: "学习", account: "微信钱包", date: dateThisMonth(2), note: "打印资料" },
    { id: "t4", type: "expense", amount: 56, category: "交通", account: "微信钱包", date: dateThisMonth(4), note: "地铁公交" },
    { id: "t5", type: "expense", amount: 129, category: "购物", account: "银行卡", date: dateThisMonth(6), note: "生活用品" },
    { id: "t6", type: "income", amount: 2600, category: "生活费", account: "银行卡", date: dateThisMonth(25), note: "本月生活费" },
    { id: "t7", type: "expense", amount: 420, category: "住房", account: "银行卡", date: dateThisMonth(22), note: "宿舍费用" },
    { id: "t8", type: "expense", amount: 198, category: "娱乐", account: "微信钱包", date: dateThisMonth(14), note: "周末聚会" },
  ],
};

const navItems: { id: View; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "dashboard", label: "总览", icon: LayoutDashboard }, { id: "transactions", label: "明细", icon: ReceiptText },
  { id: "budget", label: "预算", icon: Target }, { id: "reports", label: "报表", icon: BarChart3 }, { id: "accounts", label: "账户", icon: Landmark },
];

function loadBook(): Book {
  if (typeof window === "undefined") return seedBook;
  try { return normalizeBook(JSON.parse(localStorage.getItem("xiaozhangben-data-v1") || "null")) || seedBook; } catch { return seedBook; }
}

export default function Home() {
  const [book, setBook] = useState<Book>(seedBook);
  const [ready, setReady] = useState(false);
  const [view, setView] = useState<View>("dashboard");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | TxType>("all");
  const [toast, setToast] = useState("");
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => { queueMicrotask(() => { setBook(loadBook()); setReady(true); }); }, []);
  useEffect(() => { if (ready) localStorage.setItem("xiaozhangben-data-v1", JSON.stringify(book)); }, [book, ready]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(""), 2200); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => {
    if (window.location.protocol !== "http:") return;
    const heartbeat = () => fetch("/api/heartbeat", { method: "POST", keepalive: true }).catch(() => undefined);
    const goodbye = () => navigator.sendBeacon("/api/bye");
    void heartbeat();
    const timer = window.setInterval(() => { void heartbeat(); }, 4000);
    window.addEventListener("pagehide", goodbye);
    return () => { window.clearInterval(timer); window.removeEventListener("pagehide", goodbye); };
  }, []);

  const currentMonth = monthKey();
  const monthTx = useMemo(() => book.transactions.filter(t => t.date.startsWith(currentMonth)), [book.transactions, currentMonth]);
  const income = monthTx.filter(t => t.type === "income").reduce((sum, t) => sum + t.amount, 0);
  const expense = monthTx.filter(t => t.type === "expense").reduce((sum, t) => sum + t.amount, 0);
  const accountBalances = useMemo(() => book.accounts.map(account => ({ ...account, balance: account.opening + book.transactions.filter(t => t.account === account.name).reduce((sum, t) => sum + (t.type === "income" ? t.amount : -t.amount), 0) })), [book]);
  const balance = accountBalances.reduce((sum, a) => sum + a.balance, 0);
  const budgetLeft = book.budget - expense;
  const savingsRate = income ? Math.max(0, ((income - expense) / income) * 100) : 0;
  const categoryTotals = useMemo(() => expenseCategories.map(category => ({ category, value: monthTx.filter(t => t.type === "expense" && t.category === category).reduce((s, t) => s + t.amount, 0) })).filter(x => x.value > 0).sort((a, b) => b.value - a.value), [monthTx]);
  const maxCategory = Math.max(...categoryTotals.map(c => c.value), 1);
  const recent = [...book.transactions].sort((a, b) => b.date.localeCompare(a.date));
  const filtered = recent.filter(t => (filter === "all" || t.type === filter) && `${t.note}${t.category}${t.account}`.toLowerCase().includes(query.toLowerCase()));
  const lastSeven = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(); date.setDate(date.getDate() - (6 - index)); const key = localDateKey(date);
    return { label: ["日", "一", "二", "三", "四", "五", "六"][date.getDay()], value: book.transactions.filter(t => t.type === "expense" && t.date === key).reduce((s, t) => s + t.amount, 0) };
  });
  const chartMax = Math.max(...lastSeven.map(d => d.value), 1);

  const openCreate = () => { setEditing(null); setDialogOpen(true); };
  const openEdit = (tx: Transaction) => { setEditing(tx); setDialogOpen(true); };
  const saveTransaction = (tx: Transaction) => {
    setBook(old => ({ ...old, transactions: editing ? old.transactions.map(item => item.id === tx.id ? tx : item) : [tx, ...old.transactions] }));
    setDialogOpen(false); setToast(editing ? "记录已更新" : "记账成功");
  };
  const removeTransaction = (id: string) => { if (window.confirm("确定删除这条记录吗？")) { setBook(old => ({ ...old, transactions: old.transactions.filter(t => t.id !== id) })); setToast("记录已删除"); } };
  const exportData = () => {
    const blob = new Blob([JSON.stringify(book, null, 2)], { type: "application/json" }); const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `小账本备份-${today()}.json`; a.click(); URL.revokeObjectURL(url); setToast("备份已导出");
  };
  const importData = async (file?: File) => {
    if (!file) return;
    try { const data = normalizeBook(JSON.parse(await file.text())); if (!data) throw new Error(); setBook(data); setToast("账本已恢复"); }
    catch { setToast("文件格式不正确"); }
  };

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setView("dashboard")}><span className="brand-mark"><WalletCards size={20} /></span><span>小账本</span></button>
        <nav aria-label="主导航">{navItems.map(item => <button key={item.id} className={`nav-item ${view === item.id ? "active" : ""}`} onClick={() => setView(item.id)}><item.icon size={19} />{item.label}</button>)}</nav>
        <div className="privacy-note"><span className="privacy-dot" />数据仅保存在本机</div>
        <button className={`nav-item ${view === "settings" ? "active" : ""}`} onClick={() => setView("settings")}><Settings size={19} />设置</button>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div><p className="eyebrow">{new Date().toLocaleDateString("zh-CN", { year: "numeric", month: "long" })}</p><h1>{titleFor(view)}</h1></div>
          {view !== "settings" && <Button className="add-button" onClick={openCreate}><Plus size={17} />记一笔</Button>}
        </header>

        {view === "dashboard" && <Dashboard balance={balance} income={income} expense={expense} budget={book.budget} budgetLeft={budgetLeft} savingsRate={savingsRate} lastSeven={lastSeven} chartMax={chartMax} recent={recent.slice(0, 5)} onView={setView} onEdit={openEdit} />}
        {view === "transactions" && <TransactionsView items={filtered} query={query} setQuery={setQuery} filter={filter} setFilter={setFilter} onEdit={openEdit} onRemove={removeTransaction} />}
        {view === "budget" && <BudgetView budget={book.budget} expense={expense} totals={categoryTotals} max={maxCategory} onSave={(budget) => { if (!Number.isFinite(budget) || budget <= 0) { setToast("预算必须大于 0"); return; } setBook(old => ({ ...old, budget })); setToast("预算已保存"); }} />}
        {view === "reports" && <ReportsView income={income} expense={expense} totals={categoryTotals} max={maxCategory} />}
        {view === "accounts" && <AccountsView accounts={accountBalances} onAdd={(account) => { if (book.accounts.some(item => item.name === account.name)) { setToast("账户名称不能重复"); return false; } setBook(old => ({ ...old, accounts: [...old.accounts, account] })); setToast("账户已添加"); return true; }} onRemove={(id) => { const account = book.accounts.find(item => item.id === id); if (!account) return; if (book.accounts.length === 1) { setToast("至少需要保留一个账户"); return; } if (book.transactions.some(item => item.account === account.name)) { setToast("该账户已有交易，不能直接删除"); return; } if (window.confirm(`确定删除“${account.name}”吗？`)) setBook(old => ({ ...old, accounts: old.accounts.filter(item => item.id !== id) })); }} />}
        {view === "settings" && <SettingsView onExport={exportData} onImport={() => importRef.current?.click()} onReset={() => { if (window.confirm("确定恢复示例数据？当前账本会被覆盖。")) { setBook(seedBook); setToast("已恢复示例账本"); } }} />}
      </section>

      {dialogOpen && <TransactionDialog key={editing?.id || "new"} setOpen={setDialogOpen} editing={editing} accounts={book.accounts} onSave={saveTransaction} />}
      <input ref={importRef} type="file" accept="application/json" hidden onChange={e => { void importData(e.target.files?.[0]); e.currentTarget.value = ""; }} />
      {toast && <output className="toast">{toast}</output>}
    </main>
  );
}

function titleFor(view: View) { return ({ dashboard: "今天花了多少？", transactions: "收支明细", budget: "月度预算", reports: "财务报表", accounts: "我的账户", settings: "数据与设置" })[view]; }

function Dashboard({ balance, income, expense, budget, budgetLeft, savingsRate, lastSeven, chartMax, recent, onView, onEdit }: { balance: number; income: number; expense: number; budget: number; budgetLeft: number; savingsRate: number; lastSeven: {label:string;value:number}[]; chartMax:number; recent:Transaction[]; onView:(v:View)=>void; onEdit:(t:Transaction)=>void }) {
  const used = budget ? Math.min(100, (expense / budget) * 100) : 0;
  return <>
    <div className="summary-grid">
      <article className="balance-card"><div><p className="card-label">全部账户余额</p><strong>{money(balance)}</strong></div><div className="mini-flow"><span><ArrowDownLeft size={15} />本月收入 {money(income)}</span><span><ArrowUpRight size={15} />本月支出 {money(expense)}</span></div></article>
      <article className="metric-card"><p className="card-label">本月可用</p><strong className={budgetLeft < 0 ? "negative" : ""}>{money(budgetLeft)}</strong><span className="metric-hint">预算 {money(budget)}</span></article>
      <article className="metric-card"><p className="card-label">结余率</p><strong>{savingsRate.toFixed(1)}%</strong><span className="metric-hint positive">收入减去支出后的比例</span></article>
    </div>
    <div className="content-grid">
      <article className="panel spend-panel"><div className="panel-head"><div><p className="card-label">近七日支出</p><h2>{money(lastSeven.reduce((s,d)=>s+d.value,0))}</h2></div><button onClick={()=>onView("reports")}>查看报表</button></div><div className="bars" aria-label="近七日支出柱状图">{lastSeven.map((day,index)=><div key={index} title={`${day.label} ${money(day.value)}`} data-value={money(day.value)} className={`bar ${day.value === Math.max(...lastSeven.map(d=>d.value)) && day.value > 0 ? "active":""}`} style={{height:`${Math.max(5,day.value/chartMax*100)}%`}} />)}</div><div className="day-labels">{lastSeven.map((day,index)=><span key={index}>{day.label}</span>)}</div></article>
      <article className="panel budget-panel"><div className="panel-head"><div><p className="card-label">月度预算</p><h2>已用 {used.toFixed(1)}%</h2></div><span>{money(expense)} / {money(budget)}</span></div><div className="budget-ring" style={{background:`conic-gradient(#267354 0 ${used}%, #e6ece8 ${used}%)`}}><div><strong>{money(budgetLeft)}</strong><span>剩余可用</span></div></div><div className="progress-track"><span style={{width:`${used}%`}} /></div><p className="budget-tip">{budgetLeft >= 0 ? "预算仍有余量，继续保持" : "本月已超预算，留意接下来的支出"}</p></article>
    </div>
    <article className="panel transactions-panel"><div className="panel-head"><div><p className="card-label">最近记录</p><h2>每一笔，都清清楚楚</h2></div><button onClick={()=>onView("transactions")}>全部明细</button></div><TransactionRows items={recent} onEdit={onEdit} /></article>
  </>;
}

function TransactionsView({ items, query, setQuery, filter, setFilter, onEdit, onRemove }: { items:Transaction[];query:string;setQuery:(s:string)=>void;filter:"all"|TxType;setFilter:(v:"all"|TxType)=>void;onEdit:(t:Transaction)=>void;onRemove:(id:string)=>void }) {
  return <article className="panel page-panel"><div className="toolbar"><label htmlFor="transaction-search" className="search-box"><Search size={16}/><Input id="transaction-search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索备注、分类或账户" /></label><div className="filter-tabs">{(["all","expense","income"] as const).map(v=><button key={v} className={filter===v?"active":""} onClick={()=>setFilter(v)}>{v==="all"?"全部":v==="expense"?"支出":"收入"}</button>)}</div></div>{items.length ? <TransactionRows items={items} onEdit={onEdit} onRemove={onRemove} showActions /> : <EmptyState title="没有找到记录" description="换个关键词，或者记下新的一笔。" />}</article>;
}

function TransactionRows({ items, onEdit, onRemove, showActions=false }: {items:Transaction[];onEdit:(t:Transaction)=>void;onRemove?:(id:string)=>void;showActions?:boolean}) {
  return <div className="transaction-list">{items.map(tx=><div className="transaction" key={tx.id}><span className={`transaction-icon ${tx.type === "income" ? "green" : categoryTone(tx.category)}`}>{tx.type === "income" ? <ArrowDownLeft size={18}/> : <Utensils size={18}/>}</span><div><strong>{tx.note || tx.category}</strong><small>{tx.category} · {tx.account} · {tx.date}</small></div><b className={tx.type === "income" ? "income":""}>{tx.type === "income"?"+":"-"}{money(tx.amount)}</b>{showActions && <div className="row-actions"><button aria-label="编辑" onClick={()=>onEdit(tx)}><Pencil size={15}/></button><button aria-label="删除" onClick={()=>onRemove?.(tx.id)}><Trash2 size={15}/></button></div>}</div>)}</div>;
}

function BudgetView({budget,expense,totals,max,onSave}:{budget:number;expense:number;totals:{category:string;value:number}[];max:number;onSave:(n:number)=>void}) {
  const [value,setValue]=useState(String(budget)); return <div className="two-col-page"><article className="panel budget-setting"><p className="card-label">本月总预算</p><h2>{money(budget)}</h2><div className="budget-edit"><Input aria-label="月度预算金额" type="number" min="0.01" step="0.01" value={value} onChange={e=>setValue(e.target.value)} /><Button onClick={()=>onSave(Number(value))}>保存</Button></div><p>已支出 {money(expense)}，剩余 <b className={budget-expense<0?"negative":""}>{money(budget-expense)}</b></p></article><article className="panel"><div className="panel-head"><div><p className="card-label">分类花费</p><h2>钱都花在哪里</h2></div></div><CategoryBars totals={totals} max={max}/></article></div>;
}

function ReportsView({income,expense,totals,max}:{income:number;expense:number;totals:{category:string;value:number}[];max:number}) { return <><div className="report-cards"><article className="metric-card"><p className="card-label">收入</p><strong className="income-text">{money(income)}</strong></article><article className="metric-card"><p className="card-label">支出</p><strong>{money(expense)}</strong></article><article className="metric-card"><p className="card-label">净结余</p><strong>{money(income-expense)}</strong></article></div><article className="panel report-panel"><div className="panel-head"><div><p className="card-label">支出构成</p><h2>本月分类排行</h2></div></div>{totals.length?<CategoryBars totals={totals} max={max}/>:<EmptyState title="本月还没有支出" description="记下支出后，这里会自动生成分析。"/>}</article></>; }

function CategoryBars({totals,max}:{totals:{category:string;value:number}[];max:number}) { return <div className="category-bars">{totals.map((item,index)=><div className="category-row" key={item.category}><div><span>{index+1}. {item.category}</span><b>{money(item.value)}</b></div><div className="category-track"><span style={{width:`${item.value/max*100}%`}} /></div></div>)}</div>; }

function AccountsView({accounts,onAdd,onRemove}:{accounts:(Account&{balance:number})[];onAdd:(a:Account)=>boolean;onRemove:(id:string)=>void}) {
  const [name,setName]=useState(""); const [opening,setOpening]=useState("");
  const submit=(e:SyntheticEvent<HTMLFormElement>)=>{e.preventDefault();if(!name.trim())return;if(onAdd({id:uid(),name:name.trim(),type:"个人账户",opening:Number(opening)||0})){setName("");setOpening("");}};
  return <><div className="account-grid">{accounts.map(account=><article className="account-card" key={account.id}><span><Landmark size={20}/></span><div><small>{account.type}</small><h3>{account.name}</h3><strong>{money(account.balance)}</strong></div><button aria-label="删除账户" onClick={()=>onRemove(account.id)}><X size={15}/></button></article>)}</div><form className="panel add-account" onSubmit={submit}><div><p className="card-label">添加账户</p><h2>现金、银行卡或电子钱包</h2></div><Input required value={name} onChange={e=>setName(e.target.value)} placeholder="账户名称"/><Input type="number" step="0.01" value={opening} onChange={e=>setOpening(e.target.value)} placeholder="初始余额"/><Button type="submit"><Plus size={16}/>添加</Button></form></>;
}

function SettingsView({onExport,onImport,onReset}:{onExport:()=>void;onImport:()=>void;onReset:()=>void}) { return <div className="settings-grid"><article className="panel setting-card"><span className="setting-icon"><ShieldCheck/></span><div><h2>隐私优先</h2><p>账本存放在当前浏览器，不会上传到任何服务器。清除浏览器数据前，请先导出备份。</p></div></article><article className="panel setting-card"><span className="setting-icon"><Download/></span><div><h2>备份与恢复</h2><p>定期导出 JSON 备份，可在这台电脑或另一浏览器中恢复。</p><div className="setting-actions"><Button onClick={onExport}><Download/>导出备份</Button><Button variant="outline" onClick={onImport}><Upload/>导入备份</Button></div></div></article><article className="panel setting-card danger-card"><span className="setting-icon"><BookOpen/></span><div><h2>示例数据</h2><p>覆盖当前内容，并恢复初次打开时的示例账本。</p><Button variant="destructive" onClick={onReset}>恢复示例</Button></div></article></div>; }

function TransactionDialog({setOpen,editing,accounts,onSave}:{setOpen:(o:boolean)=>void;editing:Transaction|null;accounts:Account[];onSave:(t:Transaction)=>void}) {
  const initialType=editing?.type||"expense"; const [type,setType]=useState<TxType>(initialType); const [amount,setAmount]=useState(editing?String(editing.amount):""); const [category,setCategory]=useState(editing?.category||(initialType==="income"?incomeCategories[0]:expenseCategories[0])); const [account,setAccount]=useState(editing?.account||accounts[0]?.name||""); const [date,setDate]=useState(editing?.date||today()); const [note,setNote]=useState(editing?.note||"");
  const categories=type==="expense"?expenseCategories:incomeCategories; const submit=(e:SyntheticEvent<HTMLFormElement>)=>{e.preventDefault();if(!(Number(amount)>0))return;onSave({id:editing?.id||uid(),type,amount:Number(amount),category,account,date,note:note.trim()||category});};
  return <dialog open className="dialog-overlay"><button className="dialog-backdrop" aria-label="关闭记账窗口" onClick={()=>setOpen(false)} /><section className="transaction-dialog" aria-labelledby="transaction-title"><button className="dialog-close" aria-label="关闭" onClick={()=>setOpen(false)}><X size={17}/></button><header><h2 id="transaction-title">{editing?"编辑记录":"记一笔"}</h2><p>金额会立即计入账户余额和本月统计。</p></header><form onSubmit={submit}><div className="type-switch"><button type="button" className={type==="expense"?"active":""} onClick={()=>{setType("expense");setCategory(expenseCategories[0]);}}>支出</button><button type="button" className={type==="income"?"active income-tab":""} onClick={()=>{setType("income");setCategory(incomeCategories[0]);}}>收入</button></div><label htmlFor="tx-amount">金额<Input id="tx-amount" autoFocus required type="number" min="0.01" step="0.01" value={amount} onChange={e=>setAmount(e.target.value)} placeholder="0.00" /></label><div className="form-grid"><label htmlFor="tx-category">分类<select id="tx-category" value={category} onChange={e=>setCategory(e.target.value)}>{categories.map(c=><option key={c}>{c}</option>)}</select></label><label htmlFor="tx-account">账户<select id="tx-account" value={account} onChange={e=>setAccount(e.target.value)}>{accounts.map(a=><option key={a.id}>{a.name}</option>)}</select></label></div><label htmlFor="tx-date">日期<Input id="tx-date" required type="date" value={date} onChange={e=>setDate(e.target.value)}/></label><label htmlFor="tx-note">备注<Input id="tx-note" value={note} onChange={e=>setNote(e.target.value)} placeholder="例如：校园食堂" /></label><Button type="submit" className="submit-tx">{editing?"保存修改":"确认记账"}</Button></form></section></dialog>;
}

function EmptyState({title,description}:{title:string;description:string}) { return <div className="empty-state"><ReceiptText size={30}/><h3>{title}</h3><p>{description}</p></div>; }
function categoryTone(category:string){return category==="学习"?"blue":category==="交通"?"green":"orange";}
