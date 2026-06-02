"""资金云图 - 配置文件"""
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据目录
DATA_DIR = os.path.join(BASE_DIR, "data")

# 申万行业分类表
SW_INDUSTRY_MAP = os.path.join(DATA_DIR, "申万三级分类表.xlsx")

# SQLite 数据库
DB_PATH = os.path.join(DATA_DIR, "history.db")

# Flask
FLASK_HOST = os.environ.get("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "8080"))

# 腾讯行情接口 - 批量请求参数
TENCENT_BATCH_SIZE = 50   # 每批查询股票数
TENCENT_INTERVAL = 3       # 批次间隔(秒)
TENCENT_URL = "http://qt.gtimg.cn/q={codes}"

# 腾讯行情字段索引（~ 分隔，0-based）
TENCENT_FIELDS = {
    "name": 1,          # 名称
    "code": 2,          # 代码
    "price": 3,         # 当前价
    "prev_close": 4,    # 昨收
    "volume": 6,        # 成交量(手)
    "change_pct": 32,   # 涨跌幅(%)
    "turnover": 37,     # 成交额(万)
    "turnover_ratio": 38,  # 换手率(%)
    "float_mkt_cap": 44,   # 流通市值(亿)
    "total_mkt_cap": 45,   # 总市值(亿)
}

# 板块判断：代码前缀 -> 板块名
def get_board(code):
    """根据股票代码判断板块"""
    if code.startswith("60"):
        return "沪市主板"
    elif code.startswith("00"):
        return "深市主板"
    elif code.startswith("30"):
        return "创业板"
    elif code.startswith("688"):
        return "科创板"
    elif code.startswith(("83", "87", "43")):
        return "北交所"
    return "未知"
