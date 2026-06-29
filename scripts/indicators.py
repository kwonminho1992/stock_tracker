"""이동평균 / 이격도 / 구간분류 / 레코드 빌더.

순수 계산 로직만 둔다(네트워크·파일 IO 없음) → 단위테스트가 쉽다.
"""
from __future__ import annotations

import math
from datetime import timedelta
from typing import Dict, List, Optional

import pandas as pd

from config import (
    DEFAULT_PRIMARY_WINDOW,
    HISTORY_DAYS,
    STOCK_PRIMARY_WINDOW,
    ZONE_CAUTION_MIN,
    ZONE_LABELS,
    ZONE_NORMAL_MIN,
    ZONE_OVERHEAT_MIN,
)


def is_individual_stock(asset: Dict) -> bool:
    """개별 종목이면 True. 섹터 ETF/지수 대용 지표는 False."""
    return str(asset.get("asset_type", "")).endswith("_stock")


def primary_window_for_asset(asset: Dict) -> int:
    """과열 구간 판정에 사용할 이격도 기간."""
    return STOCK_PRIMARY_WINDOW if is_individual_stock(asset) else DEFAULT_PRIMARY_WINDOW


def add_moving_averages(df: pd.DataFrame, windows: List[int]) -> pd.DataFrame:
    """close 컬럼으로부터 ma{w} 컬럼들을 추가한 새 DataFrame 반환.

    min_periods=w 로 두어, 데이터가 부족한 구간의 이동평균은 NaN 으로 남긴다.
    (부분 평균으로 '조용히 틀린 값'이 나오는 것을 방지)
    """
    if "close" not in df.columns:
        raise ValueError(
            f"add_moving_averages: 'close' 컬럼이 필요합니다. 현재 컬럼={list(df.columns)}"
        )
    out = df.copy()
    for w in windows:
        out[f"ma{w}"] = out["close"].rolling(window=w, min_periods=w).mean()
    return out


def add_disparities(df: pd.DataFrame, windows: List[int]) -> pd.DataFrame:
    """ma{w} 컬럼으로부터 disparity{w} = close / ma{w} * 100 을 추가."""
    out = df.copy()
    for w in windows:
        ma_col = f"ma{w}"
        if ma_col not in out.columns:
            raise ValueError(
                f"add_disparities: '{ma_col}' 컬럼이 없습니다. "
                f"add_moving_averages 를 먼저 호출하세요."
            )
        ma = out[ma_col]
        # ma 가 NaN 이면 결과도 NaN, ma 가 0 이면 inf 가 되는데
        # 이후 round_or_none / sanitize 단계에서 모두 None 으로 정리된다.
        out[f"disparity{w}"] = out["close"] / ma * 100.0
    return out


def classify_zone(disparity: Optional[float]) -> Optional[str]:
    """기준 이격도 값을 구간 코드로 분류. 값이 없거나 비정상이면 None.

    경계:
      >= 130            -> overheat
      120 <= x < 130    -> caution
      105 <  x < 120    -> normal
      x <= 105          -> cooldown
    """
    if disparity is None:
        return None
    try:
        d = float(disparity)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(d):
        return None
    if d >= ZONE_OVERHEAT_MIN:
        return "overheat"
    if d >= ZONE_CAUTION_MIN:
        return "caution"
    if d > ZONE_NORMAL_MIN:
        return "normal"
    return "cooldown"


def zone_label(zone: Optional[str]) -> Optional[str]:
    if zone is None:
        return None
    return ZONE_LABELS.get(zone)


def round_or_none(value, ndigits: int = 2) -> Optional[float]:
    """숫자를 반올림해서 반환. None/NaN/Inf/변환불가 → None.

    JSON 에 NaN/Infinity 가 절대 들어가지 않도록 하는 1차 방어선.
    """
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return round(f, ndigits)


def _cell(row: pd.Series, col: str):
    """Series(행)에서 컬럼 값을 안전하게 꺼낸다(없으면 None)."""
    return row[col] if col in row.index else None


def build_latest_record(asset: Dict, df: pd.DataFrame) -> Dict:
    """이동평균/이격도가 계산된 df 의 마지막 행으로 최신 레코드(dict) 생성.

    품질 플래그(is_stale/is_suspicious/warning)는 기본값으로 채우고,
    validate_data.apply_soft_flags 에서 갱신한다.
    """
    if df is None or df.empty:
        raise ValueError("build_latest_record: 비어 있는 DataFrame")

    last = df.iloc[-1]
    last_date = df.index[-1]
    primary_window = primary_window_for_asset(asset)

    close = round_or_none(_cell(last, "close"))

    # 등락률: 직전 종가 대비.
    change_pct: Optional[float] = None
    if len(df) >= 2 and close is not None:
        prev_close = df.attrs.get("latest_previous_close", df["close"].iloc[-2])
        if pd.notna(prev_close) and float(prev_close) > 0:
            change_pct = (close / float(prev_close) - 1.0) * 100.0

    d25 = round_or_none(_cell(last, "disparity25"))
    d50 = round_or_none(_cell(last, "disparity50"))
    primary_disparity = round_or_none(_cell(last, f"disparity{primary_window}"))
    zone = classify_zone(primary_disparity)

    # 프리장/애프터마켓 시세(미국 상장 종목만). 이격도 계산엔 미반영, 표시용.
    extended_session = df.attrs.get("extended_session")
    extended_price = round_or_none(df.attrs.get("extended_price"))
    extended_change_pct = round_or_none(df.attrs.get("extended_change_pct"))

    return {
        "name": asset["name"],
        "code": asset["code"],
        "ticker": asset.get("yf_ticker") or asset["code"],
        "market": asset["market"],
        "country": asset.get("country", asset.get("market")),
        "sector": asset.get("sector"),
        "asset_type": asset["asset_type"],
        "source": asset.get("source"),
        "note": asset.get("note"),
        # AI 병목 밸류체인 분류(화면 정렬·필터·표시용)
        "sort_order": asset.get("sort_order", 9999),
        "ai_group": asset.get("ai_group"),
        "ai_subgroup": asset.get("ai_subgroup"),
        "product_group": asset.get("product_group"),
        "exposure_type": asset.get("exposure_type"),
        "date": pd.Timestamp(last_date).strftime("%Y-%m-%d"),
        "close": close,
        "ma20": round_or_none(_cell(last, "ma20")),
        "ma25": round_or_none(_cell(last, "ma25")),
        "ma50": round_or_none(_cell(last, "ma50")),
        "ma120": round_or_none(_cell(last, "ma120")),
        "disparity20": round_or_none(_cell(last, "disparity20")),
        "disparity25": d25,
        "disparity50": d50,
        "disparity120": round_or_none(_cell(last, "disparity120")),
        "primary_window": primary_window,
        "primary_disparity": primary_disparity,
        "change_pct": round_or_none(change_pct),
        "market_state": df.attrs.get("market_state"),
        "extended_session": extended_session,
        "extended_price": extended_price,
        "extended_change_pct": extended_change_pct,
        "zone": zone,
        "zone_label": zone_label(zone),
        "is_stale": False,
        "is_suspicious": False,
        "warning": None,
    }


def build_history_records(
    asset: Dict, df: pd.DataFrame, history_days: int = HISTORY_DAYS
) -> List[Dict]:
    """최근 history_days 일의 이격도 히스토리 레코드 리스트 생성.

    판정 기준 이격도가 NaN 인 (워밍업) 구간은 제외한다.
    """
    primary_window = primary_window_for_asset(asset)
    primary_col = f"disparity{primary_window}"
    if df is None or df.empty or primary_col not in df.columns:
        return []

    sub = df.dropna(subset=[primary_col])
    if sub.empty:
        return []

    last_date = pd.Timestamp(sub.index[-1])
    cutoff = last_date - timedelta(days=int(history_days))
    sub = sub[sub.index >= cutoff]

    records: List[Dict] = []
    for idx, row in sub.iterrows():
        d25 = round_or_none(row.get("disparity25"))
        d50 = round_or_none(row.get("disparity50"))
        primary_disparity = round_or_none(row.get(primary_col))
        if primary_disparity is None:
            continue
        records.append(
            {
                "date": pd.Timestamp(idx).strftime("%Y-%m-%d"),
                "close": round_or_none(row.get("close")),
                "ma25": round_or_none(row.get("ma25")),
                "ma50": round_or_none(row.get("ma50")),
                "disparity25": d25,
                "disparity50": d50,
                "primary_disparity": primary_disparity,
                "zone": classify_zone(primary_disparity),
            }
        )
    return records
