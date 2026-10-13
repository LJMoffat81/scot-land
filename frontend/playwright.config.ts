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
    // Rebuild so NEXT_PUBLIC_INTERNAL_PREVIEWS is inlined for /place-card e2e.
    command:
      "NEXT_PUBLIC_INTERNAL_PREVIEWS=1 npx next build && NEXT_PUBLIC_INTERNAL_PREVIEWS=1 npx next start -p 3100",
    url: baseURL,
    reuseExistingServer: false,
    timeout: 300_000,
    env: {
      ...process.env,
      NEXT_PUBLIC_INTERNAL_PREVIEWS: "1",
    },
  },
});
