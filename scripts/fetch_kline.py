"""K线数据：批量拉取 OHLCV + 历史回填 + 每日增量更新"""
import sys
import time
import os
import sqlite3
import datetime

import baostock as bs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_PATH
from scripts.fetch import login_bs, logout_bs, to_bs_code
from scripts.update_db import init_db

# baostock K 线字段，按索引顺序
KLINE_FIELDS = "date,open,high,low,close,volume,amount,turn,pctChg"


def fetch_kline_batch(codes, start_date, end_date, adjustflag="2"):
    """批量拉取 K 线数据。

    Args:
        codes: 6 位数字股票代码列表
        start_date: 开始日期 "YYYY-MM-DD"
        end_date: 结束日期 "YYYY-MM-DD"
        adjustflag: "2" = 前复权（推荐用于图表）, "3" = 不复权

    Returns:
        {code: [{"date": ..., "open": ..., ...}, ...]}
    """
    all_data = {}
    total = len(codes)
    t0 = time.time()
    batch_size = 1000

    for i, code in enumerate(codes):
        if i % batch_size == 0:
            if i > 0:
                logout_bs()
            login_bs()

        bs_code = to_bs_code(code)
        rs = bs.query_history_k_data_plus(
            bs_code, KLINE_FIELDS,
            start_date=start_date, end_date=end_date,
            frequency="d", adjustflag=adjustflag,
        )
        rows = []
        while (rs.error_code == "0") and rs.next():
            r = rs.get_row_data()
            try:
                rows.append({
                    "date": r[0],
                    "open": float(r[1]) if r[1] else 0.0,
                    "high": float(r[2]) if r[2] else 0.0,
                    "low": float(r[3]) if r[3] else 0.0,
                    "close": float(r[4]) if r[4] else 0.0,
                    "volume": float(r[5]) if r[5] else 0.0,
                    "amount": float(r[6]) if r[6] else 0.0,
                    "turnover_ratio": float(r[7]) if r[7] else 0.0,
                    "change_pct": float(r[8]) if r[8] else 0.0,
                })
            except (ValueError, IndexError):
                continue
        if rows:
            all_data[code] = rows

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (total - i - 1)
            print(f"\r[fetch_kline] {i+1}/{total} ({(i+1)*100//total}%) 有{len(all_data)}只 ETA {eta:.0f}s", end="", flush=True)

    logout_bs()
    elapsed = time.time() - t0
    print(f"\r[fetch_kline] 完成: {total}只, 耗时 {elapsed:.0f}s, 有数据 {len(all_data)}只")
    return all_data


def write_kline_to_db(conn, kline_data):
    """将 K 线数据写入 stock_kline 表。"""
    c = conn.cursor()
    count = 0
    for code, rows in kline_data.items():
        for r in rows:
            c.execute(
                "INSERT OR REPLACE INTO stock_kline VALUES (?,?,?,?,?,?,?,?,?,?)",
                (r["date"], code, r["open"], r["high"], r["low"], r["close"],
                 r["volume"], r["amount"], r["turnover_ratio"], r["change_pct"]),
            )
            count += 1
            if count % 5000 == 0:
                conn.commit()
    conn.commit()
    return count


def run_kline_backfill():
    """历史回填：从 stock_daily 取代码列表，分批次拉近一年 K 线写入。"""
    init_db()

    conn = sqlite3.connect(DB_PATH)
    codes = sorted(
        row[0] for row in conn.execute("SELECT DISTINCT code FROM stock_daily").fetchall()
    )
    conn.close()

    if not codes:
        print("[fetch_kline] stock_daily 无数据，先拉当日行情再回填")
        return

    end_date = datetime.date.today().isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=365)).isoformat()

    # 跳过已有 K 线数据的股票
    conn = sqlite3.connect(DB_PATH)
    existing = set(
        row[0] for row in conn.execute(
            "SELECT DISTINCT code FROM stock_kline"
        ).fetchall()
    )
    conn.close()

    codes_to_fetch = [c for c in codes if c not in existing]
    if not codes_to_fetch:
        print(f"[fetch_kline] 所有 {len(codes)} 只股票均已有K线数据，跳过回填")
        return

    print(f"[fetch_kline] 回填范围: {start_date} ~ {end_date}, "
          f"{len(codes_to_fetch)}只股票（跳过已有{len(existing)}只）")

    CHUNK = 200
    total_written = 0
    for i in range(0, len(codes_to_fetch), CHUNK):
        chunk = codes_to_fetch[i:i + CHUNK]
        print(f"[fetch_kline] 批次 {i // CHUNK + 1}: 正在拉取 {len(chunk)} 只...", flush=True)
        kline_data = fetch_kline_batch(chunk, start_date, end_date)

        conn = sqlite3.connect(DB_PATH)
        count = write_kline_to_db(conn, kline_data)
        conn.close()
        total_written += count

        done = min(i + CHUNK, len(codes_to_fetch))
        print(f"[fetch_kline] 批次完成: 写入 {count} 条, 进度 {done}/{len(codes_to_fetch)}", flush=True)

    dates = set()
    total_rows = 0
    conn = sqlite3.connect(DB_PATH)
    for row in conn.execute("SELECT date, COUNT(*) FROM stock_kline GROUP BY date").fetchall():
        dates.add(row[0])
        total_rows += row[1]
    conn.close()
    print(f"[fetch_kline] 回填完成: {total_rows}条记录, {len(dates)}个交易日")


def run_kline_daily_update(trading_day):
    """每日增量：拉取指定交易日所有股票的 K 线。"""
    init_db()

    conn = sqlite3.connect(DB_PATH)
    codes = sorted(
        row[0] for row in conn.execute(
            "SELECT DISTINCT code FROM stock_daily WHERE date=?", (trading_day,)
        ).fetchall()
    )
    conn.close()

    if not codes:
        print(f"[fetch_kline] {trading_day} 无股票数据，跳过 K 线更新")
        return

    kline_data = fetch_kline_batch(codes, trading_day, trading_day)

    conn = sqlite3.connect(DB_PATH)
    count = write_kline_to_db(conn, kline_data)
    conn.close()

    print(f"[fetch_kline] 每日更新: {count}条K线 ({trading_day})")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["backfill", "daily"])
    p.add_argument("date", nargs="?", help="trading day (daily mode)")
    args = p.parse_args()

    if args.action == "backfill":
        run_kline_backfill()
    elif args.action == "daily":
        date = args.date or datetime.date.today().isoformat()
        run_kline_daily_update(date)
