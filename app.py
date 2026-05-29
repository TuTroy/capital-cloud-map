"""资金云图 - Flask 主入口"""
import datetime
import os
import sys
import sqlite3
import webbrowser
import threading

import pandas as pd
from flask import Flask, jsonify, render_template, request

from config import DB_PATH, FLASK_HOST, FLASK_PORT, DATA_DIR
from scripts.update_db import has_data_for_date, run_update
from scripts.classify import aggregate_industry

app = Flask(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def _latest_date():
    """返回 DB 中最新的数据日期"""
    rows = _query("SELECT MAX(date) AS d FROM industry_daily")
    return rows[0]["d"] if rows and rows[0]["d"] else None


# ---------------------------------------------------------------------------
# API: dates
# ---------------------------------------------------------------------------

@app.route("/api/dates")
def api_dates():
    rows = _query(
        "SELECT DISTINCT date FROM industry_daily ORDER BY date DESC"
    )
    return jsonify([r["date"] for r in rows])


# ---------------------------------------------------------------------------
# API: market summary
# ---------------------------------------------------------------------------

@app.route("/api/market-summary")
def api_market_summary():
    date = request.args.get("date") or _latest_date()
    row = _query(
        "SELECT SUM(turnover) AS total_turnover, "
        "SUM(stock_count) AS total_stocks "
        "FROM industry_daily WHERE date=? AND level='一级'",
        (date,),
    )
    if not row or row[0]["total_turnover"] is None:
        return jsonify({"total_turnover": 0, "total_stocks": 0})
    return jsonify({
        "total_turnover": round(row[0]["total_turnover"], 2),
        "total_stocks": int(row[0]["total_stocks"]),
    })


# ---------------------------------------------------------------------------
# API: industries (with optional board/index filter → re-aggregate)
# ---------------------------------------------------------------------------

@app.route("/api/industries")
def api_industries():
    date = request.args.get("date") or _latest_date()
    level = request.args.get("level", "一级")
    parent_l1 = request.args.get("parent_l1", "")
    parent_l2 = request.args.get("parent_l2", "")
    board = request.args.get("board", "")
    index_filter = request.args.get("index", "")  # hs300 / zz500

    # --- filter path: re-aggregate from stock_daily ---
    if board or index_filter:
        where = ["date=?"]
        params = [date]
        if board:
            where.append("board=?")
            params.append(board)
        if index_filter == "hs300":
            where.append("is_hs300=1")
        elif index_filter == "zz500":
            where.append("is_zz500=1")

        stocks = _query(
            f"SELECT * FROM stock_daily WHERE {' AND '.join(where)}",
            params,
        )
        if not stocks:
            return jsonify([])

        df = pd.DataFrame(stocks)

        # filter by parent industry at the stock level
        if parent_l1:
            df = df[df["industry_l1"] == parent_l1]
        if parent_l2:
            df = df[df["industry_l2"] == parent_l2]

        if level == "一级":
            level_cols = ["industry_l1"]
        elif level == "二级":
            level_cols = ["industry_l1", "industry_l2"]
        else:
            level_cols = ["industry_l1", "industry_l2", "industry_l3"]

        agg = aggregate_industry(df, level_cols, level)
        market_turnover = df["turnover"].sum()

        # market_share: L1 vs full filtered market, L2/L3 vs parent group
        def _compute_share(row):
            if level == "一级":
                return round(row["turnover"] / market_turnover * 100, 2) if market_turnover else 0
            parent_mask = df["industry_l1"] == row["industry_l1"]
            if level == "三级":
                parent_mask &= df["industry_l2"] == row["industry_l2"]
            parent_total = df.loc[parent_mask, "turnover"].sum()
            return round(row["turnover"] / parent_total * 100, 2) if parent_total else 0

        agg["market_share"] = agg.apply(_compute_share, axis=1)

        # compute mkt_cap_change / float_cap_change by comparing with yesterday
        prev_date = (datetime.date.fromisoformat(date) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        prev_where = ["date=?"] + where[1:]
        prev_params = [prev_date] + params[1:]
        prev_stocks = _query(
            f"SELECT * FROM stock_daily WHERE {' AND '.join(prev_where)}",
            prev_params,
        )
        if prev_stocks:
            prev_df = pd.DataFrame(prev_stocks)
            if parent_l1:
                prev_df = prev_df[prev_df["industry_l1"] == parent_l1]
            if parent_l2:
                prev_df = prev_df[prev_df["industry_l2"] == parent_l2]
            prev_agg = aggregate_industry(prev_df, level_cols, level)
            prev_map = {}
            for _, pr in prev_agg.iterrows():
                prev_map[pr["industry_name"]] = {
                    "total_mkt_cap": pr["total_mkt_cap"],
                    "float_mkt_cap": pr["float_mkt_cap"],
                    "turnover": pr["turnover"],
                }
        else:
            prev_map = {}

        def _mkt_change(row):
            p = prev_map.get(row["industry_name"])
            if p and p["total_mkt_cap"] and row["total_mkt_cap"]:
                return round(float(row["total_mkt_cap"]) - float(p["total_mkt_cap"]), 2)
            return None

        def _float_change(row):
            p = prev_map.get(row["industry_name"])
            if p and p["float_mkt_cap"] and row["float_mkt_cap"]:
                return round(float(row["float_mkt_cap"]) - float(p["float_mkt_cap"]), 2)
            return None

        def _prev_turnover(row):
            p = prev_map.get(row["industry_name"])
            return p["turnover"] if p else None

        agg["mkt_cap_change"] = agg.apply(_mkt_change, axis=1)
        agg["float_cap_change"] = agg.apply(_float_change, axis=1)
        agg["prev_turnover"] = agg.apply(_prev_turnover, axis=1)

        return jsonify(agg.to_dict(orient="records"))

    # --- fast path: pre-computed data ---
    if level == "一级":
        rows = _query(
            "SELECT * FROM industry_daily WHERE date=? AND level='一级' "
            "ORDER BY turnover DESC",
            (date,),
        )
    elif level == "二级":
        rows = _query(
            "SELECT * FROM industry_daily WHERE date=? AND level='二级' "
            "AND industry_l1=? ORDER BY turnover DESC",
            (date, parent_l1),
        )
    else:
        rows = _query(
            "SELECT * FROM industry_daily WHERE date=? AND level='三级' "
            "AND industry_l1=? AND industry_l2=? ORDER BY turnover DESC",
            (date, parent_l1, parent_l2),
        )

    # L2/L3: recompute market_share vs parent group total (L1 keeps full-market)
    if level != "一级" and rows:
        parent_total = sum(r["turnover"] for r in rows)
        if parent_total > 0:
            for r in rows:
                r["market_share"] = round(r["turnover"] / parent_total * 100, 2)

    return jsonify(rows)


# ---------------------------------------------------------------------------
# API: stocks under an industry
# ---------------------------------------------------------------------------

@app.route("/api/stocks")
def api_stocks():
    date = request.args.get("date") or _latest_date()
    l1 = request.args.get("industry_l1", "")
    l2 = request.args.get("industry_l2", "")
    l3 = request.args.get("industry_l3", "")
    board = request.args.get("board", "")
    index_filter = request.args.get("index", "")

    where = ["date=?", "industry_l1=?"]
    params = [date, l1]
    if l2:
        where.append("industry_l2=?")
        params.append(l2)
    if l3:
        where.append("industry_l3=?")
        params.append(l3)
    if board:
        where.append("board=?")
        params.append(board)
    if index_filter == "hs300":
        where.append("is_hs300=1")
    elif index_filter == "zz500":
        where.append("is_zz500=1")

    rows = _query(
        f"SELECT code, name, board, total_mkt_cap, float_mkt_cap, "
        f"turnover, change_pct, turnover_ratio, is_hs300, is_zz500 "
        f"FROM stock_daily WHERE {' AND '.join(where)} "
        f"ORDER BY turnover DESC",
        params,
    )

    # 占比 = 个股成交额 / 该行业组总成交额
    group_total = sum(r["turnover"] for r in rows) if rows else 0

    # 计算市值变化（对比上一交易日）
    prev_date = (datetime.date.fromisoformat(date) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_codes = [r["code"] for r in rows]
    prev_map = {}
    if yesterday_codes:
        placeholders = ",".join(["?"] * len(yesterday_codes))
        prev_rows = _query(
            f"SELECT code, total_mkt_cap, float_mkt_cap FROM stock_daily "
            f"WHERE date=? AND code IN ({placeholders})",
            [prev_date] + yesterday_codes,
        )
        prev_map = {r["code"]: r for r in prev_rows}

    for r in rows:
        r["market_share"] = round(r["turnover"] / group_total * 100, 2) if group_total > 0 else 0
        prev = prev_map.get(r["code"])
        if prev and prev["total_mkt_cap"] and r["total_mkt_cap"]:
            r["mkt_cap_change"] = round(r["total_mkt_cap"] - prev["total_mkt_cap"], 2)
        else:
            r["mkt_cap_change"] = None
        if prev and prev["float_mkt_cap"] and r["float_mkt_cap"]:
            r["float_cap_change"] = round(r["float_mkt_cap"] - prev["float_mkt_cap"], 2)
        else:
            r["float_cap_change"] = None

    return jsonify(rows)


# ---------------------------------------------------------------------------
# main page
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# startup
# ---------------------------------------------------------------------------

def _ensure_data():
    """确保最新交易日数据已入库，返回 (success, trading_day)"""
    from scripts.fetch import get_latest_trading_day
    trading_day = get_latest_trading_day()
    print(f"[app] 最近交易日: {trading_day}")

    if has_data_for_date(trading_day):
        print(f"[app] 交易日({trading_day})数据已存在，跳过拉取")
        return True, trading_day

    print(f"[app] 交易日({trading_day})无数据，开始拉取...")

    from scripts.fetch import run_fetch
    from scripts.classify import run_classify

    df, _ = run_fetch()
    if df is None or len(df) == 0:
        print("[app] 无交易数据")
        return False, trading_day

    df, l1, l2, l3 = run_classify(df)
    run_update(df, l1, l2, l3, trading_day)
    return True, trading_day


def _open_browser():
    webbrowser.open(f"http://{FLASK_HOST}:{FLASK_PORT}")


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    ok, trading_day = _ensure_data()
    if not ok:
        print(f"[app] 交易日({trading_day})无行情数据，可能是非交易日，退出")
        sys.exit(0)

    threading.Timer(1.0, _open_browser).start()
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False)


if __name__ == "__main__":
    main()
