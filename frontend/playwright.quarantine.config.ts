import { defineConfig } from "@playwright/test";
import base from "./playwright.ci.config";

/**
 * CI-DEDUP-1a quarantine job: same suite as CI, plus JSON for step summary.
 */
export default defineConfig({
  ...base,
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "playwright-report" }],
    ["json", { outputFile: "quarantine-results.json" }],
  ],
});
