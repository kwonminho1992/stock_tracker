# market-disparity-tracker

시장/종목의 **이격도(disparity)** 를 매일 종가 기준으로 자동 계산해, 단기 과열도를
한눈에 점검하기 위한 개인용 대시보드입니다.

> ⚠️ **면책**: 이 프로젝트는 **정보 제공용**이며 매수/매도 추천이나 투자 권유가 아닙니다.
> 무료 데이터 소스(pykrx · yfinance)는 지연·결측·오류가 있을 수 있고, 모든 투자 판단과
> 책임은 이용자 본인에게 있습니다.

---

## 1. 프로젝트 목적

단순히 차트를 보는 도구가 아니라, **리스크 관리 보조 도구**입니다. 다음 질문에 답하는 것을
목표로 합니다.

- 지금 시장 전체가 과열인가?
- 코스피와 반도체 주도주의 과열이 동시에 발생했는가?
- SK하이닉스 같은 주도주가 시장보다 더 과열됐는가?
- 신규매수를 멈춰야 할 구간인가?
- 레버리지 노출을 줄여야 할 구간인가?
- 조정 후 재진입을 검토할 수 있는 구간인가?

따라서 "대충 맞는 값"을 예쁘게 보여주기보다, **값이 의심스러우면 경고(warning / suspicious /
stale / error)를 명확히 드러내는 것**을 최우선 설계 원칙으로 둡니다.

---

## 2. 이격도 산식

이격도는 현재가가 이동평균에서 얼마나 떨어져 있는지를 백분율로 나타냅니다.

```
disparity20  = close / ma20  * 100
disparity50  = close / ma50  * 100   ← 메인 판단 지표
disparity120 = close / ma120 * 100
```

- 이동평균은 `min_periods = 윈도우` 로 계산합니다. 즉 데이터가 부족한 구간은
  **부분 평균을 만들지 않고 NaN** 으로 두어 "조용히 틀린 값"을 방지합니다.

보조 지표: `disparity20`, `disparity120`, `change_pct`(전일 대비 등락률), 최근 1년 `disparity50` 추이.

---

## 3. 해석 기준 (disparity50)

| 구간 코드  | 라벨     | 조건                         | 의미(예시 해석)                       |
| ---------- | -------- | ---------------------------- | ------------------------------------- |
| `overheat` | 과열     | `disparity50 >= 130`         | 추격매수 자제, 레버리지 축소 검토      |
| `caution`  | 경계     | `120 <= disparity50 < 130`   | 신규매수 속도 조절                    |
| `normal`   | 정상     | `105 < disparity50 < 120`    | 추세 유지 구간                        |
| `cooldown` | 과열해소 | `disparity50 <= 105`         | 조정 후 재진입 검토 가능 구간         |

> 위 해석은 참고용 가이드일 뿐 매매 신호가 아닙니다. 경계값은
> [`scripts/config.py`](scripts/config.py) 의 `ZONE_*_MIN` 에서 조정할 수 있습니다.

검증 플래그:

- **suspicious(값 확인 필요)**: `disparity50 < 50` 또는 `> 200` (정상범위 이탈)
- **stale(데이터 오래됨)**: 마지막 데이터가 7일 이상 지남
- **error(데이터 오류)**: 수집 실패, `close <= 0`, `ma50 <= 0` 또는 계산 불가 등

---

## 4. 추적 자산 목록

[`scripts/config.py`](scripts/config.py) 의 `ASSETS` 에서 관리합니다(한 줄 추가/삭제로 변경).

**국내 지수 (pykrx)**
- 코스피 `1001`, 코스피200 `1028`, 코스닥 `2001`

**국내 개별종목 (pykrx)**
- SK하이닉스 `000660`, 삼성전자 `005930`, 삼성전기 `009150`, LG이노텍 `011070`
- SOL AI반도체TOP2 PLUS — **종목코드 미확정(TODO)**. `config.py` 에서 코드 입력 후
  `enabled: True` 로 바꾸면 활성화됩니다.

**해외 지수/종목 (yfinance)**
- S&P500 `^GSPC`, 나스닥100 `^NDX`, 마이크론 `MU`, 엔비디아 `NVDA`, 브로드컴 `AVGO`

> 코스닥 종합지수 코드(`2001`)나 ETF 코드가 의심되면 값이 비정상으로 표시되니
> 화면의 경고를 보고 `config.py` 에서 수정하세요.

---

## 5. 데이터 소스

| 대상            | 라이브러리 | 함수                                |
| --------------- | ---------- | ----------------------------------- |
| 국내 지수       | pykrx      | `stock.get_index_ohlcv`             |
| 국내 종목/ETF   | pykrx      | `stock.get_market_ohlcv`            |
| 해외 지수/종목  | yfinance   | `yf.download(..., auto_adjust=True)`|

- 모든 데이터는 **일봉 종가** 기준으로 통일합니다.
- 내부적으로는 모두 `date` 인덱스 + `close` 컬럼을 가진 표준 DataFrame 으로 변환합니다.
- yfinance 가 MultiIndex 컬럼을 반환해도 `Close` 를 정상 추출합니다.
- 해외 종목은 `auto_adjust=True` 로 액면분할/배당을 보정합니다(예: NVDA 분할).

---

## 6. 로컬 실행 방법

```bash
# 1) 의존성 설치
pip install -r scripts/requirements.txt

# 2) 데이터 수집 + 계산 (docs/data/*.json 생성)
python scripts/update.py --force

# 3) 정적 페이지 미리보기
cd docs
python -m http.server 8000
# 브라우저에서 http://localhost:8000 접속
```

옵션:

```bash
python scripts/update.py            # 오늘 이미 갱신했으면 생략
python scripts/update.py --force    # 강제 재실행
python scripts/update.py --asset 000660       # 특정 자산만 갱신(기존 파일에 병합)
python scripts/update.py --run-type intraday --force   # 장중(현재가) 모드
```

**모드(run_type) 설명:**

| 모드 | 데이터 | 용도 |
| --- | --- | --- |
| `close` (기본) | 국내=pykrx 종가, 해외=yfinance 종가 | 매일 장마감 후 정식 갱신 |
| `intraday` | **전 종목 yfinance 지연시세(현재가)** | 장중에 수동으로 "지금 과열도" 확인 |

- 장중 모드는 당일 진행 중인 봉의 현재가(약 15~20분 지연)를 종가 자리에 넣어 이격도를 계산합니다.
- 국내 종목·지수는 `config.py` 의 `yf_ticker`(예: `000660.KS`, `^KS11`)로 조회합니다.

테스트:

```bash
pytest -q          # mock DataFrame 기반, 네트워크 불필요
```

---

## 7. GitHub Pages 설정 방법

1. 이 폴더(`market-disparity-tracker`)를 GitHub 저장소로 push 합니다.
2. 저장소 **Settings → Pages** 로 이동합니다.
3. **Source: Deploy from a branch**, **Branch: `main` / `/docs`** 선택 후 저장.
4. 잠시 후 `https://<사용자명>.github.io/<저장소명>/` 에서 대시보드가 열립니다.

> `docs/.nojekyll` 파일이 있어 Jekyll 처리 없이 정적 파일이 그대로 서빙됩니다.

---

## 8. GitHub Actions 자동 갱신

[`.github/workflows/update.yml`](.github/workflows/update.yml)

- **스케줄**: 매 평일 **KST 16:20**(UTC `20 7 * * 1-5`)에 실행 → 항상 **종가(close) 모드**.
- **수동 실행**: Actions 탭 → **"Run workflow"** → **run_type** 선택(`intraday` 기본 / `close`).
  장중에 핸드폰·PC에서 눌러 그 시점 이격도를 즉시 갱신할 수 있습니다.
- 동작 순서: 의존성 설치 → (pytest 있으면) 테스트 → `update.py --force` →
  `docs/data/latest.json`, `docs/data/history.json` **변경 시에만** 커밋/푸시.
- 커밋 메시지: `data: update market disparity YYYY-MM-DDTHH:mmZ`
- push 실패 시 `git pull --rebase` 후 최대 3회 재시도.
- `permissions: contents: write` 로 Actions 가 커밋을 push 합니다.

> 데이터(타임스탬프 제외)에 실제 변화가 없으면 파일을 다시 쓰지 않으므로
> 불필요한 커밋이 생기지 않습니다(휴장일 등).

---

## 9. 데이터 파일 구조

### `docs/data/latest.json`

```jsonc
{
  "updated_at": "2026-06-24T16:20:00+09:00",
  "run_type": "close",
  "assets": [
    {
      "name": "SK하이닉스",
      "code": "000660",
      "market": "KR",
      "asset_type": "kr_stock",
      "date": "2026-06-24",
      "close": 2919000,
      "ma20": 2500000,
      "ma50": 2300000,
      "ma120": 1800000,
      "disparity20": 116.76,
      "disparity50": 126.91,
      "disparity120": 162.17,
      "change_pct": 5.61,
      "zone": "caution",
      "zone_label": "경계",
      "is_stale": false,
      "is_suspicious": false,
      "warning": null
    },
    {
      "name": "데이터 실패 예시",
      "code": "ERROR",
      "market": "KR",
      "asset_type": "kr_stock",
      "error": "데이터 수집 실패 사유"
    }
  ]
}
```

- 정상 자산은 모든 수치 필드를 가지며, 실패 자산은 `error` 필드만 가집니다.
- 모든 숫자 필드는 **유한한 수 또는 `null`** 입니다(NaN/Infinity 없음).

### `docs/data/history.json`

```jsonc
{
  "000660": {
    "name": "SK하이닉스",
    "code": "000660",
    "market": "KR",
    "asset_type": "kr_stock",
    "data": [
      { "date": "2026-06-24", "close": 2919000, "ma50": 2300000, "disparity50": 126.91, "zone": "caution" }
    ]
  }
}
```

- 자산 코드를 key 로 갖고, 각 값에 최근 약 1년치 `disparity50` 시계열을 담습니다.
- 데이터가 부족하거나 실패한 자산은 history 에서 **제외**됩니다.

---

## 10. 프로젝트 구조

```
market-disparity-tracker/
├─ README.md
├─ scripts/
│  ├─ config.py          # 자산 목록 · MA 윈도우 · 구간/검증 기준
│  ├─ data_sources.py    # pykrx / yfinance → 표준 DataFrame
│  ├─ indicators.py      # 이동평균 · 이격도 · 구간분류 · 레코드 빌더
│  ├─ validate_data.py   # 치명적/소프트 검증(error·suspicious·stale)
│  ├─ update.py          # 수집→계산→검증→JSON 생성 오케스트레이션
│  └─ requirements.txt
├─ docs/                 # GitHub Pages 루트
│  ├─ index.html
│  ├─ app.js
│  ├─ styles.css
│  ├─ .nojekyll
│  └─ data/
│     ├─ latest.json
│     └─ history.json
├─ tests/
│  ├─ test_indicators.py
│  └─ test_serialization.py
└─ .github/workflows/update.yml
```

---

## 11. 무료 데이터 소스의 한계

- **지연/결측**: pykrx(KRX)·yfinance(Yahoo)는 비공식/무료 소스로, 일시적 차단·지연·결측·
  컬럼 변경이 발생할 수 있습니다. 이때 해당 자산은 `error`/`stale` 로 표시됩니다.
- **휴장일 캘린더 미반영(1차)**: 정확한 거래소 휴장일 캘린더 대신 "7일 이상 미갱신"
  단순 기준으로 stale 을 판단합니다.
- **해외 종가 시점 차이**: 미국장 종가는 KST 기준 다음 날 새벽에 확정되므로, 국내 종목보다
  최대 1~3일 날짜가 뒤처질 수 있습니다(주말/휴일 포함). 7일 임계값으로 흡수합니다.
- **수정종가 사용**: 해외 종목은 분할/배당 보정된 값이라 표시 종가가 실제 체결가와 다를 수
  있습니다.

---

## 12. 1차 구현 범위 / 향후 계획

**구현됨**
- 종가(close) 모드 — 매일 자동 갱신
- 장중(intraday) 모드 — 수동 실행 시 yfinance 지연시세로 현재가 이격도 계산
- 데이터 출처 표기, 데스크탑/모바일 반응형

**미구현 / 향후 후보**
- 텔레그램·푸시 알림
- 정확한 휴장일 캘린더(현재는 7일 기준 stale 판정)
- 자산별 임계값 커스터마이즈
- 코스피200(`^KS200`) 등 일부 국내 지수의 장중 yfinance 심볼 검증
