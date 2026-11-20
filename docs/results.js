/* Buildless, read-only presentation of the sanitized reporting contract. */
(() => {
  "use strict";

  const NUMERIC = [
    ["TKQ_ACCOUNT", "CREDIT_LIMIT_AMT", "Credit limit"],
    ["TKQ_ACCOUNT_BALANCE", "CURRENT_BALANCE_AMT", "Current balance"],
    ["TKQ_ACCOUNT_BALANCE", "AVAILABLE_TO_BUY_AMT", "Available credit"],
    ["TKQ_ACCOUNT_BALANCE", "OVERLIMIT_AMT", "Overlimit amount"],
  ];
  const TABLES = [
    ["PERSON", "Customers"], ["CUSTOMER_ACCOUNT_REL", "Customer–account links"],
    ["TKQ_ACCOUNT", "Accounts"], ["TKQ_ACCOUNT_BALANCE", "Balances"],
    ["TRADELINES", "Tradelines"], ["CUSTOMER_RELATIONSHIP", "Customer relationships"],
  ];
  const BUCKETS = ["0-30%", "30-60%", "60-80%", "80-100%", "100%+"];
  const WARNINGS = Object.freeze({
    FIDELITY_THRESHOLDS_NOT_CONFIGURED: "Statistical differences need review. No overall fidelity threshold or score is configured.",
    APPROVED_RULES_NOT_IMPLEMENTED: "Some approved proposals had no matching implementation and were skipped.",
    SKIPPED_PROPOSALS: "Some proposals did not affect this dataset. Legacy generation may still supply those fields.",
    UNAVAILABLE_METRICS: "Some aggregate measurements are unavailable; they are labelled individually below.",
  });
  const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const count = (item) => isObject(item) && item.status === "AVAILABLE" &&
    Number.isSafeInteger(item.value) && item.value >= 0 ? item.value : null;
  const fraction = (item) => isObject(item) && item.status === "AVAILABLE" &&
    finite(item.value) && item.value >= 0 && item.value <= 1 ? item.value : null;

  function pick(items, expected) {
    if (!Array.isArray(items)) return null;
    if (items.length > 128) throw new Error("Invalid report");
    const matches = items.filter((row) => isObject(row) &&
      Object.entries(expected).every(([key, value]) => row[key] === value));
    if (matches.length > 1) throw new Error("Invalid report");
    return matches[0] || null;
  }

  function comparison(item, unit, range = null) {
    const empty = { source: null, generated: null, difference: null };
    if (!isObject(item) || item.difference_unit !== unit ||
        !["AVAILABLE", "UNAVAILABLE"].includes(item.status)) return empty;
    const number = (value) => finite(value) && (!range || (value >= range[0] && value <= range[1])) ? value : null;
    const source = number(item.source), generated = number(item.generated);
    const difference = item.status === "AVAILABLE" && source !== null && generated !== null && finite(item.difference)
      ? item.difference : null;
    return { source, generated, difference };
  }

  function completionDate(value) {
    const parts = typeof value === "string" && /^(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.exec(value);
    if (!parts || !Number.isFinite(Date.parse(value))) throw new Error("Invalid report");
    const [year, month, day, hour, minute, second] = parts.slice(1, 7).map(Number);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (month < 1 || month > 12 || day < 1 || day > days[month - 1] || hour > 23 || minute > 59 || second > 59) throw new Error("Invalid report");
    return new Date(value).toISOString();
  }

  function normalizeReport(report) {
    if (!isObject(report) || !["1.0", "2.0"].includes(report.schema_version) ||
        !isObject(report.generation) || !isObject(report.rules) || !isObject(report.validation) ||
        report.validation.status !== "PASS" || report.validation.fidelity_acceptance !== "NOT_CONFIGURED") throw new Error("Invalid report");
    const completedAt = completionDate(report.pipeline_completed_at);
    const generation = report.generation, rules = report.rules;
    const coverage = report.validation.account_balance_join_coverage || {};
    const dependencies = isObject(report.dependency_results) ? report.dependency_results : {};
    const numeric = NUMERIC.flatMap(([table, column, label]) =>
      ["mean_value", "p50", "p95"].map((metric) => ({ label, metric,
        ...comparison(pick(report.numeric_differences, { table, column, metric }), "value") })));
    const warnings = new Set(Array.isArray(report.warnings)
      ? report.warnings.filter(isObject).map((item) => item.code).filter((code) => Object.hasOwn(WARNINGS, code)) : []);
    // This explanation is required even when an optional warnings array is absent.
    warnings.add("FIDELITY_THRESHOLDS_NOT_CONFIGURED");
    const view = {
      completedAt,
      customers: count(generation.customers), accounts: count(generation.accounts), rows: count(generation.total_rows),
      proposed: count(rules.proposed), approved: count(rules.approved), applied: count(rules.applied),
      skipped: count(rules.skipped), unimplemented: count(rules.approved_unimplemented),
      accountCoverage: fraction(coverage.accounts_with_balance), balanceCoverage: fraction(coverage.balances_with_account),
      tables: TABLES.map(([table, label]) => ({ label, value: count(pick(generation.table_rows, { table })) })),
      numeric,
      categorical: ["Y", "N"].map((category) => ({ label: category === "Y" ? "Past due (Y)" : "Not past due (N)",
        ...comparison(pick(report.categorical_differences, { table: "TKQ_ACCOUNT", column: "PAST_DUE_INDICATO_CD", category }),
          "percentage_points", [0, 1]) })),
      correlation: comparison(dependencies.credit_limit_balance_pearson, "correlation", [-1, 1]),
      conditional: BUCKETS.map((bucket) => ({ label: bucket,
        ...comparison(pick(dependencies.delinquency_by_utilization, { utilization_bucket: bucket }), "percentage_points", [0, 1]) })),
      warnings: [...warnings].map((code) => WARNINGS[code]),
    };
    if ((view.proposed !== null && view.approved !== null && view.approved > view.proposed) ||
        (view.approved !== null && view.applied !== null && view.applied > view.approved)) throw new Error("Invalid report");
    return view;
  }

  const formatNumber = new Intl.NumberFormat("en", { maximumFractionDigits: 2 });
  const formatInteger = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });
  const formatCorrelation = new Intl.NumberFormat("en", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
  const formatPercent = new Intl.NumberFormat("en", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const formatDate = new Intl.DateTimeFormat("en", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });
  const numberText = (value, formatter = formatNumber) => value === null ? "Unavailable" : formatter.format(value);
  function differenceText(value, unit) {
    if (value === null) return "Unavailable";
    const formatter = unit === "correlation" ? formatCorrelation : formatNumber;
    return (value > 0 ? "+" : "") + formatter.format(value) + (unit === "percentage_points" ? " pp" : "");
  }

  // Only textContent and fixed DOM elements are used. Raw JSON is never inserted as HTML.
  function element(doc, tag, text, className) {
    const node = doc.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function table(doc, caption, headers, rows) {
    const region = element(doc, "div", undefined, "table-scroll");
    region.setAttribute("role", "region"); region.setAttribute("aria-label", caption); region.tabIndex = 0;
    const grid = element(doc, "table");
    if (headers.length > 2) grid.className = "comparison-table";
    grid.append(element(doc, "caption", caption, "sr-only"));
    const head = element(doc, "thead"), header = element(doc, "tr");
    headers.forEach((label) => { const cell = element(doc, "th", label); cell.scope = "col"; header.append(cell); });
    head.append(header); grid.append(head);
    const body = element(doc, "tbody");
    rows.forEach((values) => {
      const row = element(doc, "tr");
      values.forEach((value, index) => { const cell = element(doc, index ? "td" : "th", value); if (!index) cell.scope = "row"; row.append(cell); });
      body.append(row);
    });
    grid.append(body); region.append(grid); return region;
  }

  function disclosure(doc, label, ...children) {
    const details = element(doc, "details", undefined, "disclosure results-detail");
    details.append(element(doc, "summary", label), ...children); return details;
  }

  function comparisonRows(items, percent = false) {
    return items.map((row) => [row.label, numberText(row.source, percent ? formatPercent : formatNumber),
      numberText(row.generated, percent ? formatPercent : formatNumber), differenceText(row.difference, percent ? "percentage_points" : "value")]);
  }

  function renderResults(doc, view) {
    const content = element(doc, "div");
    const timestamp = element(doc, "p", undefined, "results-completed");
    const time = element(doc, "time", formatDate.format(new Date(view.completedAt)) + " UTC");
    time.dateTime = view.completedAt; timestamp.append(doc.createTextNode("Validated completion · "), time); content.append(timestamp);
    const stats = element(doc, "dl", undefined, "results-metrics");
    for (const [label, value] of [["Customers", view.customers], ["Accounts", view.accounts], ["Generated rows", view.rows],
      ["Rules proposed", view.proposed], ["Rules approved", view.approved], ["Rules applied", view.applied]]) {
      const item = element(doc, "div"); item.append(element(doc, "dt", label), element(doc, "dd", numberText(value, formatInteger))); stats.append(item);
    }
    content.append(stats);
    const coverage = element(doc, "div", undefined, "measurement-summary");
    coverage.append(element(doc, "h4", "Account / balance snapshot coverage"),
      element(doc, "p", "Accounts with a balance: " + numberText(view.accountCoverage, formatPercent)),
      element(doc, "p", "Balances with an account: " + numberText(view.balanceCoverage, formatPercent)));
    content.append(coverage, element(doc, "p", "Approval and application are separate. Applied counts include only AI-proposed rules that actually affected this dataset.", "measurement-note"));
    const headers = ["Measurement", "SOURCE", "GENERATED", "Difference"];
    content.append(element(doc, "p", "Tables scroll horizontally on smaller screens.", "table-hint"));
    content.append(element(doc, "h4", "Selected numeric means"),
      table(doc, "Numeric mean comparisons", headers, comparisonRows(view.numeric.filter((row) => row.metric === "mean_value"))));
    content.append(disclosure(doc, "Numeric quantiles", table(doc, "Numeric quantile comparisons", headers,
      comparisonRows(view.numeric.filter((row) => row.metric !== "mean_value").map((row) => ({ ...row, label: row.label + " · " + row.metric.toUpperCase() }))))));
    content.append(disclosure(doc, "Categorical proportions", table(doc, "Past-due category comparisons", headers, comparisonRows(view.categorical, true))));
    const correlation = view.correlation;
    content.append(disclosure(doc, "Dependencies & conditional outcomes",
      table(doc, "Credit-limit and balance Pearson correlation", headers, [["Balance / limit correlation", numberText(correlation.source, formatCorrelation),
        numberText(correlation.generated, formatCorrelation), differenceText(correlation.difference, "correlation")]]),
      table(doc, "Past-due rates by utilization bucket", ["Utilization", "SOURCE rate", "GENERATED rate", "Difference"], comparisonRows(view.conditional, true))));
    content.append(disclosure(doc, "Output rows & rule outcomes",
      table(doc, "Generated table row counts", ["Population", "Rows"], view.tables.map((row) => [row.label, numberText(row.value, formatInteger)])),
      table(doc, "Rule execution outcomes", ["Outcome", "Proposals"], [["Skipped", numberText(view.skipped, formatInteger)], ["Approved without implementation", numberText(view.unimplemented, formatInteger)]])));
    const notes = element(doc, "ul", undefined, "results-notes");
    view.warnings.forEach((text) => notes.append(element(doc, "li", text)));
    content.append(element(doc, "h4", "Notes for interpretation", "results-notes-title"), notes,
      element(doc, "p", "Differences are GENERATED minus SOURCE. Rate differences use percentage points (pp); join coverage and rates use percentages. Unavailable means a measurement was missing or undefined.", "measurement-note"),
      element(doc, "p", "A published snapshot of the last successfully validated pipeline export. Methodology is documented separately; this page does not connect to Databricks.", "panel-footnote"));
    return content;
  }

  async function readReport(fetcher, url, signal) {
    const response = await fetcher(url, { cache: "no-store", credentials: "omit", redirect: "error", signal });
    if (!response.ok) throw new Error("Report unavailable");
    const text = await response.text();
    if (text.length > 1024 * 1024) throw new Error("Invalid report");
    return normalizeReport(JSON.parse(text));
  }

  function mountResults(root, { fetcher = globalThis.fetch, location = globalThis.location, timeoutMs = 10000 } = {}) {
    const doc = root.ownerDocument;
    const heading = element(doc, "div", undefined, "panel-heading");
    const title = element(doc, "h3", "Latest pipeline results"); title.id = "comparison-title";
    const status = element(doc, "span", "Results pending", "status-label status-pending");
    status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite"); status.setAttribute("aria-atomic", "true");
    const button = element(doc, "button", "Refresh results", "button button-secondary results-refresh"); button.type = "button";
    heading.append(title, status);
    const body = element(doc, "div"); root.replaceChildren(heading, body, button);
    let loading = false;
    async function refresh() {
      if (loading) return;
      loading = true; button.disabled = true; root.setAttribute("aria-busy", "true");
      status.className = "status-label status-pending"; status.textContent = "Loading results";
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const url = new URL(root.dataset.reportUrl || "latest-pipeline.json", doc.baseURI);
        if (url.origin !== location.origin || !["http:", "https:"].includes(url.protocol)) throw new Error("Report unavailable");
        const view = await readReport(fetcher, url.href, controller.signal);
        body.replaceChildren(renderResults(doc, view));
        status.className = "status-label status-measured"; status.textContent = "Integrity checks passed";
      } catch (_) {
        status.className = "status-label status-pending"; status.textContent = "Latest results unavailable";
        const note = element(doc, "div", undefined, "results-notice");
        note.append(element(doc, "p", "A completed pipeline report has not been published here, or it could not be read. The project methodology remains available."));
        if (location.protocol === "file:") note.append(element(doc, "p", "Open the site through a local web server or GitHub Pages to load the reporting JSON."));
        body.replaceChildren(note);
      } finally {
        clearTimeout(timer); loading = false; button.disabled = false; root.setAttribute("aria-busy", "false");
      }
    }
    button.addEventListener("click", refresh);
    const ready = refresh();
    return { ready, refresh };
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { normalizeReport, renderResults, readReport, mountResults };
  if (typeof document !== "undefined") {
    const root = document.getElementById("latest-results");
    if (root) mountResults(root);
  }
})();
