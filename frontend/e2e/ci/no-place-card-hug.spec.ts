import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * UX-05 — "No place matched" search-miss card:
 * - desktop (≥1024) height hugs content (no empty panel under the lines)
 * - search "zzzz"; console / pageerror fail the test (do not loosen)
 */

const NO_MATCH_LINE =
  "No place matched. Try a postcode, place name, coordinates, or click the map.";

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
      /data-zones\/at|platform\/place|api\/place\.json/i.test(fail.url)
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
      if (!/https?:\/\//i.test(text) && unexpectedResourceFails.length === 0) {
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
}

async function stubNoMatchSearch(page: Page) {
  await page.route("**/backend/boundaries/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
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
  await page.route("**/backend/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        kind: "none",
        note: NO_MATCH_LINE,
      }),
    });
  });
  await page.route("**/backend/layers/open/data-zones**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
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

/** Card outer height within 24px of in-flow content + vertical padding (SW-028 pattern). */
async function assertCardHeightHugsContent(card: Locator) {
  const metrics = await card.evaluate((el) => {
    const style = getComputedStyle(el);
    const padY =
      parseFloat(style.paddingTop || "0") +
      parseFloat(style.paddingBottom || "0");
    const gap = parseFloat(style.rowGap || style.gap || "0") || 0;
    const kids = Array.from(el.children).filter((child) => {
      const cs = getComputedStyle(child);
      return (
        cs.position !== "absolute" &&
        cs.position !== "fixed" &&
        cs.display !== "none"
      );
    });
    const contentH = kids.reduce((sum, child, i) => {
      return sum + child.getBoundingClientRect().height + (i > 0 ? gap : 0);
    }, 0);
    return {
      boxH: el.getBoundingClientRect().height,
      contentH: contentH + padY,
    };
  });
  expect(
    Math.abs(metrics.boxH - metrics.contentH),
    `no-match card height ${metrics.boxH} vs content ${metrics.contentH}`,
  ).toBeLessThanOrEqual(24);
}

async function openNoPlaceCard(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();

  await page.locator("#place-query").fill("zzzz");
  await page.locator(".hud-search-go").click();

  const line = page.getByTestId("place-card-no-match");
  await expect(line).toBeVisible({ timeout: 30_000 });
  await expect(line).toContainText(/No place matched/i);

  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible();
  await expect(card).toHaveClass(/place-card-search-miss/);
  return card;
}

async function runNoPlaceHugChecks(page: Page) {
  const gate = attachConsoleGate(page);
  await stubNoMatchSearch(page);

  const card = await openNoPlaceCard(page);
  await assertCardHeightHugsContent(card);

  assertConsoleClean(gate);
}

test.describe("UX-05 no-place card hug 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("zzzz search-miss card height hugs content", async ({ page }) => {
    test.setTimeout(90_000);
    await runNoPlaceHugChecks(page);
  });
});

test.describe("UX-05 no-place card hug 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("zzzz search-miss card height hugs content", async ({ page }) => {
    test.setTimeout(90_000);
    await runNoPlaceHugChecks(page);
  });
});
