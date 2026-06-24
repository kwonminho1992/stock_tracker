"""계산 로직 단위테스트 (실제 API 호출 없음, mock DataFrame 사용)."""
import math

import pandas as pd
import pytest

from indicators import (
    add_disparities,
    add_moving_averages,
    build_history_records,
    build_latest_record,
    classify_zone,
    round_or_none,
)


def _make_df(closes, start="2025-01-01"):
    idx = pd.date_range(start=start, periods=len(closes), freq="D")
    idx.name = "date"
    return pd.DataFrame({"close": [float(c) for c in closes]}, index=idx)


# --- 이동평균 ---------------------------------------------------------------

def test_moving_average_basic():
    df = _make_df([10, 20, 30, 40, 50])
    out = add_moving_averages(df, [5])
    # 처음 4개는 NaN(min_periods=5), 마지막은 평균 30
    assert math.isnan(out["ma5"].iloc[0])
    assert out["ma5"].iloc[-1] == pytest.approx(30.0)


def test_moving_average_min_periods_nan():
    # 데이터가 윈도우보다 적으면 전부 NaN (부분평균 금지)
    df = _make_df([1, 2, 3])
    out = add_moving_averages(df, [50])
    assert out["ma50"].isna().all()


# --- 이격도 -----------------------------------------------------------------

def test_disparity_calc():
    df = _make_df([10, 20, 30, 40, 50])
    out = add_moving_averages(df, [5])
    out = add_disparities(out, [5])
    # close=50, ma5=30 → 50/30*100
    assert out["disparity5"].iloc[-1] == pytest.approx(50 / 30 * 100)


def test_disparity_value_100_when_close_equals_ma():
    df = _make_df([20, 20, 20, 20, 20])
    out = add_disparities(add_moving_averages(df, [5]), [5])
    assert out["disparity5"].iloc[-1] == pytest.approx(100.0)


# --- 구간 분류 --------------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        (135, "overheat"),
        (130, "overheat"),     # 경계값: 130 이상 = 과열
        (129.99, "caution"),
        (120, "caution"),      # 경계값: 120 이상 = 경계
        (119.99, "normal"),
        (105.01, "normal"),
        (105, "cooldown"),     # 경계값: 105 이하 = 과열해소
        (90, "cooldown"),
    ],
)
def test_classify_zone_boundaries(value, expected):
    assert classify_zone(value) == expected


def test_classify_zone_invalid():
    assert classify_zone(None) is None
    assert classify_zone(float("nan")) is None
    assert classify_zone(float("inf")) is None
    assert classify_zone("xx") is None


# --- round_or_none ----------------------------------------------------------

def test_round_or_none():
    assert round_or_none(1.23456) == 1.23
    assert round_or_none(None) is None
    assert round_or_none(float("nan")) is None
    assert round_or_none(float("inf")) is None
    assert round_or_none(float("-inf")) is None
    assert round_or_none("abc") is None


# --- 레코드 빌더 ------------------------------------------------------------

def test_build_latest_record_fields():
    closes = list(range(100, 100 + 60))  # 60일치 단조 증가
    df = _make_df(closes)
    df = add_moving_averages(df, [20, 50, 120])
    df = add_disparities(df, [20, 50, 120])
    asset = {"name": "테스트", "code": "T", "market": "KR", "asset_type": "kr_stock"}
    rec = build_latest_record(asset, df)

    assert rec["close"] is not None
    assert rec["ma50"] is not None
    assert rec["disparity50"] is not None
    # ma120 은 60행뿐이라 계산 불가 → None
    assert rec["ma120"] is None
    assert rec["disparity120"] is None
    # 모든 수치는 finite 이거나 None
    for k in ["close", "ma20", "ma50", "disparity20", "disparity50", "change_pct"]:
        v = rec[k]
        assert v is None or math.isfinite(v)
    assert rec["zone"] in {"overheat", "caution", "normal", "cooldown"}
    assert rec["is_stale"] is False  # apply_soft_flags 호출 전 기본값


def test_build_latest_record_change_pct():
    df = _make_df([100, 110])  # +10%
    df = add_moving_averages(df, [2])
    df = add_disparities(df, [2])
    asset = {"name": "T", "code": "T", "market": "KR", "asset_type": "kr_stock"}
    rec = build_latest_record(asset, df)
    assert rec["change_pct"] == pytest.approx(10.0)


def test_build_history_records_skips_warmup():
    closes = list(range(100, 100 + 60))
    df = _make_df(closes)
    df = add_moving_averages(df, [50])
    df = add_disparities(df, [50])
    asset = {"name": "테스트", "code": "T", "market": "KR", "asset_type": "kr_stock"}
    hist = build_history_records(asset, df, history_days=3650)
    # 60행 - 49(warmup) = 11개의 disparity50 존재
    assert len(hist) == 11
    for row in hist:
        assert row["disparity50"] is not None
        assert row["zone"] is not None
        assert set(row.keys()) == {"date", "close", "ma50", "disparity50", "zone"}
