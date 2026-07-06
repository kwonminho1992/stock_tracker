"""FRED(미국 세인트루이스 연준) 매크로 지표 수집.

- API 키는 환경변수 FRED_API_KEY 에서 읽는다(.env 또는 GitHub Secret).
- 키가 없거나 조회에 실패하면 None 을 돌려주고, 호출측은 '링크 전용'으로 대체한다.
  (키 유무와 무관하게 파이프라인은 절대 죽지 않는다.)
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Dict, Optional

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv() -> None:
    """저장소 루트의 .env 를 읽어 os.environ 에 채운다(이미 있는 값은 유지).

    외부 의존성(python-dotenv) 없이 KEY=VALUE 형식만 간단히 처리한다.
    """
    path = _ROOT / ".env"
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val
    except OSError:
        pass


def api_key() -> str:
    return os.environ.get("FRED_API_KEY", "").strip()


def available() -> bool:
    return bool(api_key())


def fetch_latest(series_id: str, yoy: bool = False) -> Optional[Dict]:
    """FRED 시계열의 최신 관측치를 반환.

    반환: {"value": float, "asof": "YYYY-MM-DD", "yoy_pct": float|None} 또는 None(실패).
      - yoy=True 면 12개월 전 대비 변화율(%)도 계산(월간 시계열 가정).
    """
    key = api_key()
    if not key:
        return None
    params = urllib.parse.urlencode({
        "series_id": series_id,
        "api_key": key,
        "file_type": "json",
        "observation_end": date.today().isoformat(),
        "sort_order": "desc",
        "limit": 14,
    })
    url = f"{FRED_BASE}?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "market-disparity-tracker"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        obs = [
            o for o in data.get("observations", [])
            if o.get("value") not in (".", "", None)
        ]
        if not obs:
            return None
        value = float(obs[0]["value"])
        asof = obs[0]["date"]
        yoy_pct = None
        if yoy and len(obs) >= 13:
            try:
                year_ago = float(obs[12]["value"])
                if year_ago != 0:
                    yoy_pct = round((value / year_ago - 1.0) * 100.0, 2)
            except (ValueError, TypeError):
                yoy_pct = None
        return {"value": round(value, 4), "asof": asof, "yoy_pct": yoy_pct}
    except Exception:
        return None
