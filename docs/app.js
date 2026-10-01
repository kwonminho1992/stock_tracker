"use strict";
const RESEARCH_BY_GROUP = {
  "01_COMPUTE_ASIC": {name:"NVIDIA 실적 자료",url:"https://investor.nvidia.com/financial-info/financial-reports/default.aspx",check:"데이터센터 매출, 가속기 수요와 출하, 매출총이익률"},
  "02_EDA_IP": {name:"Synopsys 기업 IR",url:"https://investor.synopsys.com/overview/default.aspx",check:"EDA·IP 매출, 계약잔액과 영업이익률"},
  "03_MEMORY_STORAGE": {name:"Micron 분기 실적",url:"https://investors.micron.com/financials/quarterly-results/default.aspx",check:"HBM 수요와 공급능력, 메모리 CAPEX, 가격·마진"},
  "04_FOUNDRY_MANUFACTURING": {name:"TSMC 2026 Q2 실적",url:"https://investor.tsmc.com/english/quarterly-results/2026/q2",check:"선단공정 수요, CoWoS 생산능력, CAPEX와 매출총이익률"},
  "05_EQUIPMENT_TEST": {name:"ASML 분기 실적",url:"https://investor.asml.com/quarterly-results",check:"순수주, 출하능력과 고객 설비투자 계획"},
  "06_MATERIALS_WAFER": {name:"SUMCO 실적 설명자료",url:"https://www.sumcosi.com/english/ir/library/presentations.html",check:"웨이퍼 출하, 가동률과 재고, 증설 계획"},
  "07_PACKAGING_SUBSTRATE_PCB": {name:"Amkor 분기 실적",url:"https://ir.amkor.com/financial-information/quarterly-results",check:"첨단 패키징 수요, 증설과 CAPEX, 영업이익률"},
  "08_MLCC_PASSIVE_COMPONENT": {name:"Murata 실적 자료",url:"https://corporate.murata.com/en-global/ir/library/results",check:"고부가 MLCC 수요, 가동률과 매출 구성, 마진"},
  "09_NETWORK_OPTICAL": {name:"Arista 재무 자료",url:"https://investors.arista.com/Financial-Information/default.aspx",check:"클라우드·AI 네트워크 매출, 고객 집중도와 마진"},
  "10_POWER_COOLING_GRID": {name:"Vertiv 분기 실적",url:"https://investors.vertiv.com/financials/quarterly-results/default.aspx",check:"유기적 수주, 수주잔고, 전력·냉각 생산능력과 마진"},
  "11_AI_SERVER_ODM": {name:"Dell 기업 IR",url:"https://investors.delltechnologies.com/",check:"AI 서버 수주·출하·수주잔고와 인프라 부문 마진"},
  "12_CLOUD_CAPEX": {name:"Microsoft FY2026 Q4 실적",url:"https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q4",check:"현금·리스 CAPEX, 클라우드 성장, 가동용량과 잉여현금흐름"}
};
const EXPOSURE = {CORE:"핵심",DEMAND:"수요",SECONDARY:"2차",SUPPORT:"보조",HIGH_RISK:"고위험",BENCHMARK:"벤치마크"};
const COUNTRY = {KR:"한국",US:"미국",JP:"일본",TW:"대만",EU:"유럽",HK:"홍콩"};
const BENCHMARK_NAMES = {"^KS11":"코스피","^GSPC":"S&P500","^N225":"닛케이225","^TWII":"대만 가권"};
const state = {latest:null,history:{},dashboard:null,selected:null,view:"ALL",group:"ALL",country:"ALL",exposure:"ALL",search:"",sort:"relative20",period:"3M",watch:new Set(),briefCodes:null,chart:null,lastLoad:0};
const $ = (id) => document.getElementById(id);
const finite = (n) => typeof n === "number" && Number.isFinite(n);
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function signed(n,unit="%",digits=1){return finite(n)?`${n>0?"+":""}${n.toFixed(digits)}${unit}`:"—";}
function number(n,digits=2){return finite(n)?n.toLocaleString("ko-KR",{maximumFractionDigits:digits}):"—";}
function tone(n){return !finite(n)?"muted":n>0?"positive":n<0?"negative":"";}
function dateTime(s){if(typeof s!=="string"||!s.trim())return "확인 불가";const d=new Date(s);return Number.isFinite(d.getTime())?d.toLocaleString("ko-KR",{timeZone:"Asia/Seoul",year:"numeric",month:"numeric",day:"numeric",hour:"2-digit",minute:"2-digit",hour12:false}):"확인 불가";}
function link(url,label,cls=""){try{const u=new URL(url);if(!["https:","http:"].includes(u.protocol))return "";return `<a class="${cls}" href="${esc(u.href)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;}catch{return "";}}
function storageRead(){try{const parsed=JSON.parse(localStorage.getItem("stock-tracker-watch")||"[]");state.watch=new Set(Array.isArray(parsed)?parsed.filter(c=>typeof c==="string"):[]);}catch{state.watch=new Set();}}
function toggleWatch(code){if(state.watch.has(code))state.watch.delete(code);else state.watch.add(code);try{localStorage.setItem("stock-tracker-watch",JSON.stringify([...state.watch]));}catch{}renderTable();renderDetail();}
function findModel(code){return state.dashboard.models.find(m=>m.code===code);}
function primaryDistance(m){return finite(m.primaryDistance)?m.primaryDistance:null;}
function isIndex(m){return /_index$/.test(m.asset.asset_type||"");}
function watchButton(m){const on=state.watch.has(m.code);return `<button class="watch-button" type="button" data-watch="${esc(m.code)}" aria-label="${esc(m.asset.name)} ${on?"관심종목 해제":"관심종목 추가"}" aria-pressed="${on}">${on?"★":"☆"}</button>`;}
function dayAge(s){if(!/^\d{4}-\d{2}-\d{2}$/.test(s||""))return null;const today=new Date(Date.now()+9*3600000).toISOString().slice(0,10);const d=Date.parse(s+"T00:00:00Z");return Number.isFinite(d)?(Date.parse(today+"T00:00:00Z")-d)/86400000:null;}
function macroQuality(a){
  if(a.link_only||!finite(a.close))return {valid:false,label:"수치 미수집",reason:a.warning||"공식 원문에서 수치를 확인하세요."};
  if(a.error||a.is_suspicious)return {valid:false,label:"값 확인 필요",reason:a.warning||a.error||"검증 경고가 있는 값은 현재 환경 요약에서 제외합니다."};
  const age=dayAge(a.date);const annual=["FPCPITOTLZGJPN","TWNPCPIPCPPPT"].includes(a.code);
  const frequency=a.macro_frequency||(a.source==="fred"?(annual?"annual":"monthly"):"daily");
  const thresholds={daily:14,weekly:35,biweekly:60,monthly:120,quarterly:240,semiannual:365,annual:550};
  const unknown=a.macro_date_type==="source_update"||a.macro_freshness==="unknown"||age==null||age<0;
  const stale=a.is_stale===true||a.macro_discontinued===true||state.dashboard.freshness.outdated||(age!=null&&age>(thresholds[frequency]||120));
  return {valid:!unknown&&!stale,label:unknown?"관측기간 확인 필요":stale?"오래된 관측치":"관측일 확인",reason:a.warning||(unknown?"출처 갱신일과 실제 관측기간을 구분해 확인하세요.":stale?"현재 환경 해석에 사용하지 않습니다.":""),frequency};
}
function macroName(a){return a.code==="INTDSRKRM193N"?"한국 할인율(IMF)":a.code==="TWNPCPIPCPPPT"?"대만 CPI 전망(연간)":a.name;}
function macroDate(a){const q=macroQuality(a);const labels={daily:"일간",weekly:"주간",biweekly:"격주",monthly:"월간",quarterly:"분기",semiannual:"반기",annual:"연간"};return a.date?`${a.macro_date_type==="source_update"?"출처 갱신":"관측"} ${a.date}${labels[q.frequency]?" · "+labels[q.frequency]:""}`:"관측기간 확인 필요";}
async function loadData(manual=false){
  const button=$("refresh-btn");if(button.disabled)return;button.disabled=true;button.textContent="확인 중…";
  try{
    const token=Date.now();const responses=await Promise.all([fetch(`data/latest.json?t=${token}`,{cache:"no-store"}),fetch(`data/history.json?t=${token}`,{cache:"no-store"})]);
    if(responses.some(r=>!r.ok))throw new Error("파일 응답 오류");
    const [latest,history]=await Promise.all(responses.map(r=>r.json()));
    if(!Array.isArray(latest.assets)||!history||typeof history!=="object"||Array.isArray(history))throw new Error("데이터 형식 오류");
    state.latest=latest;state.history=history;state.dashboard=MarketInsights.buildDashboard(latest,history);state.lastLoad=Date.now();
    if(!state.selected||!findModel(state.selected))state.selected=(state.dashboard.stocks.find(m=>state.watch.has(m.code))||state.dashboard.stocks.find(m=>m.code==="000660")||state.dashboard.stocks.find(m=>m.asset.exposure_type==="CORE")||state.dashboard.models[0])?.code;
    $("load-error").hidden=true;renderAll();
  }catch(error){
    const alert=$("load-error");alert.hidden=false;alert.textContent=state.dashboard?"최신 파일을 확인하지 못했습니다. 아래는 이전에 불러온 데이터입니다. 수집 시각과 기준일을 확인하세요.":"데이터를 불러오지 못했습니다. 잠시 후 ‘데이터 확인’을 눌러 다시 시도하세요.";
    if(!state.dashboard)$("asset-tbody").innerHTML='<tr><td colspan="6" class="empty-state">데이터를 기다리고 있습니다.</td></tr>';
  }finally{button.disabled=false;button.innerHTML='<span aria-hidden="true">↻</span> 데이터 확인';}
}
function renderAll(){renderHeader();renderOverview();renderGroups();renderTable();renderDetail();renderResearch();renderMacros();}
function renderHeader(){
  const f=state.dashboard.freshness;$("updated-at").textContent=`수집 ${dateTime(f.updatedAt)} KST`;
  $("run-type").textContent=state.latest.run_type==="intraday"?"장중 · 지연시세 포함":"종가 기준";
  $("checked-at").textContent=`파일 확인 ${new Date(state.lastLoad).toLocaleTimeString("ko-KR",{timeZone:"Asia/Seoul",hour:"2-digit",minute:"2-digit",hour12:false})} · 새 시세 수집과 별도`;
  const invalid=state.dashboard.stocks.filter(m=>!m.quality.valid);const status=$("data-status");status.classList.toggle("warning",f.outdated||!f.validStocks||!!invalid.length);
  const title=f.outdated?"현재 판단 보류 · 수집 데이터의 최신성을 확인하세요":!f.validStocks?"현재 판단 보류 · 유효한 종목 데이터 없음":`유효 종목 ${f.validStocks} / ${f.totalStocks}개`;
  status.innerHTML=`<div><strong>${esc(title)}</strong><span> · 가격 기준일 ${esc(f.oldestDate||"—")} ~ ${esc(f.newestDate||"—")}</span></div>${invalid.length?`<details><summary>집계 제외 ${invalid.length}개 · 사유 보기</summary><ul>${invalid.map(m=>`<li>${esc(m.asset.name)} · ${esc(m.quality.reasons.join(" / "))}</li>`).join("")}</ul></details>`:'<span>오류·오래된 값·이력 불일치는 집계에서 제외</span>'}`;
}
function renderOverview(){
  const valid=state.dashboard.stocks.filter(m=>m.quality.valid);const with50=valid.filter(m=>finite(m.distance50));const above50=with50.filter(m=>m.distance50>=0).length;const hot=valid.filter(m=>primaryDistance(m)>=20);const changed=valid.filter(m=>m.changes.length);
  const stats=[{label:"50일선 위 종목 비중",value:with50.length?Math.round(above50/with50.length*100)+"%":"—",context:`${above50} / ${with50.length}개 · 추세의 확산`},{label:"높은 상승 이격",value:valid.length?hot.length+"개":"—",context:"판정 평균선보다 20% 이상 높음"},{label:"최근 거래일의 새 변화",value:valid.length?changed.length+"개":"—",context:"평균선 돌파·이탈 / 이격 변화"}];
  $("overview-stats").innerHTML=stats.map(s=>`<div class="stat"><span class="stat-label">${s.label}</span><strong class="metric-value">${s.value}</strong><span class="stat-context">${s.context}</span></div>`).join("");
  const kinds={relative:"분야 비교",changes:"추세 변화",distance:"가격 이격",quality:"데이터 품질",coverage:"확인 범위"};
  $("briefing").innerHTML=state.dashboard.observations.map((o,i)=>`<article class="brief-card"><span class="eyebrow">${kinds[o.kind]||"관찰"}</span><h3>${esc(o.title)}</h3><p>${esc(o.body)}</p>${o.codes.length?`<button type="button" data-brief="${i}">관련 종목 ${o.codes.length}개 보기 →</button>`:""}</article>`).join("");
  const indexCodes=["^KS11","^GSPC","^NDX","^SOX"];
  const indexItems=indexCodes.map(code=>{const m=findModel(code);if(!m)return "";return `<div class="market-item"><span class="market-title">${esc(m.asset.name)}</span><strong>${m.quality.valid?number(m.asset.close,0):"—"} <span class="${tone(m.quality.valid?m.asset.change_pct:null)}">${m.quality.valid?signed(m.asset.change_pct):""}</span></strong><small>${esc(m.asset.date||"기준일 없음")}</small></div>`;});
  const macroItems=["^TNX","KRW=X","^VIX"].map(code=>{const a=state.latest.assets.find(x=>x.code===code);if(!a)return "";const q=macroQuality(a);return `<div class="market-item"><span class="market-title">${esc(macroName(a))}</span><strong>${q.valid?number(a.close)+(a.currency==="%"?"%":""):"—"}</strong><small>${q.valid?esc(a.date):esc(q.label)}</small></div>`;});
  $("market-strip").innerHTML=[...indexItems,...macroItems].join("");
}
function renderGroups(){
  $("chain-grid").innerHTML=state.dashboard.groups.map(g=>`<button type="button" class="chain-tile ${state.group===g.id?"active":""}" data-group="${g.id}" aria-pressed="${state.group===g.id}"><span class="group-head"><span>${esc(g.label)}</span><small>${g.valid}/${g.total}개</small></span><span class="group-values"><strong class="group-value ${tone(g.return20)}">${signed(g.return20)}</strong><span class="group-relative">시장 대비 ${signed(g.relative20,"%p")} <small>(${g.relative20Count}개)</small></span></span><span class="group-footer"><span>50일선 위 ${g.countAbove50}/${g.countWith50}</span><span class="breadth-track" aria-hidden="true"><span style="width:${finite(g.above50)?g.above50:0}%"></span></span><span>${finite(g.above50)?Math.round(g.above50)+"%":"—"}</span></span></button>`).join("");
  const d=state.dashboard.stocks.filter(m=>finite(m.return20));const starts=d.map(m=>m.returnStartDate).filter(Boolean).sort();const ends=d.map(m=>m.returnEndDate).filter(Boolean).sort();
  $("chain-basis").textContent=`추적 종목의 현지 통화 수익률 중앙값 · 주가 기준 · 산업 병목이나 기업가치 판정과 별도. ${starts.length?`20거래일 기간: 시장별 ${starts[0]}~${starts[starts.length-1]} 대비 ${ends[0]}~${ends[ends.length-1]}.`:"유효한 20거래일 비교 자료 없음."} 각 타일의 종목 수는 유효/전체이며 수익률 이력이 부족한 종목은 해당 계산에서 제외됩니다.`;
}
function filteredModels(){
  return state.dashboard.models.filter(m=>{
    const a=m.asset;if(state.group==="ALL"&&state.view!=="WATCH"&&isIndex(m))return false;
    if(state.group!=="ALL"&&a.ai_group!==state.group)return false;
    if(state.country!=="ALL"&&(a.country||a.market)!==state.country)return false;
    if(state.exposure!=="ALL"&&a.exposure_type!==state.exposure)return false;
    if(state.search&&!`${a.name} ${a.code} ${a.ticker||""} ${a.display_ticker||""}`.toLowerCase().includes(state.search))return false;
    if(state.briefCodes&&!state.briefCodes.has(m.code))return false;
    if(state.view==="WATCH"&&!state.watch.has(m.code))return false;
    if(state.view==="CHANGES"&&!m.changes.length)return false;
    if(["up","pullback","weak"].includes(state.view)&&m.trend.key!==state.view)return false;
    if(state.view==="HOT"&&(!m.quality.valid||primaryDistance(m)<20))return false;
    return true;
  }).sort((a,b)=>{
    if(state.sort==="name")return a.asset.name.localeCompare(b.asset.name,"ko");
    const key=state.sort;const av=finite(a[key])?a[key]:-Infinity;const bv=finite(b[key])?b[key]:-Infinity;
    return bv===av?(a.asset.sort_order||0)-(b.asset.sort_order||0):bv-av;
  });
}
function renderTable(){
  $("watch-count").textContent=state.dashboard.models.filter(m=>state.watch.has(m.code)).length;
  document.querySelectorAll("#view-tabs button").forEach(b=>{const on=b.dataset.view===state.view;b.classList.toggle("active",on);b.setAttribute("aria-pressed",on);});
  const models=filteredModels();$("result-count").textContent=`${state.group==="ALL"?"전체 밸류체인":state.dashboard.groupLabels[state.group]||"시장지수"} · ${models.length}개${state.briefCodes?" · 요약에서 선택한 종목":""}`;
  if(!models.length){$("asset-tbody").innerHTML=`<tr><td colspan="6" class="empty-state">${state.view==="WATCH"?"아직 관심종목이 없습니다. 종목 옆 ☆를 눌러 추가하세요.":"현재 조건에 맞는 종목이 없습니다. 다른 목록을 선택하거나 필터를 초기화하세요."}</td></tr>`;return;}
  $("asset-tbody").innerHTML=models.map(m=>{
    const a=m.asset;const distance=primaryDistance(m);const warning=!m.quality.valid?`<span class="quality-label">${esc(m.quality.reasons[0]||"판정 보류")}</span>`:"";
    return `<tr class="${state.selected===m.code?"selected":""}"><td>${watchButton(m)}</td><td><button class="asset-button" type="button" data-select="${esc(m.code)}" aria-label="${esc(a.name)} 상세 보기">${esc(a.name)}<span class="asset-ticker">${esc(a.display_ticker||a.ticker||a.code)}${a.is_adr?" · ADR":""} · ${esc(COUNTRY[a.country||a.market]||a.country_label||"")} · ${esc(a.ai_subgroup||a.sector||"")} · ${esc(EXPOSURE[a.exposure_type]||"")}</span></button></td><td class="num ${tone(m.return20)}">${signed(m.return20)}<small class="${tone(m.relative20)}">${signed(m.relative20,"%p")}${finite(m.relative20)?" 시장 대비":""}</small></td><td><span class="trend-label trend-${m.trend.key}">${esc(m.trend.label)}</span></td><td class="num ${distance>=20?"negative":""}">${signed(distance)}${distance>=30?'<small class="negative">높은 이격 · 과열 주의</small>':distance>=20?'<small class="negative">높은 상승 이격</small>':""}</td><td>${m.changes.length?`<span class="change-label">${esc(m.changes[0].label)}</span>`:""}${warning}<small>${esc(a.date||"기준일 없음")}</small></td></tr>`;
  }).join("");
}
function selectModel(code){if(!findModel(code))return;state.selected=code;renderTable();renderDetail();if(window.innerWidth<=850)$("detail-panel").scrollIntoView({behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"start"});}
function renderDetail(){
  const m=state.selected?findModel(state.selected):null;
  if(!m){$("detail-content").innerHTML='<h2 id="detail-name">살펴볼 종목을 선택하세요</h2>';$("detail-research").innerHTML="";renderChart(null);return;}
  const a=m.asset;const dist=[25,50,120].map(w=>`${w}일<strong>${signed(m["distance"+w])}</strong>`).map(s=>`<span>${s}</span>`).join("");
  const session=finite(a.extended_price)?`<p class="extended-quote">${a.extended_session==="pre"?"프리장":"애프터마켓"} ${number(a.extended_price)} · ${signed(a.extended_change_pct)} · 평균선 계산에는 미반영</p>`:"";
  $("detail-content").innerHTML=`<div class="detail-heading"><div><h2 id="detail-name">${esc(a.name)}</h2><small>${esc(a.display_ticker||a.ticker||a.code)}${a.is_adr?" · ADR":""} · ${esc(a.listing_market||"")} · ${esc(EXPOSURE[a.exposure_type]||"")}</small></div>${watchButton(m)}</div><p class="detail-role">${esc(a.product_group||a.sector||"")}</p><div class="detail-price">${number(a.close)} <span>${esc(a.currency||"")}</span><span class="detail-change ${tone(a.change_pct)}">${signed(a.change_pct)}</span></div><p class="detail-date">가격 기준 ${esc(a.date||"확인 불가")} · ${esc(a.price_source||a.source||"")}</p>${session}${!m.quality.valid?`<p class="detail-warning">${esc(m.quality.reasons.join(" / "))} · 아래 차트는 저장된 이력입니다.</p>`:""}<div class="detail-stats"><div><small>5거래일 성과</small><strong class="${tone(m.return5)}">${signed(m.return5)}</strong></div><div><small>20거래일 성과</small><strong class="${tone(m.return20)}">${signed(m.return20)}</strong></div><div><small>시장 대비 20일</small><strong class="${tone(m.relative20)}">${signed(m.relative20,"%p")}</strong></div></div><div class="detail-trend"><span class="trend-label trend-${m.trend.key}">${esc(m.trend.label)}</span></div><div class="detail-distances">${dist}</div>${m.returnStartDate?`<p class="method-note">${esc(m.returnStartDate)} → ${esc(m.returnEndDate)} · 현지 통화 기준${finite(m.relative20)?` · ${esc(BENCHMARK_NAMES[m.benchmarkCode]||m.benchmarkCode)} 대비`:" · 같은 기간 시장 비교 자료 없음"}</p>`:""}`;
  const research=RESEARCH_BY_GROUP[a.ai_group];
  $("detail-research").innerHTML=`<div class="detail-research"><h3>이 분야에서 다음에 확인할 것</h3><p>${esc(research?research.check:"시장 대비 추세와 데이터 기준일을 함께 확인하세요.")}</p>${research?link(research.url,research.name,"research-link"):""}<p>실적·산업·가치의 정량 판정은 원문 확인이 필요합니다.</p><div class="source-links">${link(a.detail_url,"시세 원문")}${a.is_adr&&a.local_ticker?`<span class="muted">본주 ${esc(a.local_ticker)}</span>`:""}</div></div>`;
  renderChart(m);
}
function renderChart(m){
  if(state.chart){state.chart.destroy();state.chart=null;}
  const fallback=$("chart-fallback");fallback.hidden=true;$("price-chart").hidden=false;
  if(!m||!m.series.length){fallback.hidden=false;fallback.textContent="표시할 가격 이력이 없습니다.";$("price-chart").hidden=true;return;}
  if(typeof Chart==="undefined"){fallback.hidden=false;$("price-chart").hidden=true;return;}
  const length=state.period==="1M"?22:state.period==="3M"?66:252;const full=m.series;
  const rolling120=full.map((r,i)=>{if(finite(r.ma120))return r.ma120;if(i<119)return null;const points=full.slice(i-119,i+1).map(x=>x.close);return points.every(x=>finite(x)&&x>0)?points.reduce((s,x)=>s+x,0)/120:null;});
  const rows=full.slice(-length);const offset=full.length-rows.length;const colors=getComputedStyle(document.documentElement);const color=k=>colors.getPropertyValue(k).trim();
  const dataset=(label,data,c)=>({label,data,borderColor:c,borderWidth:1.5,pointRadius:0,fill:false,tension:.1,spanGaps:false});
  state.chart=new Chart($("price-chart"),{type:"line",data:{labels:rows.map(r=>r.date),datasets:[dataset("가격",rows.map(r=>finite(r.close)?r.close:null),color("--accent")),dataset("50일선",rows.map(r=>finite(r.ma50)?r.ma50:null),color("--warn")),dataset("120일선",rolling120.slice(offset),color("--muted"))]},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:"index",intersect:false},scales:{x:{ticks:{color:color("--muted"),maxTicksLimit:4,font:{size:10}},grid:{display:false}},y:{ticks:{color:color("--muted"),maxTicksLimit:4,font:{size:10},callback:v=>number(v,0)},grid:{color:color("--border")}}},plugins:{legend:{labels:{color:color("--muted"),boxWidth:10,boxHeight:2,font:{size:10}}},tooltip:{callbacks:{label:ctx=>`${ctx.dataset.label}: ${number(ctx.parsed.y)}`}}}}});
  $("price-chart").setAttribute("aria-label",`${m.asset.name} ${state.period} 가격, 50일선과 120일선 추이`);
}
function renderResearch(){
  const cards=[{tag:"수요",title:"AI 투자 계획이 지속되는가",body:"현금·리스 설비투자를 구분하고, 클라우드 성장과 가동용량을 함께 확인합니다.",sources:[RESEARCH_BY_GROUP["12_CLOUD_CAPEX"]]}, {tag:"공급",title:"공급 제약은 어디에 남아 있는가",body:"HBM·첨단 패키징의 생산능력, 증설 시점과 고객 주문을 원문에서 확인합니다.",sources:[RESEARCH_BY_GROUP["03_MEMORY_STORAGE"],RESEARCH_BY_GROUP["04_FOUNDRY_MANUFACTURING"]]}, {tag:"실적",title:"수요가 이익으로 전환되는가",body:"주문과 매출 인식을 구분하고, 수주잔고·매출총이익률·현금흐름의 변화를 봅니다.",sources:[RESEARCH_BY_GROUP["01_COMPUTE_ASIC"],RESEARCH_BY_GROUP["10_POWER_COOLING_GRID"]]}, {tag:"가치·위험",title:"주가가 반영한 기대는 어느 정도인가",body:"이익·현금흐름과 가격을 비교하고, 고객 집중·투자 부담·위험 요인을 함께 확인합니다.",sources:[{name:"공시에서 확인할 사업·재무·위험",url:"https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/how-read"}]}];
  $("research-grid").innerHTML=cards.map(c=>`<article class="research-card"><span class="eyebrow">${c.tag}</span><h3>${c.title}</h3><p>${c.body}</p>${c.sources.map(s=>link(s.url,s.name)).join("")}<div class="research-state">공식 원문에서 확인 · 주가만으로 판정 보류</div></article>`).join("");
}
function renderMacros(){
  const macros=state.latest.assets.filter(a=>a.disparity_meaningful===false).sort((a,b)=>(a.sort_order||0)-(b.sort_order||0));const warning=macros.filter(a=>!macroQuality(a).valid).length;
  $("macro-summary").textContent=`${macros.length}개 · 관측기간·품질 확인 필요 ${warning}개`;
  $("macro-grid").innerHTML=macros.map(a=>{const q=macroQuality(a);return `<article class="macro-card"><h3>${esc(macroName(a))}</h3><div class="macro-number">${number(a.close)} <small>${esc(a.currency&&a.currency!=="-"?a.currency:"")}</small></div><p>${esc(macroDate(a))}</p>${!q.valid||a.macro_is_projection?`<p class="macro-warning">${esc(q.label)}${q.reason?" · "+esc(q.reason):""}</p>`:""}<p>${esc(a.product_group||"")}</p>${link(a.detail_url||a.url,"원문 확인")}</article>`;}).join("");
}
function resetFilters(){state.group="ALL";state.country="ALL";state.exposure="ALL";state.search="";state.view="ALL";state.briefCodes=null;["filter-group","filter-country","filter-exposure"].forEach(id=>$(id).value="ALL");$("search-input").value="";renderGroups();renderTable();}
function init(){
  storageRead();Object.entries(MarketInsights.groupLabels).forEach(([id,label])=>{const o=document.createElement("option");o.value=id;o.textContent=label;$("filter-group").append(o);});
  $("refresh-btn").addEventListener("click",()=>loadData(true));
  $("view-tabs").addEventListener("click",e=>{const b=e.target.closest("button[data-view]");if(!b)return;state.view=b.dataset.view;state.briefCodes=null;renderTable();});
  $("chain-grid").addEventListener("click",e=>{const b=e.target.closest("button[data-group]");if(!b)return;state.group=state.group===b.dataset.group?"ALL":b.dataset.group;state.view="ALL";state.briefCodes=null;$("filter-group").value=state.group;renderGroups();renderTable();$("explorer").scrollIntoView({behavior:window.matchMedia("(prefers-reduced-motion: reduce)").matches?"auto":"smooth",block:"start"});});
  $("briefing").addEventListener("click",e=>{const b=e.target.closest("button[data-brief]");if(!b)return;resetFilters();const o=state.dashboard.observations[Number(b.dataset.brief)];state.briefCodes=new Set(o.codes);renderTable();$("explorer").scrollIntoView({behavior:"smooth",block:"start"});});
  ["filter-group","filter-country","filter-exposure"].forEach(id=>$(id).addEventListener("change",e=>{state[id.replace("filter-","")]=e.target.value;state.briefCodes=null;renderGroups();renderTable();}));
  $("search-input").addEventListener("input",e=>{state.search=e.target.value.trim().toLowerCase();renderTable();});
  $("sort-select").addEventListener("change",e=>{state.sort=e.target.value;renderTable();});$("reset-filters").addEventListener("click",resetFilters);
  $("asset-tbody").addEventListener("click",e=>{const w=e.target.closest("[data-watch]");if(w){toggleWatch(w.dataset.watch);return;}const b=e.target.closest("[data-select]");if(b)selectModel(b.dataset.select);});
  $("detail-content").addEventListener("click",e=>{const b=e.target.closest("[data-watch]");if(b)toggleWatch(b.dataset.watch);});
  $("chart-periods").addEventListener("click",e=>{const b=e.target.closest("button[data-period]");if(!b)return;state.period=b.dataset.period;$("chart-periods").querySelectorAll("button").forEach(btn=>{const on=btn===b;btn.classList.toggle("active",on);btn.setAttribute("aria-pressed",on);});renderChart(findModel(state.selected));});
  setInterval(()=>{if(document.visibilityState==="visible"&&Date.now()-state.lastLoad>60000)loadData();},300000);
  document.addEventListener("visibilitychange",()=>{if(document.visibilityState==="visible"&&Date.now()-state.lastLoad>60000)loadData();});
  if("serviceWorker" in navigator)navigator.serviceWorker.register("sw.js").catch(()=>{});
  loadData();
}
document.addEventListener("DOMContentLoaded",init);
