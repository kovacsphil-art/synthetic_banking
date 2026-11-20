"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { normalizeReport, readReport, renderResults, mountResults } = require("../docs/results.js");
const example = JSON.parse(fs.readFileSync(path.join(__dirname, "../docs/reporting/example.json"), "utf8"));
const clone = () => structuredClone(example);

// A small DOM adapter tests the renderer's text-only boundary without a framework.
class Node {
  constructor(doc, tag, text = "") { this.ownerDocument = doc; this.tagName = tag; this.children = []; this.attributes = {}; this.value = text; this.dataset = {}; this.events = {}; }
  set textContent(value) { this.value = String(value); this.children = []; }
  get textContent() { return this.value + this.children.map((node) => node.textContent).join(" "); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.value = ""; this.children = nodes; }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener(key, handler) { this.events[key] = handler; }
}
function document() {
  const doc = { baseURI: "https://example.invalid/project/index.html" };
  doc.createElement = (tag) => new Node(doc, tag);
  doc.createTextNode = (text) => new Node(doc, "#text", text);
  return doc;
}
const location = { origin: "https://example.invalid", protocol: "https:" };
const response = (payload) => ({ ok: true, text: async () => JSON.stringify(payload) });

test("version 1.0 maps the fabricated contract to fixed presentation fields", () => {
  const view = normalizeReport(clone());
  assert.equal(view.customers, 1000); assert.equal(view.accounts, 1400); assert.equal(view.rows, 8200);
  assert.equal(view.proposed, 2); assert.equal(view.approved, 2); assert.equal(view.applied, 2);
  assert.equal(view.accountCoverage, 1); assert.equal(view.balanceCoverage, 1);
  assert.equal(view.numeric.length, 12); assert.equal(view.conditional.length, 5);
  assert.equal(view.categorical[0].difference, 1);
});

test("missing individual metrics and null counts remain unavailable, including zero counts", () => {
  const report = clone(); delete report.numeric_differences; delete report.dependency_results;
  report.rules.applied = { status: "AVAILABLE", value: 0 };
  report.generation.customers = { status: "UNAVAILABLE", value: null };
  const view = normalizeReport(report);
  assert.equal(view.numeric[0].source, null); assert.equal(view.correlation.difference, null);
  assert.equal(view.customers, null); assert.equal(view.applied, 0);
  const rendered = renderResults(document(), view).textContent;
  assert.match(rendered, /Unavailable/); assert.match(rendered, /Rules applied 0/);
});

test("unsupported versions, failed validations, malformed timestamps and contradictions are rejected", () => {
  for (const change of [
    (r) => { r.schema_version = "2.0"; }, (r) => { r.validation.status = "FAIL"; },
    (r) => { r.pipeline_completed_at = "INTERNAL_TOKEN"; },
    (r) => { r.pipeline_completed_at = "2026-02-30T12:00:00Z"; },
    (r) => { r.rules.applied.value = 3; }, (r) => { r.generation = null; },
    (r) => { r.numeric_differences.push(r.numeric_differences[0]); },
  ]) {
    const report = clone(); change(report); assert.throws(() => normalizeReport(report), /Invalid report/);
  }
});

test("numeric strings, booleans, nonfinite values and out-of-range proportions are never trusted", () => {
  const report = clone(); report.generation.customers.value = "<img src=x>";
  report.rules.applied.value = true; report.numeric_differences[0].source = Infinity;
  report.validation.account_balance_join_coverage.accounts_with_balance.value = 120;
  report.categorical_differences[0].source = 3;
  const view = normalizeReport(report);
  assert.equal(view.customers, null); assert.equal(view.applied, null);
  assert.equal(view.numeric[0].source, null); assert.equal(view.accountCoverage, null);
  assert.equal(view.categorical[0].source, null);
});

test("untrusted metadata, labels, warning text, reasons and records do not reach the DOM", () => {
  const report = clone();
  report.run_id = "SECRET_RUN_ID"; report.rows = [{ PARTY_ID: "SECRET_PARTY" }];
  report.warnings = [{ code: "SKIPPED_PROPOSALS", message: "<script>SECRET_TOKEN</script>" }, { code: "UNKNOWN_PRIVATE_WARNING" }];
  report.numeric_differences[0].reason = "SECRET_REASON";
  report.categorical_differences.push({ category: "SECRET_CATEGORY", column: "PAST_DUE_INDICATO_CD", table: "TKQ_ACCOUNT" });
  const view = normalizeReport(report);
  const text = JSON.stringify(view) + renderResults(document(), view).textContent;
  for (const forbidden of ["SECRET", "UNKNOWN_PRIVATE_WARNING", "<script>"]) assert.ok(!text.includes(forbidden));
  assert.match(text, /Some proposals did not affect this dataset/);
  assert.match(text, /Integrity|Statistical differences/);
});

test("rate differences use supplied percentage points; no relative score is invented", () => {
  const view = normalizeReport(clone());
  const content = renderResults(document(), view).textContent;
  assert.match(content, /Past due \(Y\) 10\.00% 11\.00% \+1 pp/);
  assert.match(content, /Accounts with a balance: 100\.00%/);
  assert.match(content, /no overall fidelity threshold or score/i);
});

test("HTTP, invalid JSON, oversize and fetch failures reject without displaying payload text", async () => {
  for (const fetcher of [
    async () => ({ ok: false }), async () => ({ ok: true, text: async () => "<html>404 SECRET</html>" }),
    async () => ({ ok: true, text: async () => " ".repeat(1024 * 1024 + 1) }),
    async () => { throw new Error("SECRET_URL"); },
  ]) await assert.rejects(readReport(fetcher, "https://example.invalid/project/latest-pipeline.json"));
});

test("loader uses the same-directory artifact and avoids credentials/caching", async () => {
  const doc = document(), root = new Node(doc, "div");
  const seen = [];
  const mount = mountResults(root, { location, fetcher: async (url, options) => { seen.push([url, options]); return response(example); } });
  await mount.ready;
  assert.equal(seen[0][0], "https://example.invalid/project/latest-pipeline.json");
  assert.equal(seen[0][1].credentials, "omit"); assert.equal(seen[0][1].cache, "no-store");
  assert.equal(root.attributes["aria-busy"], "false");
  assert.match(root.textContent, /Integrity checks passed/); assert.match(root.textContent, /1,000/);
  assert.equal(root.children[0].children[1].attributes["role"], "status");
});

test("failed refresh clears prior results, keeps methodology separate, and can recover", async () => {
  const doc = document(), root = new Node(doc, "div");
  let healthy = true;
  const mount = mountResults(root, { location, fetcher: async () => healthy ? response(example) : { ok: false } });
  await mount.ready; const button = root.children[2];
  healthy = false; await mount.refresh();
  assert.match(root.textContent, /Latest results unavailable/); assert.ok(!root.textContent.includes("1,000"));
  assert.equal(root.children[2], button); assert.equal(button.disabled, false);
  healthy = true; await button.events.click();
  assert.match(root.textContent, /Integrity checks passed/);
});

test("file URLs and cross-origin reports fail safely with useful offline context", async () => {
  const doc = document(), root = new Node(doc, "div");
  root.dataset.reportUrl = "https://other.invalid/private.json";
  let calls = 0;
  await mountResults(root, { location, fetcher: async () => { calls++; return response(example); } }).ready;
  assert.equal(calls, 0); assert.match(root.textContent, /Latest results unavailable/);
  doc.baseURI = "file:///project/index.html"; root.dataset.reportUrl = "latest-pipeline.json";
  await mountResults(root, { location: { origin: "null", protocol: "file:" }, fetcher: async () => { calls++; } }).ready;
  assert.equal(calls, 0); assert.match(root.textContent, /local web server or GitHub Pages/);
});

test("a stalled request times out and leaves a retryable unavailable state", async () => {
  const doc = document(), root = new Node(doc, "div");
  const fetcher = async (_, { signal }) => new Promise((resolve, reject) => signal.addEventListener("abort", () => reject(new Error("aborted"))));
  await mountResults(root, { location, fetcher, timeoutMs: 5 }).ready;
  assert.match(root.textContent, /Latest results unavailable/);
  assert.equal(root.attributes["aria-busy"], "false"); assert.equal(root.children[2].disabled, false);
});
