"""历史数据回填：通过 baostock K线 + 市值估算，回填指定日期的数据"""
import sys
import time
import os
import sqlite3
import datetime
import pandas as pd
import baostock as bs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH
from scripts.classify import load_sw_map, aggregate_industry
from scripts.fetch import login_bs, logout_bs, to_bs_code
from scripts.update_db import init_db

DATES = ["2026-05-25", "2026-05-26", "2026-05-27"]
REF_DATE = "2026-05-28"


def fetch_all_kline(codes, start, end):
    """拉取所有股票 K 线，返回 {code: {date: {close, amount, turn, pctChg}}}"""
    all_data = {}
    total = len(codes)
    t0 = time.time()
    batch_size = 1000  # 每 1000 次重登，避免会话超时

    for i, code in enumerate(codes):
        # 定时重登
        if i % batch_size == 0:
            if i > 0:
                logout_bs()
            login_bs()

        bs_code = to_bs_code(code)
        rs = bs.query_history_k_data_plus(
            bs_code, "date,close,amount,turn,pctChg",
            start_date=start, end_date=end, frequency="d", adjustflag="3",
        )
        rows = {}
        while (rs.error_code == "0") and rs.next():
            r = rs.get_row_data()
            try:
                # fields: date,close,amount,turn,pctChg → indices 0,1,2,3,4
                rows[r[0]] = {
                    "close": float(r[1]) if r[1] else 0,
                    "amount": float(r[2]) if r[2] else 0,  # 元
                    "turn": float(r[3]) if r[3] else 0,    # %
                    "pctChg": float(r[4]) if r[4] else 0,  # %
                }
            except (ValueError, IndexError):
                continue
        if rows:
            all_data[code] = rows

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (total - i - 1)
            print(f"\r[backfill] K线: {i+1}/{total} ({(i+1)*100//total}%) 有{len(all_data)}只 ETA {eta:.0f}s", end="", flush=True)

    logout_bs()
    elapsed = time.time() - t0
    print(f"\r[backfill] K线拉取完成: {total}只, 耗时 {elapsed:.0f}s, 有数据 {len(all_data)}只")
    return all_data


def build_dataframes(kline_data, sw_map):
    """
    构建逐日的个股 DataFrame 和行业汇聚 DataFrame。
    返回 {date_str: (stock_df, l1_df, l2_df, l3_df)}
    """
    # 按日期构建
    result = {}
    for date_str in DATES:
        rows = []
        for code, days in kline_data.items():
            if date_str not in days:
                continue
            kd = days[date_str]
            turnover_yi = kd["amount"] / 1e8  # 元→亿
            if turnover_yi == 0:
                continue

            l1 = sw_map.get(code, {}).get("l1", "未分类")
            l2 = sw_map.get(code, {}).get("l2", "未分类")
            l3 = sw_map.get(code, {}).get("l3", "未分类")

            if code.startswith("60"):     board = "沪市主板"
            elif code.startswith("00"):   board = "深市主板"
            elif code.startswith("30"):   board = "创业板"
            elif code.startswith("688"):  board = "科创板"
            elif code.startswith(("83","87","43")): board = "北交所"
            else:                          board = "未知"

            rows.append({
                "code": code, "name": code,
                "industry_l1": l1, "industry_l2": l2, "industry_l3": l3,
                "board": board,
                "total_mkt_cap": 0.0, "float_mkt_cap": 0.0,
                "turnover": turnover_yi,
                "change_pct": kd["pctChg"],
                "turnover_ratio": kd["turn"],
                "is_hs300": 0, "is_zz500": 0,
            })

        if not rows:
            print(f"[backfill] {date_str}: 无有效数据")
            result[date_str] = (None, None, None, None)
            continue

        df = pd.DataFrame(rows)
        market_total = df["turnover"].sum()
        print(f"[backfill] {date_str}: {len(df)}只, 成交额 {market_total:.0f}亿")

        # 汇聚行业
        l1 = aggregate_industry(df, ["industry_l1"], "一级")
        l1["market_share"] = round(l1["turnover"] / market_total * 100, 2)
        l2 = aggregate_industry(df[df["industry_l2"] != "未分类"],
                                ["industry_l1", "industry_l2"], "二级")
        l2["market_share"] = round(l2["turnover"] / market_total * 100, 2)
        l3 = aggregate_industry(df[df["industry_l3"] != "未分类"],
                                ["industry_l1", "industry_l2", "industry_l3"], "三级")
        l3["market_share"] = round(l3["turnover"] / market_total * 100, 2)

        result[date_str] = (df, l1, l2, l3)

    return result


def write_to_db(date_str, stock_df, l1, l2, l3):
    """写入 stock_daily 和 industry_daily"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 个股
    for _, row in stock_df.iterrows():
        c.execute(
            "INSERT OR REPLACE INTO stock_daily VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (date_str, row["code"], row["code"],  # name=code fallback
             row["industry_l1"], row["industry_l2"], row["industry_l3"],
             row["board"], 0.0, 0.0, row["turnover"],
             row["change_pct"], row["turnover_ratio"], 0, 0),
        )

    # 行业
    all_ind = pd.concat([l1, l2, l3], ignore_index=True)

    # 加载前一日对比数据
    prev = (datetime.date.fromisoformat(date_str) - datetime.timedelta(days=1)).isoformat()
    c.execute(
        "SELECT industry_name, total_mkt_cap, float_mkt_cap, turnover "
        "FROM industry_daily WHERE date=? AND level='一级'", (prev,)
    )
    prev_map = {r[0]: (r[1], r[2], r[3]) for r in c.fetchall()}

    for _, row in all_ind.iterrows():
        name = row["industry_name"]
        prev_data = prev_map.get(name)
        mkt_change = None
        float_change = None
        prev_turnover = None
        if prev_data:
            if prev_data[0] is not None:
                mkt_change = row["total_mkt_cap"] - prev_data[0]
            if prev_data[1] is not None:
                float_change = row["float_mkt_cap"] - prev_data[1]
            prev_turnover = prev_data[2]

        c.execute(
            "INSERT OR REPLACE INTO industry_daily VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (date_str, row["level"], name,
             row["industry_l1"], row["industry_l2"], row["industry_l3"],
             int(row["stock_count"]), row["total_mkt_cap"], row["float_mkt_cap"],
             row["turnover"], row["change_pct"],
             mkt_change, float_change, row["turnover_ratio"],
             row["market_share"], prev_turnover),
        )

    conn.commit()
    print(f"[backfill] {date_str}: 个股{len(stock_df)}条, 行业{len(all_ind)}条 写入完成")
    conn.close()


def main():
    # 1. 加载参考数据和 SW 分类
    print("[backfill] 加载分类表...")
    sw_map = load_sw_map()

    # 从 DB 参考日取所有代码
    conn = sqlite3.connect(DB_PATH)
    codes = sorted(pd.read_sql_query(
        f"SELECT DISTINCT code FROM stock_daily WHERE date='{REF_DATE}'", conn
    )["code"].tolist())
    conn.close()
    print(f"[backfill] 参考日{REF_DATE}: {len(codes)}只股票")

    # 2. 拉取 K 线（内部处理 login/logout/重登）
    kline_data = fetch_all_kline(codes, DATES[0], DATES[-1])

    # 3. 构建逐日数据
    print("[backfill] 构建数据...")
    daily_data = build_dataframes(kline_data, sw_map)

    # 4. 写入 DB
    init_db()
    for date_str in DATES:
        stock_df, l1, l2, l3 = daily_data[date_str]
        if stock_df is not None:
            write_to_db(date_str, stock_df, l1, l2, l3)

    # 5. 补股票名称（从参考日抄）
    print("[backfill] 补股票名称...")
    conn = sqlite3.connect(DB_PATH)
    names = pd.read_sql_query(
        f"SELECT code, name FROM stock_daily WHERE date='{REF_DATE}'", conn
    ).set_index("code")["name"].to_dict()
    c = conn.cursor()
    for code, name in names.items():
        if code == name or not name:
            continue
        for date_str in DATES:
            c.execute(
                "UPDATE stock_daily SET name=? WHERE date=? AND code=?",
                (name, date_str, code)
            )
    conn.commit()
    conn.close()

    print("[backfill] ✅ 全部完成")


if __name__ == "__main__":
    main()
