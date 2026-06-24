"""데이터 검증.

가장 중요한 원칙: 값이 의심스러우면 '조용히 정상처럼' 보여주지 않는다.
- 치명적 문제(close<=0, ma50<=0, ma50 계산불가) → 호출측에서 error 자산으로 처리하도록 메시지 반환
- 소프트 문제(이격도 비정상 범위, 데이터 오래됨) → 레코드에 플래그/경고를 단다
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd

from config import (
    STALE_DAYS,
    SUSPICIOUS_DISPARITY_MAX,
    SUSPICIOUS_DISPARITY_MIN,
)


class DataValidationError(Exception):
    """수집/계산 단계에서 더 진행할 수 없는 치명적 데이터 문제."""


def validate_dataframe(df: pd.DataFrame, min_rows: int = 2) -> None:
    """수집 직후의 원천 DataFrame 검증. 문제가 있으면 DataValidationError."""
    if df is None or df.empty:
        raise DataValidationError("데이터가 비어 있습니다.")
    if "close" not in df.columns:
        raise DataValidationError(f"'close' 컬럼이 없습니다. 컬럼={list(df.columns)}")
    if len(df) < min_rows:
        raise DataValidationError(f"데이터 행이 부족합니다(>= {min_rows} 필요): {len(df)}행")
    if df["close"].isna().all():
        raise DataValidationError("종가가 전부 NaN 입니다.")
    n_bad = int((df["close"] <= 0).sum())
    if n_bad > 0:
        raise DataValidationError(f"0 이하 종가가 {n_bad}건 존재합니다.")


def check_fatal(record: Dict) -> Optional[str]:
    """최신 레코드에 치명적 문제가 있으면 에러 메시지, 없으면 None.

    - close 값이 0 이하 → error
    - ma50 값이 None(계산불가) 또는 0 이하 → error
    """
    close = record.get("close")
    if close is None or close <= 0:
        return f"close 값이 비정상입니다: {close}"
    ma50 = record.get("ma50")
    if ma50 is None:
        return "ma50 계산 불가 (데이터 부족 가능성: 최소 50거래일 필요)"
    if ma50 <= 0:
        return f"ma50 값이 비정상입니다: {ma50}"
    return None


def _parse_date(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def apply_soft_flags(record: Dict, today: Optional[date] = None) -> Dict:
    """레코드에 is_suspicious / is_stale / warning 을 설정(in-place) 후 반환."""
    if today is None:
        today = date.today()

    warnings: List[str] = []

    # 1) 이격도 비정상 범위 → 값 확인 필요(suspicious)
    d50 = record.get("disparity50")
    suspicious = False
    if d50 is not None and (
        d50 < SUSPICIOUS_DISPARITY_MIN or d50 > SUSPICIOUS_DISPARITY_MAX
    ):
        suspicious = True
        warnings.append(
            f"disparity50 {d50} 가 정상범위"
            f"[{SUSPICIOUS_DISPARITY_MIN}, {SUSPICIOUS_DISPARITY_MAX}]를 벗어남"
        )

    # 2) 데이터 오래됨 → stale
    stale = False
    rec_date = _parse_date(record.get("date", ""))
    if rec_date is None:
        stale = True
        warnings.append("날짜를 해석할 수 없습니다.")
    else:
        age = (today - rec_date).days
        if age >= STALE_DAYS:
            stale = True
            warnings.append(f"마지막 데이터가 {age}일 전입니다(>= {STALE_DAYS}일).")

    record["is_suspicious"] = suspicious
    record["is_stale"] = stale
    record["warning"] = "; ".join(warnings) if warnings else None
    return record
