"""Build a minimal test DB for CI. Uses update_db helpers to stay consistent."""
import os
import sys
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.update_db import init_db, write_stocks, write_industry
from scripts.classify import aggregate_industry
import sqlite3


DATES = ["2026-05-28", "2026-05-29"]


def _make_stock(code, name, l1, l2, l3, board, mkt_cap, turnover, pct, ratio, hs300=0, zz500=0):
    return {
        "code": code, "name": name,
        "industry_l1": l1, "industry_l2": l2, "industry_l3": l3,
        "board": board,
        "total_mkt_cap": mkt_cap, "float_mkt_cap": mkt_cap * 0.7,
        "turnover": turnover, "change_pct": pct, "turnover_ratio": ratio,
        "is_hs300": hs300, "is_zz500": zz500,
    }


def build_stocks(date_str):
    """Return a list of stock dicts for a given date (slight variation between dates)."""
    mult = 1.0 if date_str == "2026-05-28" else 1.05  # small day-over-day change
    return [
        # 电子 / 半导体 / 数字芯片设计
        _make_stock("688001", "华创科技", "电子", "半导体", "数字芯片设计", "科创板", 500*mult, 12*mult, 3.5, 4.0, hs300=0, zz500=0),
        _make_stock("688002", "中芯集成", "电子", "半导体", "数字芯片设计", "科创板", 800*mult, 20*mult, -1.2, 5.0, hs300=1, zz500=0),
        _make_stock("300001", "韦尔股份", "电子", "半导体", "数字芯片设计", "创业板", 1200*mult, 35*mult, 5.0, 3.0, hs300=1, zz500=0),
        _make_stock("002001", "北方华创", "电子", "半导体", "数字芯片设计", "深市主板", 1500*mult, 40*mult, 2.0, 2.5, hs300=1, zz500=0),
        _make_stock("688003", "兆易创新", "电子", "半导体", "数字芯片设计", "科创板", 400*mult, 8*mult, -0.5, 3.5, hs300=0, zz500=1),
        # 电子 / 半导体 / 集成电路制造
        _make_stock("688010", "中微公司", "电子", "半导体", "集成电路制造", "科创板", 600*mult, 15*mult, 4.0, 3.0, hs300=1, zz500=0),
        _make_stock("300010", "长电科技", "电子", "半导体", "集成电路制造", "创业板", 350*mult, 10*mult, -2.0, 2.0, hs300=0, zz500=1),
        _make_stock("600010", "士兰微", "电子", "半导体", "集成电路制造", "沪市主板", 450*mult, 12*mult, 1.0, 2.5, hs300=0, zz500=0),
        # 电子 / 元件
        _make_stock("002010", "三环集团", "电子", "元件", "被动元件", "深市主板", 300*mult, 8*mult, 2.5, 2.0, hs300=0, zz500=1),
        _make_stock("300020", "顺络电子", "电子", "元件", "被动元件", "创业板", 200*mult, 6*mult, -1.0, 3.0, hs300=0, zz500=0),
        # 计算机 / 计算机设备
        _make_stock("300030", "中科曙光", "计算机", "计算机设备", "服务器", "创业板", 1000*mult, 30*mult, 6.0, 5.0, hs300=1, zz500=0),
        _make_stock("002030", "浪潮信息", "计算机", "计算机设备", "服务器", "深市主板", 800*mult, 25*mult, 4.0, 4.0, hs300=0, zz500=1),
        _make_stock("688030", "金山办公", "计算机", "未分类", "未分类", "科创板", 600*mult, 18*mult, 3.0, 3.5, hs300=1, zz500=0),
        _make_stock("300031", "深信服", "计算机", "未分类", "未分类", "创业板", 400*mult, 10*mult, -1.5, 2.5, hs300=0, zz500=0),
        _make_stock("002031", "未分类设备", "计算机", "计算机设备", "未分类", "深市主板", 150*mult, 4*mult, 1.0, 2.0, hs300=0, zz500=0),
        # 通信 / 通信设备
        _make_stock("300040", "中兴通讯", "通信", "通信设备", "通信终端", "创业板", 1200*mult, 35*mult, 5.5, 4.0, hs300=1, zz500=0),
        _make_stock("002040", "烽火通信", "通信", "通信设备", "通信终端", "深市主板", 300*mult, 8*mult, -0.8, 2.0, hs300=0, zz500=0),
        _make_stock("688040", "光迅科技", "通信", "通信设备", "光模块", "科创板", 250*mult, 7*mult, 2.0, 3.0, hs300=0, zz500=1),
        _make_stock("300041", "亿联网络", "通信", "通信设备", "通信终端", "创业板", 350*mult, 10*mult, -2.5, 2.5, hs300=0, zz500=0),
        _make_stock("600040", "亨通光电", "通信", "通信设备", "光纤光缆", "沪市主板", 280*mult, 6*mult, 1.0, 1.5, hs300=0, zz500=0),
        _make_stock("002041", "中天科技", "通信", "通信设备", "光纤光缆", "深市主板", 320*mult, 9*mult, -1.0, 2.0, hs300=0, zz500=0),
        # 未分类 (L1)
        _make_stock("688100", "未知科创", "未分类", "未分类", "未分类", "科创板", 100*mult, 2*mult, 5.0, 8.0, hs300=0, zz500=0),
        _make_stock("300100", "未知创业", "未分类", "未分类", "未分类", "创业板", 80*mult, 1.5*mult, -3.0, 6.0, hs300=0, zz500=0),
        _make_stock("002100", "未知中小", "未分类", "未分类", "未分类", "深市主板", 120*mult, 2.5*mult, 1.5, 5.0, hs300=0, zz500=0),
    ]


def seed_db(db_path):
    """Build minimal test DB at db_path. Returns None if OK."""
    import config
    original = config.DB_PATH
    config.DB_PATH = db_path

    # Also patch update_db's DB_PATH
    import scripts.update_db as udb
    udb.DB_PATH = db_path

    try:
        init_db()
        conn = sqlite3.connect(db_path)

        for date_str in DATES:
            stocks = build_stocks(date_str)
            df = pd.DataFrame(stocks)
            market_total = df["turnover"].sum()

            # Aggregate industry levels
            l1 = aggregate_industry(df, ["industry_l1"], "一级")
            l1["market_share"] = round(l1["turnover"] / market_total * 100, 2)
            l2 = aggregate_industry(df, ["industry_l1", "industry_l2"], "二级")
            l2["market_share"] = round(l2["turnover"] / market_total * 100, 2)
            l3 = aggregate_industry(df, ["industry_l1", "industry_l2", "industry_l3"], "三级")
            l3["market_share"] = round(l3["turnover"] / market_total * 100, 2)

            # Write stocks
            write_stocks(conn, df, date_str)

            # Write industry data
            all_ind = pd.concat([l1, l2, l3], ignore_index=True)
            c = conn.cursor()

            # Load previous day for change calculations
            if date_str != DATES[0]:
                prev_date = DATES[DATES.index(date_str) - 1]
                c.execute(
                    "SELECT industry_name, level, total_mkt_cap, float_mkt_cap, turnover "
                    "FROM industry_daily WHERE date=?",
                    (prev_date,),
                )
                prev_rows = c.fetchall()
                prev_map = {(r[0], r[1]): (r[2], r[3], r[4]) for r in prev_rows}
            else:
                prev_map = {}

            for _, row in all_ind.iterrows():
                name = row["industry_name"]
                level = row["level"]
                prev = prev_map.get((name, level))
                mkt_change = None
                float_change = None
                prev_turnover = None
                if prev:
                    prev_turnover = prev[2]
                    if prev[0] and prev[0] > 0 and row["total_mkt_cap"] > 0:
                        mkt_change = round(row["total_mkt_cap"] - prev[0], 2)
                    if prev[1] and prev[1] > 0 and row["float_mkt_cap"] > 0:
                        float_change = round(row["float_mkt_cap"] - prev[1], 2)

                c.execute(
                    "INSERT OR REPLACE INTO industry_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (date_str, row["level"], name,
                     row.get("industry_l1", ""), row.get("industry_l2", ""), row.get("industry_l3", ""),
                     int(row["stock_count"]), row["total_mkt_cap"], row["float_mkt_cap"],
                     row["turnover"], row["change_pct"],
                     mkt_change, float_change, row["turnover_ratio"],
                     row["market_share"], prev_turnover),
                )

            conn.commit()

        conn.close()
        return stocks  # Return last date's raw data for tests to reference
    finally:
        config.DB_PATH = original
        udb.DB_PATH = original


if __name__ == "__main__":
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    seed_db(path)
    print(f"Test DB created: {path}")
    # Show stats
    conn = sqlite3.connect(path)
    for table in ["stock_daily", "industry_daily"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table}: {count} rows")
    conn.close()
    os.remove(path)
