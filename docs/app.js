"use strict";

// 구간 코드 → 표시 라벨 / CSS 클래스
const ZONE_META = {
  overheat: { label: "과열", cls: "zone-overheat" },
  caution: { label: "경계", cls: "zone-caution" },
  normal: { label: "정상", cls: "zone-normal" },
  cooldown: { label: "과열해소", cls: "zone-cooldown" },
};

const DATA = { latest: null, history: null };
let chart = null;
let sortByDisparity = false;
let selectedCode = null;
let lastLoadAt = 0;
let filterCountry = "ALL"; // ALL | KR | JP | TW | US
let filterType = "ALL"; // ALL | index | stock

// 탭이 떠 있는 동안 주기적으로 최신 커밋 데이터를 다시 받아온다.
const AUTO_REFRESH_MS = 5 * 60 * 1000;

document.addEventListener("DOMContentLoaded", init);

async function init() {
  document
    .getElementById("sort-by-disparity")
    .addEventListener("change", (e) => {
      sortByDisparity = e.target.checked;
      renderTable();
    });
  document.getElementById("asset-select").addEventListener("change", (e) => {
    selectedCode = e.target.value;
    renderChart();
    highlightSelectedRow();
  });
  setupRefresh();
  setupFilters();
  await loadData();
}

function setupFilters() {
  const wire = (groupId, attr, set) => {
    const group = document.getElementById(groupId);
    if (!group) return;
    group.addEventListener("click", (e) => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      set(btn.getAttribute(attr));
      Array.from(group.querySelectorAll(".chip")).forEach((c) =>
        c.classList.toggle("active", c === btn)
      );
      renderTable();
    });
  };
  wire("filter-country", "data-country", (v) => (filterCountry = v));
  wire("filter-type", "data-type", (v) => (filterType = v));
}

function matchesFilter(a) {
  if (filterCountry !== "ALL" && (a.country || a.market) !== filterCountry) {
    return false;
  }
  if (filterType !== "ALL") {
    const isStock = String(a.asset_type || "").endsWith("_stock");
    if (filterType === "stock" && !isStock) return false;
    if (filterType === "index" && isStock) return false;
  }
  return true;
}

function setupRefresh() {
  const btn = document.getElementById("refresh-btn");
  if (btn) btn.addEventListener("click", () => refreshData(true));
  // 주기적 자동 새로고침(탭이 보일 때만 동작해 불필요한 요청을 막는다).
  setInterval(() => {
    if (document.visibilityState === "visible") refreshData(false);
  }, AUTO_REFRESH_MS);
  // 다른 탭/앱에서 돌아오면 즉시 최신 상태로 맞춘다.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refreshData(false);
  });
}

async function refreshData(manual) {
  // 자동 새로고침은 최근 1분 내 받았으면 건너뛴다(수동 클릭은 항상 실행).
  if (!manual && Date.now() - lastLoadAt < 60 * 1000) return;
  const btn = document.getElementById("refresh-btn");
  if (btn) {
    if (btn.dataset.loading === "1") return; // 진행 중 중복 클릭 방지
    btn.dataset.loading = "1";
    btn.classList.add("loading");
    btn.disabled = true;
  }
  try {
    await loadData();
  } finally {
    if (btn) {
      btn.dataset.loading = "0";
      btn.classList.remove("loading");
      btn.disabled = false;
    }
  }
}

async function loadData() {
  lastLoadAt = Date.now();
  try {
    const [latest, history] = await Promise.all([
      fetchJson("data/latest.json"),
      fetchJson("data/history.json"),
    ]);
    DATA.latest = latest;
    DATA.history = history || {};
    renderHeader();
    renderTable();
    populateAssetSelect();
    renderChart();
  } catch (err) {
    document.getElementById("latest-tbody").innerHTML =
      `<tr><td colspan="9" class="loading">데이터를 불러오지 못했습니다: ${escapeHtml(
        String(err)
      )}</td></tr>`;
  }
}

function fetchJson(path) {
  // 캐시 무력화를 위해 타임스탬프 쿼리 추가
  return fetch(`${path}?t=${Date.now()}`).then((r) => {
    if (!r.ok) throw new Error(`${path} (${r.status})`);
    return r.json();
  });
}

function renderHeader() {
  const el = document.getElementById("updated-at");
  const updated = DATA.latest && DATA.latest.updated_at;
  el.textContent = updated
    ? `업데이트: ${formatDateTime(updated)}${relAge(updated)}`
    : "업데이트 시각 없음 (아직 데이터가 생성되지 않았습니다)";
  const rt = document.getElementById("run-type");
  const runType = DATA.latest && DATA.latest.run_type;
  rt.textContent =
    runType === "intraday"
      ? "장중(현재가) 기준"
      : runType === "close"
      ? "종가 기준"
      : runType || "";
}

function renderTable() {
  const tbody = document.getElementById("latest-tbody");
  const all = ((DATA.latest && DATA.latest.assets) || []).map((a, idx) => ({
    ...a,
    _order: idx,
  }));
  if (all.length === 0) {
    tbody.innerHTML =
      `<tr><td colspan="9" class="loading">표시할 데이터가 없습니다.</td></tr>`;
    return;
  }
  const assets = all.filter(matchesFilter);
  if (assets.length === 0) {
    tbody.innerHTML =
      `<tr><td colspan="9" class="loading">해당 조건의 자산이 없습니다.</td></tr>`;
    return;
  }

  if (sortByDisparity) {
    assets.sort(groupedAssetCompare(true));
  } else {
    assets.sort(groupedAssetCompare(false));
  }

  tbody.innerHTML = assets.map(rowHtml).join("");

  Array.from(tbody.querySelectorAll("tr[data-code]")).forEach((tr) => {
    tr.addEventListener("click", () => {
      const code = tr.getAttribute("data-code");
      if (DATA.history && DATA.history[code]) {
        selectedCode = code;
        document.getElementById("asset-select").value = code;
        renderChart();
        highlightSelectedRow();
      }
    });
  });
  highlightSelectedRow();
}

function disparityForSort(a) {
  if (a.error || a.primary_disparity == null) return -Infinity;
  return a.primary_disparity;
}

function groupedAssetCompare(sortByMetric) {
  return (a, b) => {
    const countryDiff = countryRank(a) - countryRank(b);
    if (countryDiff !== 0) return countryDiff;
    const typeDiff = assetTypeRank(a) - assetTypeRank(b);
    if (typeDiff !== 0) return typeDiff;
    if (sortByMetric) {
      const metricDiff = disparityForSort(b) - disparityForSort(a);
      if (metricDiff !== 0) return metricDiff;
    }
    return (a._order || 0) - (b._order || 0);
  };
}

function countryRank(a) {
  const order = { KR: 0, JP: 1, TW: 2, US: 3 };
  const country = a.country || a.market || "";
  return Object.prototype.hasOwnProperty.call(order, country) ? order[country] : 99;
}

function assetTypeRank(a) {
  const t = String(a.asset_type || "");
  if (t.endsWith("_index")) return 0;
  if (t === "semiconductor_index") return 1;
  if (t.endsWith("_stock")) return 2;
  return 9;
}

function rowHtml(a) {
  // 데이터 오류 자산
  if (a.error) {
    return `<tr class="row-error" data-code="${escapeHtml(a.code)}">
      <td class="cell-name"><div class="asset-name">${escapeHtml(a.name)}</div><div class="asset-source">${escapeHtml(
        sourceLabel(a)
      )}</div>${assetNotesHtml(a)}</td>
      <td colspan="7" data-label="오류"><span class="warn-tag warn-error">데이터 오류</span> ${escapeHtml(
        a.error
      )}</td>
      <td class="cell-empty"></td>
    </tr>`;
  }

  const zoneMeta = ZONE_META[a.zone] || { label: a.zone || "-", cls: "" };
  const change = a.change_pct;
  const changeCls = change == null ? "" : change >= 0 ? "pos" : "neg";
  const changeTxt =
    change == null ? "-" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`;

  const warns = [];
  if (a.is_stale) warns.push(`<span class="warn-tag warn-stale">데이터 오래됨</span>`);
  if (a.is_suspicious)
    warns.push(`<span class="warn-tag warn-suspicious">값 확인 필요</span>`);

  return `<tr data-code="${escapeHtml(a.code)}" title="${escapeHtml(
    a.warning || ""
  )}">
    <td class="cell-name"><div class="asset-name">${escapeHtml(a.name)}</div><div class="asset-source">${escapeHtml(
      sourceLabel(a)
    )}</div>${assetNotesHtml(a)}</td>
    <td class="num" data-label="현재가">${fmtNum(a.close)}${extendedHtml(a)}</td>
    <td class="num ${changeCls}" data-label="등락률">${changeTxt}</td>
    <td class="num cell-secondary" data-label="20일">${fmtDisp(a.disparity20)}</td>
    <td class="num ${primaryMetricClass(a, 25)}" data-label="25일">${fmtDisp(a.disparity25)}</td>
    <td class="num ${primaryMetricClass(a, 50)}" data-label="50일">${fmtDisp(a.disparity50)}</td>
    <td class="num cell-secondary" data-label="120일">${fmtDisp(a.disparity120)}</td>
    <td data-label="구간"><span class="zone-pill ${zoneMeta.cls}">${escapeHtml(
      zoneMeta.label
    )}</span><div class="basis-note">${basisLabel(a)}</div></td>
    <td class="cell-warn" data-label="경고">${warns.join(" ")}</td>
  </tr>`;
}

function extendedHtml(a) {
  // 프리장/애프터마켓 시세(미국 상장 종목, 해당 세션일 때만). 이격도와 무관한 표시용.
  if (!a.extended_session || a.extended_price == null) return "";
  const label = a.extended_session === "pre" ? "프리" : "애프터";
  const cls = a.extended_session === "pre" ? "ext-pre" : "ext-post";
  const chg = a.extended_change_pct;
  const chgTxt =
    chg == null
      ? ""
      : ` <span class="${chg >= 0 ? "pos" : "neg"}">(${chg >= 0 ? "+" : ""}${chg.toFixed(
          2
        )}%)</span>`;
  return `<div class="ext-quote ${cls}">${label} ${fmtNum(
    a.extended_price
  )}${chgTxt}</div>`;
}

function highlightSelectedRow() {
  const tbody = document.getElementById("latest-tbody");
  Array.from(tbody.querySelectorAll("tr")).forEach((tr) => {
    tr.classList.toggle(
      "selected",
      tr.getAttribute("data-code") === selectedCode
    );
  });
}

function populateAssetSelect() {
  const sel = document.getElementById("asset-select");
  const hist = DATA.history || {};
  const codes = Object.keys(hist);
  if (codes.length === 0) {
    sel.innerHTML = `<option>히스토리 없음</option>`;
    selectedCode = null;
    return;
  }
  const latestOrder = new Map(
    ((DATA.latest && DATA.latest.assets) || []).map((a, idx) => [a.code, idx])
  );
  codes.sort((a, b) =>
    groupedAssetCompare(false)(
      { ...hist[a], _order: latestOrder.get(a) ?? 9999 },
      { ...hist[b], _order: latestOrder.get(b) ?? 9999 }
    )
  );
  sel.innerHTML = codes
    .map(
      (c) =>
        `<option value="${escapeHtml(c)}">${escapeHtml(hist[c].name)}</option>`
    )
    .join("");
  // 기본 선택: SK하이닉스(000660) 있으면 그것, 없으면 첫 번째
  if (!selectedCode || !hist[selectedCode]) {
    selectedCode = hist["000660"] ? "000660" : codes[0];
  }
  sel.value = selectedCode;
}

function renderChart() {
  const canvas = document.getElementById("disparity-chart");
  const hist = DATA.history || {};
  const entry = selectedCode ? hist[selectedCode] : null;

  if (!entry || !entry.data || entry.data.length === 0) {
    if (chart) {
      chart.destroy();
      chart = null;
    }
    return;
  }

  const labels = entry.data.map((d) => d.date);
  const primaryWindow = entry.primary_window || 50;
  const values = entry.data.map((d) =>
    d.primary_disparity == null ? d[`disparity${primaryWindow}`] : d.primary_disparity
  );
  const closes = entry.data.map((d) => d.close);

  const refLine = (val, color) => ({
    label: `ref-${val}`,
    data: labels.map(() => val),
    yAxisID: "disparity",
    borderColor: color,
    borderWidth: 1,
    borderDash: [5, 5],
    pointRadius: 0,
    fill: false,
    tension: 0,
  });

  const datasets = [
    {
      label: `${entry.name} ${primaryWindow}일 판정 이격도`,
      data: values,
      yAxisID: "disparity",
      borderColor: "#4c8bf5",
      backgroundColor: "rgba(76,139,245,0.12)",
      borderWidth: 2,
      pointRadius: 0,
      fill: true,
      tension: 0.15,
    },
    {
      label: `${entry.name} 가격`,
      data: closes,
      yAxisID: "price",
      borderColor: "#d9a441",
      backgroundColor: "rgba(217,164,65,0.08)",
      borderWidth: 1.5,
      pointRadius: 0,
      fill: false,
      tension: 0.15,
    },
    refLine(130, "#ff7b8a"),
    refLine(120, "#ffc15e"),
    refLine(105, "#6fb6e8"),
  ];

  if (chart) chart.destroy();
  chart = new Chart(canvas.getContext("2d"), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          ticks: { color: "#9aa7b4", maxTicksLimit: 8, autoSkip: true },
          grid: { color: "#222b36" },
        },
        disparity: {
          type: "linear",
          position: "left",
          ticks: {
            color: "#9aa7b4",
            callback: (value) => `${value}%`,
          },
          grid: { color: "#222b36" },
          title: { display: true, text: "이격도", color: "#9aa7b4" },
        },
        price: {
          type: "linear",
          position: "right",
          ticks: {
            color: "#b8a06a",
            callback: (value) => fmtCompactNum(value),
          },
          grid: { drawOnChartArea: false },
          title: { display: true, text: "가격", color: "#b8a06a" },
        },
      },
      plugins: {
        legend: {
          labels: {
            color: "#9aa7b4",
            // 기준선(ref-*) 범례는 숨긴다
            filter: (item) => !String(item.text).startsWith("ref-"),
          },
        },
        tooltip: {
          filter: (item) => !String(item.dataset.label).startsWith("ref-"),
          callbacks: {
            label: (ctx) => {
              const row = entry.data[ctx.dataIndex] || {};
              if (ctx.dataset.yAxisID === "price") {
                return `${ctx.dataset.label}: ${fmtNum(row.close)}`;
              }
              return [
                `${ctx.dataset.label}: ${fmtDisp(
                  row.primary_disparity == null
                    ? row[`disparity${primaryWindow}`]
                    : row.primary_disparity
                )}%`,
                `가격: ${fmtNum(row.close)}`,
                `25일선: ${fmtNum(row.ma25)}`,
                `50일선: ${fmtNum(row.ma50)}`,
              ];
            },
          },
        },
      },
    },
  });
}

// ---- helpers ----
function sourceLabel(a) {
  // 장중 모드: 국내 개별종목은 KRX 히스토리에 Yahoo 최신가를 보강하고, 나머지는 yfinance 조회.
  if (DATA.latest && DATA.latest.run_type === "intraday") {
    if (a.source === "pykrx_stock+yfinance") return "KRX · pykrx + Yahoo Finance";
    return "Yahoo Finance · yfinance";
  }
  if (a.source === "yfinance") return "Yahoo Finance · yfinance";
  if (a.source === "pykrx_index" || a.source === "pykrx_stock") return "KRX · pykrx";
  if (a.source === "pykrx_stock+yfinance") return "KRX · pykrx + Yahoo Finance";
  return a.market === "US" || a.market === "JP"
    ? "Yahoo Finance · yfinance"
    : "KRX · pykrx";
}
function assetNotesHtml(a) {
  const notes = [
    a.ticker || a.code,
    countryLabel(a.country || a.market),
    a.sector,
    isIndividualStock(a) ? "판정: 25일" : "판정: 50일",
  ].filter(Boolean);
  if (a.note) notes.push(a.note);
  if (notes.length === 0) return "";
  return `<div class="asset-note">${notes.map(escapeHtml).join(" · ")}</div>`;
}
function countryLabel(country) {
  return { KR: "한국", JP: "일본", TW: "대만", US: "미국" }[country] || country;
}
function isIndividualStock(a) {
  return String(a.asset_type || "").endsWith("_stock");
}
function primaryMetricClass(a, window) {
  return Number(a.primary_window || 50) === window ? "metric-primary" : "";
}
function basisLabel(a) {
  const window = a.primary_window || 50;
  return `${window}일 기준`;
}
function fmtNum(v) {
  if (v == null) return "-";
  return Number(v).toLocaleString("ko-KR", { maximumFractionDigits: 2 });
}
function fmtCompactNum(v) {
  if (v == null) return "-";
  return Number(v).toLocaleString("ko-KR", {
    notation: "compact",
    maximumFractionDigits: 1,
  });
}
function fmtDisp(v) {
  if (v == null) return "-";
  return Number(v).toFixed(2);
}
function relAge(iso) {
  // updated_at(데이터 생성 시각) 기준 경과 시간을 보조 표기 → 데이터가 얼마나 오래됐는지 즉시 확인.
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "";
  const mins = Math.round((Date.now() - t) / 60000);
  if (mins < 1) return " · 방금";
  if (mins < 60) return ` · ${mins}분 전`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return ` · ${hrs}시간 ${mins % 60}분 전`;
  return ` · ${Math.floor(hrs / 24)}일 전`;
}
function formatDateTime(iso) {
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString("ko-KR", { hour12: false });
  } catch (e) {
    return iso;
  }
}
function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
