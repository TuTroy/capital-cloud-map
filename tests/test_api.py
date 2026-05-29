"""API endpoint tests — uses real DB via Flask test client."""
import json


# ---------------------------------------------------------------------------
# /api/dates
# ---------------------------------------------------------------------------

def test_dates_returns_list(client):
    r = client.get("/api/dates")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert isinstance(data, list)
    assert len(data) > 0
    # sorted desc
    assert data == sorted(data, reverse=True)


# ---------------------------------------------------------------------------
# /api/market-summary
# ---------------------------------------------------------------------------

def test_market_summary_defaults(client):
    r = client.get("/api/market-summary")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert "total_turnover" in data
    assert "total_stocks" in data
    assert data["total_turnover"] > 0
    assert data["total_stocks"] > 0


def test_market_summary_specific_date(client):
    r = client.get("/api/market-summary?date=2026-05-29")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["total_turnover"] > 0
    assert data["total_stocks"] > 0


def test_market_summary_bad_date(client):
    r = client.get("/api/market-summary?date=2099-01-01")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data["total_turnover"] == 0
    assert data["total_stocks"] == 0


# ---------------------------------------------------------------------------
# /api/industries — fast path (no filter)
# ---------------------------------------------------------------------------

def test_industries_l1_fast(client):
    r = client.get("/api/industries?date=2026-05-29&level=一级")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) == 4
    # sorted by turnover desc
    turnovers = [d["turnover"] for d in data]
    assert turnovers == sorted(turnovers, reverse=True)
    # fields present
    d0 = data[0]
    for f in ["total_mkt_cap", "float_mkt_cap", "mkt_cap_change", "float_cap_change",
              "market_share", "prev_turnover", "stock_count", "change_pct", "turnover_ratio"]:
        assert f in d0, f"missing field: {f}"
    # market_share sums to ~100
    total_share = sum(d["market_share"] for d in data)
    assert 99.0 <= total_share <= 101.0, f"L1 share sum: {total_share}"


def test_industries_l2_fast(client):
    r = client.get("/api/industries?date=2026-05-29&level=二级&parent_l1=电子")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) == 2  # 半导体, 元件
    for d in data:
        assert d["level"] == "二级"
        assert d["industry_l1"] == "电子"
    total_share = sum(d["market_share"] for d in data)
    assert 99.0 <= total_share <= 101.0, f"L2 share sum: {total_share}"


def test_industries_l3_fast(client):
    r = client.get("/api/industries?date=2026-05-29&level=三级&parent_l1=电子&parent_l2=半导体")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) == 2  # 数字芯片设计, 集成电路制造
    for d in data:
        assert d["level"] == "三级"
        assert d["industry_l1"] == "电子"
        assert d["industry_l2"] == "半导体"
    total_share = sum(d["market_share"] for d in data)
    assert 99.0 <= total_share <= 101.0, f"L3 share sum: {total_share}"


def test_industries_l2_missing_parent(client):
    """L2 without parent_l1 should return 400 error."""
    r = client.get("/api/industries?date=2026-05-29&level=二级&parent_l1=")
    assert r.status_code == 400
    data = json.loads(r.data)
    assert "error" in data


def test_industries_l3_missing_parent(client):
    """L3 without parent_l2 should return 400 error."""
    r = client.get("/api/industries?date=2026-05-29&level=三级&parent_l1=电子&parent_l2=")
    assert r.status_code == 400
    data = json.loads(r.data)
    assert "error" in data


def test_industries_invalid_level(client):
    """Invalid level should return 400."""
    r = client.get("/api/industries?date=2026-05-29&level=四级")
    assert r.status_code == 400


def test_industries_invalid_date(client):
    """Invalid date should return 400."""
    r = client.get("/api/industries?date=not-a-date&level=一级")
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /api/industries — filter path (board / index)
# ---------------------------------------------------------------------------

def test_industries_l1_board(client):
    r = client.get("/api/industries?date=2026-05-29&level=一级&board=创业板")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) > 0
    d0 = data[0]
    for f in ["total_mkt_cap", "float_mkt_cap", "mkt_cap_change", "float_cap_change",
              "prev_turnover", "market_share"]:
        assert f in d0, f"missing field in filter path: {f}"
    total_share = sum(d["market_share"] for d in data)
    assert 99.0 <= total_share <= 101.0, f"board share sum: {total_share}"


def test_industries_l1_index_hs300(client):
    r = client.get("/api/industries?date=2026-05-29&level=一级&index=hs300")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) > 0
    total_share = sum(d["market_share"] for d in data)
    assert 99.0 <= total_share <= 101.0


def test_industries_l1_index_zz500(client):
    r = client.get("/api/industries?date=2026-05-29&level=一级&index=zz500")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) > 0


def test_industries_filter_combo(client):
    """board + index combined"""
    r = client.get("/api/industries?date=2026-05-29&level=一级&board=科创板&index=hs300")
    assert r.status_code == 200
    data = json.loads(r.data)
    # May be empty if no stocks match both, that's ok
    if data:
        total_share = sum(d["market_share"] for d in data)
        assert 99.0 <= total_share <= 101.0


def test_industries_l2_board_drilldown(client):
    """L2 with board filter: stock counts should be consistent"""
    r = client.get("/api/industries?date=2026-05-29&level=二级&parent_l1=通信&board=创业板")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) > 0
    total_stocks = sum(d["stock_count"] for d in data)
    # should match L1 stock_count for 通信 with same filter
    r_l1 = client.get("/api/industries?date=2026-05-29&level=一级&board=创业板")
    l1_data = json.loads(r_l1.data)
    tx = [d for d in l1_data if d["industry_name"] == "通信"]
    if tx:
        assert total_stocks == tx[0]["stock_count"], \
            f"L2 stock sum {total_stocks} != L1 stock count {tx[0]['stock_count']}"
    total_share = sum(d["market_share"] for d in data)
    assert 99.0 <= total_share <= 101.0


# ---------------------------------------------------------------------------
# /api/stocks
# ---------------------------------------------------------------------------

def test_stocks_basic(client):
    r = client.get("/api/stocks?date=2026-05-29&industry_l1=电子&industry_l2=半导体&industry_l3=数字芯片设计")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) == 5
    d0 = data[0]
    for f in ["code", "name", "board", "total_mkt_cap", "float_mkt_cap",
              "turnover", "change_pct", "turnover_ratio", "market_share",
              "mkt_cap_change", "float_cap_change"]:
        assert f in d0, f"missing field: {f}"
    # sorted by turnover desc
    turnovers = [d["turnover"] for d in data]
    assert turnovers == sorted(turnovers, reverse=True)
    # market_share sums to ~100
    total_share = sum(d["market_share"] for d in data)
    assert 99.0 <= total_share <= 101.0, f"stock share sum: {total_share}"


def test_stocks_with_board_filter(client):
    r = client.get("/api/stocks?date=2026-05-29&industry_l1=通信&industry_l2=通信设备&board=创业板")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) == 2
    for d in data:
        assert d["board"] == "创业板"


def test_stocks_with_index_filter(client):
    r = client.get("/api/stocks?date=2026-05-29&industry_l1=通信&industry_l2=通信设备&index=hs300")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) == 1
    for d in data:
        assert d["is_hs300"] == 1


def test_stocks_empty_industry(client):
    r = client.get("/api/stocks?date=2026-05-29&industry_l1=不存在的行业")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data == []


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------

def test_default_date_when_missing(client):
    """API should work without explicit date param."""
    r = client.get("/api/industries")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) > 0


def test_index_page_loads(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "资金云图" in r.data.decode("utf-8")


# ---------------------------------------------------------------------------
# 未分类 drill-down
# ---------------------------------------------------------------------------

def test_unclassified_l1_exists(client):
    """L1 未分类 should exist with reasonable stock count."""
    r = client.get("/api/industries?date=2026-05-29&level=一级")
    data = json.loads(r.data)
    unclassified = [d for d in data if d["industry_name"] == "未分类"]
    assert len(unclassified) == 1
    uc = unclassified[0]
    assert uc["stock_count"] > 0
    assert uc["turnover"] > 0


def test_unclassified_l1_stocks_match(client):
    """Stocks under L1 未分类 count == L1 未分类 stock_count."""
    r_l1 = client.get("/api/industries?date=2026-05-29&level=一级")
    l1_data = json.loads(r_l1.data)
    uc = [d for d in l1_data if d["industry_name"] == "未分类"][0]

    r_stocks = client.get("/api/stocks?date=2026-05-29&industry_l1=未分类")
    stocks = json.loads(r_stocks.data)
    assert len(stocks) == uc["stock_count"], \
        f"未分类 L1 stock_count={uc['stock_count']} != stocks={len(stocks)}"


def test_unclassified_l1_turnover_consistent(client):
    """L1 未分类 turnover == sum of stocks under 未分类."""
    r_l1 = client.get("/api/industries?date=2026-05-29&level=一级")
    l1_data = json.loads(r_l1.data)
    uc = [d for d in l1_data if d["industry_name"] == "未分类"][0]

    r_stocks = client.get("/api/stocks?date=2026-05-29&industry_l1=未分类")
    stocks = json.loads(r_stocks.data)
    stock_turnover_sum = sum(s["turnover"] for s in stocks)
    assert abs(uc["turnover"] - stock_turnover_sum) < 0.1, \
        f"L1 未分类 turnover={uc['turnover']:.2f} != stocks sum={stock_turnover_sum:.2f}"


def test_unclassified_l2_exists(client):
    """L2 should have disambiguated 未分类 entries like '未分类(计算机)'."""
    r = client.get("/api/industries?date=2026-05-29&level=二级&parent_l1=计算机")
    data = json.loads(r.data)
    uc = [d for d in data if d["industry_name"].startswith("未分类")]
    assert len(uc) >= 1, f"Expected 未分类 entries in 计算机 L2, got {[d['industry_name'] for d in data]}"
    for d in uc:
        assert d["industry_l2"] == "未分类"
        assert d["stock_count"] > 0


def test_unclassified_l2_stocks_match(client):
    """Stocks under L2 未分类(计算机) count == L2 未分类(计算机) stock_count."""
    r_l2 = client.get("/api/industries?date=2026-05-29&level=二级&parent_l1=计算机")
    l2_data = json.loads(r_l2.data)
    uc = [d for d in l2_data if d["industry_name"].startswith("未分类")][0]

    r_stocks = client.get(
        f"/api/stocks?date=2026-05-29&industry_l1=计算机&industry_l2=未分类"
    )
    stocks = json.loads(r_stocks.data)
    assert len(stocks) == uc["stock_count"], \
        f"未分类(计算机) stock_count={uc['stock_count']} != stocks={len(stocks)}"


def test_unclassified_l3_exists(client):
    """L3 should have disambiguated 未分类 entries."""
    r = client.get(
        "/api/industries?date=2026-05-29&level=三级&parent_l1=计算机&parent_l2=计算机设备"
    )
    data = json.loads(r.data)
    uc = [d for d in data if d["industry_name"].startswith("未分类")]
    assert len(uc) >= 1, f"Expected 未分类 entries in 计算机-计算机设备 L3"
    for d in uc:
        assert d["industry_l3"] == "未分类"


def test_unclassified_l3_stocks_match(client):
    """Stocks under L3 未分类 count == L3 未分类 stock_count."""
    r_l3 = client.get(
        "/api/industries?date=2026-05-29&level=三级&parent_l1=计算机&parent_l2=计算机设备"
    )
    l3_data = json.loads(r_l3.data)
    uc = [d for d in l3_data if d["industry_name"].startswith("未分类")][0]

    r_stocks = client.get(
        f"/api/stocks?date=2026-05-29&industry_l1=计算机"
        f"&industry_l2=计算机设备&industry_l3=未分类"
    )
    stocks = json.loads(r_stocks.data)
    assert len(stocks) == uc["stock_count"], \
        f"L3 未分类 stock_count={uc['stock_count']} != stocks={len(stocks)}"


def test_unclassified_l2_turnover_consistent(client):
    """L2 未分类 turnover == sum of stocks under that 未分类 group."""
    r_l2 = client.get("/api/industries?date=2026-05-29&level=二级&parent_l1=计算机")
    l2_data = json.loads(r_l2.data)
    uc = [d for d in l2_data if d["industry_name"].startswith("未分类")][0]

    r_stocks = client.get(
        f"/api/stocks?date=2026-05-29&industry_l1=计算机&industry_l2=未分类"
    )
    stocks = json.loads(r_stocks.data)
    stock_turnover_sum = sum(s["turnover"] for s in stocks)
    assert abs(uc["turnover"] - stock_turnover_sum) < 0.1, \
        f"L2 未分类 turnover={uc['turnover']:.2f} != stocks sum={stock_turnover_sum:.2f}"


# ---------------------------------------------------------------------------
# date / level validation
# ---------------------------------------------------------------------------

def test_market_summary_invalid_date(client):
    """Invalid date should return 400."""
    r = client.get("/api/market-summary?date=abc")
    assert r.status_code == 400


def test_stocks_invalid_date(client):
    """Invalid date in stocks should return 400."""
    r = client.get("/api/stocks?date=bad-date&industry_l1=电子")
    assert r.status_code == 400
