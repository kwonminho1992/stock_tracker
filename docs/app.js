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
  await loadData();
}

async function loadData() {
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
    ? `업데이트: ${formatDateTime(updated)}`
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
  const assets = ((DATA.latest && DATA.latest.assets) || []).map((a, idx) => ({
    ...a,
    _order: idx,
  }));
  if (assets.length === 0) {
    tbody.innerHTML =
      `<tr><td colspan="9" class="loading">표시할 데이터가 없습니다.</td></tr>`;
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
      <td><div class="asset-name">${escapeHtml(a.name)}</div><div class="asset-source">${escapeHtml(
        sourceLabel(a)
      )}</div>${assetNotesHtml(a)}</td>
      <td colspan="7"><span class="warn-tag warn-error">데이터 오류</span> ${escapeHtml(
        a.error
      )}</td>
      <td></td>
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
    <td><div class="asset-name">${escapeHtml(a.name)}</div><div class="asset-source">${escapeHtml(
      sourceLabel(a)
    )}</div>${assetNotesHtml(a)}</td>
    <td class="num">${fmtNum(a.close)}</td>
    <td class="num ${changeCls}">${changeTxt}</td>
    <td class="num">${fmtDisp(a.disparity20)}</td>
    <td class="num ${primaryMetricClass(a, 25)}">${fmtDisp(a.disparity25)}</td>
    <td class="num ${primaryMetricClass(a, 50)}">${fmtDisp(a.disparity50)}</td>
    <td class="num">${fmtDisp(a.disparity120)}</td>
    <td><span class="zone-pill ${zoneMeta.cls}">${escapeHtml(
      zoneMeta.label
    )}</span><div class="basis-note">${basisLabel(a)}</div></td>
    <td>${warns.join(" ")}</td>
  </tr>`;
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
