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
      `<tr><td colspan="8" class="loading">데이터를 불러오지 못했습니다: ${escapeHtml(
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
  const assets = ((DATA.latest && DATA.latest.assets) || []).slice();
  if (assets.length === 0) {
    tbody.innerHTML =
      `<tr><td colspan="8" class="loading">표시할 데이터가 없습니다.</td></tr>`;
    return;
  }

  if (sortByDisparity) {
    assets.sort((a, b) => disparityForSort(b) - disparityForSort(a));
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
  if (a.error || a.disparity50 == null) return -Infinity;
  return a.disparity50;
}

function rowHtml(a) {
  // 데이터 오류 자산
  if (a.error) {
    return `<tr class="row-error" data-code="${escapeHtml(a.code)}">
      <td><div class="asset-name">${escapeHtml(a.name)}</div><div class="asset-source">${escapeHtml(
        sourceLabel(a)
      )}</div></td>
      <td colspan="6"><span class="warn-tag warn-error">데이터 오류</span> ${escapeHtml(
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
    )}</div></td>
    <td class="num">${fmtNum(a.close)}</td>
    <td class="num ${changeCls}">${changeTxt}</td>
    <td class="num">${fmtDisp(a.disparity20)}</td>
    <td class="num">${fmtDisp(a.disparity50)}</td>
    <td class="num">${fmtDisp(a.disparity120)}</td>
    <td><span class="zone-pill ${zoneMeta.cls}">${escapeHtml(
      zoneMeta.label
    )}</span></td>
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
  const values = entry.data.map((d) => d.disparity50);

  const refLine = (val, color) => ({
    label: `ref-${val}`,
    data: labels.map(() => val),
    borderColor: color,
    borderWidth: 1,
    borderDash: [5, 5],
    pointRadius: 0,
    fill: false,
    tension: 0,
  });

  const datasets = [
    {
      label: `${entry.name} 50일 이격도`,
      data: values,
      borderColor: "#4c8bf5",
      backgroundColor: "rgba(76,139,245,0.12)",
      borderWidth: 2,
      pointRadius: 0,
      fill: true,
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
        y: { ticks: { color: "#9aa7b4" }, grid: { color: "#222b36" } },
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
          callbacks: {
            // 기준선 항목은 툴팁에서 제외
            label: (ctx) =>
              String(ctx.dataset.label).startsWith("ref-")
                ? null
                : `${ctx.dataset.label}: ${Number(ctx.parsed.y).toFixed(2)}`,
          },
        },
      },
    },
  });
}

// ---- helpers ----
function sourceLabel(a) {
  // 장중 모드에서는 전 종목을 yfinance 지연시세로 받는다.
  if (DATA.latest && DATA.latest.run_type === "intraday") {
    return "Yahoo Finance · yfinance";
  }
  // 종가 모드: 국내 = pykrx(KRX), 해외 = yfinance(Yahoo)
  return a.market === "US" ? "Yahoo Finance · yfinance" : "KRX · pykrx";
}
function fmtNum(v) {
  if (v == null) return "-";
  return Number(v).toLocaleString("ko-KR", { maximumFractionDigits: 2 });
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
