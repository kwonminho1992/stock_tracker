"""데이터 소스 어댑터.

모든 fetch_* 함수는 '표준 DataFrame' 을 반환한다:
  - index : DatetimeIndex (tz-naive), name="date", 오름차순
  - column: 단일 "close" (float)

FinanceDataReader / yfinance 는 함수 내부에서 lazy import 한다.
→ 라이브러리 미설치 환경에서도 이 모듈 import 자체는 실패하지 않고,
  계산/직렬화 단위테스트를 돌릴 수 있다.
"""
from __future__ import annotations

import warnings
from datetime import datetime, timedelta
from typing import Dict, Tuple

import pandas as pd

from config import KR_LOOKBACK_DAYS, US_PERIOD

# KRX(한글 '종가') / yfinance·FDR(영문 'Close') 양쪽을 커버하는 종가 컬럼 후보.
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
    """결과 DataFrame 에서 종가 컬럼을 찾는다(KRX '종가' / yfinance·FDR 'Close')."""
    for col in CLOSE_CANDIDATES:
        if col in df.columns:
            return df[col]
    raise ValueError(
        f"[{source}] 종가 컬럼을 찾을 수 없습니다. "
        f"기대={CLOSE_CANDIDATES}, 실제={list(df.columns)}"
    )


def _fetch_fdr(symbol: str) -> pd.DataFrame:
    """FinanceDataReader 로 일봉을 받아 표준 DataFrame(date index, close)으로 반환.

    국내(KRX) 종목·지수를 안정적으로 커버한다. 비조정가(실제 체결가) 기준이라
    기존 pykrx 와 동일한 기준선을 유지한다(분할조정 불일치 없음).
    """
    try:
        import FinanceDataReader as fdr
    except ImportError as e:
        raise ImportError(
            "FinanceDataReader 가 설치되지 않았습니다. `pip install finance-datareader`"
        ) from e

    fromdate, _ = _kr_date_range()  # YYYYMMDD
    start = f"{fromdate[:4]}-{fromdate[4:6]}-{fromdate[6:]}"
    df = fdr.DataReader(symbol, start)
    if df is None or len(df) == 0:
        raise ValueError(f"[FDR {symbol}] 빈 데이터 (심볼/네트워크 확인)")
    close = _extract_close_column(df, f"FDR {symbol}")
    return _standardize(close, f"FDR {symbol}")


def fetch_kr_index(asset: Dict) -> pd.DataFrame:
    """국내 지수: FinanceDataReader 사용(심볼은 ^ 없이 KS11/KQ11 등)."""
    return _fetch_fdr(str(asset["code"]).lstrip("^"))


def fetch_kr_stock(asset: Dict) -> pd.DataFrame:
    """국내 개별종목: FinanceDataReader 사용(6자리 종목코드)."""
    return _fetch_fdr(asset["code"])


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


def _quote_date(info: Dict):
    """quote 의 regularMarketTime 을 거래소 현지 날짜로 변환. 실패 시 None."""
    ts = info.get("regularMarketTime")
    if not ts:
        return None
    try:
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo

        tz_name = info.get("exchangeTimezoneName")
        tz = ZoneInfo(tz_name) if tz_name else None
        return _dt.fromtimestamp(int(ts), tz).date()
    except Exception:
        return None


def _reconcile_with_quote(info: Dict, out: pd.DataFrame, source: str) -> None:
    """야후 '차트' 일봉을 '쿼트'(regularMarketPrice/Time)와 정합시킨다(in-place).

    야후 차트 엔드포인트는 일부 지수(^KS200, ^TNX, ^N225 등)에서 며칠씩
    뒤처진 봉을 주는 경우가 있다. 쿼트 엔드포인트는 신선하므로:
      - 쿼트 날짜 > 마지막 봉 날짜 → 쿼트 가격으로 새 봉 추가(최신화)
      - 쿼트 날짜 = 마지막 봉 날짜 → 마지막 봉을 쿼트 가격으로 갱신
      - 쿼트 날짜 < 마지막 봉 날짜 → 쿼트보다 미래의 봉 제거(휴장일 유령 봉 방어)
    """
    price = info.get("regularMarketPrice")
    qdate = _quote_date(info)
    if price is None or pd.isna(price) or qdate is None or out.empty:
        return
    price = float(price)
    if price <= 0:
        return
    qts = pd.Timestamp(qdate)
    last_ts = out.index[-1]
    if qts > last_ts:
        out.loc[qts, "close"] = price
        out.sort_index(inplace=True)
    elif qts == last_ts:
        out.iloc[-1, out.columns.get_loc("close")] = price
    else:
        # 차트가 쿼트보다 미래 봉을 갖고 있음(휴장일 유령 봉 등) → 잘라낸다.
        drop = out.index > qts
        if drop.any():
            out.drop(out.index[drop], inplace=True)


def _attach_extended_quote(info: Dict, out: pd.DataFrame) -> None:
    """프리장/애프터마켓(시간외) 시세를 out.attrs 에 보강.

    야후는 '미국 상장 종목'에만 pre/post 가격을 준다(지수·한/일/대만은 null).
    이격도 계산에는 쓰지 않고, 화면 '가격' 표시용으로만 들고 간다.
    실패해도 일봉 계산은 그대로 진행한다.
    """
    state = info.get("marketState")
    out.attrs["market_state"] = state

    session = price = change = None
    if state == "PRE" and info.get("preMarketPrice") is not None:
        session, price, change = (
            "pre",
            info.get("preMarketPrice"),
            info.get("preMarketChangePercent"),
        )
    elif state in ("POST", "POSTPOST") and info.get("postMarketPrice") is not None:
        session, price, change = (
            "post",
            info.get("postMarketPrice"),
            info.get("postMarketChangePercent"),
        )

    if session and price is not None and pd.notna(price):
        out.attrs["extended_session"] = session
        out.attrs["extended_price"] = float(price)
        # 야후 pre/postMarketChangePercent 는 이미 % 단위(직전 정규장 종가 대비).
        if change is not None and pd.notna(change):
            out.attrs["extended_change_pct"] = float(change)


def _fetch_yf(ticker: str, want_extended: bool = False) -> pd.DataFrame:
    """yfinance 일봉을 받아 표준 DataFrame 으로 반환.

    장중에 호출하면 당일(진행중) 봉의 Close 가 '현재가(지연시세)'로 채워지므로,
    종가 모드와 장중 모드가 같은 함수를 공유한다.

    want_extended=True 면(미국 상장 종목) 프리/애프터마켓 시세도 attrs 에 보강한다.
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
            info = yf.Ticker(ticker).info or {}
        # 차트 일봉이 뒤처졌으면 쿼트로 최신화(지수 며칠 지연·유령 봉 방어).
        _reconcile_with_quote(info, out, f"yfinance {ticker}")
        previous_close = info.get("regularMarketPreviousClose")
        if previous_close is not None and pd.notna(previous_close):
            out.attrs["latest_previous_close"] = float(previous_close)
        if want_extended:
            _attach_extended_quote(info, out)
    except Exception:
        # quote 메타데이터가 실패해도 일봉 계산은 계속 진행한다.
        pass

    return out


def wants_extended_quote(asset: Dict) -> bool:
    """프리/애프터마켓 시세를 받을 대상인지: 미국 상장 개별종목(미국주 + TSMC ADR)."""
    return asset.get("market") == "US" and str(asset.get("asset_type", "")).endswith(
        "_stock"
    )


def fetch_us(asset: Dict) -> pd.DataFrame:
    """해외 지수/종목: yfinance 사용(yf_ticker 없으면 code 사용)."""
    return _fetch_yf(
        asset.get("yf_ticker") or asset["code"],
        want_extended=wants_extended_quote(asset),
    )


def fetch_kr_intraday(asset: Dict) -> pd.DataFrame:
    """국내 종목/지수 장중 모드: FDR(KRX) 히스토리에 yfinance 쿼트 최신가만 보강.

    yfinance 국내 히스토리는 일부 날짜가 KRX 종가와 어긋나거나 며칠 뒤처지는
    경우가 있어, 이동평균 계산용 과거 데이터는 FDR(KRX) 를 우선한다.
    단, 장중에는 FDR 에 당일 봉이 없을 수 있으므로 yfinance 쿼트가 더 최신
    날짜일 때만 추가한다(같은 날짜면 KRX 공식값 유지).
    """
    if asset.get("asset_type") == "kr_stock":
        out = fetch_kr_stock(asset).copy()
    else:
        out = fetch_kr_index(asset).copy()

    try:
        import yfinance as yf

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            info = yf.Ticker(asset.get("yf_ticker") or f"{asset['code']}.KS").info or {}
        price = info.get("regularMarketPrice")
        qdate = _quote_date(info)
        if price is not None and pd.notna(price) and float(price) > 0 and qdate:
            qts = pd.Timestamp(qdate)
            if qts > out.index[-1]:
                out.loc[qts, "close"] = float(price)
                out = out.sort_index()
        previous_close = info.get("regularMarketPreviousClose")
        if previous_close is not None and pd.notna(previous_close):
            out.attrs["latest_previous_close"] = float(previous_close)
    except Exception:
        # 쿼트 보강 실패 시 FDR(KRX) 데이터만으로 진행한다.
        pass
    return out


_FETCHERS = {
    "krx_index": fetch_kr_index,
    "krx_stock": fetch_kr_stock,
    "yfinance": fetch_us,
}


def fetch_asset(asset: Dict, run_type: str = "close") -> pd.DataFrame:
    """run_type 과 asset['source'] 에 따라 적절한 fetch 함수로 라우팅.

    - run_type="close"    : 종가 모드. 국내=FDR(KRX), 해외=yfinance.
    - run_type="intraday" : 장중 모드. 국내 종목/지수는 FDR(KRX) 히스토리에
      yfinance 쿼트 최신가를 보강하고, 나머지는 yf_ticker 로 yfinance(지연시세) 조회.
    """
    if run_type == "intraday":
        yf_ticker = asset.get("yf_ticker")
        if not yf_ticker or str(yf_ticker).startswith("TODO"):
            raise ValueError(
                f"장중 모드에는 yf_ticker 가 필요합니다(미설정): {asset.get('name')}"
            )
        if asset.get("asset_type") == "kr_stock" or asset.get("source") in (
            "krx_index",
            "krx_stock",
        ):
            return fetch_kr_intraday(asset)
        return _fetch_yf(yf_ticker, want_extended=wants_extended_quote(asset))

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
