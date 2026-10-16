import { expect, test, type Page } from "@playwright/test";

/**
 * UX-05 / MAP-CARDS P6 — search miss is an inline message under the search box.
 * Card stays closed; old pin is cleared. (Legacy "no-match card hug" retired.)
 */

const NO_MATCH_LINE =
  /No place matched|Try a postcode|place name|click the map/i;

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

type ConsoleGate = {
  consoleErrors: string[];
  resourceFails: Array<{ url: string; status: number }>;
};

function attachConsoleGate(page: Page): ConsoleGate {
  const consoleErrors: string[] = [];
  const resourceFails: Array<{ url: string; status: number }> = [];
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
    if (status === 404 || status === 400 || status === 503) {
      resourceFails.push({ url: response.url(), status });
    }
  });
  return { consoleErrors, resourceFails };
}

function assertConsoleClean(gate: ConsoleGate) {
  const unexpectedResourceFails = gate.resourceFails.filter((fail) => {
    if (
      (fail.status === 404 || fail.status === 400) &&
      /\/favicon|apple-touch|openfreemap|glyph|sprite/i.test(fail.url)
    ) {
      return false;
    }
    return true;
  });
  expect(
    unexpectedResourceFails,
    `unexpected HTTP 400/404/503:\n${unexpectedResourceFails
      .map((f) => `${f.status} ${f.url}`)
      .join("\n")}`,
  ).toEqual([]);

  const meaningful = gate.consoleErrors.filter((text) => {
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
    if (
      /Failed to load resource: the server responded with a status of (400|404|503)/i.test(
        text,
      )
    ) {
      return false;
    }
    if (text === "Error") return false;
    return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
}

async function stubNoMatchSearch(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/health/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/boundaries\//i.test(url) || /\/layers\//i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY_FC),
      });
      return;
    }
    if (/\/place\?/i.test(url) && !/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
}

async function openNoMatchInline(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();

  await page.locator("#place-query").fill("zzzz");
  await page.locator(".hud-search-go").click();

  const line = page.getByTestId("search-no-match");
  await expect(line).toBeVisible({ timeout: 30_000 });
  await expect(line).toContainText(NO_MATCH_LINE);
  await expect(page.getByTestId("place-card")).toHaveCount(0);
  await expect(page.locator(".maplibregl-marker")).toHaveCount(0);
  return line;
}

async function runNoMatchChecks(page: Page) {
  const gate = attachConsoleGate(page);
  await stubNoMatchSearch(page);
  await openNoMatchInline(page);
  assertConsoleClean(gate);
}

test.describe("UX-05 no-place card hug 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });
  test("zzzz search-miss card height hugs content", async ({ page }) => {
    test.setTimeout(90_000);
    await runNoMatchChecks(page);
  });
});

test.describe("UX-05 no-place card hug 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("zzzz search-miss card height hugs content", async ({ page }) => {
    test.setTimeout(90_000);
    await runNoMatchChecks(page);
  });
});
