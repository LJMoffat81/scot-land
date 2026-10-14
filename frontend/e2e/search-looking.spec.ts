import { expect, test, type Page } from "@playwright/test";

const POSTCODE = "EH1 1YZ";
const LOOKING = "Looking…";
/** Delay place stubs so Looking… can paint before the response lands. */
const PLACE_DELAY_MS = 400;

const EMPTY_FC = JSON.stringify({
  type: "FeatureCollection",
  features: [],
});

/**
 * Fail the test on pageerror and console error, same pattern as data-page.spec.ts.
 * Chromium also logs intentional HTTP error stubs as console "error"; allow those
 * statuses so a place 500 fixture does not false-fail the trap.
 */
function attachConsoleTraps(
  page: Page,
  opts: { allowHttpStatuses?: number[] } = {},
): string[] {
  const allow = new Set(opts.allowHttpStatuses ?? []);
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    const statusMatch = text.match(
      /Failed to load resource: the server responded with a status of (\d+)/,
    );
    if (statusMatch && allow.has(Number(statusMatch[1]))) return;
    consoleErrors.push(text);
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
  return consoleErrors;
}

async function stubMapBackend(
  page: Page,
  place: "success" | "error",
) {
  await page.route("**/backend/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path.endsWith("/health") || path.includes("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          routers: {
            "api.agr_routes": { loaded: true },
            "api.platform_routes": { loaded: true },
          },
        }),
      });
      return;
    }

    if (path.includes("/place") && !path.includes("/platform/place")) {
      await new Promise((r) => setTimeout(r, PLACE_DELAY_MS));
      if (place === "error") {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "stubbed place failure" }),
        });
        return;
      }
      const q = (url.searchParams.get("q") || "")
        .toUpperCase()
        .replace(/\s+/g, " ");
      if (q.includes("EH1")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            kind: "postcode",
            postcode: POSTCODE,
            lat: 55.952,
            lng: -3.189,
            label: POSTCODE,
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "none", note: "No matches" }),
      });
      return;
    }

    if (path.includes("/postcode/")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          postcode: { postcode: POSTCODE },
          lat: 55.952,
          lng: -3.189,
          square: { lat: 55.952, lng: -3.189 },
        }),
      });
      return;
    }

    if (path.includes("/platform/place")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          contract: "place_card_v1",
          lat: 55.952,
          lng: -3.189,
          place_label: "Edinburgh Old Town",
          council_name: "City of Edinburgh",
          data_zone: {
            status: "ok",
            code: "S01008677",
            name: "Old Town",
            vintage: 2022,
          },
          intermediate_zone: { status: "ok", name: "Old Town and Canongate" },
          agr_rows: [
            {
              id: "surface",
              label: "Land",
              tag: "proxy",
              status: "in_progress",
              applies: true,
            },
          ],
          constraints: [],
          layers: [],
          links: [],
        }),
      });
      return;
    }

    if (path.includes("/layers/catalog") || path.endsWith("/catalog")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
      return;
    }

    // Quiet other map layer / context probes so the proxy does not 503.
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: EMPTY_FC,
    });
  });
}

async function openMapSearch(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  const search = page.locator("#place-query");
  await search.waitFor();
  const dismiss = page.getByTestId("research-banner-dismiss");
  if (await dismiss.count()) {
    await dismiss.click({ force: true });
  }
  return search;
}

function expectNoConsoleErrors(consoleErrors: string[]) {
  expect(
    consoleErrors,
    `console errors:\n${consoleErrors.join("\n")}`,
  ).toEqual([]);
}

test.describe("search dropdown Looking…", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("selecting a postcode clears Looking… within 1s", async ({ page }) => {
    test.setTimeout(90_000);
    const consoleErrors = attachConsoleTraps(page);
    await stubMapBackend(page, "success");

    const search = await openMapSearch(page);
    await search.fill(POSTCODE);
    await expect(page.getByText(LOOKING)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("option", { name: POSTCODE })).toBeVisible({
      timeout: 10_000,
    });
    // Keyboard select (active option is index 0) — avoids banner pointer intercept.
    await search.press("Enter");

    await page.waitForTimeout(1000);
    await expect(page.getByText(LOOKING)).toHaveCount(0);
    await expect(page.locator(".search-suggest")).toHaveCount(0);
    expectNoConsoleErrors(consoleErrors);
  });

  test("empty results show No matches and clear Looking…", async ({ page }) => {
    test.setTimeout(60_000);
    const consoleErrors = attachConsoleTraps(page);
    await stubMapBackend(page, "success");

    const search = await openMapSearch(page);
    await search.fill("zzznowhere");
    await expect(page.getByText(LOOKING)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("No matches")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(LOOKING)).toHaveCount(0);
    expectNoConsoleErrors(consoleErrors);
  });

  test("Escape clears Looking… after it appears", async ({ page }) => {
    test.setTimeout(60_000);
    const consoleErrors = attachConsoleTraps(page);
    await stubMapBackend(page, "success");

    const search = await openMapSearch(page);
    await search.fill("EH1");
    await expect(page.getByText(LOOKING)).toBeVisible({ timeout: 5_000 });
    await search.press("Escape");
    await expect(page.getByText(LOOKING)).toHaveCount(0);
    await expect(page.locator(".search-suggest")).toHaveCount(0);
    expectNoConsoleErrors(consoleErrors);
  });

  test("place 500 clears Looking…", async ({ page }) => {
    test.setTimeout(60_000);
    const consoleErrors = attachConsoleTraps(page, { allowHttpStatuses: [500] });
    await stubMapBackend(page, "error");

    const search = await openMapSearch(page);
    await search.fill(POSTCODE);
    await expect(page.getByText(LOOKING)).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText(LOOKING)).toHaveCount(0, { timeout: 10_000 });
    expectNoConsoleErrors(consoleErrors);
  });

  test("blur clears Looking…", async ({ page }) => {
    test.setTimeout(60_000);
    const consoleErrors = attachConsoleTraps(page);
    await stubMapBackend(page, "success");

    const search = await openMapSearch(page);
    await search.fill(POSTCODE);
    await expect(page.getByText(LOOKING)).toBeVisible({ timeout: 5_000 });
    await search.blur();
    // onBlur clears after 180ms; allow debounce/abort to settle.
    await expect(page.getByText(LOOKING)).toHaveCount(0, { timeout: 5_000 });
    await expect(page.locator(".search-suggest")).toHaveCount(0);
    expectNoConsoleErrors(consoleErrors);
  });
});
