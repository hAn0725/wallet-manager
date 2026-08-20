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

## 测试

```bash
# 服务层单元测试(37 项)
uv run python -m pytest app/tests/test_services.py -v

# UI 烟雾测试(无头模式)
uv run python -m app.tests.test_ui_smoke
```

## 项目结构

```
app/
├── main.py                 # 程序入口
├── ui/
│   ├── main_window.py       # 主窗口 + 侧边栏导航
│   ├── dashboard.py         # 首页 Dashboard
│   ├── transaction_page.py  # 快速记账 + 账单列表(含删除)
│   ├── statistics_page.py   # 消费统计(饼图/柱状图/月度对比)
│   ├── budget_page.py       # 预算管理
│   ├── savings_page.py      # 储蓄目标
│   ├── settings_page.py     # 设置 / 分类管理 / 数据导入导出
│   └── widgets.py           # 可复用 UI 组件
├── database/
│   ├── database.py          # 连接 + 初始化 + 迁移
│   └── models.py            # 表结构定义
├── services/
│   ├── finance_service.py   # 记账 / 账单 / 余额
│   ├── budget_service.py    # 预算 / 剩余 / 建议 / 提醒
│   ├── statistics_service.py# 分类统计 / 每日趋势 / 月度对比
│   ├── prediction_service.py# 月底消费预测(可替换算法)
│   ├── savings_service.py   # 储蓄目标
│   ├── category_service.py  # 分类管理
│   └── settings_service.py  # 导入导出 / 备份恢复
└── utils/
    └── helpers.py          # 格式化 / 日期 / 样式表
```

## 核心功能

- **首页 Dashboard**:本月剩余预算、进度条、今日建议消费、月底预测、累计余额、超支提醒、储蓄目标概览
- **快速记账**:金额/分类/日期/备注 + 支出/收入切换,一键添加
- **账单管理**:按类型/分类筛选、备注搜索、双击编辑、删除按钮
- **预算管理**:月度预算、自然月/自定义周期、实时使用情况与提醒(80%/100%/超支)
- **消费统计**:分类占比饼图、每日消费趋势柱状图、月度对比表
- **月底预测**:融合周期日均(0.4)+ 近 7 日日均(0.6),预计总消费/余额/超支
- **储蓄目标**:新增/编辑/删除、存入/取出、进度条
- **数据管理**:JSON 全量导入导出(合并/替换)、CSV 账单导出、SQLite 备份恢复
- **分类管理**:新增/编辑/删除分类,删除时账单保留但变未分类

## 开发阶段

- 第一阶段:项目结构 + 数据库 + 核心 UI + 数据逻辑 ✅
- 第二阶段:MVP(Dashboard + 记账 + 账单 + 预算 + 基础统计) ✅
- 第三阶段:月底预测 + 储蓄目标 + 月度对比 + 数据导入导出 + 备份 ✅
