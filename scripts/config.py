"""중앙 설정 파일.

추적 자산 목록, 이동평균 윈도우, 이격도 구간 기준을 한 곳에서 관리한다.
새 종목을 추가하려면 ASSETS 리스트에 dict 한 줄만 추가하면 된다.
"""
from __future__ import annotations

from typing import Dict, List

# ---------------------------------------------------------------------------
# 이동평균 / 이격도 설정
# ---------------------------------------------------------------------------

# 계산할 이동평균 기간(일). disparity{w} 가 각 윈도우마다 생성된다.
MA_WINDOWS: List[int] = [20, 25, 50, 120]

# 메인 판단 지표로 사용할 이격도 윈도우.
# 개별종목은 25일, 지수/ETF/섹터 대용 지표는 50일 기준으로 과열 구간을 판단한다.
STOCK_PRIMARY_WINDOW: int = 25
DEFAULT_PRIMARY_WINDOW: int = 50

# ---------------------------------------------------------------------------
# 이격도 구간(zone) 기준
#   개별종목: disparity25 기준
#   지수/ETF/섹터 대용 지표: disparity50 기준
#   overheat  : 기준 이격도 >= 130            과열
#   caution   : 120 <= 기준 이격도 < 130      경계
#   normal    : 105 <  기준 이격도 < 120      정상
#   cooldown  : 기준 이격도 <= 105            과열해소
# 경계값을 바꾸고 싶으면 아래 숫자만 수정하면 된다.
# ---------------------------------------------------------------------------

ZONE_OVERHEAT_MIN: float = 130.0   # 이 값 이상이면 과열
ZONE_CAUTION_MIN: float = 120.0    # (과열이 아니고) 이 값 이상이면 경계
ZONE_NORMAL_MIN: float = 105.0     # (경계가 아니고) 이 값 '초과'면 정상, '이하'면 과열해소

ZONE_LABELS: Dict[str, str] = {
    "overheat": "과열",
    "caution": "경계",
    "normal": "정상",
    "cooldown": "과열해소",
}

# ---------------------------------------------------------------------------
# 데이터 검증 기준
# ---------------------------------------------------------------------------

# 기준 이격도가 이 범위를 벗어나면 "값 확인 필요(suspicious)" 플래그를 단다.
SUSPICIOUS_DISPARITY_MIN: float = 50.0
SUSPICIOUS_DISPARITY_MAX: float = 200.0

# 마지막 데이터가 today 기준 이 일수 이상 지났으면 "데이터 오래됨(stale)" 으로 본다.
# 정확한 휴장일 캘린더는 2차 기능. 주말 + 단기 연휴를 감안해 7일로 둔다.
STALE_DAYS: int = 7

# ---------------------------------------------------------------------------
# 데이터 수집 범위
# ---------------------------------------------------------------------------

# 국내(pykrx) 조회 시작일을 정하는 lookback (달력일 기준).
# 약 2년치를 받아서 ma120 워밍업 + 최근 1년 히스토리를 모두 커버한다.
KR_LOOKBACK_DAYS: int = 730

# 해외(yfinance) 조회 기간. yfinance period 문자열.
US_PERIOD: str = "2y"

# 히스토리(차트)로 내보낼 최근 기간(달력일). 약 1년.
HISTORY_DAYS: int = 365

# ---------------------------------------------------------------------------
# 추적 자산 목록
#   name       : 화면에 표시할 이름
#   code       : 식별 코드 (pykrx 티커 / yfinance 심볼)
#   market     : "KR" | "US" | "JP" | "TW" (조회/상장 시장)
#   country    : "KR" | "JP" | "TW" | "US" (화면 정렬용 국적)
#   sector     : 화면에 표시할 섹터/분류
#   asset_type : "kr_index" | "kr_stock" | "us_index" | "us_stock" | "jp_index" | "jp_stock" | "tw_index" | "tw_stock" | "semiconductor_index"
#   source     : "pykrx_index" | "pykrx_stock" | "yfinance"  (종가 모드에서 사용)
#   yf_ticker  : 장중(intraday) 모드에서 쓰는 yfinance 심볼
#                (국내 종목=<코드>.KS, 코스피=^KS11, 코스닥=^KQ11, 해외=code 그대로)
#   note       : 화면에 함께 보여줄 짧은 참고 문구(선택)
#   enabled    : False 이면 수집에서 제외 (코드 미확정 종목 등)
# ---------------------------------------------------------------------------

ASSETS: List[Dict] = [
    # ----- 국내 지수 (GitHub Actions 무인 실행 안정성을 위해 yfinance 사용) -----
    {"name": "코스피",     "code": "1001", "market": "KR", "country": "KR", "sector": "시장지수", "asset_type": "kr_index", "source": "yfinance", "yf_ticker": "^KS11",  "enabled": True},
    {"name": "코스피200",  "code": "1028", "market": "KR", "country": "KR", "sector": "시장지수", "asset_type": "kr_index", "source": "yfinance", "yf_ticker": "^KS200", "enabled": True},
    {"name": "코스닥",     "code": "2001", "market": "KR", "country": "KR", "sector": "시장지수", "asset_type": "kr_index", "source": "yfinance", "yf_ticker": "^KQ11",  "enabled": True},
    {"name": "한국 반도체", "code": "091160.KS", "market": "KR", "country": "KR", "sector": "반도체 ETF", "asset_type": "semiconductor_index", "source": "yfinance", "yf_ticker": "091160.KS", "note": "KODEX 반도체 ETF, 국내 반도체 지수 대용", "enabled": True},

    # ----- 국내 개별종목 (종가=pykrx / 장중=yfinance, 티커=<코드>.KS) -----
    {"name": "SK하이닉스", "code": "000660", "market": "KR", "country": "KR", "sector": "반도체", "asset_type": "kr_stock", "source": "pykrx_stock", "yf_ticker": "000660.KS", "enabled": True},
    {"name": "삼성전자",   "code": "005930", "market": "KR", "country": "KR", "sector": "반도체/전자", "asset_type": "kr_stock", "source": "pykrx_stock", "yf_ticker": "005930.KS", "enabled": True},
    {"name": "삼성전기",   "code": "009150", "market": "KR", "country": "KR", "sector": "전자부품", "asset_type": "kr_stock", "source": "pykrx_stock", "yf_ticker": "009150.KS", "enabled": True},
    {"name": "LG이노텍",   "code": "011070", "market": "KR", "country": "KR", "sector": "전자부품", "asset_type": "kr_stock", "source": "pykrx_stock", "yf_ticker": "011070.KS", "enabled": True},
    {"name": "SK스퀘어",   "code": "402340", "market": "KR", "country": "KR", "sector": "반도체 투자/지주", "asset_type": "kr_stock", "source": "pykrx_stock", "yf_ticker": "402340.KS", "enabled": True},
    {"name": "삼성물산",   "code": "028260", "market": "KR", "country": "KR", "sector": "지주/건설", "asset_type": "kr_stock", "source": "pykrx_stock", "yf_ticker": "028260.KS", "enabled": True},
    {"name": "파두",       "code": "440110", "market": "KR", "country": "KR", "sector": "반도체", "asset_type": "kr_stock", "source": "pykrx_stock", "yf_ticker": "440110.KQ", "enabled": True},
    # TODO: SOL AI반도체TOP2 PLUS ETF 종목코드를 확인해 code 와 yf_ticker(예: "473490.KS")를 채우고 enabled=True 로 변경.
    {"name": "SOL AI반도체TOP2 PLUS", "code": "TODO_FILL_ME", "market": "KR", "country": "KR", "sector": "반도체 ETF", "asset_type": "kr_stock", "source": "pykrx_stock", "yf_ticker": "TODO_FILL_ME", "enabled": False},

    # ----- 일본 지수/종목 (yfinance) -----
    {"name": "닛케이225", "code": "^N225", "market": "JP", "country": "JP", "sector": "시장지수", "asset_type": "jp_index", "source": "yfinance", "yf_ticker": "^N225", "note": "닛케이지수", "enabled": True},
    {"name": "닛케이 반도체", "code": "200A.T", "market": "JP", "country": "JP", "sector": "반도체 ETF", "asset_type": "semiconductor_index", "source": "yfinance", "yf_ticker": "200A.T", "note": "Nikkei Semiconductor Stock Index 추종 ETF", "enabled": True},
    {"name": "무라타제작소", "code": "6981.T", "market": "JP", "country": "JP", "sector": "전자부품", "asset_type": "jp_stock", "source": "yfinance", "yf_ticker": "6981.T", "enabled": True},
    {"name": "키옥시아", "code": "285A.T", "market": "JP", "country": "JP", "sector": "반도체", "asset_type": "jp_stock", "source": "yfinance", "yf_ticker": "285A.T", "enabled": True},

    # ----- 대만 지수/종목 (yfinance) -----
    {"name": "대만 가권지수", "code": "^TWII", "market": "TW", "country": "TW", "sector": "시장지수", "asset_type": "tw_index", "source": "yfinance", "yf_ticker": "^TWII", "enabled": True},
    {"name": "TSMC", "code": "TSM", "market": "US", "country": "TW", "sector": "반도체", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "TSM", "note": "TSMC ADR", "enabled": True},
    {"name": "UMC", "code": "2303.TW", "market": "TW", "country": "TW", "sector": "반도체", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "2303.TW", "note": "대만 보통주", "enabled": True},
    {"name": "미디어텍", "code": "2454.TW", "market": "TW", "country": "TW", "sector": "반도체", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "2454.TW", "enabled": True},
    {"name": "Alchip Technology", "code": "3661.TW", "market": "TW", "country": "TW", "sector": "반도체", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "3661.TW", "enabled": True},

    # ----- 미국 지수/종목 (종가·장중 모두 yfinance, yf_ticker = code) -----
    {"name": "S&P500",   "code": "^GSPC", "market": "US", "country": "US", "sector": "시장지수", "asset_type": "us_index", "source": "yfinance", "yf_ticker": "^GSPC", "enabled": True},
    {"name": "나스닥100", "code": "^NDX",  "market": "US", "country": "US", "sector": "시장지수", "asset_type": "us_index", "source": "yfinance", "yf_ticker": "^NDX",  "enabled": True},
    {"name": "PHLX 반도체", "code": "^SOX", "market": "US", "country": "US", "sector": "반도체 지수", "asset_type": "semiconductor_index", "source": "yfinance", "yf_ticker": "^SOX", "enabled": True},
    {"name": "마이크론",  "code": "MU",    "market": "US", "country": "US", "sector": "반도체", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "MU",    "enabled": True},
    {"name": "엔비디아",  "code": "NVDA",  "market": "US", "country": "US", "sector": "반도체", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "NVDA",  "enabled": True},
    {"name": "샌디스크",  "code": "SNDK",  "market": "US", "country": "US", "sector": "반도체", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "SNDK",  "enabled": True},
    {"name": "브로드컴",  "code": "AVGO",  "market": "US", "country": "US", "sector": "반도체", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "AVGO",  "enabled": True},
    {"name": "인텔",      "code": "INTC",  "market": "US", "country": "US", "sector": "반도체", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "INTC",  "enabled": True},
    {"name": "AMD",       "code": "AMD",   "market": "US", "country": "US", "sector": "반도체", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "AMD",   "enabled": True},
]


def enabled_assets() -> List[Dict]:
    """enabled=True 인 자산만 반환."""
    return [a for a in ASSETS if a.get("enabled", True)]
