"""데이터 소스 어댑터.

모든 fetch_* 함수는 '표준 DataFrame' 을 반환한다:
  - index : DatetimeIndex (tz-naive), name="date", 오름차순
  - column: 단일 "close" (float)

pykrx / yfinance 는 함수 내부에서 lazy import 한다.
→ 라이브러리 미설치 환경에서도 이 모듈 import 자체는 실패하지 않고,
  계산/직렬화 단위테스트를 돌릴 수 있다.
"""
from __future__ import annotations

import warnings
from datetime import datetime, timedelta
from typing import Dict, Tuple

import pandas as pd

from config import KR_LOOKBACK_DAYS, US_PERIOD

# pykrx(한글) / yfinance(영문) 양쪽을 모두 커버하는 종가 컬럼 후보.
CLOSE_CANDIDATES = ["종가", "Close", "close", "CLOSE"]


def _standardize(close_like, source: str) -> pd.DataFrame:
    """임의의 종가 시리즈/프레임을 표준 DataFrame(date index, close)으로 정규화."""
    if isinstance(close_like, pd.DataFrame):
        if close_like.shape[1] != 1:
            raise ValueError(
                f"[{source}] close 추출 결과가 단일 컬럼이 아닙니다: shape={close_like.shape}"
            )
        close_like = close_like.iloc[:, 0]

    s = pd.Series(close_like)
    values = pd.to_numeric(s, errors="coerce")
    idx = pd.to_datetime(s.index)

    out = pd.DataFrame({"close": values.to_numpy()}, index=idx)

    # tz 정보가 있으면 제거(일봉은 날짜만 의미 있음).
    if isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None:
        out.index = out.index.tz_localize(None)

    out.index.name = "date"
    out = out[~out.index.duplicated(keep="last")]
    out = out.sort_index()
    out = out.dropna(subset=["close"])
    if out.empty:
        raise ValueError(f"[{source}] 표준화 후 데이터가 비었습니다.")
    return out


def _kr_date_range() -> Tuple[str, str]:
    today = datetime.now()
    fromdate = (today - timedelta(days=KR_LOOKBACK_DAYS)).strftime("%Y%m%d")
    todate = today.strftime("%Y%m%d")
    return fromdate, todate


def _extract_close_column(df: pd.DataFrame, source: str) -> pd.Series:
    """pykrx 결과(단일 인덱스 컬럼)에서 종가 컬럼을 찾는다."""
    for col in CLOSE_CANDIDATES:
        if col in df.columns:
            return df[col]
    raise ValueError(
        f"[{source}] 종가 컬럼을 찾을 수 없습니다. "
        f"기대={CLOSE_CANDIDATES}, 실제={list(df.columns)}"
    )


def fetch_kr_index(asset: Dict) -> pd.DataFrame:
    """국내 지수: pykrx get_index_ohlcv 사용."""
    try:
        from pykrx import stock
    except ImportError as e:  # noqa: F841
        raise ImportError("pykrx 가 설치되지 않았습니다. `pip install pykrx`") from e

    fromdate, todate = _kr_date_range()
    getter = getattr(stock, "get_index_ohlcv", None) or getattr(
        stock, "get_index_ohlcv_by_date"
    )
    df = getter(fromdate, todate, asset["code"])
    if df is None or len(df) == 0:
        raise ValueError(
            f"[pykrx index {asset['code']}] 빈 데이터 (코드/기간 확인: {fromdate}~{todate})"
        )
    close = _extract_close_column(df, f"pykrx index {asset['code']}")
    return _standardize(close, f"pykrx index {asset['code']}")


def fetch_kr_stock(asset: Dict) -> pd.DataFrame:
    """국내 개별종목/ETF: pykrx get_market_ohlcv 사용."""
    try:
        from pykrx import stock
    except ImportError as e:
        raise ImportError("pykrx 가 설치되지 않았습니다. `pip install pykrx`") from e

    fromdate, todate = _kr_date_range()
    getter = getattr(stock, "get_market_ohlcv", None) or getattr(
        stock, "get_market_ohlcv_by_date"
    )
    df = getter(fromdate, todate, asset["code"])
    if df is None or len(df) == 0:
        raise ValueError(
            f"[pykrx stock {asset['code']}] 빈 데이터 (코드/기간 확인: {fromdate}~{todate})"
        )
    close = _extract_close_column(df, f"pykrx stock {asset['code']}")
    return _standardize(close, f"pykrx stock {asset['code']}")


def _extract_close_from_yf(df: pd.DataFrame, ticker: str) -> pd.Series:
    """yfinance 결과에서 Close 시리즈 추출. MultiIndex 컬럼도 처리한다."""
    if isinstance(df.columns, pd.MultiIndex):
        # 보통 ('Close', 'NVDA') 형태. 우선 정확히 매칭 시도.
        if ("Close", ticker) in df.columns:
            return df[("Close", ticker)]
        # level0 == 'Close' 인 것들 중 첫 컬럼.
        lvl0 = df.columns.get_level_values(0)
        if "Close" in lvl0:
            sub = df.xs("Close", axis=1, level=0)
            if isinstance(sub, pd.DataFrame):
                return sub.iloc[:, 0]
            return sub
        raise ValueError(
            f"[yfinance {ticker}] MultiIndex 에서 Close 를 찾을 수 없습니다: {list(df.columns)}"
        )
    # 단일 인덱스 컬럼.
    for col in CLOSE_CANDIDATES:
        if col in df.columns:
            return df[col]
    raise ValueError(f"[yfinance {ticker}] Close 컬럼 없음: {list(df.columns)}")


def _fetch_yf(ticker: str) -> pd.DataFrame:
    """yfinance 일봉을 받아 표준 DataFrame 으로 반환.

    장중에 호출하면 당일(진행중) 봉의 Close 가 '현재가(지연시세)'로 채워지므로,
    종가 모드와 장중 모드가 같은 함수를 공유한다.
    """
    try:
        import yfinance as yf
    except ImportError as e:
        raise ImportError("yfinance 가 설치되지 않았습니다. `pip install yfinance`") from e

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        df = yf.download(
            ticker,
            period=US_PERIOD,
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False,
        )
    if df is None or len(df) == 0:
        raise ValueError(f"[yfinance {ticker}] 빈 데이터 (심볼/네트워크 확인)")

    close = _extract_close_from_yf(df, ticker)
    out = _standardize(close, f"yfinance {ticker}")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            fast_info = yf.Ticker(ticker).fast_info
            previous_close = fast_info.get("previousClose")
        if previous_close is not None and pd.notna(previous_close):
            out.attrs["latest_previous_close"] = float(previous_close)
    except Exception:
        # quote 메타데이터가 실패해도 일봉 계산은 계속 진행한다.
        pass

    return out


def fetch_us(asset: Dict) -> pd.DataFrame:
    """해외 지수/종목: yfinance 사용(yf_ticker 없으면 code 사용)."""
    return _fetch_yf(asset.get("yf_ticker") or asset["code"])


def fetch_kr_stock_intraday(asset: Dict) -> pd.DataFrame:
    """국내 개별종목 장중 모드: pykrx 종가 히스토리에 yfinance 최신가만 보강.

    yfinance 국내 종목 히스토리는 일부 날짜가 KRX 종가와 어긋나는 경우가 있어,
    이동평균 계산용 과거 데이터는 pykrx 를 우선한다. 단, 장중에는 pykrx 에 당일 봉이
    없을 수 있으므로 yfinance 최신 행이 더 최신 날짜일 때만 추가한다.
    """
    base = fetch_kr_stock(asset)
    yf_df = _fetch_yf(asset.get("yf_ticker") or f"{asset['code']}.KS")

    out = base.copy()
    if not yf_df.empty:
        yf_last_date = yf_df.index[-1]
        base_last_date = out.index[-1]
        if yf_last_date > base_last_date:
            out.loc[yf_last_date, "close"] = yf_df["close"].iloc[-1]
            out = out.sort_index()
        out.attrs.update(yf_df.attrs)
    return out


_FETCHERS = {
    "pykrx_index": fetch_kr_index,
    "pykrx_stock": fetch_kr_stock,
    "yfinance": fetch_us,
}


def fetch_asset(asset: Dict, run_type: str = "close") -> pd.DataFrame:
    """run_type 과 asset['source'] 에 따라 적절한 fetch 함수로 라우팅.

    - run_type="close"    : 종가 모드. 국내=pykrx, 해외=yfinance.
    - run_type="intraday" : 장중 모드. 국내 개별종목은 pykrx 종가 히스토리에
      yfinance 최신가를 보강하고, 나머지는 yf_ticker 로 yfinance(지연시세) 조회.
    """
    if run_type == "intraday":
        yf_ticker = asset.get("yf_ticker")
        if not yf_ticker or str(yf_ticker).startswith("TODO"):
            raise ValueError(
                f"장중 모드에는 yf_ticker 가 필요합니다(미설정): {asset.get('name')}"
            )
        if asset.get("asset_type") == "kr_stock":
            return fetch_kr_stock_intraday(asset)
        return _fetch_yf(yf_ticker)

    source = asset.get("source")
    fetcher = _FETCHERS.get(source)
    if fetcher is None:
        # source 미지정 시 market/asset_type 으로 추론(하위호환).
        if asset.get("market") == "US":
            fetcher = fetch_us
        elif asset.get("asset_type") == "kr_index":
            fetcher = fetch_kr_index
        elif asset.get("asset_type") == "kr_stock":
            fetcher = fetch_kr_stock
        else:
            raise ValueError(
                f"알 수 없는 데이터 소스: source={source}, asset={asset.get('name')}"
            )
    return fetcher(asset)
