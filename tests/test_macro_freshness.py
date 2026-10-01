"""발표 지연, 중단 계열, 날짜 미확인을 실제 네트워크 없이 검증한다."""
import io
import json
from datetime import date, datetime, timedelta

import pytest

import fred_source
import update
from config import FRED_MACROS


TODAY = date(2026, 10, 1)


@pytest.mark.parametrize("frequency,limit", [("monthly", 120), ("quarterly", 240), ("annual", 550)])
def test_publication_cadence_allows_delay_but_flags_overdue_data(frequency, limit):
    within = update.macro_freshness((TODAY - timedelta(days=limit)).isoformat(), frequency, TODAY)
    overdue = update.macro_freshness((TODAY - timedelta(days=limit + 1)).isoformat(), frequency, TODAY)
    assert within["is_stale"] is False
    assert within["warning"] is None
    assert overdue["is_stale"] is True
    assert overdue["macro_age_days"] == limit + 1
    assert overdue["macro_stale_after_days"] == limit
    assert overdue["macro_freshness"] == "stale"
    assert str(limit) in overdue["warning"]


def test_old_korean_m2_is_not_fresh_after_a_successful_fetch(monkeypatch):
    item = next(item for item in FRED_MACROS if item["series_id"] == "MYAGM2KRM189S")
    monkeypatch.setattr(update, "now_kst", lambda: datetime(2026, 10, 1, tzinfo=update.KST))
    monkeypatch.setattr(update, "fetch_fred_latest", lambda *_args, **_kwargs: {
        "value": 2457795500000000, "yoy_pct": 6.4, "asof": "2017-05-01",
        "frequency": "monthly", "source_updated_at": "2026-10-01 09:00:00-05",
    })
    record = update._fred_macro_record(item)
    assert record["date"] == "2017-05-01"
    assert record["close"] == 6.4
    assert record["is_stale"] is True
    assert record["macro_age_days"] > 3000
    assert record["macro_source_updated_at"].startswith("2026-10-01")
    assert "2017-05-01" in record["warning"]


def test_annual_data_does_not_use_stock_price_freshness_rules():
    result = update.macro_freshness("2025-04-01", "A", TODAY)
    assert result["macro_frequency"] == "annual"
    assert result["macro_age_days"] == 548
    assert result["is_stale"] is False


@pytest.mark.parametrize("asof,frequency", [(None, "monthly"), ("bad-date", "monthly"), ("2026-10-02", "monthly"), ("2026-09-01", None)])
def test_unverifiable_observation_does_not_look_fresh(asof, frequency):
    result = update.macro_freshness(asof, frequency, TODAY)
    assert result["is_stale"] is True
    assert result["macro_freshness"] == "unknown"
    assert "검증 불가" in result["warning"]


def test_discontinued_series_is_flagged_even_with_a_recent_date():
    result = update.macro_freshness("2026-09-01", "monthly", TODAY, discontinued=True)
    assert result["is_stale"] is True
    assert result["macro_discontinued"] is True
    assert result["macro_freshness"] == "stale"
    assert "중단한 계열" in result["warning"]


def test_link_fallback_explicitly_has_no_value_or_verified_freshness():
    record = update._macro_link_record({"name": "테스트", "frequency": "monthly"}, "FRED", "조회 실패")
    assert record["link_only"] is True
    assert record["close"] is None
    assert record["date"] is None
    assert record["is_stale"] is None
    assert record["macro_age_days"] is None
    assert record["macro_freshness"] == "unavailable"
    assert "수치 미수집" in record["warning"]


def test_source_page_update_is_not_treated_as_a_verified_observation(monkeypatch):
    monkeypatch.setattr(update, "fetch_tradingeconomics", lambda _item: {"value": 2.0, "asof": TODAY.isoformat()})
    record = update._external_macro_record({"name": "테스트", "frequency": "monthly"})
    assert record["macro_date_type"] == "source_update"
    assert record["macro_freshness"] == "unknown"
    assert record["is_stale"] is True
    assert "관측기간 미확인" in record["warning"]


def test_external_fetch_failure_falls_back_instead_of_aborting_update(monkeypatch):
    def fail(_item):
        raise OSError("mock network failure")
    monkeypatch.setattr(update, "fetch_tradingeconomics", fail)
    record = update._external_macro_record({"name": "테스트"})
    assert record["link_only"] is True
    assert record["close"] is None


def _response(payload):
    return io.BytesIO(json.dumps(payload).encode("utf-8"))


def test_fred_metadata_exposes_frequency_and_source_dates(monkeypatch):
    responses = iter([
        {"observations": [{"date": "2026-09-01", "value": "120"}]},
        {"seriess": [{"frequency_short": "M", "frequency": "Monthly", "observation_end": "2026-09-01",
                     "last_updated": "2026-09-30 08:00:00-05", "title": "Example (DISCONTINUED)"}]},
    ])
    monkeypatch.setattr(fred_source, "api_key", lambda: "mock-key")
    monkeypatch.setattr(fred_source.urllib.request, "urlopen", lambda *_args, **_kwargs: _response(next(responses)))
    result = fred_source.fetch_latest("EXAMPLE")
    assert result["frequency"] == "monthly"
    assert result["source_updated_at"] == "2026-09-30 08:00:00-05"
    assert result["series_end"] == "2026-09-01"
    assert result["is_discontinued"] is True
    assert result["value"] == 120


def test_metadata_failure_keeps_successful_observation(monkeypatch):
    def fetch(request, **_kwargs):
        if "/observations?" in request.full_url:
            return _response({"observations": [{"date": "2026-09-01", "value": "3.5"}]})
        raise OSError("mock metadata outage")
    monkeypatch.setattr(fred_source, "api_key", lambda: "mock-key")
    monkeypatch.setattr(fred_source.urllib.request, "urlopen", fetch)
    result = fred_source.fetch_latest("EXAMPLE")
    assert result["value"] == 3.5
    assert result["asof"] == "2026-09-01"


def test_projection_series_is_labeled_when_metadata_is_unavailable(monkeypatch):
    item = next(item for item in FRED_MACROS if item["series_id"] == "TWNPCPIPCPPPT")
    monkeypatch.setattr(update, "fetch_fred_latest", lambda *_args, **_kwargs: {
        "value": 1.7, "asof": "2026-01-01", "yoy_pct": None,
    })
    record = update._fred_macro_record(item)
    assert record["macro_is_projection"] is True
    assert record["macro_frequency"] == "annual"
    assert "전망" in record["name"]
    assert "전망치" in record["warning"]


def test_korean_discount_rate_is_not_named_bok_base_rate():
    item = next(item for item in FRED_MACROS if item["series_id"] == "INTDSRKRM193N")
    assert item["name"] == "한국 할인율(IMF)"
    assert "한국은행 기준금리와 다른 계열" in item["desc"]
