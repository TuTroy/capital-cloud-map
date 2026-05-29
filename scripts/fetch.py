"""数据拉取：baostock股票列表 + 腾讯行情 + 指数成分股"""
import sys
import time
import datetime
import requests
import pandas as pd
import baostock as bs

from config import (
    TENCENT_URL, TENCENT_BATCH_SIZE, TENCENT_INTERVAL,
    TENCENT_FIELDS, get_board,
)


def login_bs():
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")
    return lg


def logout_bs():
    bs.logout()


def to_bs_code(code):
    if code.startswith(("60", "688")):
        return f"sh.{code}"
    elif code.startswith(("00", "30")):
        return f"sz.{code}"
    else:
        return f"bj.{code}"


def _find_latest_trading_day():
    """找到 baostock 最近的交易日"""
    today = datetime.date.today()
    for offset in range(0, 30):
        day = (today - datetime.timedelta(days=offset)).strftime("%Y-%m-%d")
        rs = bs.query_all_stock(day=day)
        if rs.error_code == "0":
            # 检查是否有数据
            rs.next()
            row = rs.get_row_data()
            if row and len(row) > 0:
                return day
    raise RuntimeError("baostock 近30天无交易日数据")


def get_latest_trading_day():
    """获取最近交易日（轻量，仅用于缓存检查）"""
    lg = bs.login()
    if lg.error_code != "0":
        raise RuntimeError(f"baostock 登录失败: {lg.error_msg}")
    day = _find_latest_trading_day()
    bs.logout()
    return day


def get_stock_list():
    """获取全A股代码列表"""
    login_bs()

    # 找到最近有数据的交易日
    trading_day = _find_latest_trading_day()
    print(f"[fetch] baostock 最近交易日: {trading_day}")

    rs = bs.query_all_stock(day=trading_day)
    stocks = []
    while (rs.error_code == "0") and rs.next():
        row = rs.get_row_data()
        code = row[0]
        name = row[2] if len(row) > 2 else ""

        # 只保留A股（沪深北）
        if code.startswith(("sh.60", "sh.688", "sz.00", "sz.30", "bj.8", "bj.4")):
            clean_code = code.split(".")[1] if "." in code else code
            stocks.append({"code": clean_code, "name": name})

    logout_bs()

    # 去重
    seen = set()
    unique = []
    for s in stocks:
        if s["code"] not in seen:
            seen.add(s["code"])
            unique.append(s)

    print(f"[fetch] 获取到 {len(unique)} 只A股")
    return unique, trading_day


def get_index_stocks():
    """获取沪深300/中证500成分股"""
    login_bs()

    hs300 = set()
    zz500 = set()

    # 沪深300
    try:
        rs = bs.query_hs300_stocks()
        while (rs.error_code == "0") and rs.next():
            row = rs.get_row_data()
            code = row[1].replace("sh.", "").replace("sz.", "")
            hs300.add(code)
        print(f"[fetch] 沪深300成分股: {len(hs300)} 只")
    except Exception as e:
        print(f"[fetch] 沪深300获取失败: {e}")

    # 中证500
    try:
        rs = bs.query_zz500_stocks()
        while (rs.error_code == "0") and rs.next():
            row = rs.get_row_data()
            code = row[1].replace("sh.", "").replace("sz.", "")
            zz500.add(code)
        print(f"[fetch] 中证500成分股: {len(zz500)} 只")
    except Exception as e:
        print(f"[fetch] 中证500获取失败: {e}")

    logout_bs()
    return hs300, zz500


def _fetch_batch(codes):
    """从腾讯接口拉取一批股票行情，返回解析后的列表"""
    code_str = ",".join(codes)
    url = TENCENT_URL.format(codes=code_str)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Referer": "https://gu.qq.com/",
    }

    try:
        r = requests.get(url, headers=headers, timeout=15)
        r.encoding = "gbk"
    except requests.RequestException as e:
        print(f"  [warn] 请求失败: {e}")
        return []

    results = []
    for line in r.text.strip().split("\n"):
        line = line.strip()
        if not line or "=" not in line:
            continue

        # 解析 v_shXXXXXX="data~data~..."
        raw = line.split("=", 1)[1].strip().strip('"').strip(";")
        if not raw:
            continue

        parts = raw.split("~")
        if len(parts) < 46:
            continue

        try:
            turnover = _parse_float(parts[TENCENT_FIELDS["turnover"]])
            # 跳过停牌（成交额=0）
            if turnover == 0:
                continue

            stock = {
                "code": parts[TENCENT_FIELDS["code"]],
                "name": parts[TENCENT_FIELDS["name"]],
                "price": _parse_float(parts[TENCENT_FIELDS["price"]]),
                "prev_close": _parse_float(parts[TENCENT_FIELDS["prev_close"]]),
                "change_pct": _parse_float(parts[TENCENT_FIELDS["change_pct"]]),
                "turnover": turnover,  # 万 → 亿转换在汇聚时做
                "turnover_ratio": _parse_float(parts[TENCENT_FIELDS["turnover_ratio"]]),
                "total_mkt_cap": _parse_float(parts[TENCENT_FIELDS["total_mkt_cap"]]),
                "float_mkt_cap": _parse_float(parts[TENCENT_FIELDS["float_mkt_cap"]]),
                "board": get_board(parts[TENCENT_FIELDS["code"]]),
            }
            results.append(stock)
        except (IndexError, ValueError) as e:
            continue

    return results


def _parse_float(val):
    """解析浮点数，空值返回0"""
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def fetch_all_quotes(stock_list, hs300, zz500):
    """分批拉取全市场行情，返回 DataFrame"""
    all_results = []
    codes = [s["code"] for s in stock_list]
    total_batches = (len(codes) + TENCENT_BATCH_SIZE - 1) // TENCENT_BATCH_SIZE

    print(f"[fetch] 共 {len(codes)} 只股票，分 {total_batches} 批拉取...")

    for i in range(0, len(codes), TENCENT_BATCH_SIZE):
        batch_codes = codes[i : i + TENCENT_BATCH_SIZE]
        batch_num = i // TENCENT_BATCH_SIZE + 1

        # 构造 sh/sz 前缀
        prefixed = []
        for c in batch_codes:
            if c.startswith(("60", "688")):
                prefixed.append(f"sh{c}")
            elif c.startswith(("00", "30")):
                prefixed.append(f"sz{c}")
            # 北交所暂不处理

        if not prefixed:
            continue

        results = _fetch_batch(prefixed)
        all_results.extend(results)

        pct = min(100, batch_num * 100 // total_batches)
        print(f"\r[fetch] 进度: {batch_num}/{total_batches} ({pct}%) - "
              f"已获取 {len(all_results)} 只", end="", flush=True)

        if batch_num < total_batches:
            time.sleep(TENCENT_INTERVAL)

    print()  # 换行

    if not all_results:
        print("[fetch] ❌ 未获取到任何股票数据，可能非交易日")
        return None

    df = pd.DataFrame(all_results)

    # 标记指数成分股
    df["is_hs300"] = df["code"].apply(lambda x: 1 if x in hs300 else 0)
    df["is_zz500"] = df["code"].apply(lambda x: 1 if x in zz500 else 0)

    # 成交额从万转为亿
    df["turnover"] = df["turnover"] / 10000.0

    print(f"[fetch] ✅ 拉取完成: {len(df)} 只有效股票")
    return df


def run_fetch():
    """主入口：拉取全量数据，返回 (DataFrame, trading_day)"""
    print("[fetch] 开始拉取数据...")

    # 1. 股票列表
    stock_list, trading_day = get_stock_list()
    if not stock_list:
        print("[fetch] ❌ 无法获取股票列表")
        return None, None

    # 2. 指数成分股
    hs300, zz500 = get_index_stocks()

    # 3. 行情数据
    df = fetch_all_quotes(stock_list, hs300, zz500)

    return df, trading_day


if __name__ == "__main__":
    df, td = run_fetch()
    if df is not None:
        print(f"[fetch] 交易日: {td}")
        print(df.head())
        print(f"\n列: {df.columns.tolist()}")
        print(f"沪深300: {df['is_hs300'].sum()}, 中证500: {df['is_zz500'].sum()}")
