/**
 * Install Playwright Chromium only when the executable is missing.
 * Avoids reinstalling (and --with-deps) on every local / CI re-run.
 */
import { accessSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

function chromiumPresent() {
  try {
    accessSync(chromium.executablePath());
    return true;
  } catch {
    return false;
  }
}

if (!chromiumPresent()) {
  process.stdout.write(
    "ensure-playwright-chromium: Chromium missing — installing with deps…\n",
  );
  const res = spawnSync(
    process.execPath,
    [
      require.resolve("playwright/cli.js"),
      "install",
      "--with-deps",
      "chromium",
    ],
    { stdio: "inherit" },
  );
  if (res.status !== 0) process.exit(res.status ?? 1);
}
