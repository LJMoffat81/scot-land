import { expect, test } from "@playwright/test";

/**
 * Suggestion 26: unpackaged /developers download cards show
 * exactly "Not packaged yet" instead of bare Size —.
 * Console errors / pageerror fail the test.
 */

const consoleErrors: string[] = [];
const resourceFails: Array<{ url: string; status: number }> = [];

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const KNOWN_OPTIONAL_FAIL_URL = [
  /\/favicon\.ico(?:\?|$)/i,
  /\/apple-touch-icon/i,
];

function isKnownOptionalFailUrl(url: string): boolean {
  return KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(url));
}

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  resourceFails.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
  page.on("response", (response) => {
    const status = response.status();
    if (status === 404 || status === 503) {
      resourceFails.push({ url: response.url(), status });
    }
  });

  // Catch-all first (Playwright is LIFO — later routes win).
  await page.route("**/backend/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
      }),
    });
  });
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  await page.route("**/backend/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  // Leave /downloads/manifest.json unstubbed so real unpackaged cards load.
});

test.afterEach(() => {
  const unknownResourceFails = resourceFails.filter(
    (fail) => !isKnownOptionalFailUrl(fail.url),
  );
  expect(
    unknownResourceFails,
    `unexpected HTTP 404/503:\n${unknownResourceFails
      .map((f) => `${f.status} ${f.url}`)
      .join("\n")}`,
  ).toEqual([]);

  const meaningful = consoleErrors.filter((text) => {
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
    if (
      /Failed to load resource: the server responded with a status of (404|503)/i.test(
        text,
      )
    ) {
      if (KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(text))) return false;
      if (!/https?:\/\//i.test(text) && unknownResourceFails.length === 0) {
        return false;
      }
      return true;
    }
    return true;
  });
  expect(
    meaningful,
    `console errors:\n${meaningful.join("\n")}`,
  ).toEqual([]);
});

test.describe("Suggestion 26 — Not packaged yet", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("unpackaged download cards show Not packaged yet", async ({ page }) => {
    await page.goto("/developers#downloads");
    await expect(page.getByTestId("developers-downloads")).toBeVisible();

    const unpackaged = page.locator(
      '[data-testid^="download-card-"][data-has-file="false"]',
    );
    await expect(unpackaged.first()).toBeVisible();
    const count = await unpackaged.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i++) {
      const card = unpackaged.nth(i);
      const id = await card.getAttribute("data-testid");
      const bundleId = id?.replace(/^download-card-/, "") ?? "";
      await expect(
        card.getByTestId(`download-not-packaged-${bundleId}`),
      ).toHaveText("Not packaged yet");
      await expect(card.getByText("Pack not published yet", { exact: false })).toHaveCount(
        0,
      );
    }

    await expect(page.getByText("Pack not published yet")).toHaveCount(0);

    const packaged = page.locator(
      '[data-testid^="download-card-"][data-has-file="true"]',
    );
    if ((await packaged.count()) > 0) {
      await expect(
        packaged.first().getByTestId(/^download-size-/),
      ).toBeVisible();
      await expect(
        packaged.first().getByText("Not packaged yet", { exact: true }),
      ).toHaveCount(0);
    }
  });
});
