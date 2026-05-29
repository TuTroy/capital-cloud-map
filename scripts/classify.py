"""申万行业分类匹配 + 行业汇聚计算"""
import pandas as pd
import numpy as np

from config import SW_INDUSTRY_MAP


def load_sw_map():
    """加载申万三级分类表，返回 {股票代码: {l1, l2, l3}} 的映射"""
    df = pd.read_excel(SW_INDUSTRY_MAP)
    # 股票代码统一为6位字符串
    df["code_str"] = df["股票代码"].astype(str).str.zfill(6)

    industry_map = {}
    for _, row in df.iterrows():
        industry_map[row["code_str"]] = {
            "l1": str(row["一级行业名称"]),
            "l2": str(row["二级行业名称"]),
            "l3": str(row["三级行业名称"]),
        }

    print(f"[classify] 申万分类表加载: {len(industry_map)} 条映射")
    return industry_map


def classify_stocks(df, industry_map):
    """将股票匹配到申万行业，未匹配标记为'未分类'"""
    unmatched = 0

    for idx, row in df.iterrows():
        code = row["code"]
        if code in industry_map:
            info = industry_map[code]
            df.at[idx, "industry_l1"] = info["l1"]
            df.at[idx, "industry_l2"] = info["l2"]
            df.at[idx, "industry_l3"] = info["l3"]
        else:
            df.at[idx, "industry_l1"] = "未分类"
            df.at[idx, "industry_l2"] = "未分类"
            df.at[idx, "industry_l3"] = "未分类"
            unmatched += 1

    if unmatched > 0:
        print(f"[classify] ⚠️ {unmatched} 只股票未匹配申万分类")

    return df


def _wavg(values, weights):
    """加权平均"""
    total_w = sum(weights)
    if total_w == 0:
        return 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_w


def aggregate_industry(df, level_cols, level_name):
    """按行业层级汇聚计算"""
    results = []

    for level_key, group in df.groupby(level_cols, dropna=False):
        # level_key 可能是 str 或 tuple
        if isinstance(level_key, tuple):
            names = list(level_key)
        else:
            names = [level_key]

        stock_count = len(group)

        # 成交额求和
        total_turnover = group["turnover"].sum()

        # 涨跌幅：成交额加权平均
        wavg_pct = _wavg(group["change_pct"].tolist(), group["turnover"].tolist())

        # 总市值/流通市值求和
        total_mkt = group["total_mkt_cap"].sum()
        float_mkt = group["float_mkt_cap"].sum()

        # 换手率：成交额加权
        wavg_turnover_ratio = _wavg(
            group["turnover_ratio"].tolist(), group["turnover"].tolist()
        )

        results.append({
            "level": level_name,
            "industry_name": names[-1] if names else "",
            "industry_l1": names[0] if len(names) >= 1 else "",
            "industry_l2": names[1] if len(names) >= 2 else "",
            "industry_l3": names[2] if len(names) >= 3 else "",
            "stock_count": stock_count,
            "total_mkt_cap": total_mkt,
            "float_mkt_cap": float_mkt,
            "turnover": total_turnover,
            "change_pct": round(wavg_pct, 2),
            "turnover_ratio": round(wavg_turnover_ratio, 2),
        })

    return pd.DataFrame(results)


def aggregate_all_levels(df, market_total_turnover):
    """汇聚一级/二级/三级行业数据，返回三个DataFrame"""
    # 一级：按 industry_l1
    l1 = aggregate_industry(df, ["industry_l1"], "一级")
    l1["market_share"] = round(l1["turnover"] / market_total_turnover * 100, 2)

    # 二级：按 industry_l1 + industry_l2
    l2 = aggregate_industry(
        df[df["industry_l2"] != "未分类"], ["industry_l1", "industry_l2"], "二级"
    )
    l2["market_share"] = round(l2["turnover"] / market_total_turnover * 100, 2)

    # 三级：按 industry_l1 + industry_l2 + industry_l3
    l3 = aggregate_industry(
        df[df["industry_l3"] != "未分类"],
        ["industry_l1", "industry_l2", "industry_l3"],
        "三级",
    )
    l3["market_share"] = round(l3["turnover"] / market_total_turnover * 100, 2)

    print(f"[classify] 汇聚完成: 一级{l1['stock_count'].sum()}只/二级{l2['stock_count'].sum()}只/三级{l3['stock_count'].sum()}只")
    return l1, l2, l3


def run_classify(df):
    """主入口：分类+汇聚"""
    print("[classify] 开始行业分类...")

    # 1. 加载申万分类表
    industry_map = load_sw_map()

    # 2. 匹配分类
    df = classify_stocks(df, industry_map)

    # 3. 全市场成交额
    market_total_turnover = df["turnover"].sum()

    # 4. 汇聚各层级
    l1, l2, l3 = aggregate_all_levels(df, market_total_turnover)

    return df, l1, l2, l3


if __name__ == "__main__":
    # 测试用
    import sys
    sys.path.insert(0, "..")
    from scripts.fetch import run_fetch

    df = run_fetch()
    if df is not None:
        df, l1, l2, l3 = run_classify(df)
        print(f"\n一级行业({len(l1)}个):")
        print(l1[["industry_l1", "stock_count", "turnover", "change_pct"]]
              .sort_values("turnover", ascending=False).head(10))
