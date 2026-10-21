import { defineConfig, devices } from "@playwright/test";

/**
 * CI gate suite: every *.spec.ts under e2e/ci/ is auto-discovered.
 * Full map/GIS specs stay under e2e/ (need a live API) and are not run here.
 */
const baseURL = "http://localhost:3100";

export default defineConfig({
  testDir: "e2e/ci",
  testMatch: "**/*.spec.ts",
  retries: 0,
  workers: 1,
  use: {
    baseURL,
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    // Rebuild so NEXT_PUBLIC_INTERNAL_PREVIEWS is inlined for /place-card e2e.
    command:
      "NEXT_PUBLIC_INTERNAL_PREVIEWS=1 NEXT_PUBLIC_E2E_HOOKS=1 npx next build && NEXT_PUBLIC_INTERNAL_PREVIEWS=1 NEXT_PUBLIC_E2E_HOOKS=1 npx next start -p 3100",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 300_000,
    env: {
      ...process.env,
      NEXT_PUBLIC_INTERNAL_PREVIEWS: "1",
      NEXT_PUBLIC_E2E_HOOKS: "1",
    },
  },
});
