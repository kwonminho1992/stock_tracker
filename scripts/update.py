"""전체 자산 수집 → 계산 → 검증 → latest.json / history.json 생성.

설계 원칙:
- 한 자산이 실패해도 전체 실행은 계속된다(실패 자산은 error 로 기록).
- NaN/Infinity 는 JSON 에 절대 들어가지 않는다(sanitize + allow_nan=False).
- 값이 의심스러우면 suspicious/stale/warning 으로 드러낸다.
- 정상 수집 0건 + 기존 정상 데이터 존재 시 덮어쓰지 않는다(좋은 데이터 보존).

사용법:
    python update.py                # 오늘 이미 갱신했으면 생략
    python update.py --force        # 강제 실행(자동화에서 사용)
    python update.py --asset 000660 # 특정 자산만 갱신(기존 파일에 병합)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from config import ASSETS, FRED_MACROS, HISTORY_DAYS, LINK_MACROS, MA_WINDOWS, enabled_assets
from data_sources import fetch_asset
from external_macro_source import fetch_tradingeconomics
from fred_source import available as fred_available
from fred_source import fetch_latest as fetch_fred_latest
from fred_source import load_dotenv
from fred_source import normalize_frequency
from indicators import (
    add_disparities,
    add_moving_averages,
    build_history_records,
    build_latest_record,
)
from validate_data import (
    DataValidationError,
    apply_soft_flags,
    check_fatal,
    validate_dataframe,
)

KST = timezone(timedelta(hours=9))

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "docs" / "data"
LATEST_PATH = DATA_DIR / "latest.json"
HISTORY_PATH = DATA_DIR / "history.json"

RUN_TYPE = "close"

COUNTRY_CODES = {
    "한국": "KR",
    "미국": "US",
    "일본": "JP",
    "대만": "TW",
    "유럽": "EU",
    "홍콩": "HK",
}

# 관측기간 시작일 기준의 보수적인 허용 지연(달력 일수).
# 월간 120일은 일반적인 발표 지연 및 월초 날짜 표기를 허용한다.
# 분기 240일/연간 550일은 더 느린 발표주기를 고려한다.
# 이는 공급기관의 SLA나 다음 발표일 예측이 아닌 화면상의 오래됨 경고 기준이다.
MACRO_STALE_AFTER_DAYS = {
    "daily": 14, "weekly": 35, "biweekly": 60,
    "monthly": 120, "quarterly": 240, "semiannual": 365, "annual": 550,
}


def macro_freshness(
    asof: Optional[str], frequency: Optional[str], today: Optional[date] = None,
    discontinued: bool = False,
) -> Dict:
    """관측일과 발표 빈도로 최신성을 판단. 조회 성공과 최신 관측치를 구분한다."""
    today = today or now_kst().date()
    frequency = normalize_frequency(frequency)
    threshold = MACRO_STALE_AFTER_DAYS.get(frequency)
    age_days = None
    warnings = []
    try:
        observed = date.fromisoformat(str(asof))
        age_days = (today - observed).days
    except (ValueError, TypeError):
        warnings.append("관측일을 확인할 수 없어 최신성 검증 불가")
    if age_days is not None and age_days < 0:
        warnings.append("미래 관측일로 최신성 검증 불가")
    if threshold is None:
        warnings.append("발표 빈도를 확인할 수 없어 최신성 검증 불가")
    unknown = age_days is None or age_days < 0 or threshold is None
    stale = not unknown and age_days > threshold
    if stale:
        warnings.append(
            f"오래된 관측치: {asof} · {age_days}일 경과 "
            f"(경고 기준 {threshold}일). 발표 지연 또는 계열 갱신 중단 확인 필요"
        )
    if discontinued:
        warnings.append("공급기관이 중단한 계열 · 현재 투자환경 해석에서 제외")
    return {
        "macro_frequency": frequency,
        "macro_age_days": age_days,
        "macro_stale_after_days": threshold,
        "macro_freshness": "unknown" if unknown else "stale" if stale or discontinued else "fresh",
        "macro_discontinued": bool(discontinued),
        "is_stale": bool(unknown or stale or discontinued),
        "warning": " / ".join(warnings) or None,
    }


# --------------------------------------------------------------------------- #
# 유틸
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    print(msg, flush=True)


def now_kst() -> datetime:
    return datetime.now(KST)


def _uses_krx(asset: Dict) -> bool:
    """장중 모드에서 KRX(FDR) 히스토리를 기반으로 하는 자산인지."""
    return asset.get("asset_type") == "kr_stock" or asset.get("source") in (
        "krx_index",
        "krx_stock",
    )


def make_error_record(asset: Dict, message: str) -> Dict:
    return {
        "name": asset.get("name", "?"),
        "code": asset.get("code", "?"),
        "ticker": asset.get("yf_ticker") or asset.get("code", "?"),
        "market": asset.get("market", "?"),
        "country": asset.get("country", asset.get("market", "?")),
        "sector": asset.get("sector"),
        "asset_type": asset.get("asset_type", "?"),
        "source": asset.get("source"),
        "note": asset.get("note"),
        "sort_order": asset.get("sort_order", 9999),
        "ai_group": asset.get("ai_group"),
        "ai_subgroup": asset.get("ai_subgroup"),
        "product_group": asset.get("product_group"),
        "exposure_type": asset.get("exposure_type"),
        "disparity_meaningful": asset.get("disparity_meaningful", True),
        "country_label": asset.get("country_label"),
        "listing_market": asset.get("listing_market"),
        "currency": asset.get("currency"),
        "price_source": asset.get("price_source"),
        "is_adr": asset.get("is_adr", False),
        "local_ticker": asset.get("local_ticker"),
        "display_ticker": asset.get("display_ticker") or asset.get("yf_ticker") or asset.get("code"),
        "detail_url": asset.get("detail_url"),
        "error": message,
    }


def sanitize_for_json(obj):
    """재귀적으로 NaN/Infinity → None 으로 치환(최종 방어선)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    return obj


def _country_code(label: Optional[str]) -> str:
    return COUNTRY_CODES.get(str(label or ""), str(label or "-"))


def _macro_link_record(item: Dict, source: str, reason: Optional[str] = None) -> Dict:
    country_label = item.get("country_label")
    country = _country_code(country_label)
    note = item.get("note") or source
    if reason:
        note = f"{note}: {reason}"
    return {
        "name": item.get("name"),
        "code": item.get("series_id") or item.get("code") or item.get("name"),
        "ticker": item.get("series_id") or item.get("code") or item.get("name"),
        "market": country,
        "country": country,
        "country_label": country_label,
        "sector": item.get("group"),
        "asset_type": "macro_link",
        "source": source,
        "note": note,
        "sort_order": item.get("sort_order", 9999),
        "ai_group": "00_INDEX",
        "ai_subgroup": item.get("group"),
        "product_group": item.get("desc"),
        "exposure_type": "BENCHMARK",
        "macro_group": item.get("group"),
        "macro_target": item.get("target"),
        "macro_target_label": item.get("target_label"),
        "disparity_meaningful": False,
        "listing_market": "-",
        "currency": item.get("unit") or "-",
        "price_source": source,
        "is_adr": False,
        "local_ticker": None,
        "display_ticker": item.get("series_id") or item.get("code") or "",
        "detail_url": item.get("url"),
        "link_only": True,
        "date": None,
        "close": None,
        "macro_frequency": normalize_frequency(item.get("frequency")),
        "macro_age_days": None,
        "macro_stale_after_days": MACRO_STALE_AFTER_DAYS.get(normalize_frequency(item.get("frequency"))),
        "macro_freshness": "unavailable",
        "macro_date_type": None,
        "is_stale": None,
        "warning": f"수치 미수집 · {reason or '외부 링크에서 직접 확인 필요'}",
    }


def _fred_macro_record(item: Dict) -> Dict:
    obs = fetch_fred_latest(item["series_id"], yoy=item.get("mode") == "yoy")
    if obs is None:
        return _macro_link_record(item, "FRED", "API 키 없음/조회 실패")

    mode = item.get("mode")
    value = obs.get("yoy_pct") if mode == "yoy" else obs.get("value")
    if value is None:
        return _macro_link_record(item, "FRED", "전년동월대비 계산 불가")

    country_label = item.get("country_label")
    country = _country_code(country_label)
    frequency = obs.get("frequency") or item.get("frequency")
    freshness = macro_freshness(
        obs.get("asof"), frequency,
        discontinued=obs.get("is_discontinued", False),
    )
    projection = bool(obs.get("is_projection") or item.get("is_projection"))
    if projection:
        projection_warning = "IMF 연간 전망 계열 · 당해·미래연도 수치는 전망치"
        freshness["warning"] = " / ".join(filter(None, [freshness["warning"], projection_warning]))
    return {
        "name": item["name"],
        "code": item["series_id"],
        "ticker": item["series_id"],
        "market": country,
        "country": country,
        "country_label": country_label,
        "sector": item.get("group"),
        "asset_type": "macro_index",
        "source": "fred",
        "note": item.get("note"),
        "sort_order": item.get("sort_order", 9999),
        "ai_group": "00_INDEX",
        "ai_subgroup": item.get("group"),
        "product_group": item.get("desc"),
        "exposure_type": "BENCHMARK",
        "macro_group": item.get("group"),
        "macro_mode": mode,
        "macro_target": item.get("target"),
        "macro_target_label": item.get("target_label"),
        "disparity_meaningful": False,
        "listing_market": "-",
        "currency": item.get("unit"),
        "price_source": "FRED",
        "is_adr": False,
        "local_ticker": None,
        "display_ticker": item["series_id"],
        "detail_url": item.get("url"),
        "date": obs.get("asof"),
        "close": value,
        "change_pct": None,
        "zone": None,
        "zone_label": None,
        "is_suspicious": False,
        "macro_date_type": "observation",
        "macro_frequency_source": "FRED metadata" if obs.get("frequency") else "configured",
        "macro_source_frequency": obs.get("source_frequency"),
        "macro_source_updated_at": obs.get("source_updated_at"),
        "macro_series_end": obs.get("series_end"),
        "macro_is_projection": projection,
        **freshness,
    }


def _external_macro_record(item: Dict) -> Dict:
    try:
        obs = fetch_tradingeconomics(item)
    except Exception:
        return _macro_link_record(item, item.get("note") or "Link", "조회 실패")
    if obs is None:
        return _macro_link_record(item, item.get("note") or "Link", "조회 실패")

    country_label = item.get("country_label")
    country = _country_code(country_label)
    freshness = macro_freshness(obs.get("asof"), item.get("frequency"))
    # HTML의 LastUpdate는 관측기간이 아니라 페이지 갱신일이다.
    # 값을 읽었어도 관측일을 검증하지 못했음을 표시한다.
    freshness["macro_freshness"] = "unknown"
    freshness["is_stale"] = True
    freshness["warning"] = " / ".join(filter(None, [
        freshness["warning"], "관측기간 미확인 · 표시 날짜는 출처 페이지 갱신일",
    ]))
    return {
        "name": item["name"],
        "code": item.get("code") or item["name"],
        "ticker": item.get("code") or item["name"],
        "market": country,
        "country": country,
        "country_label": country_label,
        "sector": item.get("group"),
        "asset_type": "macro_index",
        "source": str(item.get("note") or "external").lower(),
        "note": item.get("note"),
        "sort_order": item.get("sort_order", 9999),
        "ai_group": "00_INDEX",
        "ai_subgroup": item.get("group"),
        "product_group": item.get("desc"),
        "exposure_type": "BENCHMARK",
        "macro_group": item.get("group"),
        "macro_target": item.get("target"),
        "macro_target_label": item.get("target_label"),
        "disparity_meaningful": False,
        "listing_market": "-",
        "currency": item.get("unit") or "-",
        "price_source": item.get("note") or "external",
        "is_adr": False,
        "local_ticker": None,
        "display_ticker": item.get("code") or item.get("note") or "",
        "detail_url": item.get("url"),
        "date": obs.get("asof"),
        "close": obs.get("value"),
        "change_pct": None,
        "zone": None,
        "zone_label": None,
        "is_suspicious": False,
        "macro_date_type": "source_update",
        "macro_frequency_source": "configured",
        **freshness,
    }


def build_macro_records() -> List[Dict]:
    """FRED/API 매크로와 링크 전용 매크로를 latest payload용 레코드로 변환."""
    records: List[Dict] = []
    if not fred_available():
        records.extend(_macro_link_record(item, "FRED", "API 키 필요") for item in FRED_MACROS)
    else:
        records.extend(_fred_macro_record(item) for item in FRED_MACROS)
    for item in LINK_MACROS:
        if item.get("parser"):
            records.append(_external_macro_record(item))
        else:
            records.append(_macro_link_record(item, item.get("note") or "Link"))
    return records


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = sanitize_for_json(payload)
    # allow_nan=False : 혹시라도 비정상 float 이 남아 있으면 여기서 예외로 드러난다.
    text = json.dumps(clean, ensure_ascii=False, allow_nan=False, indent=2)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


# --------------------------------------------------------------------------- #
# 자산 1개 처리
# --------------------------------------------------------------------------- #

def process_asset(
    asset: Dict,
    fetch_fn: Optional[Callable[[Dict], "object"]] = None,
    today: Optional[date] = None,
    run_type: str = "close",
) -> Tuple[Dict, Optional[Tuple[str, Dict]]]:
    """자산 1개를 처리.

    반환: (latest_record, history_entry_or_None)
      - 성공: (정상 latest dict, (code, history_dict))
      - 실패: (error 가 포함된 latest dict, None)
    어떤 예외도 밖으로 던지지 않는다(자산 실패 격리).
    """
    if fetch_fn is None:
        def fetch_fn(a):
            return fetch_asset(a, run_type=run_type)
    if today is None:
        today = now_kst().date()

    name = asset.get("name", "?")
    code = asset.get("code", "?")
    try:
        df = fetch_fn(asset)
        validate_dataframe(df)

        df = add_moving_averages(df, MA_WINDOWS)
        df = add_disparities(df, MA_WINDOWS)

        latest = build_latest_record(asset, df)
        if run_type == "intraday":
            latest["source"] = (
                "krx+yfinance" if _uses_krx(asset) else "yfinance"
            )

        fatal = check_fatal(latest)
        if fatal:
            log(f"  ! {name}({code}) 치명적 검증 실패: {fatal}")
            return make_error_record(asset, fatal), None

        apply_soft_flags(latest, today=today)

        history = build_history_records(asset, df, history_days=HISTORY_DAYS)
        if not history:
            primary_window = latest.get("primary_window", 50)
            msg = f"히스토리 데이터가 부족합니다(disparity{primary_window} 계산 가능 구간 없음)."
            log(f"  ! {name}({code}) {msg}")
            return make_error_record(asset, msg), None

        hist_entry = {
            "name": asset["name"],
            "code": asset["code"],
            "ticker": asset.get("yf_ticker") or asset["code"],
            "market": asset["market"],
            "country": asset.get("country", asset.get("market")),
            "sector": asset.get("sector"),
            "asset_type": asset["asset_type"],
            "source": (
                "krx+yfinance"
                if run_type == "intraday" and _uses_krx(asset)
                else "yfinance" if run_type == "intraday" else asset.get("source")
            ),
            "note": asset.get("note"),
            "sort_order": asset.get("sort_order", 9999),
            "ai_group": asset.get("ai_group"),
            "product_group": asset.get("product_group"),
            "exposure_type": asset.get("exposure_type"),
            "disparity_meaningful": asset.get("disparity_meaningful", True),
            "primary_window": latest.get("primary_window"),
            "data": history,
        }

        flags = []
        if latest["is_stale"]:
            flags.append("STALE")
        if latest["is_suspicious"]:
            flags.append("SUSPICIOUS")
        flag_str = (" [" + ",".join(flags) + "]") if flags else ""
        log(
            f"  OK {name}({code}) "
            f"close={latest['close']} d{latest.get('primary_window')}={latest.get('primary_disparity')} "
            f"zone={latest['zone']}({latest['zone_label']}){flag_str}"
        )
        return latest, (asset["code"], hist_entry)

    except DataValidationError as e:
        log(f"  ! {name}({code}) 데이터 검증 실패: {e}")
        return make_error_record(asset, f"데이터 검증 실패: {e}"), None
    except ImportError as e:
        log(f"  ! {name}({code}) 라이브러리 오류: {e}")
        return make_error_record(asset, f"라이브러리 오류: {e}"), None
    except Exception as e:  # noqa: BLE001  (한 자산 실패가 전체를 멈추면 안 됨)
        log(f"  ! {name}({code}) 수집/계산 실패: {type(e).__name__}: {e}")
        return make_error_record(asset, f"{type(e).__name__}: {e}"), None


# --------------------------------------------------------------------------- #
# 전체 실행
# --------------------------------------------------------------------------- #

def run(
    assets: List[Dict], today: Optional[date] = None, run_type: str = "close"
) -> Tuple[List[Dict], Dict[str, Dict]]:
    latest_records: List[Dict] = []
    history_map: Dict[str, Dict] = {}

    total = len(assets)
    for i, asset in enumerate(assets, start=1):
        log(f"[{i}/{total}] {asset.get('name')} ({asset.get('code')}) 처리 중...")
        latest, hist = process_asset(asset, today=today, run_type=run_type)
        latest_records.append(latest)
        if hist is not None:
            code, entry = hist
            history_map[code] = entry

    return latest_records, history_map


def build_latest_payload(records: List[Dict], run_type: str = RUN_TYPE) -> Dict:
    return {
        "updated_at": now_kst().isoformat(timespec="seconds"),
        "run_type": run_type,
        "assets": records,
    }


def count_ok(records: List[Dict]) -> int:
    return sum(1 for r in records if "error" not in r)


def already_updated_today(today: date) -> bool:
    data = load_json(LATEST_PATH)
    if not data:
        return False
    ts = str(data.get("updated_at", ""))
    return ts[:10] == today.isoformat()


def has_good_existing() -> bool:
    """기존 latest.json 에 정상(error 아님) 자산이 하나라도 있는지."""
    data = load_json(LATEST_PATH)
    if not data:
        return False
    return any("error" not in a for a in data.get("assets", []))


def content_changed(new_assets: List[Dict], new_history: Dict[str, Dict]) -> bool:
    """updated_at 을 제외한 실제 내용이 기존 파일과 달라졌는지 비교.

    updated_at(타임스탬프)만 바뀐 경우 불필요한 커밋을 막기 위함.
    """
    old_latest = load_json(LATEST_PATH) or {}
    old_history = load_json(HISTORY_PATH) or {}
    if old_latest.get("assets") != new_assets:
        return True
    if old_history != new_history:
        return True
    return False


def merge_single_asset(
    latest_record: Dict, hist: Optional[Tuple[str, Dict]], run_type: str = RUN_TYPE
) -> None:
    """--asset 모드: 기존 파일을 읽어 해당 자산만 교체 후 저장."""
    latest_data = load_json(LATEST_PATH) or {"run_type": RUN_TYPE, "assets": []}
    assets = latest_data.get("assets", [])
    code = latest_record.get("code")
    replaced = False
    for idx, a in enumerate(assets):
        if a.get("code") == code:
            assets[idx] = latest_record
            replaced = True
            break
    if not replaced:
        assets.append(latest_record)
    latest_data["assets"] = assets
    latest_data["updated_at"] = now_kst().isoformat(timespec="seconds")
    latest_data["run_type"] = run_type
    write_json(LATEST_PATH, latest_data)

    history_data = load_json(HISTORY_PATH) or {}
    if hist is not None:
        h_code, entry = hist
        history_data[h_code] = entry
    # 실패한 경우 기존 히스토리는 그대로 둔다(굳이 지우지 않음).
    write_json(HISTORY_PATH, history_data)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="시장/종목 이격도 트래커 데이터 갱신")
    parser.add_argument(
        "--force", action="store_true", help="오늘 이미 갱신했어도 강제로 다시 실행"
    )
    parser.add_argument(
        "--asset", type=str, default=None, help="특정 자산 코드만 갱신(기존 파일에 병합)"
    )
    parser.add_argument(
        "--run-type",
        choices=["close", "intraday"],
        default="close",
        help="close=종가(국내 FDR/KRX), intraday=장중(국내 종목 FDR+yfinance, 그 외 yfinance)",
    )
    args = parser.parse_args(argv)
    run_type = args.run_type
    load_dotenv()

    today = now_kst().date()
    start = time.time()

    log(f"=== market-disparity-tracker 갱신 시작 ({now_kst().isoformat(timespec='seconds')}) ===")
    log(f"실행 모드: {run_type} / 출력 경로: {DATA_DIR}")

    # --- 단일 자산 모드 ---
    if args.asset:
        target = next((a for a in ASSETS if a.get("code") == args.asset), None)
        if target is None:
            log(f"[에러] config.ASSETS 에서 code={args.asset} 를 찾을 수 없습니다.")
            return 2
        log(f"[단일 모드/{run_type}] {target.get('name')} ({args.asset}) 만 갱신합니다.")
        latest, hist = process_asset(target, today=today, run_type=run_type)
        merge_single_asset(latest, hist, run_type=run_type)
        log(f"완료. ({time.time() - start:.1f}s)")
        return 0 if "error" not in latest else 1

    # --- 전체 모드 ---
    # 종가 모드만 '오늘 이미 갱신' 가드를 적용한다(장중 모드는 하루에 여러 번 갱신 가능).
    if run_type == "close" and not args.force and already_updated_today(today):
        log(f"오늘({today}) 이미 갱신됨. 다시 실행하려면 --force 를 사용하세요.")
        return 0

    assets = enabled_assets()
    log(f"대상 자산 {len(assets)}개 (비활성 제외)")

    latest_records, history_map = run(assets, today=today, run_type=run_type)
    macro_records = build_macro_records()
    latest_records.extend(macro_records)
    fred_values = sum(1 for r in macro_records if r.get("source") == "fred")
    fred_fallbacks = sum(
        1 for r in macro_records if r.get("source") == "FRED" and r.get("link_only")
    )
    link_only = sum(1 for r in macro_records if r.get("link_only"))
    log(
        f"매크로 참고 지표 {len(macro_records)}개 추가 "
        f"(FRED 값 {fred_values}개 / FRED 링크대체 {fred_fallbacks}개 / 링크전용 {link_only}개)"
    )
    ok = count_ok(latest_records)
    err = len(latest_records) - ok
    stale = sum(1 for r in latest_records if r.get("is_stale"))
    susp = sum(1 for r in latest_records if r.get("is_suspicious"))

    log("--- 요약 ---")
    log(f"  정상 {ok} / 실패 {err} / stale {stale} / suspicious {susp}")

    # 정상 0건인데 기존 정상 데이터가 있으면 덮어쓰지 않는다(좋은 데이터 보존).
    if ok == 0 and has_good_existing():
        log("[중단] 정상 수집 0건 + 기존 정상 데이터 존재 → 기존 파일 보존, 갱신 생략")
        return 1

    # 타임스탬프 외 실제 내용이 동일하면 쓰지 않는다(불필요한 커밋 방지).
    if not content_changed(latest_records, history_map):
        log("데이터 변경 없음 → 파일 유지(불필요한 커밋 방지)")
        return 0 if ok > 0 else 1

    latest_payload = build_latest_payload(latest_records, run_type=run_type)
    write_json(LATEST_PATH, latest_payload)
    write_json(HISTORY_PATH, history_map)
    log(f"  latest : {LATEST_PATH}")
    log(f"  history: {HISTORY_PATH} (자산 {len(history_map)}개)")
    log(f"완료. ({time.time() - start:.1f}s)")

    if ok == 0:
        log("[경고] 정상 수집된 자산이 하나도 없습니다.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
