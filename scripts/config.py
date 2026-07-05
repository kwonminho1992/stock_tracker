"""중앙 설정 파일 — AI 병목 밸류체인 대시보드.

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
# 개별종목은 25일, 지수/벤치마크는 50일 기준으로 과열 구간을 판단한다.
STOCK_PRIMARY_WINDOW: int = 25
DEFAULT_PRIMARY_WINDOW: int = 50

# ---------------------------------------------------------------------------
# 이격도 구간(zone) 기준
#   개별종목: disparity25 기준 / 지수·벤치마크: disparity50 기준
#   overheat  : 기준 이격도 >= 130            과열
#   caution   : 120 <= 기준 이격도 < 130      경계
#   normal    : 105 <  기준 이격도 < 120      정상
#   cooldown  : 기준 이격도 <= 105            과열해소
# ---------------------------------------------------------------------------

ZONE_OVERHEAT_MIN: float = 130.0
ZONE_CAUTION_MIN: float = 120.0
ZONE_NORMAL_MIN: float = 105.0

ZONE_LABELS: Dict[str, str] = {
    "overheat": "과열",
    "caution": "경계",
    "normal": "정상",
    "cooldown": "과열해소",
}

# ---------------------------------------------------------------------------
# 데이터 검증 기준
# ---------------------------------------------------------------------------

SUSPICIOUS_DISPARITY_MIN: float = 50.0
SUSPICIOUS_DISPARITY_MAX: float = 200.0
STALE_DAYS: int = 7

# ---------------------------------------------------------------------------
# 데이터 수집 범위
# ---------------------------------------------------------------------------

KR_LOOKBACK_DAYS: int = 730
US_PERIOD: str = "2y"
HISTORY_DAYS: int = 365

# ---------------------------------------------------------------------------
# AI 병목 밸류체인 대분류(화면 정렬 순서). 표는 이 순서대로, 그룹 안에서는
# sort_order 오름차순으로 표시한다.
# ---------------------------------------------------------------------------

AI_GROUP_ORDER: List[str] = [
    "00_INDEX",
    "01_AI_COMPUTE_ASIC",
    "02_MEMORY_STORAGE",
    "03_FOUNDRY_MANUFACTURING",
    "04_EQUIPMENT_TEST",
    "05_PACKAGING_SUBSTRATE_PCB",
    "06_MLCC_PASSIVE_COMPONENT",
    "07_NETWORK_OPTICAL",
    "08_POWER_COOLING_GRID",
    "09_AI_SERVER_ODM",
    "10_INDIRECT_HOLDING",
]

# ---------------------------------------------------------------------------
# 추적 자산 목록
#   name         : 화면에 표시할 이름
#   code         : 식별 코드 (KRX 6자리 / yfinance 심볼)
#   market       : 조회/상장 시장 "KR" | "US" | "JP" | "TW"
#   country      : 화면 정렬·필터용 국적 "KR" | "US" | "JP" | "TW" | "EU"
#   sector       : 화면 표시용 섹터
#   asset_type   : "*_index" | "*_stock" | "fx"  (개별종목=25일, 그 외=50일 판정)
#   source       : "yfinance" | "krx_stock" | "krx_index" | "custom"
#   yf_ticker    : 장중(intraday)·해외 수집용 yfinance 심볼
#   sort_order   : 화면 정렬용 숫자(그룹 내 오름차순)
#   ai_group     : AI 병목 대분류(AI_GROUP_ORDER 중 하나)
#   ai_subgroup  : 세부 하위분류
#   product_group: 주요 제품군/분야 설명
#   exposure_type: CORE | SECONDARY | INDIRECT | BENCHMARK | HIGH_RISK
#   disparity_meaningful: False 면 이격도 과열 판정을 하지 않는다(환율·금리·변동성 등
#                 가격 추세가 아닌 지표). 생략 시 True. 값은 참고용으로 계속 표시된다.
#   note         : 짧은 설명(선택)
#   enabled      : False 이면 수집에서 제외
# ---------------------------------------------------------------------------

ASSETS: List[Dict] = [
    # ===================== 00_INDEX : 지수·환율·금리 (BENCHMARK) =====================
    {"name": "코스피", "code": "^KS11", "market": "KR", "country": "KR", "sector": "시장지수", "asset_type": "kr_index", "source": "krx_index", "yf_ticker": "^KS11", "sort_order": 1, "ai_group": "00_INDEX", "ai_subgroup": "시장지수", "product_group": "한국 종합주가지수", "exposure_type": "BENCHMARK", "enabled": True},
    {"name": "코스피200", "code": "^KS200", "market": "KR", "country": "KR", "sector": "시장지수", "asset_type": "kr_index", "source": "krx_index", "yf_ticker": "^KS200", "sort_order": 2, "ai_group": "00_INDEX", "ai_subgroup": "시장지수", "product_group": "코스피 대형주 지수", "exposure_type": "BENCHMARK", "enabled": True},
    {"name": "코스닥", "code": "^KQ11", "market": "KR", "country": "KR", "sector": "시장지수", "asset_type": "kr_index", "source": "krx_index", "yf_ticker": "^KQ11", "sort_order": 3, "ai_group": "00_INDEX", "ai_subgroup": "시장지수", "product_group": "코스닥 종합지수", "exposure_type": "BENCHMARK", "enabled": True},
    {"name": "코스닥150", "code": "^KQ47", "market": "KR", "country": "KR", "sector": "시장지수", "asset_type": "kr_index", "source": "custom", "yf_ticker": "^KQ47", "sort_order": 4, "ai_group": "00_INDEX", "ai_subgroup": "시장지수", "product_group": "코스닥 대형주 지수", "exposure_type": "BENCHMARK", "note": "yfinance 미제공(^KQ47 무응답) → custom source 필요", "enabled": False},
    {"name": "닛케이225", "code": "^N225", "market": "JP", "country": "JP", "sector": "시장지수", "asset_type": "jp_index", "source": "yfinance", "yf_ticker": "^N225", "sort_order": 5, "ai_group": "00_INDEX", "ai_subgroup": "시장지수", "product_group": "일본 대표 지수", "exposure_type": "BENCHMARK", "enabled": True},
    {"name": "TOPIX", "code": "^TOPX", "market": "JP", "country": "JP", "sector": "시장지수", "asset_type": "jp_index", "source": "custom", "yf_ticker": "^TOPX", "sort_order": 6, "ai_group": "00_INDEX", "ai_subgroup": "시장지수", "product_group": "도쿄증시 전체 지수", "exposure_type": "BENCHMARK", "note": "yfinance 미제공(^TOPX 무응답) → custom source 필요", "enabled": False},
    {"name": "대만 가권지수", "code": "^TWII", "market": "TW", "country": "TW", "sector": "시장지수", "asset_type": "tw_index", "source": "yfinance", "yf_ticker": "^TWII", "sort_order": 7, "ai_group": "00_INDEX", "ai_subgroup": "시장지수", "product_group": "대만 가권 종합지수", "exposure_type": "BENCHMARK", "enabled": True},
    {"name": "S&P500", "code": "^GSPC", "market": "US", "country": "US", "sector": "시장지수", "asset_type": "us_index", "source": "yfinance", "yf_ticker": "^GSPC", "sort_order": 8, "ai_group": "00_INDEX", "ai_subgroup": "시장지수", "product_group": "미국 대형주 지수", "exposure_type": "BENCHMARK", "enabled": True},
    {"name": "나스닥100", "code": "^NDX", "market": "US", "country": "US", "sector": "시장지수", "asset_type": "us_index", "source": "yfinance", "yf_ticker": "^NDX", "sort_order": 9, "ai_group": "00_INDEX", "ai_subgroup": "기술주지수", "product_group": "나스닥 대형 기술주", "exposure_type": "BENCHMARK", "enabled": True},
    {"name": "PHLX 반도체", "code": "^SOX", "market": "US", "country": "US", "sector": "반도체 지수", "asset_type": "us_index", "source": "yfinance", "yf_ticker": "^SOX", "sort_order": 10, "ai_group": "00_INDEX", "ai_subgroup": "반도체지수", "product_group": "필라델피아 반도체 지수", "exposure_type": "BENCHMARK", "enabled": True},
    {"name": "VIX 변동성", "code": "^VIX", "market": "US", "country": "US", "sector": "변동성", "asset_type": "us_index", "source": "yfinance", "yf_ticker": "^VIX", "sort_order": 11, "ai_group": "00_INDEX", "ai_subgroup": "변동성", "product_group": "S&P500 변동성 지수(공포)", "exposure_type": "BENCHMARK", "disparity_meaningful": False, "enabled": True},
    {"name": "美 국채 10년 금리", "code": "^TNX", "market": "US", "country": "US", "sector": "금리", "asset_type": "us_index", "source": "yfinance", "yf_ticker": "^TNX", "sort_order": 12, "ai_group": "00_INDEX", "ai_subgroup": "금리", "product_group": "미국 10년물 국채 금리", "exposure_type": "BENCHMARK", "disparity_meaningful": False, "enabled": True},
    {"name": "원/달러 환율", "code": "KRW=X", "market": "KR", "country": "KR", "sector": "환율", "asset_type": "fx", "source": "yfinance", "yf_ticker": "KRW=X", "sort_order": 13, "ai_group": "00_INDEX", "ai_subgroup": "환율", "product_group": "USD/KRW", "exposure_type": "BENCHMARK", "disparity_meaningful": False, "enabled": True},
    {"name": "엔/달러 환율", "code": "JPY=X", "market": "JP", "country": "JP", "sector": "환율", "asset_type": "fx", "source": "yfinance", "yf_ticker": "JPY=X", "sort_order": 14, "ai_group": "00_INDEX", "ai_subgroup": "환율", "product_group": "USD/JPY", "exposure_type": "BENCHMARK", "disparity_meaningful": False, "enabled": True},
    {"name": "닛케이 반도체지수", "code": "NKSCD_CUSTOM", "market": "JP", "country": "JP", "sector": "반도체 지수", "asset_type": "jp_index", "source": "custom", "yf_ticker": "NKSCD_CUSTOM", "sort_order": 15, "ai_group": "00_INDEX", "ai_subgroup": "반도체지수", "product_group": "Nikkei Semiconductor Stock Index", "exposure_type": "BENCHMARK", "note": "yfinance 직접 수집 불가 → custom source 필요", "enabled": False},

    # ===================== 01_AI_COMPUTE_ASIC : AI 연산·ASIC =====================
    {"name": "엔비디아", "code": "NVDA", "market": "US", "country": "US", "sector": "AI 가속기", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "NVDA", "sort_order": 100, "ai_group": "01_AI_COMPUTE_ASIC", "ai_subgroup": "GPU", "product_group": "데이터센터 GPU/AI 가속기", "exposure_type": "CORE", "enabled": True},
    {"name": "AMD", "code": "AMD", "market": "US", "country": "US", "sector": "AI 가속기", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "AMD", "sort_order": 101, "ai_group": "01_AI_COMPUTE_ASIC", "ai_subgroup": "GPU/CPU", "product_group": "GPU·CPU·AI 가속기", "exposure_type": "CORE", "enabled": True},
    {"name": "브로드컴", "code": "AVGO", "market": "US", "country": "US", "sector": "ASIC/네트워크", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "AVGO", "sort_order": 102, "ai_group": "01_AI_COMPUTE_ASIC", "ai_subgroup": "ASIC", "product_group": "커스텀 AI ASIC·AI 네트워킹", "exposure_type": "CORE", "note": "07 네트워크 축에도 해당", "enabled": True},
    {"name": "마벨", "code": "MRVL", "market": "US", "country": "US", "sector": "ASIC/네트워크", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "MRVL", "sort_order": 103, "ai_group": "01_AI_COMPUTE_ASIC", "ai_subgroup": "ASIC", "product_group": "커스텀 ASIC·광 DSP", "exposure_type": "CORE", "note": "07 네트워크 축에도 해당", "enabled": True},
    {"name": "미디어텍", "code": "2454.TW", "market": "TW", "country": "TW", "sector": "SoC", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "2454.TW", "sort_order": 104, "ai_group": "01_AI_COMPUTE_ASIC", "ai_subgroup": "SoC", "product_group": "엣지 AI·모바일 SoC", "exposure_type": "SECONDARY", "enabled": True},
    {"name": "알칩 테크놀로지", "code": "3661.TW", "market": "TW", "country": "TW", "sector": "ASIC 디자인", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "3661.TW", "sort_order": 105, "ai_group": "01_AI_COMPUTE_ASIC", "ai_subgroup": "ASIC 디자인하우스", "product_group": "AI ASIC 설계 서비스", "exposure_type": "HIGH_RISK", "enabled": True},

    # ===================== 02_MEMORY_STORAGE : 메모리·스토리지 =====================
    {"name": "SK하이닉스", "code": "000660", "market": "KR", "country": "KR", "sector": "메모리", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "000660.KS", "sort_order": 200, "ai_group": "02_MEMORY_STORAGE", "ai_subgroup": "HBM/DRAM", "product_group": "HBM·DRAM·낸드", "exposure_type": "CORE", "enabled": True},
    {"name": "삼성전자", "code": "005930", "market": "KR", "country": "KR", "sector": "메모리/종합반도체", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "005930.KS", "sort_order": 201, "ai_group": "02_MEMORY_STORAGE", "ai_subgroup": "HBM/DRAM/NAND", "product_group": "DRAM·HBM·낸드(+파운드리)", "exposure_type": "CORE", "note": "03 파운드리 축에도 해당", "enabled": True},
    {"name": "마이크론", "code": "MU", "market": "US", "country": "US", "sector": "메모리", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "MU", "sort_order": 202, "ai_group": "02_MEMORY_STORAGE", "ai_subgroup": "HBM/DRAM/NAND", "product_group": "DRAM·HBM·낸드", "exposure_type": "CORE", "enabled": True},
    {"name": "키옥시아", "code": "285A.T", "market": "JP", "country": "JP", "sector": "메모리", "asset_type": "jp_stock", "source": "yfinance", "yf_ticker": "285A.T", "sort_order": 203, "ai_group": "02_MEMORY_STORAGE", "ai_subgroup": "NAND", "product_group": "낸드플래시", "exposure_type": "SECONDARY", "enabled": True},
    {"name": "파두", "code": "440110", "market": "KR", "country": "KR", "sector": "스토리지 컨트롤러", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "440110.KQ", "sort_order": 204, "ai_group": "02_MEMORY_STORAGE", "ai_subgroup": "SSD 컨트롤러", "product_group": "SSD 컨트롤러·SmartNIC", "exposure_type": "HIGH_RISK", "enabled": True},

    # ===================== 03_FOUNDRY_MANUFACTURING : 파운드리·제조 =====================
    {"name": "TSMC", "code": "TSM", "market": "US", "country": "TW", "sector": "파운드리", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "TSM", "sort_order": 300, "ai_group": "03_FOUNDRY_MANUFACTURING", "ai_subgroup": "선단 파운드리", "product_group": "선단공정 파운드리 1위", "exposure_type": "CORE", "note": "TSMC ADR", "enabled": True},
    {"name": "인텔", "code": "INTC", "market": "US", "country": "US", "sector": "IDM/파운드리", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "INTC", "sort_order": 301, "ai_group": "03_FOUNDRY_MANUFACTURING", "ai_subgroup": "IDM/파운드리", "product_group": "CPU·IDM·파운드리", "exposure_type": "SECONDARY", "enabled": True},
    {"name": "UMC", "code": "2303.TW", "market": "TW", "country": "TW", "sector": "파운드리", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "2303.TW", "sort_order": 302, "ai_group": "03_FOUNDRY_MANUFACTURING", "ai_subgroup": "성숙 파운드리", "product_group": "성숙공정 파운드리", "exposure_type": "SECONDARY", "enabled": True},

    # ===================== 04_EQUIPMENT_TEST : 장비·테스트 =====================
    {"name": "한미반도체", "code": "042700", "market": "KR", "country": "KR", "sector": "반도체 장비", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "042700.KS", "sort_order": 400, "ai_group": "04_EQUIPMENT_TEST", "ai_subgroup": "후공정 장비", "product_group": "HBM TC 본더", "exposure_type": "CORE", "enabled": True},
    {"name": "어플라이드 머티어리얼즈", "code": "AMAT", "market": "US", "country": "US", "sector": "반도체 장비", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "AMAT", "sort_order": 401, "ai_group": "04_EQUIPMENT_TEST", "ai_subgroup": "전공정 장비", "product_group": "증착·식각 등 종합장비", "exposure_type": "CORE", "enabled": True},
    {"name": "램리서치", "code": "LRCX", "market": "US", "country": "US", "sector": "반도체 장비", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "LRCX", "sort_order": 402, "ai_group": "04_EQUIPMENT_TEST", "ai_subgroup": "식각/증착", "product_group": "식각·증착 장비", "exposure_type": "CORE", "enabled": True},
    {"name": "KLA", "code": "KLAC", "market": "US", "country": "US", "sector": "반도체 장비", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "KLAC", "sort_order": 403, "ai_group": "04_EQUIPMENT_TEST", "ai_subgroup": "검사/계측", "product_group": "공정 검사·계측", "exposure_type": "CORE", "enabled": True},
    {"name": "ASML", "code": "ASML", "market": "US", "country": "EU", "sector": "노광 장비", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "ASML", "sort_order": 404, "ai_group": "04_EQUIPMENT_TEST", "ai_subgroup": "노광(EUV)", "product_group": "EUV/DUV 노광장비 독점", "exposure_type": "CORE", "note": "네덜란드, 미국 ADR 수집", "enabled": True},
    {"name": "도쿄일렉트론", "code": "8035.T", "market": "JP", "country": "JP", "sector": "반도체 장비", "asset_type": "jp_stock", "source": "yfinance", "yf_ticker": "8035.T", "sort_order": 405, "ai_group": "04_EQUIPMENT_TEST", "ai_subgroup": "전공정 장비", "product_group": "코터·증착·식각 장비", "exposure_type": "CORE", "enabled": True},
    {"name": "어드반테스트", "code": "6857.T", "market": "JP", "country": "JP", "sector": "테스트 장비", "asset_type": "jp_stock", "source": "yfinance", "yf_ticker": "6857.T", "sort_order": 406, "ai_group": "04_EQUIPMENT_TEST", "ai_subgroup": "테스터", "product_group": "HBM·SoC 테스터", "exposure_type": "CORE", "enabled": True},

    # ===================== 05_PACKAGING_SUBSTRATE_PCB : 패키징·기판·PCB =====================
    {"name": "대덕전자", "code": "353200", "market": "KR", "country": "KR", "sector": "기판", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "353200.KS", "sort_order": 500, "ai_group": "05_PACKAGING_SUBSTRATE_PCB", "ai_subgroup": "FC-BGA 기판", "product_group": "패키지 기판(FC-BGA)", "exposure_type": "SECONDARY", "enabled": True},
    {"name": "이수페타시스", "code": "007660", "market": "KR", "country": "KR", "sector": "PCB", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "007660.KS", "sort_order": 501, "ai_group": "05_PACKAGING_SUBSTRATE_PCB", "ai_subgroup": "고다층 PCB", "product_group": "AI 가속기용 고다층 PCB", "exposure_type": "HIGH_RISK", "enabled": True},
    {"name": "ASE 테크놀로지", "code": "3711.TW", "market": "TW", "country": "TW", "sector": "OSAT", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "3711.TW", "sort_order": 502, "ai_group": "05_PACKAGING_SUBSTRATE_PCB", "ai_subgroup": "OSAT 패키징", "product_group": "후공정 패키징·테스트", "exposure_type": "CORE", "enabled": True},
    {"name": "유니마이크론", "code": "3037.TW", "market": "TW", "country": "TW", "sector": "기판", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "3037.TW", "sort_order": 503, "ai_group": "05_PACKAGING_SUBSTRATE_PCB", "ai_subgroup": "ABF 기판", "product_group": "ABF 패키지 기판", "exposure_type": "CORE", "enabled": True},
    {"name": "이비덴", "code": "4062.T", "market": "JP", "country": "JP", "sector": "기판", "asset_type": "jp_stock", "source": "yfinance", "yf_ticker": "4062.T", "sort_order": 504, "ai_group": "05_PACKAGING_SUBSTRATE_PCB", "ai_subgroup": "ABF 기판", "product_group": "ABF 패키지 기판 선두", "exposure_type": "CORE", "enabled": True},

    # ===================== 06_MLCC_PASSIVE_COMPONENT : MLCC·수동부품 =====================
    {"name": "삼성전기", "code": "009150", "market": "KR", "country": "KR", "sector": "MLCC/기판", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "009150.KS", "sort_order": 600, "ai_group": "06_MLCC_PASSIVE_COMPONENT", "ai_subgroup": "MLCC", "product_group": "MLCC 세계 2위·FC-BGA 기판", "exposure_type": "CORE", "note": "05 기판 축에도 해당", "enabled": True},
    {"name": "무라타제작소", "code": "6981.T", "market": "JP", "country": "JP", "sector": "MLCC", "asset_type": "jp_stock", "source": "yfinance", "yf_ticker": "6981.T", "sort_order": 601, "ai_group": "06_MLCC_PASSIVE_COMPONENT", "ai_subgroup": "MLCC", "product_group": "MLCC 세계 1위", "exposure_type": "CORE", "enabled": True},
    {"name": "타이요유덴", "code": "6976.T", "market": "JP", "country": "JP", "sector": "MLCC", "asset_type": "jp_stock", "source": "yfinance", "yf_ticker": "6976.T", "sort_order": 602, "ai_group": "06_MLCC_PASSIVE_COMPONENT", "ai_subgroup": "MLCC", "product_group": "MLCC·인덕터", "exposure_type": "SECONDARY", "enabled": True},
    {"name": "TDK", "code": "6762.T", "market": "JP", "country": "JP", "sector": "수동부품", "asset_type": "jp_stock", "source": "yfinance", "yf_ticker": "6762.T", "sort_order": 603, "ai_group": "06_MLCC_PASSIVE_COMPONENT", "ai_subgroup": "수동부품", "product_group": "MLCC·소형 배터리", "exposure_type": "SECONDARY", "enabled": True},
    {"name": "야게오", "code": "2327.TW", "market": "TW", "country": "TW", "sector": "수동부품", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "2327.TW", "sort_order": 604, "ai_group": "06_MLCC_PASSIVE_COMPONENT", "ai_subgroup": "수동부품", "product_group": "칩저항·MLCC", "exposure_type": "SECONDARY", "enabled": True},

    # ===================== 07_NETWORK_OPTICAL : 네트워크·광 =====================
    {"name": "아리스타 네트웍스", "code": "ANET", "market": "US", "country": "US", "sector": "네트워크", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "ANET", "sort_order": 700, "ai_group": "07_NETWORK_OPTICAL", "ai_subgroup": "스위치", "product_group": "AI 데이터센터 스위치", "exposure_type": "CORE", "enabled": True},
    {"name": "코히어런트", "code": "COHR", "market": "US", "country": "US", "sector": "광부품", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "COHR", "sort_order": 701, "ai_group": "07_NETWORK_OPTICAL", "ai_subgroup": "광트랜시버", "product_group": "광트랜시버·광부품", "exposure_type": "CORE", "enabled": True},
    {"name": "액톤 테크놀로지", "code": "2345.TW", "market": "TW", "country": "TW", "sector": "네트워크", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "2345.TW", "sort_order": 702, "ai_group": "07_NETWORK_OPTICAL", "ai_subgroup": "스위치 ODM", "product_group": "화이트박스 스위치 ODM", "exposure_type": "SECONDARY", "enabled": True},

    # ===================== 08_POWER_COOLING_GRID : 전력·냉각·그리드 =====================
    {"name": "HD현대일렉트릭", "code": "267260", "market": "KR", "country": "KR", "sector": "전력기기", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "267260.KS", "sort_order": 800, "ai_group": "08_POWER_COOLING_GRID", "ai_subgroup": "전력기기", "product_group": "변압기·전력기기", "exposure_type": "SECONDARY", "enabled": True},
    {"name": "LS ELECTRIC", "code": "010120", "market": "KR", "country": "KR", "sector": "전력기기", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "010120.KS", "sort_order": 801, "ai_group": "08_POWER_COOLING_GRID", "ai_subgroup": "전력/배전", "product_group": "배전·전력 인프라", "exposure_type": "SECONDARY", "enabled": True},
    {"name": "버티브", "code": "VRT", "market": "US", "country": "US", "sector": "전력/냉각", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "VRT", "sort_order": 802, "ai_group": "08_POWER_COOLING_GRID", "ai_subgroup": "전력/냉각", "product_group": "데이터센터 전력·냉각", "exposure_type": "CORE", "enabled": True},
    {"name": "이튼", "code": "ETN", "market": "US", "country": "US", "sector": "전력관리", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "ETN", "sort_order": 803, "ai_group": "08_POWER_COOLING_GRID", "ai_subgroup": "전력관리", "product_group": "전력관리·배전", "exposure_type": "CORE", "enabled": True},
    {"name": "델타 일렉트로닉스", "code": "2308.TW", "market": "TW", "country": "TW", "sector": "전원/냉각", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "2308.TW", "sort_order": 804, "ai_group": "08_POWER_COOLING_GRID", "ai_subgroup": "전원/냉각", "product_group": "전원공급·열관리 솔루션", "exposure_type": "CORE", "enabled": True},

    # ===================== 09_AI_SERVER_ODM : AI 서버·ODM =====================
    {"name": "슈퍼마이크로", "code": "SMCI", "market": "US", "country": "US", "sector": "AI 서버", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "SMCI", "sort_order": 900, "ai_group": "09_AI_SERVER_ODM", "ai_subgroup": "AI 서버", "product_group": "AI 서버·랙 시스템", "exposure_type": "CORE", "enabled": True},
    {"name": "델 테크놀로지스", "code": "DELL", "market": "US", "country": "US", "sector": "AI 서버", "asset_type": "us_stock", "source": "yfinance", "yf_ticker": "DELL", "sort_order": 901, "ai_group": "09_AI_SERVER_ODM", "ai_subgroup": "AI 서버", "product_group": "AI 서버·엔터프라이즈", "exposure_type": "SECONDARY", "enabled": True},
    {"name": "폭스콘(홍하이)", "code": "2317.TW", "market": "TW", "country": "TW", "sector": "EMS/ODM", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "2317.TW", "sort_order": 902, "ai_group": "09_AI_SERVER_ODM", "ai_subgroup": "AI 서버 ODM", "product_group": "AI 서버 위탁생산 1위", "exposure_type": "CORE", "enabled": True},
    {"name": "콴타 컴퓨터", "code": "2382.TW", "market": "TW", "country": "TW", "sector": "ODM", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "2382.TW", "sort_order": 903, "ai_group": "09_AI_SERVER_ODM", "ai_subgroup": "AI 서버 ODM", "product_group": "AI 서버 ODM", "exposure_type": "CORE", "enabled": True},
    {"name": "위윈 (Wiwynn)", "code": "6669.TW", "market": "TW", "country": "TW", "sector": "ODM", "asset_type": "tw_stock", "source": "yfinance", "yf_ticker": "6669.TW", "sort_order": 904, "ai_group": "09_AI_SERVER_ODM", "ai_subgroup": "하이퍼스케일 ODM", "product_group": "하이퍼스케일 서버 ODM", "exposure_type": "HIGH_RISK", "enabled": True},

    # ===================== 10_INDIRECT_HOLDING : 간접·지주 =====================
    {"name": "SK스퀘어", "code": "402340", "market": "KR", "country": "KR", "sector": "지주", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "402340.KS", "sort_order": 1000, "ai_group": "10_INDIRECT_HOLDING", "ai_subgroup": "반도체 지주", "product_group": "SK하이닉스 지배 지주사", "exposure_type": "INDIRECT", "enabled": True},
    {"name": "삼성물산", "code": "028260", "market": "KR", "country": "KR", "sector": "지주", "asset_type": "kr_stock", "source": "krx_stock", "yf_ticker": "028260.KS", "sort_order": 1001, "ai_group": "10_INDIRECT_HOLDING", "ai_subgroup": "그룹 지주", "product_group": "삼성그룹 지배구조 핵심", "exposure_type": "INDIRECT", "enabled": True},
]


def enabled_assets() -> List[Dict]:
    """enabled=True 인 자산만 반환."""
    return [a for a in ASSETS if a.get("enabled", True)]
