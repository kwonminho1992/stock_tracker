"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const MarketInsights = require("../docs/insights.js");

const now = new Date("2026-10-01T12:00:00+09:00");
class FixedDate extends Date {
  constructor(...args) { super(...(args.length ? args : [now.getTime()])); }
  static now() { return now.getTime(); }
}

// Load the actual browser functions without starting the page or fetching data.
const listeners = new Map();
const context = vm.createContext({
  Date: FixedDate,
  MarketInsights,
  document: {
    addEventListener(name, callback) { listeners.set(name, callback); },
    getElementById() { throw new Error("DOMContentLoaded init must not run in this test"); },
  },
});
vm.runInContext(fs.readFileSync(path.join(__dirname, "../docs/app.js"), "utf8"), context, { filename: "app.js" });
const evaluate = (code) => vm.runInContext(code, context);
assert.equal(typeof listeners.get("DOMContentLoaded"), "function");
assert.equal(evaluate("state.dashboard"), null, "registering init must not execute it");

function asset(code, type, group, overrides = {}) {
  return {
    code, name: code, market: "US", country: "US", asset_type: type,
    ai_group: group, date: "2026-09-30", close: 100, ma25: 90, ma50: 95,
    ma120: 85, ...overrides,
  };
}
function dashboard(assets) {
  const history = Object.fromEntries(assets.map((item) => [item.code, { data: [
    { date: "2026-09-29", close: 99, ma25: 90, ma50: 95 },
    { date: item.date, close: item.close, ma25: item.ma25, ma50: item.ma50 },
  ] }]));
  return MarketInsights.buildDashboard({ updated_at: "2026-10-01T10:00:00+09:00", assets }, history, now);
}

{
  context.fixtureDashboard = dashboard([
    asset("STOCK", "us_stock", "01_COMPUTE_ASIC"),
    asset("^KS11", "kr_index", "00_INDEX", { market: "KR", country: "KR" }),
  ]);
  evaluate("state.dashboard = fixtureDashboard; state.group = 'ALL'; state.view = 'ALL'");
  assert.deepEqual(Array.from(evaluate("filteredModels().map(model => model.code)")), ["STOCK"]);
  evaluate("state.watch = new Set(['^KS11']); state.view = 'WATCH'");
  assert.equal(evaluate("state.dashboard.models.filter(model => state.watch.has(model.code)).length"), 1);
  assert.deepEqual(Array.from(evaluate("filteredModels().map(model => model.code)")), ["^KS11"], "a watched index remains visible in the all-groups watch list");
}

{
  evaluate("state.dashboard.freshness.outdated = false");
  context.macroFixture = { code: "^TNX", close: 5.29, date: "2026-09-30", source: "yfinance", disparity_meaningful: false };
  assert.equal(evaluate("macroQuality(macroFixture).valid"), true, "a recent unflagged numeric macro remains usable");
  context.macroFixture = { ...context.macroFixture, is_suspicious: true };
  assert.equal(evaluate("macroQuality(macroFixture).valid"), false, "suspect macro values must not enter the market summary");
  context.macroFixture = { ...context.macroFixture, is_suspicious: false, error: "quote mismatch" };
  assert.equal(evaluate("macroQuality(macroFixture).valid"), false, "collection errors exclude even recent numeric macro values");
}

for (const value of [null, undefined, "", " ", "invalid-date"]) {
  context.timestampFixture = value;
  assert.equal(evaluate("dateTime(timestampFixture)"), "확인 불가", "a missing or invalid timestamp must not display the Unix epoch");
}
context.timestampFixture = "2026-10-01T03:00:00Z";
assert.match(evaluate("dateTime(timestampFixture)"), /2026/, "a valid timestamp retains its year");

{
  context.fixtureDashboard = dashboard([
    asset("ETF", "sector_etf", "00_INDEX", { ma25: 50, ma50: null }),
  ]);
  const model = context.fixtureDashboard.models[0];
  assert.equal(model.quality.valid, true);
  assert.equal(model.primaryWindow, 50);
  assert.equal(model.primaryDistance, null);
  assert.equal(model.distance25, 100, "the unrelated 25-day value deliberately looks hot");
  context.etfFixture = model;
  assert.equal(evaluate("primaryDistance(etfFixture)"), null, "missing ETF 50-day distance must not fall back to its 25-day distance");
  evaluate("state.dashboard = fixtureDashboard; state.view = 'HOT'; state.group = 'ALL'; state.watch = new Set()");
  assert.equal(evaluate("filteredModels().length"), 0, "missing primary distance cannot qualify for the high-distance view");
  context.distanceFixture = { primaryDistance: 0, distance25: 100 };
  assert.equal(evaluate("primaryDistance(distanceFixture)"), 0, "zero primary distance is a valid value");
}

console.log("app: all assertions passed");
