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

from config import ASSETS, HISTORY_DAYS, MA_WINDOWS, enabled_assets
from data_sources import fetch_asset
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
