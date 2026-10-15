import { expect, test, type Page } from "@playwright/test";

/**
 * SHARE-FIX — Coming soon when scoped layer tiles return 503;
 * place lookup shows Try again (not Service busy) after exhausted retries.
 */

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const CATALOG = {
  version: 2,
  layers: [
    {
      id: "builtup_mask",
      group: "spatial",
      status: "live",
      label: "Built-up display mask",
      licence: "OGL-3.0",
    },
  ],
};

type ConsoleGate = { consoleErrors: string[]; pageErrors: string[] };

function attachConsoleGate(page: Page): ConsoleGate {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  return { consoleErrors, pageErrors };
}

function filterNoise(errors: string[]): string[] {
  return errors.filter(
    (text) =>
      !/AbortError|aborted|Failed to fetch|net::ERR_|400|404|503/i.test(text),
  );
}

async function stubShareFixBackend(
  page: Page,
  opts: { unavailablePath?: RegExp } = {},
) {
  const unavailable = opts.unavailablePath;
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
    if (/\/layers\/catalog/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CATALOG),
      });
      return;
    }
    if (unavailable && unavailable.test(url)) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "not loaded" }),
      });
      return;
    }
    if (/\/layers\//i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY_FC),
      });
      return;
    }
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          contract: "place_card_v1",
          lat: 55.86,
          lng: -4.25,
          place_label: "Glasgow",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
}

async function openLayers(page: Page) {
  const btn = page.getByTestId("hud-layers-btn");
  await expect(btn).toBeVisible({ timeout: 30_000 });
  if ((await page.getByTestId("layers-panel").count()) === 0) {
    await btn.click();
  }
  await expect(page.getByTestId("layers-panel")).toBeVisible({
    timeout: 15_000,
  });
}

const COMING_SOON_CASES: Array<{
  name: string;
  path: RegExp;
  toggle: string;
}> = [
  { name: "hla", path: /\/layers\/open\/hla/i, toggle: "hla" },
  {
    name: "onshore wind and hydro",
    path: /\/layers\/open\/repd-onshore-wind/i,
    toggle: "3",
  },
  {
    name: "aquaculture",
    path: /\/layers\/open\/ces-aquaculture/i,
    toggle: "5",
  },
  { name: "lca", path: /\/layers\/open\/lca/i, toggle: "lca" },
];

test.describe("SHARE-FIX Coming soon on 503 tiles", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  for (const layer of COMING_SOON_CASES) {
    test(`${layer.name} 503 → Coming soon / disabled`, async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubShareFixBackend(page, { unavailablePath: layer.path });

      await page.goto("/?lat=55.8609&lng=-4.2514");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await openLayers(page);

      const toggle = page.getByTestId(`layer-toggle-${layer.toggle}`);
      await expect(toggle).toBeVisible({ timeout: 30_000 });
      await expect(toggle).toBeEnabled();
      await toggle.click();

      await expect(
        page.getByTestId(`layer-coming-soon-${layer.toggle}`),
      ).toHaveText("Coming soon", { timeout: 15_000 });
      await expect(toggle).toBeDisabled();
      await expect(
        page.getByTestId(`map-layer-${layer.toggle}`),
      ).toHaveAttribute("data-coming-soon", "true");
      await expect(page.getByTestId("layer-notice")).toHaveCount(0);
      await expect(page.locator("aside.hud-tools")).not.toContainText(
        /Service busy/i,
      );

      expect(filterNoise(gate.consoleErrors)).toEqual([]);
      expect(filterNoise(gate.pageErrors)).toEqual([]);
    });
  }
});

test.describe("SHARE-FIX place lookup Try again", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("exhausted 503 retries show Try again, not Service busy", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    let placeHits = 0;
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
      if (/\/place\?/i.test(url) || /\/place$/i.test(url)) {
        placeHits += 1;
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({
            detail: "Place search is busy. Try again in a moment.",
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(/\/layers\//i.test(url) ? EMPTY_FC : {}),
      });
    });

    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
    const input = page.locator(".hud-search input");
    await expect(input).toBeVisible({ timeout: 15_000 });
    await input.fill("Leith Walk");
    await page.keyboard.press("Enter");

    await expect(page.locator("body")).toContainText("Try again", {
      timeout: 20_000,
    });
    await expect(page.locator("body")).not.toContainText(/Service busy/i);
    expect(placeHits).toBeGreaterThanOrEqual(2);

    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });
});
