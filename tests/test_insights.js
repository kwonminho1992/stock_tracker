"use strict";
const assert = require("node:assert/strict");
const { buildDashboard, thresholds, explain } = require("../docs/insights.js");
const now = new Date("2026-10-01T12:00:00+09:00");
const group = "01_COMPUTE_ASIC";
function rows(code, count = 61) {
  return Array.from({ length: count }, (_, i) => ({ date: new Date(Date.UTC(2026, 7, 1 + i)).toISOString().slice(0, 10), close: 100 + i, ma25: 95 + i, ma50: 90 + i, primary_disparity: 110 }));
}
function fixture() {
  const data = rows("TEST");
  const benchmark = data.map((row, i) => ({ ...row, close: 200 + i }));
  const last = data.at(-1);
  const asset = { name: "테스트", code: "TEST", market: "US", country: "TW", listing_market: "NASDAQ/NYSE", is_adr: true, asset_type: "us_stock", ai_group: group, ...last, ma120: 130 };
  const index = { name: "S&P 500", code: "^GSPC", market: "US", asset_type: "index", ...benchmark.at(-1), ma120: 200 };
  return { latest: { updated_at: "2026-10-01T10:00:00+09:00", assets: [asset, index] }, history: { TEST: { data }, "^GSPC": { data: benchmark } } };
}
function run(data, date = now) { return buildDashboard(data.latest, data.history, date); }
function stock(data, date = now) { return run(data, date).stocks[0]; }
function approximately(actual, expected) { assert.ok(Math.abs(actual - expected) < 1e-10, `${actual} != ${expected}`); }

{
  const data = fixture();
  const model = stock(data);
  assert.equal(model.quality.valid, true);
  approximately(model.return5, (160 / 155 - 1) * 100);
  approximately(model.return20, (160 / 140 - 1) * 100);
  approximately(model.return60, 60);
  approximately(model.relative20, ((160 / 140 - 1) - (260 / 240 - 1)) * 100);
  assert.equal(model.benchmarkCode, "^GSPC", "ADR follows US listing rather than TW country");
  assert.equal(model.primaryWindow, 25);
  approximately(model.primaryDistance, (160 / 155 - 1) * 100);
  assert.equal(model.trend.key, "up");
  const stats = run(data).groups.find((item) => item.id === group);
  assert.equal(stats.above50, 100);
  assert.equal(stats.relative20Count, 1);
  assert.equal(run(data).groups.length, 12);
}
{
  const data = fixture();
  data.latest.assets[0].date = "2026-10-01";
  const model = stock(data);
  assert.equal(model.quality.valid, false);
  assert.equal(model.return20, null);
  assert.equal(run(data).groups[0].return20, null);
}
{
  const data = fixture();
  data.latest.assets[0].close += 1;
  assert.equal(stock(data).quality.valid, false, "same-date latest/history price mismatch is excluded");
}
{
  const data = fixture();
  data.history["^GSPC"].data.splice(40, 1);
  assert.equal(stock(data).quality.valid, true);
  assert.equal(stock(data).relative20, null, "holiday date mismatch must not compare different periods");
  assert.ok(stock(data).return20 > 0);
}
{
  const data = fixture();
  data.latest.updated_at = "2026-09-24T10:00:00+09:00";
  const result = run(data);
  assert.equal(result.freshness.outdated, true);
  assert.equal(result.freshness.validStocks, 0);
  assert.equal(result.groups[0].return20, null);
  assert.equal(result.stocks[0].trend.key, "unknown");
  assert.equal(result.observations[0].kind, "quality");
}
{
  const data = fixture();
  const oldRows = rows("OLD", 1);
  data.history.TEST.data = oldRows;
  Object.assign(data.latest.assets[0], oldRows[0]);
  assert.equal(run(data).freshness.outdated, false);
  assert.equal(stock(data).quality.stale, true, "a fresh refresh does not revive old asset prices");
}
for (const flag of ["error", "is_stale", "is_suspicious"]) {
  const data = fixture();
  data.latest.assets[0][flag] = flag === "error" ? "failed" : true;
  assert.equal(stock(data).quality.valid, false, `${flag} is excluded`);
}
for (const price of [null, NaN, Infinity, 0, -1, "160"]) {
  const data = fixture();
  data.latest.assets[0].close = price;
  assert.equal(stock(data).quality.valid, false, "invalid prices must not coerce to usable values");
}
{
  const data = fixture();
  data.latest.assets[0].ma50 = null;
  assert.equal(stock(data).quality.valid, true);
  assert.equal(stock(data).trend.key, "unknown");
  assert.equal(stock(data).distance50, null);
  assert.equal(run(data).groups[0].above50, null);
  delete data.history.TEST;
  assert.equal(stock(data).quality.valid, false);
}
{
  const data = fixture();
  data.history.TEST.data = data.history.TEST.data.slice(-20);
  assert.equal(stock(data).return20, null, "20-session return needs 21 observations");
  assert.equal(stock(data).return60, null);
}
{
  const data = fixture();
  const asset = data.latest.assets[0];
  asset.ma50 = 165;
  assert.equal(stock(data).trend.key, "pullback");
  data.history.TEST.data.at(-6).ma50 = 170;
  asset.ma120 = 180;
  assert.equal(stock(data).trend.key, "weak");
  asset.ma120 = 155;
  assert.equal(stock(data).trend.key, "recovering");
}
{
  const data = fixture();
  const before = data.history.TEST.data.at(-2);
  before.ma50 = 170;
  before.primary_disparity = 119;
  before.ma25 = before.close / 1.19;
  data.latest.assets[0].ma25 = 120;
  data.latest.assets[0].ma120 = 200;
  const changes = stock(data).changes.map((item) => item.kind);
  assert.deepEqual(changes, ["ma50_up", "distance120_up", "distance130_up"]);
  assert.ok(stock(data).changes[1].label.startsWith("25일"));
  assert.ok(stock(data).distance120 < 0, "120-day trend position is separate from 25-day heat");
  assert.equal(run(data).groups[0].hotCount, 1);
  assert.ok(run(data).observations.some((item) => item.kind === "distance"));
  data.history.TEST.data.splice(-1, 0, { ...data.history.TEST.data.at(-1), close: 161, ma50: 165 });
  assert.deepEqual(stock(data).changes.map((item) => item.kind), changes, "same-day duplicate does not become a prior trading day");
  assert.equal(stock(data).series.length, 61);
}
{
  const data = fixture();
  data.latest.assets[0].ma120 = 100;
  assert.ok(stock(data).distance120 >= 30);
  assert.ok(stock(data).primaryDistance < 20);
  assert.equal(run(data).groups[0].hotCount, 0, "high 120-day position does not imply primary-window heat");
  assert.equal(stock(data).changes.some((change) => change.kind.startsWith("distance")), false);
  assert.equal(run(data).observations.some((item) => item.kind === "distance"), false);
}
{
  const data = fixture();
  const asset = data.latest.assets[0];
  asset.asset_type = "sector_etf";
  asset.ma50 = 120;
  data.history.TEST.data.at(-2).ma50 = 140;
  const result = run(data);
  const model = result.models.find((item) => item.code === "TEST");
  assert.equal(model.primaryWindow, 50, "ETF defaults to the 50-day primary average");
  assert.ok(model.primaryDistance >= 30);
  assert.ok(model.changes.some((change) => change.kind === "distance130_up" && change.label.startsWith("50일")));
  assert.equal(result.stocks.length, 0, "ETF must not count as an individual stock");
}
{
  const data = fixture();
  const asset = data.latest.assets[0];
  asset.primary_window = 50;
  asset.ma50 = 120;
  const model = stock(data);
  assert.equal(model.primaryWindow, 50, "stored primary-window metadata takes precedence");
  approximately(model.primaryDistance, (160 / 120 - 1) * 100);
  asset.ma50 = null;
  asset.primary_disparity = 130;
  assert.equal(stock(data).primaryDistance, 30, "falls back to stored primary disparity when average is missing");
  asset.primary_disparity = null;
  asset.disparity50 = 125;
  assert.equal(stock(data).primaryDistance, 25, "period-specific disparity is the final fallback");
}
{
  const data = fixture();
  data.latest.assets[0].market = "EU";
  data.latest.assets[0].listing_market = "XETRA";
  assert.equal(stock(data).benchmarkCode, null);
  assert.equal(stock(data).relative20, null);
}
{
  const data = fixture();
  data.latest.assets[1].is_suspicious = true;
  assert.equal(stock(data).return20 !== null, true);
  assert.equal(stock(data).relative20, null, "untrusted benchmark is excluded without discarding the stock return");
}
{
  const data = fixture();
  const first = data.latest.assets[0];
  const second = { ...first, code: "SECOND", name: "두 번째", close: 200, ma50: 220 };
  const excluded = { ...first, code: "EXCLUDED", is_suspicious: true };
  data.latest.assets.push(second, excluded, { code: "MACRO", asset_type: "macro_index", disparity_meaningful: false });
  data.history.SECOND = { data: data.history.TEST.data.map((row, i) => ({ ...row, close: i === 60 ? 200 : row.close })) };
  data.history.EXCLUDED = { data: data.history.TEST.data };
  const result = run(data);
  const stats = result.groups[0];
  assert.equal(stats.total, 3);
  assert.equal(stats.valid, 2);
  assert.equal(stats.above50, 50);
  approximately(stats.return20, (((160 / 140 - 1) * 100) + ((200 / 140 - 1) * 100)) / 2);
  assert.equal(result.models.some((model) => model.code === "MACRO"), false);
  assert.equal(result.freshness.excludedStocks, 1);
}
{
  const data = fixture();
  const result = run(data, new Date("2026-10-07T15:05:00Z"));
  assert.equal(result.freshness.outdated, true, "uses Seoul calendar date across UTC midnight");
  assert.ok(explain.trend.includes("5거래일"));
  assert.equal(thresholds.staleCalendarDays, 7);
  assert.deepEqual(buildDashboard(null, null, now).stocks, []);
}
console.log("insights: all assertions passed");
