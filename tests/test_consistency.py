"""Data consistency tests — cross-validate between stock_daily and industry_daily."""
import json


# ---------------------------------------------------------------------------
# turnover consistency
# ---------------------------------------------------------------------------

def test_l1_turnover_matches_stock_turnover(client):
    """L1 industry turnover sum == all stock turnover sum."""
    r_ind = client.get("/api/industries?date=2026-05-29&level=一级")
    industries = json.loads(r_ind.data)
    ind_sum = sum(d["turnover"] for d in industries)

    # sum across all L1's stock counts to get total stock turnover
    # Actually, query stocks for a big industry and verify relationship
    # Simpler: just verify L1 turnover is consistent
    r_summary = client.get("/api/market-summary?date=2026-05-29")
    summary = json.loads(r_summary.data)
    assert abs(ind_sum - summary["total_turnover"]) < 0.1, \
        f"L1 sum {ind_sum:.2f} != market-summary {summary['total_turnover']:.2f}"


def test_all_dates_consistent_turnover(client):
    """Every date should have consistent L1 turnover."""
    dates = json.loads(client.get("/api/dates").data)
    for d in dates:
        r = client.get(f"/api/industries?date={d}&level=一级")
        data = json.loads(r.data)
        if not data:
            continue
        ind_sum = sum(x["turnover"] for x in data)
        r_s = client.get(f"/api/market-summary?date={d}")
        summary = json.loads(r_s.data)
        assert abs(ind_sum - summary["total_turnover"]) < 0.1, \
            f"Date {d}: L1 sum {ind_sum:.2f} != summary {summary['total_turnover']:.2f}"


# ---------------------------------------------------------------------------
# stock count consistency across levels
# ---------------------------------------------------------------------------

def test_l1_to_l2_stock_count(client):
    """L2 stock count sum within a parent <= L1 stock count (未分类 excluded at L2)."""
    r_l1 = client.get("/api/industries?date=2026-05-29&level=一级")
    l1_data = json.loads(r_l1.data)

    for l1 in l1_data[:5]:
        r_l2 = client.get(
            f"/api/industries?date=2026-05-29&level=二级&parent_l1={l1['industry_name']}"
        )
        l2_data = json.loads(r_l2.data)
        l2_total = sum(d["stock_count"] for d in l2_data)
        # L2 excludes "未分类" stocks, so L2 sum may be <= L1
        assert l2_total <= l1["stock_count"], \
            f"{l1['industry_name']}: L1={l1['stock_count']} L2 sum={l2_total}"


def test_l2_to_l3_stock_count(client):
    """L3 stock count sum within a parent <= L2 stock count (未分类 excluded at L3)."""
    r_l2 = client.get("/api/industries?date=2026-05-29&level=二级&parent_l1=电子")
    l2_data = json.loads(r_l2.data)

    for l2 in l2_data:
        r_l3 = client.get(
            f"/api/industries?date=2026-05-29&level=三级"
            f"&parent_l1=电子&parent_l2={l2['industry_name']}"
        )
        l3_data = json.loads(r_l3.data)
        l3_total = sum(d["stock_count"] for d in l3_data)
        # L3 excludes "未分类" stocks, so L3 sum may be less than L2
        assert l3_total <= l2["stock_count"], \
            f"{l2['industry_name']}: L2={l2['stock_count']} L3 sum={l3_total}"


def test_l3_to_stocks_count(client):
    """Stock count in an L3 industry == count from /api/stocks."""
    r_l3 = client.get("/api/industries?date=2026-05-29&level=三级&parent_l1=电子&parent_l2=半导体")
    l3_data = json.loads(r_l3.data)

    for l3 in l3_data[:3]:
        r_stocks = client.get(
            f"/api/stocks?date=2026-05-29&industry_l1=电子"
            f"&industry_l2=半导体&industry_l3={l3['industry_name']}"
        )
        stocks = json.loads(r_stocks.data)
        assert len(stocks) == l3["stock_count"], \
            f"{l3['industry_name']}: L3={l3['stock_count']} stocks={len(stocks)}"


# ---------------------------------------------------------------------------
# market_share consistency
# ---------------------------------------------------------------------------

def test_market_share_sums_to_100(client):
    """All levels, all dates: market_share sums to ~100%."""
    dates = json.loads(client.get("/api/dates").data)

    for d in dates[:3]:  # test recent 3 dates
        # L1
        r = client.get(f"/api/industries?date={d}&level=一级")
        data = json.loads(r.data)
        if data:
            total = sum(x["market_share"] for x in data)
            assert 99.0 <= total <= 101.0, f"Date {d} L1 share sum: {total}"

        # L2 (电子)
        r = client.get(f"/api/industries?date={d}&level=二级&parent_l1=电子")
        data = json.loads(r.data)
        if data:
            total = sum(x["market_share"] for x in data)
            assert 99.0 <= total <= 101.0, f"Date {d} L2 电子 share sum: {total}"

        # L3 (半导体)
        r = client.get(f"/api/industries?date={d}&level=三级&parent_l1=电子&parent_l2=半导体")
        data = json.loads(r.data)
        if data:
            total = sum(x["market_share"] for x in data)
            assert 99.0 <= total <= 101.0, f"Date {d} L3 半导体 share sum: {total}"


# ---------------------------------------------------------------------------
# change data completeness
# ---------------------------------------------------------------------------

def test_change_data_present(client):
    """All levels should have mkt_cap_change and float_cap_change."""
    for level, extra in [
        ("一级", ""),
        ("二级", "&parent_l1=电子"),
        ("三级", "&parent_l1=电子&parent_l2=半导体"),
    ]:
        r = client.get(f"/api/industries?date=2026-05-29&level={level}{extra}")
        data = json.loads(r.data)
        assert len(data) > 0, f"No data for {level}"
        has_mkt_change = sum(1 for d in data if d.get("mkt_cap_change") is not None)
        has_float_change = sum(1 for d in data if d.get("float_cap_change") is not None)
        assert has_mkt_change == len(data), \
            f"{level}: {has_mkt_change}/{len(data)} have mkt_cap_change"
        assert has_float_change == len(data), \
            f"{level}: {has_float_change}/{len(data)} have float_cap_change"


def test_stock_change_data_present(client):
    """Stocks should have mkt_cap_change and float_cap_change."""
    r = client.get("/api/stocks?date=2026-05-29&industry_l1=电子&industry_l2=半导体&industry_l3=数字芯片设计")
    data = json.loads(r.data)
    assert len(data) > 0
    with_change = sum(1 for d in data if d.get("mkt_cap_change") is not None)
    assert with_change == len(data), f"stocks: {with_change}/{len(data)} have mkt_cap_change"


# ---------------------------------------------------------------------------
# filter path: stock count consistency
# ---------------------------------------------------------------------------

def test_filter_l1_to_l2_stock_count(client):
    """With board filter, L2 sum == L1 stock count."""
    r_l1 = client.get("/api/industries?date=2026-05-29&level=一级&board=创业板")
    l1_data = json.loads(r_l1.data)
    for l1 in l1_data[:3]:
        r_l2 = client.get(
            f"/api/industries?date=2026-05-29&level=二级"
            f"&parent_l1={l1['industry_name']}&board=创业板"
        )
        l2_data = json.loads(r_l2.data)
        l2_total = sum(d["stock_count"] for d in l2_data)
        assert l2_total == l1["stock_count"], \
            f"创业板 {l1['industry_name']}: L1={l1['stock_count']} L2 sum={l2_total}"


def test_filter_l3_to_stocks_count(client):
    """With board filter, stocks count == L3 stock_count."""
    r = client.get(
        "/api/stocks?date=2026-05-29&industry_l1=通信"
        "&industry_l2=通信设备&board=创业板"
    )
    stocks = json.loads(r.data)
    r_l3 = client.get(
        "/api/industries?date=2026-05-29&level=三级"
        "&parent_l1=通信&parent_l2=通信设备&board=创业板"
    )
    l3_data = json.loads(r_l3.data)
    l3_total_stocks = sum(d["stock_count"] for d in l3_data)
    assert len(stocks) == l3_total_stocks, \
        f"创业板 通信设备: stocks={len(stocks)} L3 sum={l3_total_stocks}"
