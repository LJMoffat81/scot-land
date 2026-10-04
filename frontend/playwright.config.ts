import { defineConfig, devices } from "@playwright/test";

const baseURL = "http://localhost:3100";

export default defineConfig({
  testDir: "e2e",
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
    command: "npx next start -p 3100",
    url: baseURL,
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
