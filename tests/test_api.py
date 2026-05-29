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
    assert len(data) == 32
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
    assert len(data) == 6
    for d in data:
        assert d["level"] == "二级"
        assert d["industry_l1"] == "电子"
    total_share = sum(d["market_share"] for d in data)
    assert 99.0 <= total_share <= 101.0, f"L2 share sum: {total_share}"


def test_industries_l3_fast(client):
    r = client.get("/api/industries?date=2026-05-29&level=三级&parent_l1=电子&parent_l2=半导体")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) == 7
    for d in data:
        assert d["level"] == "三级"
        assert d["industry_l1"] == "电子"
        assert d["industry_l2"] == "半导体"
    total_share = sum(d["market_share"] for d in data)
    assert 99.0 <= total_share <= 101.0, f"L3 share sum: {total_share}"


def test_industries_l2_missing_parent(client):
    """L2 without parent_l1 should still return data (empty if none match)"""
    r = client.get("/api/industries?date=2026-05-29&level=二级&parent_l1=")
    # Returns empty because parent_l1="" matches nothing in WHERE
    assert r.status_code == 200


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
    assert len(data) == 51
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
    assert len(data) == 38
    for d in data:
        assert d["board"] == "创业板"


def test_stocks_with_index_filter(client):
    r = client.get("/api/stocks?date=2026-05-29&industry_l1=通信&industry_l2=通信设备&index=hs300")
    assert r.status_code == 200
    data = json.loads(r.data)
    assert len(data) == 6
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
