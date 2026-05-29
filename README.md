# 资金云图

每日 A 股资金热度可视化工具。以成交额为核心维度，通过矩形树图直观展示全市场行业资金流向，支持行业一/二/三级下钻和个股明细。

## 技术栈

- **后端**: Python Flask
- **前端**: ECharts 5 矩形树图
- **数据源**: 腾讯行情接口 (qt.gtimg.cn) + baostock (K线/指数成分)
- **行业分类**: 申万三级行业分类
- **存储**: SQLite

## 快速开始

```bash
# 1. 安装依赖
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. 启动
python app.py
```

首次启动会自动拉取最新交易日数据，随后浏览器打开 `http://127.0.0.1:8080`。

## 测试

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

44 个测试用例，覆盖 API 端点、数据一致性和工具函数。

## 目录结构

```
├── app.py                  # Flask 主入口，API 路由
├── config.py               # 配置常量
├── requirements.txt
├── scripts/
│   ├── fetch.py            # 数据拉取 (腾讯行情 + baostock)
│   ├── classify.py         # 申万行业分类 + 行业汇聚
│   ├── update_db.py        # SQLite 建表/写入/环比计算
│   └── backfill.py         # 历史数据回填工具
├── tests/
│   ├── conftest.py         # pytest fixtures
│   ├── test_api.py         # API 端点测试 (19)
│   ├── test_consistency.py # 数据一致性测试 (10)
│   └── test_scripts.py     # 工具函数单元测试 (15)
├── templates/
│   └── index.html          # 前端页面 (ECharts 树图)
├── static/
│   └── style.css
└── data/
    └── 申万三级分类表.xlsx  # 行业分类映射表
```

## 功能

- **矩形树图**: 面积代表成交额大小，红色=上涨/流入，绿色=下跌/流出
- **行业下钻**: 点击进入二级→三级→个股，双击返回上级
- **板块/指数过滤**: 按市场板块（科创板/创业板等）或指数成分（沪深300/中证500）筛选
- **排行侧边栏**: 实时显示 TOP 5 涨跌幅或资金流入/流出
- **数据表**: 所有层级的数据明细，按成交额排序
- **历史回看**: 日期选择器切换历史交易日
