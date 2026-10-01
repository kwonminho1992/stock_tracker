/* Pure snapshot analysis shared by the browser and Node verification. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.MarketInsights = api;
})(typeof window !== "undefined" ? window : null, function () {
  "use strict";

  const DAY = 86400000;
  const thresholds = Object.freeze({ staleCalendarDays: 7, caution: 120, hot: 130, slopeSessions: 5 });
  const groupLabels = Object.freeze({
    "01_COMPUTE_ASIC": "AI 연산·ASIC",
    "02_EDA_IP": "EDA·IP",
    "03_MEMORY_STORAGE": "메모리·스토리지",
    "04_FOUNDRY_MANUFACTURING": "파운드리·제조",
    "05_EQUIPMENT_TEST": "장비·테스트",
    "06_MATERIALS_WAFER": "소재·웨이퍼",
    "07_PACKAGING_SUBSTRATE_PCB": "패키징·기판·PCB",
    "08_MLCC_PASSIVE_COMPONENT": "MLCC·수동부품",
    "09_NETWORK_OPTICAL": "네트워크·광",
    "10_POWER_COOLING_GRID": "전력·냉각·그리드",
    "11_AI_SERVER_ODM": "AI 서버·ODM",
    "12_CLOUD_CAPEX": "클라우드·CAPEX",
  });
  const explain = Object.freeze({
    returns: "최근 5·20·60개 고유 거래일 전 제공처 가격 대비 성과. 장중 값과 해외 수정주가의 분할·배당 보정이 포함될 수 있습니다. 원화 환산이나 별도로 계산한 현금배당 총수익률은 아닙니다.",
    relative: "종목의 20거래일 시작일·종료일과 같은 날짜의 상장시장 지수 수익률을 뺀 %p. 날짜가 맞지 않으면 표시하지 않습니다.",
    groups: "유효한 개별 종목의 수익률 중앙값. 시장 대비 성과는 비교 가능한 종목의 중앙값이며 산업 성장률·시가총액 가중 지수가 아닙니다.",
    trend: "50·120일 평균선 위치와 50일선의 5거래일 방향을 함께 확인합니다. 두 선 위이고 50일선 상승 시 상승 추세, 120일선 위·50일선 아래이고 50일선 상승 시 추세 속 조정, 두 선 아래이고 50일선 하락 시 추세 약화, 그 외는 회복 확인 중입니다. 평균선이나 기울기가 부족하면 판정하지 않습니다.",
    distance: "현재 가격이 해당 이동평균보다 얼마나 높은지 %로 표시합니다. 판정 평균선은 주식 25일·지수와 ETF 50일이 기본이며 종목 메타에 지정된 기간을 우선합니다. 판정 평균보다 20% 이상 높으면 높은 이격, 30% 이상이면 과열 주의로 분류하며 매수·매도 신호가 아닙니다. 120일 평균선은 중기 위치와 추세 확인에 사용합니다.",
    freshness: "서울 기준 달력일로 7일 이상 지난 데이터, 오류·지연·의심 플래그, 최신값과 이력 불일치는 현재 요약과 분야 통계에서 제외합니다.",
    changes: "최신 고유 거래일과 바로 전 거래일의 50일선 교차 및 판정 이격도 120%·130%(판정 평균 대비 +20%·+30%) 경계 통과를 표시합니다. 주식은 기본 25일·지수와 ETF는 기본 50일 평균이 기준입니다. 같은 날짜의 반복 갱신은 새 변화로 세지 않습니다.",
  });

  function finite(value) { return typeof value === "number" && Number.isFinite(value); }
  function positive(value) { return finite(value) && value > 0; }
  function dateTime(value) {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
    const ms = Date.parse(value + "T00:00:00Z");
    return Number.isFinite(ms) && new Date(ms).toISOString().slice(0, 10) === value ? ms : null;
  }
  function seoulDate(now) { return new Date(now.getTime() + 9 * 3600000).toISOString().slice(0, 10); }
  function ageInDays(value, today) {
    const valueTime = dateTime(value);
    return valueTime === null ? null : (dateTime(today) - valueTime) / DAY;
  }
  function pct(start, end) { return positive(start) && positive(end) ? (end / start - 1) * 100 : null; }
  function distance(asset, window) { return positive(asset.close) && positive(asset["ma" + window]) ? pct(asset["ma" + window], asset.close) : null; }
  function median(values) {
    const sorted = values.filter(finite).sort((a, b) => a - b);
    const i = Math.floor(sorted.length / 2);
    return sorted.length ? sorted.length % 2 ? sorted[i] : (sorted[i - 1] + sorted[i]) / 2 : null;
  }
  function seriesFor(history, code) {
    const entry = history && history[code];
    const rows = Array.isArray(entry) ? entry : entry && Array.isArray(entry.data) ? entry.data : [];
    const dates = new Map();
    rows.forEach((row) => { if (row && dateTime(row.date) !== null) dates.set(row.date, row); });
    return Array.from(dates.values()).sort((a, b) => a.date.localeCompare(b.date));
  }
  function isStock(asset) { return /_stock$/.test(asset.asset_type || ""); }
  function primaryWindowFor(asset) {
    return Number.isInteger(asset.primary_window) && asset.primary_window > 0 ? asset.primary_window : isStock(asset) ? 25 : 50;
  }
  function benchmarkFor(asset) {
    const listing = String(asset.listing_market || "").toUpperCase();
    let market = asset.market;
    if (/NASDAQ|NYSE|US INDEX/.test(listing)) market = "US";
    else if (/KRX/.test(listing)) market = "KR";
    else if (/TWSE|TPEX/.test(listing)) market = "TW";
    else if (/^TSE$|TOKYO/.test(listing)) market = "JP";
    else if (/HKEX/.test(listing)) market = "HK";
    else if (/XETRA|EURONEXT|SIX|WIENER/.test(listing)) market = "EU";
    return { KR: "^KS11", US: "^GSPC", JP: "^N225", TW: "^TWII" }[market] || null;
  }
  function qualityFor(asset, rows, today, globalOutdated) {
    const reasons = [];
    const age = ageInDays(asset.date, today);
    const stale = globalOutdated || asset.is_stale === true || (age !== null && age >= thresholds.staleCalendarDays);
    if (asset.error) reasons.push("수집 오류");
    if (stale) reasons.push("오래된 데이터");
    if (asset.is_suspicious) reasons.push("품질 확인 필요");
    if (age === null) reasons.push("기준일 없음");
    else if (age < 0) reasons.push("미래 기준일");
    if (!positive(asset.close)) reasons.push("유효한 가격 없음");
    const end = rows[rows.length - 1];
    if (!end) reasons.push("가격 이력 없음");
    else if (end.date !== asset.date) reasons.push("최신값과 이력 날짜 불일치");
    else if (!positive(end.close) || !positive(asset.close) || Math.abs(end.close - asset.close) > Math.max(0.000001, Math.abs(asset.close) * 0.00000001)) reasons.push("최신값과 이력 가격 불일치");
    if (end && (end.error || end.is_stale || end.is_suspicious)) reasons.push("최신 이력 품질 확인 필요");
    return { valid: reasons.length === 0, stale, reasons };
  }
  function periodReturn(rows, sessions) {
    if (rows.length <= sessions) return null;
    const end = rows[rows.length - 1];
    const start = rows[rows.length - 1 - sessions];
    return pct(start.close, end.close);
  }
  function classifyTrend(asset, rows, valid) {
    const unknown = { key: "unknown", label: "판정 보류" };
    if (!valid || !positive(asset.ma50) || !positive(asset.ma120) || rows.length <= thresholds.slopeSessions) return unknown;
    const previousAverage = rows[rows.length - 1 - thresholds.slopeSessions].ma50;
    if (!positive(previousAverage)) return unknown;
    const rising = asset.ma50 > previousAverage;
    const falling = asset.ma50 < previousAverage;
    if (asset.close >= asset.ma50 && asset.close >= asset.ma120 && rising) return { key: "up", label: "상승 추세" };
    if (asset.close < asset.ma50 && asset.close >= asset.ma120 && rising) return { key: "pullback", label: "추세 속 조정" };
    if (asset.close < asset.ma50 && asset.close < asset.ma120 && falling) return { key: "weak", label: "추세 약화" };
    return { key: "recovering", label: "회복 확인 중" };
  }
  function primaryDisparity(row, window) {
    if (!positive(row.close)) return null;
    if (positive(row["ma" + window])) return row.close / row["ma" + window] * 100;
    if (positive(row.primary_disparity)) return row.primary_disparity;
    return positive(row["disparity" + window]) ? row["disparity" + window] : null;
  }
  function changesFor(asset, rows, valid) {
    if (!valid || rows.length < 2) return [];
    const previous = rows[rows.length - 2];
    const changes = [];
    if (positive(previous.close) && positive(previous.ma50) && positive(asset.ma50)) {
      if (previous.close <= previous.ma50 && asset.close > asset.ma50) changes.push({ kind: "ma50_up", label: "50일선 상향 돌파" });
      else if (previous.close >= previous.ma50 && asset.close < asset.ma50) changes.push({ kind: "ma50_down", label: "50일선 하향 이탈" });
    }
    const window = primaryWindowFor(asset);
    const before = primaryDisparity(previous, window);
    const after = primaryDisparity(asset, window);
    if (finite(before) && finite(after)) {
      [thresholds.caution, thresholds.hot].forEach((boundary) => {
        if (before < boundary && after >= boundary) changes.push({ kind: "distance" + boundary + "_up", label: window + "일 평균 대비 +" + (boundary - 100) + "% 진입" });
        else if (before >= boundary && after < boundary) changes.push({ kind: "distance" + boundary + "_down", label: window + "일 평균 대비 +" + (boundary - 100) + "% 아래로 감소" });
      });
    }
    return changes;
  }
  function relativeReturn(model, history, today, globalOutdated, assetsByCode) {
    if (!model.quality.valid || model.return20 === null || !model.benchmarkCode) return null;
    const benchmarkRows = seriesFor(history, model.benchmarkCode);
    const benchmarkAsset = assetsByCode.get(model.benchmarkCode);
    if (benchmarkAsset && !qualityFor(benchmarkAsset, benchmarkRows, today, globalOutdated).valid) return null;
    const start = benchmarkRows.find((row) => row.date === model.returnStartDate);
    const end = benchmarkRows.find((row) => row.date === model.returnEndDate);
    if (!start || !end || start.error || end.error || start.is_stale || end.is_stale || start.is_suspicious || end.is_suspicious) return null;
    const benchmarkReturn = pct(start.close, end.close);
    return benchmarkReturn === null ? null : model.return20 - benchmarkReturn;
  }
  function buildDashboard(latest, history, now) {
    now = now instanceof Date && Number.isFinite(now.getTime()) ? now : new Date();
    const today = seoulDate(now);
    const assets = latest && Array.isArray(latest.assets) ? latest.assets : [];
    const assetsByCode = new Map(assets.map((asset) => [asset.code, asset]));
    const updatedAt = latest && latest.updated_at || null;
    const updateMs = updatedAt ? Date.parse(updatedAt) : NaN;
    const updatedDate = Number.isFinite(updateMs) ? seoulDate(new Date(updateMs)) : null;
    const updatedAge = ageInDays(updatedDate, today);
    const outdated = updatedAge === null || updatedAge >= thresholds.staleCalendarDays || updatedAge < 0;
    const models = assets.filter((asset) => asset.disparity_meaningful !== false).map((asset) => {
      const rows = seriesFor(history, asset.code);
      const quality = qualityFor(asset, rows, today, outdated);
      const start = rows.length > 20 ? rows[rows.length - 21] : null;
      const end = rows[rows.length - 1];
      const primaryWindow = primaryWindowFor(asset);
      const primaryValue = quality.valid ? primaryDisparity(asset, primaryWindow) : null;
      return {
        asset, code: asset.code, quality,
        primaryWindow, primaryDistance: finite(primaryValue) ? primaryValue - 100 : null,
        return5: quality.valid ? periodReturn(rows, 5) : null,
        return20: quality.valid ? periodReturn(rows, 20) : null,
        return60: quality.valid ? periodReturn(rows, 60) : null,
        relative20: null, benchmarkCode: benchmarkFor(asset),
        returnStartDate: quality.valid && start ? start.date : null,
        returnEndDate: quality.valid && end ? end.date : null,
        distance25: quality.valid ? distance(asset, 25) : null,
        distance50: quality.valid ? distance(asset, 50) : null,
        distance120: quality.valid ? distance(asset, 120) : null,
        trend: classifyTrend(asset, rows, quality.valid),
        changes: changesFor(asset, rows, quality.valid), series: rows,
      };
    });
    models.forEach((model) => { model.relative20 = relativeReturn(model, history, today, outdated, assetsByCode); });
    const stocks = models.filter((model) => isStock(model.asset));
    const groups = Object.keys(groupLabels).map((id) => {
      const members = stocks.filter((model) => model.asset.ai_group === id);
      const valid = members.filter((model) => model.quality.valid);
      const with50 = valid.filter((model) => finite(model.distance50));
      const countAbove50 = with50.filter((model) => model.distance50 >= 0).length;
      return {
        id, label: groupLabels[id], total: members.length, valid: valid.length,
        return20: median(valid.map((model) => model.return20)),
        relative20: median(valid.map((model) => model.relative20)),
        return20Count: valid.filter((model) => finite(model.return20)).length,
        relative20Count: valid.filter((model) => finite(model.relative20)).length,
        above50: with50.length ? countAbove50 / with50.length * 100 : null,
        countAbove50, countWith50: with50.length,
        hotCount: valid.filter((model) => finite(model.primaryDistance) && model.primaryDistance >= thresholds.hot - 100).length,
        models: members,
      };
    });
    const dates = stocks.map((model) => model.asset.date).filter((value) => dateTime(value) !== null).sort();
    const freshness = {
      updatedAt, outdated, totalStocks: stocks.length,
      validStocks: stocks.filter((model) => model.quality.valid).length,
      excludedStocks: stocks.filter((model) => !model.quality.valid).length,
      oldestDate: dates[0] || null, newestDate: dates[dates.length - 1] || null,
    };
    const observations = [];
    if (outdated || !freshness.validStocks) {
      observations.push({ title: "현재 시장 판단을 보류합니다", body: outdated ? "수집 시각이 7일 이상 지났거나 확인되지 않아 현재 요약과 분야 통계에서 제외했습니다. 최신 데이터 갱신을 확인하세요." : "유효한 종목 데이터가 없어 현재 요약을 만들 수 없습니다. 기준일과 데이터 품질을 확인하세요.", codes: [], kind: "quality" });
      observations.push({ title: "저장된 데이터 범위", body: freshness.oldestDate ? freshness.oldestDate + " ~ " + freshness.newestDate + " · " + freshness.totalStocks + "개 종목. 차트는 저장된 과거 이력을 확인하는 용도입니다." : "확인 가능한 종목 기준일이 없습니다.", codes: [], kind: "coverage" });
    } else {
      const strongest = groups.filter((group) => finite(group.relative20) && group.relative20Count >= 3).sort((a, b) => b.relative20 - a.relative20)[0];
      if (strongest) observations.push({ title: "20거래일 상대 성과 1위: " + strongest.label, body: "상장시장 지수 대비 중앙값 " + (strongest.relative20 >= 0 ? "+" : "") + strongest.relative20.toFixed(1) + "%p · 비교 가능 " + strongest.relative20Count + "/" + strongest.total + "개. 주가 성과이며 산업 수요를 직접 뜻하지 않습니다.", codes: strongest.models.filter((model) => finite(model.relative20)).map((model) => model.code), kind: "relative" });
      const changed = stocks.filter((model) => model.changes.length);
      if (changed.length) observations.push({ title: "새 거래일의 변화 " + changed.length + "개 종목", body: changed.slice(0, 3).map((model) => model.asset.name + " · " + model.changes[0].label).join(" / ") + ". 각 종목 최신 거래일과 바로 전 거래일을 비교했습니다.", codes: changed.map((model) => model.code), kind: "changes" });
      const high = stocks.filter((model) => model.quality.valid && finite(model.primaryDistance) && model.primaryDistance >= thresholds.caution - 100);
      const hot = high.filter((model) => model.primaryDistance >= thresholds.hot - 100);
      if (high.length) observations.push({ title: "높은 상승 이격 " + high.length + "개 종목", body: "각 종목 판정 평균선(주식 기본 25일)보다 20% 이상 높으며, 이 중 " + hot.length + "개는 30% 이상 높습니다. 추세의 방향과 가격의 이격을 함께 확인하세요.", codes: high.map((model) => model.code), kind: "distance" });
      if (observations.length < 3) observations.push({ title: "데이터 확인 범위", body: "전체 " + freshness.totalStocks + "개 중 " + freshness.validStocks + "개 사용 · " + freshness.excludedStocks + "개 제외. 기준일 " + (freshness.oldestDate || "—") + " ~ " + (freshness.newestDate || "—") + ".", codes: stocks.filter((model) => !model.quality.valid).map((model) => model.code), kind: "coverage" });
    }
    return { models, stocks, groups, freshness, observations: observations.slice(0, 3), groupLabels };
  }
  return { buildDashboard, groupLabels, explain, thresholds };
});
