# 大学生个人财务管理助手

本地优先的 Windows 桌面端大学生个人财务管理软件。

核心理念:不仅记录钱花到哪里,更重要的是帮助用户判断接下来应该怎么花。

## 技术栈

- Python 3.12
- PySide6 (Qt for Python)
- SQLite (本地数据库)

## 运行

```bash
uv run python app/main.py
```

## 项目结构

```
app/
├── main.py                 # 程序入口
├── ui/
│   ├── main_window.py       # 主窗口 + 侧边栏导航
│   ├── dashboard.py         # 首页 Dashboard
│   ├── transaction_page.py  # 快速记账 + 账单列表
│   ├── statistics_page.py   # 消费统计
│   ├── budget_page.py       # 预算管理
│   ├── savings_page.py      # 储蓄目标
│   └── settings_page.py     # 设置 / 分类管理 / 数据导入导出
├── database/
│   ├── database.py          # 连接 + 初始化 + 迁移
│   └── models.py            # 表结构定义
├── services/
│   ├── finance_service.py   # 记账 / 账单 / 余额
│   ├── budget_service.py    # 预算 / 剩余 / 建议 / 提醒
│   ├── statistics_service.py# 分类统计 / 每日趋势 / 月度对比
│   └── prediction_service.py# 月底消费预测
└── utils/
    └── helpers.py          # 格式化 / 日期 / 颜色等工具
```

## 开发阶段

- 第一阶段:项目结构 + 数据库 + 核心 UI + 数据逻辑
- 第二阶段:MVP(Dashboard + 记账 + 账单 + 预算 + 基础统计)
- 第三阶段:月底预测 + 储蓄目标 + 月度对比 + 数据导入导出 + 备份
