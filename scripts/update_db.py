"""SQLite 数据库：建表 + 写入今日数据 + 计算环比变化"""
import sqlite3
import datetime
import pandas as pd

from config import DB_PATH


def init_db():
    """建表（如不存在）"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS industry_daily (
            date            TEXT,
            level           TEXT,
            industry_name   TEXT,
            industry_l1     TEXT,
            industry_l2     TEXT,
            industry_l3     TEXT,
            stock_count     INTEGER,
            total_mkt_cap   REAL,
            float_mkt_cap   REAL,
            turnover        REAL,
            change_pct      REAL,
            mkt_cap_change  REAL,
            float_cap_change REAL,
            turnover_ratio  REAL,
            market_share    REAL,
            prev_turnover   REAL,
            PRIMARY KEY (date, level, industry_name)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS stock_daily (
            date            TEXT,
            code            TEXT,
            name            TEXT,
            industry_l1     TEXT,
            industry_l2     TEXT,
            industry_l3     TEXT,
            board           TEXT,
            total_mkt_cap   REAL,
            float_mkt_cap   REAL,
            turnover        REAL,
            change_pct      REAL,
            turnover_ratio  REAL,
            is_hs300        INTEGER,
            is_zz500        INTEGER,
            PRIMARY KEY (date, code)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS stock_kline (
            date            TEXT,
            code            TEXT,
            open            REAL,
            high            REAL,
            low             REAL,
            close           REAL,
            volume          REAL,
            amount          REAL,
            turnover_ratio  REAL,
            change_pct      REAL,
            PRIMARY KEY (date, code)
        )
    """)

    conn.commit()
    conn.close()
    print("[update_db] 数据库表已就绪")


def _prev_trading_day(trading_day_str):
    """返回前一日日期字符串（简单的 date - 1，非精确交易日）"""
    d = datetime.date.fromisoformat(trading_day_str)
    return (d - datetime.timedelta(days=1)).strftime("%Y-%m-%d")


def _load_yesterday_industry(conn, date_str):
    """加载昨日行业数据，返回 {(level, industry_name): {total_mkt_cap, float_mkt_cap, turnover}}"""
    c = conn.cursor()
    c.execute(
        "SELECT level, industry_name, total_mkt_cap, float_mkt_cap, turnover "
        "FROM industry_daily WHERE date=?",
        (date_str,),
    )
    rows = c.fetchall()
    if not rows:
        return {}
    return {
        (r[0], r[1]): {"total_mkt_cap": r[2], "float_mkt_cap": r[3], "turnover": r[4]}
        for r in rows
    }


def write_industry(conn, df_industry, today_str, yesterday_data):
    """写入行业快照，计算环比变化"""
    c = conn.cursor()
    count = 0
    matched = 0

    for _, row in df_industry.iterrows():
        name = row["industry_name"]
        level = row["level"]
        yest = yesterday_data.get((level, name), {})

        mkt_cap_change = None
        float_cap_change = None
        prev_turnover = None

        if yest:
            prev_turnover = yest["turnover"]
            matched += 1
            if yest.get("total_mkt_cap") is not None and yest["total_mkt_cap"] > 0 and row["total_mkt_cap"] > 0:
                mkt_cap_change = round(row["total_mkt_cap"] - yest["total_mkt_cap"], 2)
            if yest.get("float_mkt_cap") is not None and yest["float_mkt_cap"] > 0 and row["float_mkt_cap"] > 0:
                float_cap_change = round(row["float_mkt_cap"] - yest["float_mkt_cap"], 2)

        c.execute(
            "INSERT OR REPLACE INTO industry_daily VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                today_str,
                row["level"],
                name,
                row.get("industry_l1", ""),
                row.get("industry_l2", ""),
                row.get("industry_l3", ""),
                int(row["stock_count"]),
                row["total_mkt_cap"],
                row["float_mkt_cap"],
                row["turnover"],
                row["change_pct"],
                mkt_cap_change,
                float_cap_change,
                row["turnover_ratio"],
                row["market_share"],
                prev_turnover,
            ),
        )
        count += 1

    conn.commit()
    print(f"[update_db] 行业数据写入: {count} 条 ({matched}条含昨日对比)")
    return count


def write_stocks(conn, df, today_str):
    """写入个股快照"""
    c = conn.cursor()
    count = 0

    for _, row in df.iterrows():
        c.execute(
            "INSERT OR REPLACE INTO stock_daily VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                today_str,
                row["code"],
                row["name"],
                row["industry_l1"],
                row["industry_l2"],
                row["industry_l3"],
                row["board"],
                row["total_mkt_cap"],
                row["float_mkt_cap"],
                row["turnover"],
                row["change_pct"],
                row["turnover_ratio"],
                int(row["is_hs300"]),
                int(row["is_zz500"]),
            ),
        )
        count += 1

    conn.commit()
    print(f"[update_db] 个股数据写入: {count} 条")
    return count


def run_update(df, l1, l2, l3, trading_day):
    """主入口：写入所有数据"""
    print(f"[update_db] 开始写入数据库 ({trading_day})...")

    init_db()
    conn = sqlite3.connect(DB_PATH)

    yest_str = _prev_trading_day(trading_day)
    yesterday_data = _load_yesterday_industry(conn, yest_str)
    if yesterday_data:
        print(f"[update_db] 加载昨日({yest_str})数据: {len(yesterday_data)} 个一级行业")
    else:
        print(f"[update_db] 无昨日数据({yest_str})，变化值标记为 null")

    all_industry = pd.concat([l1, l2, l3], ignore_index=True)
    write_industry(conn, all_industry, trading_day, yesterday_data)
    write_stocks(conn, df, trading_day)

    conn.close()
    print("[update_db] ✅ 数据库写入完成")


def has_data_for_date(trading_day):
    """检查指定交易日数据是否已存在"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM industry_daily WHERE date=?",
        (trading_day,),
    )
    count = c.fetchone()[0]
    conn.close()
    return count > 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "..")
    from scripts.fetch import run_fetch
    from scripts.classify import run_classify

    df, td = run_fetch()
    if df is not None:
        df, l1, l2, l3 = run_classify(df)
        run_update(df, l1, l2, l3, td)
