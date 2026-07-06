"""중앙 설정 파일 — AI 병목 밸류체인 대시보드.

자산은 빌더 A(...) 로 만든다. 티커 접미사로 상장시장·통화·시장을 자동 유추하고,
국내(KRX)는 FinanceDataReader, 그 외는 yfinance 로 수집한다.
상세 링크는 국내=네이버증권, 그 외=야후 파이낸스.
"""
from __future__ import annotations

from typing import Dict, List

# ---------------------------------------------------------------------------
# 이동평균 / 이격도 / 구간 / 검증 / 수집범위
# ---------------------------------------------------------------------------
MA_WINDOWS: List[int] = [20, 25, 50, 120]
STOCK_PRIMARY_WINDOW: int = 25
DEFAULT_PRIMARY_WINDOW: int = 50

ZONE_OVERHEAT_MIN: float = 130.0
ZONE_CAUTION_MIN: float = 120.0
ZONE_NORMAL_MIN: float = 105.0
ZONE_LABELS: Dict[str, str] = {
    "overheat": "과열", "caution": "경계", "normal": "정상", "cooldown": "과열해소",
}

SUSPICIOUS_DISPARITY_MIN: float = 50.0
SUSPICIOUS_DISPARITY_MAX: float = 200.0
STALE_DAYS: int = 7

KR_LOOKBACK_DAYS: int = 730
US_PERIOD: str = "2y"
HISTORY_DAYS: int = 365

# ---------------------------------------------------------------------------
# AI 병목 밸류체인 대분류(화면 정렬 순서).
# ---------------------------------------------------------------------------
AI_GROUP_ORDER: List[str] = [
    "00_INDEX",
    "01_COMPUTE_ASIC",
    "02_EDA_IP",
    "03_MEMORY_STORAGE",
    "04_FOUNDRY_MANUFACTURING",
    "05_EQUIPMENT_TEST",
    "06_MATERIALS_WAFER",
    "07_PACKAGING_SUBSTRATE_PCB",
    "08_MLCC_PASSIVE_COMPONENT",
    "09_NETWORK_OPTICAL",
    "10_POWER_COOLING_GRID",
    "11_AI_SERVER_ODM",
    "12_CLOUD_CAPEX",
]

# ---------------------------------------------------------------------------
# 빌더 헬퍼
# ---------------------------------------------------------------------------
# 국가 라벨 → 필터용 국가코드 (독일·네덜란드·프랑스·스위스·오스트리아 = EU)
_CC = {
    "한국": "KR", "미국": "US", "일본": "JP", "대만": "TW", "유럽": "EU",
    "독일": "EU", "네덜란드": "EU", "프랑스": "EU", "스위스": "EU",
    "오스트리아": "EU", "홍콩": "HK",
}
_EXP = {
    "벤치마크": "BENCHMARK", "핵심": "CORE", "2차": "SECONDARY",
    "보조": "SUPPORT", "고위험": "HIGH_RISK", "수요": "DEMAND",
}
# 티커 접미사 → (상장시장코드, 상장시장표기, 통화). 긴 접미사 우선.
_SUFFIX_INFO = [
    (".TWO", "TW", "TPEx", "TWD"),
    (".HK", "HK", "HKEX", "HKD"),
    (".DE", "EU", "XETRA", "EUR"),
    (".PA", "EU", "Euronext Paris", "EUR"),
    (".AS", "EU", "Euronext Amsterdam", "EUR"),
    (".VI", "EU", "Wiener Börse", "EUR"),
    (".SW", "EU", "SIX", "CHF"),
    (".TW", "TW", "TWSE", "TWD"),
    (".T", "JP", "TSE", "JPY"),
]


def _infer_market(yf_ticker: str, country_code: str, source: str):
    """(market, listing_market, currency) 를 티커/소스에서 유추."""
    if source in ("krx_stock", "krx_index"):
        return "KR", "KRX", "KRW"
    if yf_ticker.startswith("^"):
        idx = {
            "KR": ("KR", "KRX", "KRW"), "JP": ("JP", "TSE", "JPY"),
            "TW": ("TW", "TWSE", "TWD"), "US": ("US", "US Index", "USD"),
        }
        return idx.get(country_code, ("US", "US Index", "USD"))
    for suf, mk, li, cur in _SUFFIX_INFO:
        if yf_ticker.endswith(suf):
            return mk, li, cur
    return "US", "NASDAQ/NYSE", "USD"


def A(so, grp, name, clabel, ticker, sector, sub, product, exp,
      *, adr=False, local=None, disp=None, enabled=True, dm=True, note=None):
    """자산 dict 빌더. clabel=국가 한글 라벨, ticker=화면표기 티커."""
    cc = _CC[clabel]
    is_index = ticker.startswith("^")
    if clabel == "한국" and not is_index:
        code = ticker.split(".")[0]           # 6자리 (FDR·네이버용)
        yf = ticker                           # 000660.KS (쿼트 보강용)
        source = "krx_stock"
    elif clabel == "한국" and is_index:
        code = yf = ticker
        source = "krx_index"
    else:
        code = yf = ticker
        source = "yfinance"

    market, listing, currency = _infer_market(yf, cc, source)
    asset_type = f"{cc.lower()}_index" if is_index else f"{market.lower()}_stock"

    if cc == "KR" and not is_index:
        detail_url = f"https://finance.naver.com/item/main.naver?code={code}"
    else:
        detail_url = f"https://finance.yahoo.com/quote/{yf}"
    price_source = "KRX(FDR)+Yahoo" if source.startswith("krx") else "Yahoo Finance"

    return {
        "name": name, "code": code, "yf_ticker": yf,
        "market": market, "country": cc, "country_label": clabel,
        "sector": sector, "asset_type": asset_type, "source": source,
        "sort_order": so, "ai_group": grp, "ai_subgroup": sub,
        "product_group": product, "exposure_type": _EXP[exp],
        "listing_market": listing, "currency": currency,
        "price_source": price_source, "is_adr": adr,
        "local_ticker": local, "display_ticker": disp or ticker,
        "detail_url": detail_url, "disparity_meaningful": dm,
        "note": note, "enabled": enabled,
    }


# ---------------------------------------------------------------------------
# 매크로 참고 지표(환율·금리·변동성) — 표가 아닌 상단 스트립 전용(disparity_meaningful=False).
# ---------------------------------------------------------------------------
# 매크로 표시 그룹(관련 지표끼리 묶는다). 화면 정렬 순서.
MACRO_GROUP_ORDER: List[str] = [
    "fx", "rates", "policy", "cpi", "ppi", "money", "commodity", "risk",
]


def _macro(so, name, code, clabel, unit, group, desc, url):
    cc = _CC[clabel]
    return {
        "name": name, "code": code, "yf_ticker": code, "market": cc,
        "country": cc, "country_label": clabel, "sector": group,
        "asset_type": "fx" if code.endswith("=X") else "macro_index",
        "source": "yfinance", "sort_order": so, "ai_group": "00_INDEX",
        "ai_subgroup": group, "product_group": desc, "exposure_type": "BENCHMARK",
        "macro_group": group,
        "listing_market": "-", "currency": unit, "price_source": "Yahoo Finance",
        "is_adr": False, "local_ticker": None, "display_ticker": code,
        "detail_url": url, "disparity_meaningful": False, "note": None, "enabled": True,
    }


ASSETS: List[Dict] = [
    # ===== 매크로 참고(상단 스트립) — 값·등락은 야후, 상세는 링크. 이격도 판정 안 함 =====
    _macro(9001, "원/달러 환율", "KRW=X", "한국", "원", "fx",
           "원화 가치. 상승=원화 약세(수출주 유리·외국인 매도 압력·수입물가↑)",
           "https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDKRW"),
    _macro(9002, "엔/달러 환율", "JPY=X", "일본", "엔", "fx",
           "엔화 가치. 엔 약세=일본 수출주 유리·엔캐리 트레이드 확대 신호",
           "https://finance.naver.com/marketindex/exchangeDetail.naver?marketindexCd=FX_USDJPY"),
    _macro(9003, "달러인덱스 DXY", "DX-Y.NYB", "미국", "pt", "fx",
           "주요 6개 통화 대비 달러 강세. 상승=신흥국·원자재·위험자산에 역풍",
           "https://www.investing.com/indices/usdollar"),
    _macro(9004, "美 10년 국채금리", "^TNX", "미국", "%", "rates",
           "미국 10년물 금리. 상승=성장주·기술주 밸류에이션 부담·할인율↑",
           "https://www.investing.com/rates-bonds/u.s.-10-year-bond-yield"),
    _macro(9005, "美 단기금리(13주)", "^IRX", "미국", "%", "rates",
           "미국 13주 T-bill 금리. 연준 정책금리 방향 대용 지표",
           "https://www.investing.com/rates-bonds/u.s.-3-month-bond-yield"),
    _macro(9006, "WTI 유가", "CL=F", "미국", "$", "commodity",
           "서부텍사스유 선물. 상승=인플레·에너지 비용↑, 경기·물가의 핵심 변수",
           "https://www.investing.com/commodities/crude-oil"),
    _macro(9007, "금", "GC=F", "미국", "$", "commodity",
           "금 선물. 안전자산·인플레 헤지, 실질금리·달러와 역상관 경향",
           "https://www.investing.com/commodities/gold"),
    _macro(9008, "은", "SI=F", "미국", "$", "commodity",
           "은 선물. 안전자산+산업금속(태양광·전자) 성격을 함께 가짐",
           "https://www.investing.com/commodities/silver"),
    _macro(9009, "구리", "HG=F", "미국", "$", "commodity",
           "구리 선물('닥터 코퍼'). 제조업·글로벌 경기의 선행 지표",
           "https://www.investing.com/commodities/copper"),
    _macro(9010, "천연가스", "NG=F", "미국", "$", "commodity",
           "천연가스 선물. 난방·전력·데이터센터 전력비용의 변수",
           "https://www.investing.com/commodities/natural-gas"),
    _macro(9011, "비트코인", "BTC-USD", "미국", "$", "risk",
           "위험자산·유동성 심리 바로미터. 급등락=리스크온/오프 신호",
           "https://finance.yahoo.com/quote/BTC-USD"),
    _macro(9012, "이더리움", "ETH-USD", "미국", "$", "risk",
           "2위 암호자산. 알트코인·위험선호(리스크온) 심리에 민감",
           "https://finance.yahoo.com/quote/ETH-USD"),
    _macro(9013, "VIX 변동성", "^VIX", "미국", "pt", "risk",
           "S&P500 변동성('공포지수'). 급등=위험회피 심리 확대",
           "https://www.investing.com/indices/volatility-s-p-500"),

    # ===== 00 시장지수 =====
    A(1, "00_INDEX", "코스피", "한국", "^KS11", "시장지수", "시장지수", "한국 종합주가지수", "벤치마크"),
    A(2, "00_INDEX", "코스피200", "한국", "^KS200", "시장지수", "대형주지수", "한국 대형주 벤치마크", "벤치마크"),
    A(3, "00_INDEX", "코스닥", "한국", "^KQ11", "시장지수", "성장주지수", "한국 성장주/중소형주 심리", "보조"),
    A(4, "00_INDEX", "TOPIX", "일본", "^TOPX", "시장지수", "일본전체지수", "일본 전체 시장 벤치마크", "벤치마크",
      enabled=False, note="yfinance·FDR 미제공(^TOPX 무응답) → 비활성"),
    A(5, "00_INDEX", "닛케이225", "일본", "^N225", "시장지수", "일본대표지수", "일본 대표 대형주 지수", "벤치마크"),
    A(6, "00_INDEX", "대만 가권지수", "대만", "^TWII", "시장지수", "대만지수", "대만 반도체/전자 밸류체인 심리", "벤치마크"),
    A(7, "00_INDEX", "S&P500", "미국", "^GSPC", "시장지수", "미국대형주", "미국 대형주 지수", "벤치마크"),
    A(8, "00_INDEX", "나스닥100", "미국", "^NDX", "시장지수", "기술주지수", "미국 대형 기술주 지수", "벤치마크"),
    A(9, "00_INDEX", "PHLX 반도체", "미국", "^SOX", "반도체지수", "반도체지수", "글로벌 반도체 심리 핵심 지수", "벤치마크"),

    # ===== 01 AI 연산·ASIC =====
    A(100, "01_COMPUTE_ASIC", "엔비디아", "미국", "NVDA", "AI 가속기", "GPU", "데이터센터 GPU/AI 가속기 절대 핵심", "핵심"),
    A(101, "01_COMPUTE_ASIC", "AMD", "미국", "AMD", "AI 가속기", "GPU/CPU", "GPU·CPU·AI 가속기", "핵심"),
    A(102, "01_COMPUTE_ASIC", "브로드컴", "미국", "AVGO", "ASIC/네트워크", "ASIC/네트워크", "커스텀 AI ASIC·스위치 ASIC·네트워킹", "핵심"),
    A(103, "01_COMPUTE_ASIC", "마벨", "미국", "MRVL", "ASIC/네트워크", "ASIC/광DSP", "커스텀 ASIC·광 DSP·데이터센터 연결", "핵심"),
    A(104, "01_COMPUTE_ASIC", "퀄컴", "미국", "QCOM", "AI 추론/SoC", "엣지AI/추론", "엣지 AI·저전력 추론·모바일 SoC", "2차"),
    A(105, "01_COMPUTE_ASIC", "미디어텍", "대만", "2454.TW", "SoC", "SoC", "엣지 AI·모바일·ASIC 가능성", "2차"),
    A(106, "01_COMPUTE_ASIC", "알칩 테크놀로지", "대만", "3661.TW", "ASIC 디자인", "ASIC 디자인하우스", "AI ASIC 설계 서비스·고변동성", "고위험"),
    A(107, "01_COMPUTE_ASIC", "Astera Labs", "미국", "ALAB", "AI 연결", "PCIe/CXL", "AI 서버 PCIe·CXL 연결 칩", "핵심"),
    A(108, "01_COMPUTE_ASIC", "Credo Technology", "미국", "CRDO", "AI 연결", "SerDes/DSP", "AI 클러스터 고속 연결·액티브 전기케이블", "고위험"),

    # ===== 02 EDA·IP =====
    A(150, "02_EDA_IP", "Synopsys", "미국", "SNPS", "EDA/IP", "EDA/IP", "반도체 설계 자동화·IP·검증", "핵심"),
    A(151, "02_EDA_IP", "Cadence Design Systems", "미국", "CDNS", "EDA/IP", "EDA", "반도체 설계 자동화·시뮬레이션", "핵심"),
    A(152, "02_EDA_IP", "Arm Holdings", "미국", "ARM", "CPU IP", "CPU IP", "AI 서버 CPU·반도체 IP·라이선스", "핵심"),
    A(153, "02_EDA_IP", "Siemens", "독일", "SIE.DE", "EDA/산업소프트웨어", "EDA/산업SW", "Siemens EDA 포함·순수 EDA주는 아님", "2차"),

    # ===== 03 메모리·스토리지 =====
    A(200, "03_MEMORY_STORAGE", "SK하이닉스", "한국", "000660.KS", "메모리", "HBM/DRAM/NAND", "HBM·DRAM·낸드 핵심 공급자", "핵심"),
    A(201, "03_MEMORY_STORAGE", "삼성전자", "한국", "005930.KS", "메모리/종합반도체", "HBM/DRAM/NAND/파운드리", "메모리·HBM·낸드·파운드리", "핵심"),
    A(202, "03_MEMORY_STORAGE", "마이크론", "미국", "MU", "메모리", "HBM/DRAM/NAND", "미국 메모리 핵심 기업", "핵심"),
    A(203, "03_MEMORY_STORAGE", "키옥시아", "일본", "285A.T", "메모리", "NAND", "낸드플래시·AI 스토리지 수혜", "핵심"),
    A(204, "03_MEMORY_STORAGE", "Sandisk", "미국", "SNDK", "메모리", "NAND/SSD", "낸드·SSD·AI 데이터센터 스토리지", "핵심"),
    A(205, "03_MEMORY_STORAGE", "Western Digital", "미국", "WDC", "스토리지", "HDD/스토리지", "대용량 데이터 저장·HDD 중심", "2차"),
    A(206, "03_MEMORY_STORAGE", "Seagate", "미국", "STX", "스토리지", "HDD/스토리지", "니어라인 HDD·AI 데이터 저장", "2차"),
    A(207, "03_MEMORY_STORAGE", "파두", "한국", "440110.KQ", "스토리지 컨트롤러", "SSD 컨트롤러", "SSD 컨트롤러·실적 변동성 큼", "고위험"),

    # ===== 04 파운드리·제조 =====
    A(300, "04_FOUNDRY_MANUFACTURING", "TSMC", "대만", "TSM", "파운드리", "선단 파운드리", "선단공정 파운드리 절대 핵심", "핵심", adr=True, local="2330.TW"),
    A(301, "04_FOUNDRY_MANUFACTURING", "인텔", "미국", "INTC", "IDM/파운드리", "CPU/IDM/파운드리", "CPU·IDM·파운드리 턴어라운드 관찰", "2차"),
    A(302, "04_FOUNDRY_MANUFACTURING", "GlobalFoundries", "미국", "GFS", "파운드리", "성숙 파운드리", "성숙공정·특수공정 파운드리", "2차"),
    A(303, "04_FOUNDRY_MANUFACTURING", "UMC", "대만", "2303.TW", "파운드리", "성숙 파운드리", "AI 핵심보다는 성숙공정 사이클 체크용", "보조"),

    # ===== 05 장비·테스트 =====
    A(400, "05_EQUIPMENT_TEST", "ASML", "유럽", "ASML", "노광 장비", "노광(EUV/DUV)", "EUV 노광장비 독점적 지위", "핵심", adr=True, local="ASML.AS"),
    A(401, "05_EQUIPMENT_TEST", "Applied Materials", "미국", "AMAT", "반도체 장비", "전공정 장비", "증착·식각·공정장비 종합", "핵심"),
    A(402, "05_EQUIPMENT_TEST", "Lam Research", "미국", "LRCX", "반도체 장비", "식각/증착", "식각·증착·메모리 장비", "핵심"),
    A(403, "05_EQUIPMENT_TEST", "KLA", "미국", "KLAC", "반도체 장비", "검사/계측", "공정 검사·계측 병목", "핵심"),
    A(404, "05_EQUIPMENT_TEST", "도쿄일렉트론", "일본", "8035.T", "반도체 장비", "전공정 장비", "코터·증착·식각 장비", "핵심"),
    A(405, "05_EQUIPMENT_TEST", "어드반테스트", "일본", "6857.T", "테스트 장비", "테스터", "HBM·SoC·AI 칩 테스트", "핵심"),
    A(406, "05_EQUIPMENT_TEST", "Teradyne", "미국", "TER", "테스트 장비", "테스터", "반도체 자동 테스트 장비", "2차"),
    A(407, "05_EQUIPMENT_TEST", "DISCO", "일본", "6146.T", "후공정 장비", "다이싱/그라인딩", "웨이퍼 절단·연마·후공정 핵심", "핵심"),
    A(408, "05_EQUIPMENT_TEST", "Lasertec", "일본", "6920.T", "검사 장비", "EUV 마스크 검사", "EUV 마스크 검사 장비", "2차"),
    A(409, "05_EQUIPMENT_TEST", "ASM International", "네덜란드", "ASM.AS", "반도체 장비", "ALD/증착", "원자층증착 ALD 장비", "2차"),
    A(410, "05_EQUIPMENT_TEST", "BE Semiconductor", "네덜란드", "BESI.AS", "후공정 장비", "패키징 장비", "하이브리드 본딩·패키징 장비", "2차"),
    A(411, "05_EQUIPMENT_TEST", "한미반도체", "한국", "042700.KS", "후공정 장비", "HBM TC 본더", "HBM 후공정 장비 핵심", "핵심"),

    # ===== 06 소재·웨이퍼 =====
    A(450, "06_MATERIALS_WAFER", "Shin-Etsu Chemical", "일본", "4063.T", "소재/웨이퍼", "실리콘웨이퍼/소재", "반도체 웨이퍼·화학소재", "핵심"),
    A(451, "06_MATERIALS_WAFER", "SUMCO", "일본", "3436.T", "웨이퍼", "실리콘웨이퍼", "반도체 실리콘 웨이퍼", "핵심"),
    A(452, "06_MATERIALS_WAFER", "Tokyo Ohka Kogyo", "일본", "4186.T", "포토레지스트", "포토레지스트", "반도체 감광재·EUV 소재", "2차"),
    A(453, "06_MATERIALS_WAFER", "Hoya", "일본", "7741.T", "포토마스크", "포토마스크 블랭크", "EUV/반도체 포토마스크 소재", "2차"),
    A(454, "06_MATERIALS_WAFER", "Entegris", "미국", "ENTG", "소재/부품", "필터/소재/케미컬", "첨단공정 소재·오염 제어", "핵심"),
    A(455, "06_MATERIALS_WAFER", "Resonac", "일본", "4004.T", "소재", "패키징/반도체소재", "후공정·패키징 소재", "2차"),
    A(456, "06_MATERIALS_WAFER", "Air Liquide", "프랑스", "AI.PA", "산업가스", "반도체 가스", "반도체용 특수가스·산업가스", "2차"),

    # ===== 07 패키징·기판·PCB =====
    A(500, "07_PACKAGING_SUBSTRATE_PCB", "ASE Technology", "대만", "3711.TW", "OSAT", "OSAT", "후공정 패키징·테스트", "핵심"),
    A(501, "07_PACKAGING_SUBSTRATE_PCB", "Amkor Technology", "미국", "AMKR", "OSAT", "OSAT", "후공정 패키징·테스트", "핵심"),
    A(502, "07_PACKAGING_SUBSTRATE_PCB", "Unimicron", "대만", "3037.TW", "기판", "ABF 기판", "ABF 패키지 기판", "핵심"),
    A(503, "07_PACKAGING_SUBSTRATE_PCB", "Ibiden", "일본", "4062.T", "기판", "ABF 기판", "ABF 패키지 기판 선두권", "핵심"),
    A(504, "07_PACKAGING_SUBSTRATE_PCB", "Nan Ya PCB", "대만", "8046.TW", "기판", "ABF/PCB", "패키지 기판·PCB", "2차"),
    A(505, "07_PACKAGING_SUBSTRATE_PCB", "Kingboard Laminates", "홍콩", "1888.HK", "PCB 소재", "동박적층판/CCL", "PCB 핵심 소재·AI 서버 PCB 수혜", "2차"),
    A(506, "07_PACKAGING_SUBSTRATE_PCB", "AT&S", "오스트리아", "ATS.VI", "기판", "ABF/IC 기판", "고성능 IC 기판·패키징 기판", "2차"),
    A(507, "07_PACKAGING_SUBSTRATE_PCB", "대덕전자", "한국", "353200.KS", "기판", "FC-BGA 기판", "패키지 기판·FC-BGA", "2차"),
    A(508, "07_PACKAGING_SUBSTRATE_PCB", "이수페타시스", "한국", "007660.KS", "PCB", "고다층 PCB", "AI 가속기용 고다층 PCB·고변동성", "고위험"),

    # ===== 08 MLCC·수동부품 =====
    A(600, "08_MLCC_PASSIVE_COMPONENT", "무라타제작소", "일본", "6981.T", "MLCC", "MLCC", "MLCC 세계 최상위권", "핵심"),
    A(601, "08_MLCC_PASSIVE_COMPONENT", "삼성전기", "한국", "009150.KS", "MLCC/기판", "MLCC/FC-BGA", "MLCC 세계 상위권·FC-BGA 기판", "핵심"),
    A(602, "08_MLCC_PASSIVE_COMPONENT", "타이요유덴", "일본", "6976.T", "MLCC", "MLCC/인덕터", "MLCC·인덕터·수동부품", "2차"),
    A(603, "08_MLCC_PASSIVE_COMPONENT", "TDK", "일본", "6762.T", "수동부품", "수동부품/배터리", "MLCC·인덕터·소형 배터리", "2차"),
    A(604, "08_MLCC_PASSIVE_COMPONENT", "Yageo", "대만", "2327.TW", "수동부품", "MLCC/칩저항", "칩저항·MLCC·수동부품", "2차"),
    A(605, "08_MLCC_PASSIVE_COMPONENT", "Kyocera", "일본", "6971.T", "세라믹/부품", "세라믹패키지/부품", "세라믹 부품·전자부품", "2차"),

    # ===== 09 네트워크·광 =====
    A(700, "09_NETWORK_OPTICAL", "Arista Networks", "미국", "ANET", "네트워크", "스위치", "AI 데이터센터 이더넷 스위치", "핵심"),
    A(701, "09_NETWORK_OPTICAL", "Coherent", "미국", "COHR", "광부품", "광트랜시버/레이저", "광트랜시버·광부품", "핵심"),
    A(702, "09_NETWORK_OPTICAL", "Lumentum", "미국", "LITE", "광부품", "광부품/레이저", "광통신 부품·레이저", "핵심"),
    A(703, "09_NETWORK_OPTICAL", "Fabrinet", "미국", "FN", "광부품 제조", "광부품 제조", "광통신 부품 위탁제조", "2차"),
    A(704, "09_NETWORK_OPTICAL", "Applied Optoelectronics", "미국", "AAOI", "광트랜시버", "광트랜시버", "데이터센터 광모듈·고변동성", "고위험"),
    A(705, "09_NETWORK_OPTICAL", "Accton Technology", "대만", "2345.TW", "네트워크", "스위치 ODM", "화이트박스 스위치 ODM", "2차"),
    A(706, "09_NETWORK_OPTICAL", "Ciena", "미국", "CIEN", "광네트워크", "광네트워크", "데이터센터 인터커넥트·광전송", "2차"),

    # ===== 10 전력·냉각·그리드 =====
    A(800, "10_POWER_COOLING_GRID", "Vertiv", "미국", "VRT", "전력/냉각", "전력/냉각", "데이터센터 전력·냉각 인프라", "핵심"),
    A(801, "10_POWER_COOLING_GRID", "Eaton", "미국", "ETN", "전력관리", "전력관리/배전", "전력관리·배전·스위치기어", "핵심"),
    A(802, "10_POWER_COOLING_GRID", "Schneider Electric", "프랑스", "SU.PA", "전력관리", "전력관리/배전", "데이터센터 전력·자동화", "핵심"),
    A(803, "10_POWER_COOLING_GRID", "ABB", "스위스", "ABBN.SW", "전력/자동화", "전력기기/자동화", "전력기기·배전·자동화", "2차"),
    A(804, "10_POWER_COOLING_GRID", "GE Vernova", "미국", "GEV", "전력인프라", "전력망/발전", "전력망·발전 인프라", "2차"),
    A(805, "10_POWER_COOLING_GRID", "Siemens Energy", "독일", "ENR.DE", "전력인프라", "전력망/발전", "전력망·변전·발전 인프라", "2차"),
    A(806, "10_POWER_COOLING_GRID", "Delta Electronics", "대만", "2308.TW", "전원/냉각", "전원/냉각", "전원공급·열관리 솔루션", "핵심"),
    A(807, "10_POWER_COOLING_GRID", "Lite-On Technology", "대만", "2301.TW", "전원공급", "서버 PSU", "데이터센터 전원공급장치·파워모듈", "2차"),
    A(808, "10_POWER_COOLING_GRID", "Monolithic Power Systems", "미국", "MPWR", "전력반도체", "PMIC/전원칩", "AI 서버 전력관리 반도체", "핵심"),
    A(809, "10_POWER_COOLING_GRID", "HD현대일렉트릭", "한국", "267260.KS", "전력기기", "변압기/전력기기", "변압기·전력기기", "2차"),
    A(810, "10_POWER_COOLING_GRID", "LS ELECTRIC", "한국", "010120.KS", "전력기기", "배전/전력인프라", "배전·전력 인프라", "2차"),
    A(811, "10_POWER_COOLING_GRID", "Auras Technology", "대만", "3324.TWO", "냉각", "액체냉각/콜드플레이트", "AI 서버 액체냉각 부품", "고위험"),
    A(812, "10_POWER_COOLING_GRID", "Asia Vital Components", "대만", "3017.TW", "냉각", "팬/열관리", "AI 서버 열관리·냉각 솔루션", "고위험"),
    A(813, "10_POWER_COOLING_GRID", "Bloom Energy", "미국", "BE", "전력공급", "연료전지/분산전원", "AI 데이터센터 전력 공급 테마", "고위험"),

    # ===== 11 AI 서버·ODM =====
    A(900, "11_AI_SERVER_ODM", "Super Micro Computer", "미국", "SMCI", "AI 서버", "AI 서버/랙", "AI 서버·랙 시스템·고변동성", "고위험"),
    A(901, "11_AI_SERVER_ODM", "Dell Technologies", "미국", "DELL", "AI 서버", "AI 서버/엔터프라이즈", "AI 서버·엔터프라이즈 인프라", "핵심"),
    A(902, "11_AI_SERVER_ODM", "HPE", "미국", "HPE", "AI 서버", "AI 서버/HPC", "서버·HPC·엔터프라이즈 인프라", "2차"),
    A(903, "11_AI_SERVER_ODM", "Foxconn Hon Hai", "대만", "2317.TW", "EMS/ODM", "AI 서버 ODM", "AI 서버 위탁생산 핵심", "핵심"),
    A(904, "11_AI_SERVER_ODM", "Quanta Computer", "대만", "2382.TW", "ODM", "AI 서버 ODM", "AI 서버 ODM", "핵심"),
    A(905, "11_AI_SERVER_ODM", "Wiwynn", "대만", "6669.TW", "ODM", "하이퍼스케일 서버", "하이퍼스케일 AI 서버 ODM", "고위험"),
    A(906, "11_AI_SERVER_ODM", "Wistron", "대만", "3231.TW", "ODM", "AI 서버 ODM", "AI 서버·서버 ODM", "2차"),
    A(907, "11_AI_SERVER_ODM", "Inventec", "대만", "2356.TW", "ODM", "서버 ODM", "서버·노트북·AI 서버 ODM", "2차"),
    A(908, "11_AI_SERVER_ODM", "Gigabyte", "대만", "2376.TW", "서버/메인보드", "GPU 서버/메인보드", "AI 서버·메인보드·부품", "2차"),

    # ===== 12 클라우드·CAPEX(수요) =====
    A(950, "12_CLOUD_CAPEX", "Microsoft", "미국", "MSFT", "클라우드/CAPEX", "Azure/AI 인프라", "AI 데이터센터 CAPEX 방향성 핵심", "수요"),
    A(951, "12_CLOUD_CAPEX", "Amazon", "미국", "AMZN", "클라우드/CAPEX", "AWS/AI 인프라", "AI 데이터센터 수요·자체칩", "수요"),
    A(952, "12_CLOUD_CAPEX", "Alphabet", "미국", "GOOGL", "클라우드/CAPEX", "Google Cloud/TPU", "AI 인프라 수요·TPU", "수요"),
    A(953, "12_CLOUD_CAPEX", "Meta Platforms", "미국", "META", "클라우드/CAPEX", "AI 인프라/MTIA", "AI 데이터센터 투자 수요 핵심", "수요"),
    A(954, "12_CLOUD_CAPEX", "Oracle", "미국", "ORCL", "클라우드/CAPEX", "OCI/AI 인프라", "AI 클라우드 인프라 수요", "수요"),
    A(955, "12_CLOUD_CAPEX", "CoreWeave", "미국", "CRWV", "AI 클라우드", "GPU 클라우드", "AI GPU 클라우드·고변동성", "고위험"),
    A(956, "12_CLOUD_CAPEX", "Nebius", "미국", "NBIS", "AI 클라우드", "AI 클라우드", "AI 인프라 클라우드·고변동성", "고위험"),
]


# ---------------------------------------------------------------------------
# FRED 매크로 지표 — API 키가 있으면 값(mode=yoy: 전년동월대비 %, level: 현재 수준)을
# 채우고, 없거나 실패하면 링크 전용 카드로 대체된다.
#   fields: name, series_id, group, unit, mode, desc, url, country_label, target(선택)
# series_id 는 널리 쓰이는 값이나, 키 넣고 첫 실행 후 오차 있으면 조정.
# ---------------------------------------------------------------------------
FRED_MACROS: List[Dict] = [
    # 장기금리(월간, OECD)
    {"name": "한국 10년 금리", "series_id": "IRLTLT01KRM156N", "group": "rates", "unit": "%", "mode": "level",
     "country_label": "한국", "sort_order": 9020,
     "desc": "한국 10년물 국채금리(월간). 유동성·환율·부동산과 연동",
     "url": "https://fred.stlouisfed.org/series/IRLTLT01KRM156N"},
    {"name": "일본 10년 금리", "series_id": "IRLTLT01JPM156N", "group": "rates", "unit": "%", "mode": "level",
     "country_label": "일본", "sort_order": 9021,
     "desc": "일본 10년물 국채금리(월간). BOJ 정책·엔화와 직결",
     "url": "https://fred.stlouisfed.org/series/IRLTLT01JPM156N"},

    # 기준금리/정책금리
    {"name": "美 기준금리", "series_id": "FEDFUNDS", "group": "policy", "unit": "%", "mode": "level",
     "country_label": "미국", "target": "2.0%", "target_label": "물가목표", "sort_order": 9040,
     "desc": "연방기금금리(실효). 목표 표시는 금리 목표가 아니라 Fed의 장기 물가목표",
     "url": "https://fred.stlouisfed.org/series/FEDFUNDS"},
    {"name": "한국 기준금리", "series_id": "INTDSRKRM193N", "group": "policy", "unit": "%", "mode": "level",
     "country_label": "한국", "target": "2.0%", "target_label": "물가목표", "sort_order": 9041,
     "desc": "FRED/IMF 할인율 계열. 목표 표시는 금리 목표가 아니라 한은 물가안정목표",
     "url": "https://fred.stlouisfed.org/series/INTDSRKRM193N"},
    {"name": "일본 정책금리", "series_id": "IRSTCB01JPM156N", "group": "policy", "unit": "%", "mode": "level",
     "country_label": "일본", "target": "2.0%", "target_label": "물가목표", "sort_order": 9042,
     "desc": "일본 중앙은행 단기 정책금리 계열. 목표 표시는 금리 목표가 아니라 BOJ 물가목표",
     "url": "https://fred.stlouisfed.org/series/IRSTCB01JPM156N"},

    # 물가(CPI) — 전년동월대비 %
    {"name": "美 CPI", "series_id": "CPIAUCSL", "group": "cpi", "unit": "%", "mode": "yoy",
     "country_label": "미국", "target": "2.0%", "target_label": "물가목표", "sort_order": 9060,
     "desc": "미국 소비자물가 전년동월대비. 연준 정책의 핵심 변수",
     "url": "https://fred.stlouisfed.org/series/CPIAUCSL"},
    {"name": "美 근원 CPI", "series_id": "CPILFESL", "group": "cpi", "unit": "%", "mode": "yoy",
     "country_label": "미국", "target": "2.0%", "target_label": "물가목표", "sort_order": 9061,
     "desc": "식품·에너지 제외 근원물가(전년동월대비). 추세 인플레 지표",
     "url": "https://fred.stlouisfed.org/series/CPILFESL"},
    {"name": "한국 CPI", "series_id": "KORCPIALLMINMEI", "group": "cpi", "unit": "%", "mode": "yoy",
     "country_label": "한국", "target": "2.0%", "target_label": "물가목표", "sort_order": 9062,
     "desc": "한국 소비자물가 전년동월대비(OECD). 한은 목표 2%",
     "url": "https://fred.stlouisfed.org/series/KORCPIALLMINMEI"},
    {"name": "일본 CPI", "series_id": "FPCPITOTLZGJPN", "group": "cpi", "unit": "%", "mode": "level",
     "country_label": "일본", "target": "2.0%", "target_label": "물가목표", "sort_order": 9063,
     "desc": "일본 소비자물가 상승률(FRED/World Bank 연간 계열). BOJ 목표 2%",
     "url": "https://fred.stlouisfed.org/series/FPCPITOTLZGJPN"},
    {"name": "대만 CPI", "series_id": "TWNPCPIPCPPPT", "group": "cpi", "unit": "%", "mode": "level",
     "country_label": "대만", "target": "~2%", "target_label": "물가목표", "sort_order": 9064,
     "desc": "대만 소비자물가 상승률(FRED/IMF WEO 연간 계열). CBC 물가 안정 목표 참고",
     "url": "https://fred.stlouisfed.org/series/TWNPCPIPCPPPT"},

    # 생산자물가(PPI)
    {"name": "美 PPI", "series_id": "PPIACO", "group": "ppi", "unit": "%", "mode": "yoy",
     "country_label": "미국", "sort_order": 9080,
     "desc": "미국 생산자물가지수 전년동월대비. CPI 선행 성격",
     "url": "https://fred.stlouisfed.org/series/PPIACO"},
    {"name": "한국 PPI", "series_id": "KORPPDMMINMEI", "group": "ppi", "unit": "%", "mode": "yoy",
     "country_label": "한국", "sort_order": 9081,
     "desc": "한국 제조업 생산자물가 전년동월대비(OECD/FRED). 최신성은 날짜 확인",
     "url": "https://fred.stlouisfed.org/series/KORPPDMMINMEI"},
    {"name": "일본 PPI", "series_id": "JPNPPDMMINMEI", "group": "ppi", "unit": "%", "mode": "yoy",
     "country_label": "일본", "sort_order": 9082,
     "desc": "일본 제조업 생산자물가 전년동월대비(OECD/FRED). 최신성은 날짜 확인",
     "url": "https://fred.stlouisfed.org/series/JPNPPDMMINMEI"},

    # 통화량(M2)
    {"name": "美 M2 통화량", "series_id": "M2SL", "group": "money", "unit": "%", "mode": "yoy",
     "country_label": "미국", "sort_order": 9100,
     "desc": "미국 광의통화 전년동월대비. 유동성=자산가격 큰 흐름",
     "url": "https://fred.stlouisfed.org/series/M2SL"},
    {"name": "한국 M2 통화량", "series_id": "MYAGM2KRM189S", "group": "money", "unit": "%", "mode": "yoy",
     "country_label": "한국", "sort_order": 9101,
     "desc": "한국 광의통화(M2) 전년동월대비. 국내 유동성",
     "url": "https://fred.stlouisfed.org/series/MYAGM2KRM189S"},
]

# ---------------------------------------------------------------------------
# 링크 전용 매크로 — 값 자동수집이 마땅치 않아 해설 + 외부 링크만 제공.
#   fields: name, group, desc, url, note, country_label, target(선택), sort_order
# ---------------------------------------------------------------------------
LINK_MACROS: List[Dict] = [
    # FRED에서 안정적인 자동수집 계열을 찾기 어려운 항목
    {"name": "대만 기준금리", "group": "policy", "country_label": "대만", "sort_order": 9043, "note": "TE",
     "unit": "%", "target": "~2%", "target_label": "물가목표", "parser": "te_last_recorded_percent",
     "desc": "대만중앙은행(CBC) 정책금리. 목표 표시는 금리 목표가 아니라 물가 안정 목표 참고",
     "url": "https://tradingeconomics.com/taiwan/interest-rate"},
    {"name": "대만 PPI", "group": "ppi", "country_label": "대만", "sort_order": 9083, "note": "TE",
     "unit": "%", "parser": "te_ppi_change_percent",
     "desc": "대만 생산자물가 전년동월대비",
     "url": "https://tradingeconomics.com/taiwan/producer-prices-change"},
    # 통화량(일본)
    {"name": "일본 M2 통화량", "group": "money", "country_label": "일본", "sort_order": 9102, "note": "TE",
     "unit": "JPY bn", "parser": "te_money_level",
     "desc": "일본 M2 잔액(JPY Billion). 엔 유동성",
     "url": "https://tradingeconomics.com/japan/money-supply-m2"},
    # 위험자산·심리
    {"name": "코스피 변동성(VKOSPI)", "group": "risk", "country_label": "한국", "sort_order": 9120, "note": "Investing",
     "desc": "코스피200 변동성 지수(한국판 VIX). 급등=국내 위험회피",
     "url": "https://www.investing.com/indices/kospi-volatility"},
    {"name": "공포탐욕지수", "group": "risk", "country_label": "미국", "sort_order": 9121, "note": "CNN",
     "desc": "시장 심리 종합(0=극공포 ~ 100=극탐욕). CNN 집계",
     "url": "https://edition.cnn.com/markets/fear-and-greed"},
]


def enabled_assets() -> List[Dict]:
    """enabled=True 인 자산만 반환."""
    return [a for a in ASSETS if a.get("enabled", True)]
