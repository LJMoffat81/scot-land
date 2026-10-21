import { defineConfig, devices } from "@playwright/test";

/**
 * ESRI-KEY-PROD-1 B1/B2 — production build with / without the Esri key.
 * No NEXT_PUBLIC_E2E_HOOKS: the key can only come from the build-time env.
 * Servers are launched by scripts/esri-key-build-servers.mjs (sequential builds).
 */
export default defineConfig({
  testDir: "e2e/build-key",
  testMatch: "**/*.spec.ts",
  retries: 0,
  workers: 1,
  timeout: 180_000,
  use: {
    ...devices["Desktop Chrome"],
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    {
      name: "build-key-present",
      use: { baseURL: "http://127.0.0.1:3200" },
      grep: /B1/,
    },
    {
      name: "build-key-absent",
      use: { baseURL: "http://127.0.0.1:3201" },
      grep: /B2/,
    },
  ],
  webServer: {
    command: "node scripts/esri-key-build-servers.mjs",
    url: "http://127.0.0.1:3200",
    reuseExistingServer: false,
    timeout: 600_000,
  },
});
