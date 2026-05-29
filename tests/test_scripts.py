"""Unit tests for classify.py and update_db.py."""
import datetime

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# classify._wavg
# ---------------------------------------------------------------------------

from scripts.classify import _wavg, aggregate_industry


def test_wavg_normal():
    assert _wavg([1, 2, 3], [1, 1, 1]) == 2.0


def test_wavg_weighted():
    result = _wavg([10, 20], [3, 1])
    assert result == (10 * 3 + 20 * 1) / 4


def test_wavg_zero_weights():
    assert _wavg([1, 2, 3], [0, 0, 0]) == 0.0


def test_wavg_single_value():
    assert _wavg([5], [10]) == 5.0


def test_wavg_empty():
    assert _wavg([], []) == 0.0


# ---------------------------------------------------------------------------
# classify.aggregate_industry
# ---------------------------------------------------------------------------

def _make_df(rows):
    return pd.DataFrame(rows)


def test_aggregate_single_group():
    df = _make_df([
        {"industry_l1": "A", "turnover": 100, "change_pct": 5.0, "turnover_ratio": 3.0,
         "total_mkt_cap": 500, "float_mkt_cap": 300},
        {"industry_l1": "A", "turnover": 200, "change_pct": 10.0, "turnover_ratio": 2.0,
         "total_mkt_cap": 800, "float_mkt_cap": 500},
    ])
    result = aggregate_industry(df, ["industry_l1"], "一级")
    assert len(result) == 1
    row = result.iloc[0]
    assert row["industry_name"] == "A"
    assert row["level"] == "一级"
    assert row["stock_count"] == 2
    assert row["turnover"] == 300
    assert row["total_mkt_cap"] == 1300
    assert row["float_mkt_cap"] == 800
    # weighted avg change_pct: (100*5 + 200*10) / 300 = 8.33
    assert abs(row["change_pct"] - 8.33) < 0.1


def test_aggregate_multi_group():
    df = _make_df([
        {"industry_l1": "A", "industry_l2": "A1", "turnover": 100, "change_pct": 2.0,
         "turnover_ratio": 1.0, "total_mkt_cap": 100, "float_mkt_cap": 50},
        {"industry_l1": "A", "industry_l2": "A2", "turnover": 300, "change_pct": 4.0,
         "turnover_ratio": 2.0, "total_mkt_cap": 200, "float_mkt_cap": 100},
    ])
    result = aggregate_industry(df, ["industry_l1", "industry_l2"], "二级")
    assert len(result) == 2
    names = set(result["industry_name"])
    assert names == {"A1", "A2"}
    for _, row in result.iterrows():
        assert row["level"] == "二级"
        assert row["industry_l1"] == "A"


def test_aggregate_required_columns():
    df = _make_df([
        {"industry_l1": "X", "turnover": 100, "change_pct": 1.0, "turnover_ratio": 1.0,
         "total_mkt_cap": 100, "float_mkt_cap": 50},
    ])
    result = aggregate_industry(df, ["industry_l1"], "一级")
    expected_cols = {"level", "industry_name", "industry_l1", "industry_l2", "industry_l3",
                     "stock_count", "total_mkt_cap", "float_mkt_cap",
                     "turnover", "change_pct", "turnover_ratio"}
    for col in expected_cols:
        assert col in result.columns, f"missing column: {col}"


def test_aggregate_empty_df():
    df = _make_df([])
    result = aggregate_industry(df, ["industry_l1"], "一级")
    assert len(result) == 0
    assert isinstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# update_db
# ---------------------------------------------------------------------------

from scripts.update_db import init_db, has_data_for_date, _prev_trading_day


def test_prev_trading_day_normal():
    assert _prev_trading_day("2026-05-29") == "2026-05-28"


def test_prev_trading_day_cross_month():
    assert _prev_trading_day("2026-05-01") == "2026-04-30"


def test_prev_trading_day_cross_year():
    assert _prev_trading_day("2026-01-01") == "2025-12-31"


def test_init_db_creates_tables(tmp_db):
    init_db()
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [r[0] for r in c.fetchall()]
    assert "industry_daily" in tables
    assert "stock_daily" in tables

    # verify industry_daily schema
    c.execute("PRAGMA table_info(industry_daily)")
    cols = [r[1] for r in c.fetchall()]
    for expected in ["date", "level", "industry_name", "total_mkt_cap", "float_mkt_cap",
                     "turnover", "change_pct", "mkt_cap_change", "float_cap_change",
                     "market_share", "prev_turnover"]:
        assert expected in cols, f"missing column in industry_daily: {expected}"

    # verify stock_daily schema
    c.execute("PRAGMA table_info(stock_daily)")
    cols = [r[1] for r in c.fetchall()]
    for expected in ["date", "code", "name", "total_mkt_cap", "float_mkt_cap",
                     "turnover", "change_pct", "is_hs300", "is_zz500"]:
        assert expected in cols, f"missing column in stock_daily: {expected}"

    conn.close()


def test_has_data_for_date_empty(tmp_db):
    init_db()
    assert has_data_for_date("2026-01-01") is False


def test_has_data_for_date_with_data(tmp_db):
    init_db()
    import sqlite3
    conn = sqlite3.connect(tmp_db)
    conn.execute(
        "INSERT INTO industry_daily (date, level, industry_name, stock_count, total_mkt_cap, "
        "float_mkt_cap, turnover, change_pct, turnover_ratio, market_share) "
        "VALUES ('2026-01-01', '一级', '测试', 1, 100, 50, 10, 1.0, 2.0, 5.0)"
    )
    conn.commit()
    conn.close()
    assert has_data_for_date("2026-01-01") is True
