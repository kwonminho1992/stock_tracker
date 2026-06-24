"""직렬화 안전성 + 자산 실패 격리 테스트."""
import json
import math

import pandas as pd

from indicators import round_or_none
from update import make_error_record, process_asset, sanitize_for_json


# --- NaN/Infinity 차단 ------------------------------------------------------

def test_round_or_none_blocks_naninf():
    assert round_or_none(float("nan")) is None
    assert round_or_none(float("inf")) is None
    assert round_or_none(float("-inf")) is None


def test_sanitize_replaces_nan_inf():
    payload = {
        "a": float("nan"),
        "b": float("inf"),
        "c": [1.0, float("-inf"), {"d": float("nan")}],
        "e": "ok",
        "f": 3,
    }
    clean = sanitize_for_json(payload)
    # allow_nan=False 로 직렬화해도 예외가 없어야 한다.
    text = json.dumps(clean, allow_nan=False)
    assert "NaN" not in text
    assert "Infinity" not in text
    assert clean["a"] is None
    assert clean["b"] is None
    assert clean["c"][1] is None
    assert clean["c"][2]["d"] is None
    assert clean["e"] == "ok"
    assert clean["f"] == 3


# --- 자산 실패 격리 ---------------------------------------------------------

ASSET = {
    "name": "테스트",
    "code": "TEST",
    "market": "KR",
    "asset_type": "kr_stock",
    "source": "pykrx_stock",
}


def _good_df(asset):
    idx = pd.date_range("2024-01-01", periods=200, freq="D")
    idx.name = "date"
    closes = [100.0 + i * 0.5 for i in range(200)]  # 완만한 상승
    return pd.DataFrame({"close": closes}, index=idx)


def _boom_df(asset):
    raise RuntimeError("네트워크 실패 시뮬레이션")


def _bad_close_df(asset):
    # 0 이하 종가 → validate_dataframe 에서 치명적 에러
    idx = pd.date_range("2024-01-01", periods=60, freq="D")
    idx.name = "date"
    return pd.DataFrame({"close": [0.0] * 60}, index=idx)


def test_asset_failure_isolation_on_exception():
    # fetch 가 예외를 던져도 process_asset 은 예외를 밖으로 내지 않는다.
    latest, hist = process_asset(ASSET, fetch_fn=_boom_df)
    assert "error" in latest
    assert hist is None
    assert latest["code"] == "TEST"
    assert "RuntimeError" in latest["error"]


def test_asset_failure_isolation_on_bad_data():
    latest, hist = process_asset(ASSET, fetch_fn=_bad_close_df)
    assert "error" in latest
    assert hist is None


def test_asset_success_serializes():
    latest, hist = process_asset(ASSET, fetch_fn=_good_df)
    assert "error" not in latest
    assert latest["disparity50"] is not None
    assert hist is not None
    code, entry = hist
    assert code == "TEST"
    assert len(entry["data"]) > 0
    # latest + history 모두 allow_nan=False 직렬화 통과해야 한다.
    json.dumps(latest, allow_nan=False)
    json.dumps(entry, allow_nan=False)


def test_full_payload_serializes_with_mixed_results():
    """정상 + 실패가 섞인 payload 가 allow_nan=False 로 직렬화되는지."""
    ok_latest, _ = process_asset(ASSET, fetch_fn=_good_df)
    err_latest, _ = process_asset(ASSET, fetch_fn=_boom_df)
    payload = {
        "updated_at": "2026-06-24T16:20:00+09:00",
        "run_type": "close",
        "assets": [ok_latest, err_latest],
    }
    clean = sanitize_for_json(payload)
    text = json.dumps(clean, ensure_ascii=False, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text


def test_make_error_record_shape():
    rec = make_error_record(ASSET, "사유")
    assert rec["error"] == "사유"
    assert rec["name"] == "테스트"
    assert rec["code"] == "TEST"
    # error 레코드에는 수치 필드가 없다.
    assert "close" not in rec
    assert "disparity50" not in rec


# --- 장중(intraday) 모드 가드 ----------------------------------------------

def test_intraday_requires_yf_ticker():
    """yf_ticker 없으면 장중 fetch 는 ValueError(네트워크/설치 무관하게 즉시)."""
    import pytest
    from data_sources import fetch_asset

    no_ticker = {
        "name": "코스피", "code": "1001", "market": "KR",
        "asset_type": "kr_index", "source": "pykrx_index",
    }
    with pytest.raises(ValueError):
        fetch_asset(no_ticker, run_type="intraday")

    # TODO 자리표시자도 거부
    with pytest.raises(ValueError):
        fetch_asset({**no_ticker, "yf_ticker": "TODO_FILL_ME"}, run_type="intraday")


def test_process_asset_intraday_missing_ticker_isolated():
    """장중 모드 + yf_ticker 미설정 → 예외 없이 error 레코드로 격리."""
    asset = {
        "name": "코스피", "code": "1001", "market": "KR",
        "asset_type": "kr_index", "source": "pykrx_index",
    }
    latest, hist = process_asset(asset, run_type="intraday")
    assert "error" in latest
    assert hist is None
    assert "yf_ticker" in latest["error"]
