/**
 * CI-DEDUP-1a — write pass/fail lines for quarantined Playwright tests
 * into $GITHUB_STEP_SUMMARY from a JSON reporter file.
 */
import { appendFileSync, readFileSync, existsSync } from "node:fs";

const resultsPath = process.argv[2] || "quarantine-results.json";
const summaryPath = process.env.GITHUB_STEP_SUMMARY;

if (!existsSync(resultsPath)) {
  const msg = `### Quarantine results\n- missing results file: ${resultsPath}\n`;
  if (summaryPath) appendFileSync(summaryPath, msg);
  else process.stdout.write(msg);
  process.exit(0);
}

const data = JSON.parse(readFileSync(resultsPath, "utf8"));
const lines = ["### Quarantine results", ""];

/**
 * @param {any} suite
 * @param {string[]} titles
 */
function walkSuite(suite, titles) {
  const next = suite.title ? [...titles, suite.title] : titles;
  for (const child of suite.suites || []) walkSuite(child, next);
  for (const spec of suite.specs || []) {
    const name = [...next, spec.title].filter(Boolean).join(" › ");
    const ok = Boolean(spec.ok);
    lines.push(`- ${ok ? "PASS" : "FAIL"}: ${name}`);
  }
}

for (const suite of data.suites || []) walkSuite(suite, []);
if (lines.length === 2) lines.push("- (no quarantined tests reported)");

const body = `${lines.join("\n")}\n`;
if (summaryPath) appendFileSync(summaryPath, body);
else process.stdout.write(body);
